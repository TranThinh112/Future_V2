"""Safe paper worker: public market data only and no exchange order submission."""
import asyncio
import logging
import math
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
import numpy as np

from app.config import Settings, TradingMode
from app.execution.paper import PaperBroker
from app.features.indicators import compute_features
from app.market_data.okx import OKXClient
from app.market_data.orderbook import estimated_slippage
from app.market_data.service import Snapshot, candles_frame, validate_snapshot
from app.news.service import NewsService
from app.orchestrator import Orchestrator
from app.risk.state import RiskState
from app.storage.json_store import JsonStore
from app.storage.repository import repository_from_url
from app.strategy import signal

log = logging.getLogger(__name__)

class PaperWorker:
    def __init__(self, settings: Settings, interval_seconds: int = 30):
        if settings.trading_mode != TradingMode.paper:
            raise ValueError("PaperWorker can only run in paper mode")
        self.settings, self.interval, self.running = settings, interval_seconds, False
        self.client = OKXClient(
            settings.okx_api_key,
            settings.okx_secret_key,
            settings.okx_passphrase,
            demo=settings.okx_demo_trading,
            read_only=settings.okx_read_only,
        )
        self.audit = repository_from_url(settings.database_url)
        self.state_store = JsonStore()
        self.broker = PaperBroker.restore(self.state_store.load({}))
        self.risk_state = RiskState(self.broker.cash, self.broker.cash)
        self.orchestrator = Orchestrator(settings)
        self.news = NewsService(
            settings.news_provider_url,
            settings.news_api_key,
            settings.news_lookback_minutes,
            settings.news_max_items,
        )
        self.last_ai_advisory_at: dict[str, float] = {}
        self.last_audit_tick_at: dict[str, float] = {}
        self.close_history: dict[str, list[float]] = {}
        self.last_cleanup_at = 0.0
        self.last_tick_at = 0.0
        self.last_error = ""
        self.exchange_portfolio: dict | None = None
        self.exchange_sync_error = ""
        self.exchange_sync_at = 0.0
        self.exchange_sync_lock = asyncio.Lock()
        self.exchange_sync_attempts = 0
        self.exchange_sync_step = ""

    def should_call_ai(self, symbol: str, decision: dict, now: float) -> tuple[bool, str]:
        if not self.settings.enable_ai_advisory:
            return False, "ai_advisory_disabled"
        if decision.get("action") == "hold" and not self.settings.ai_advisory_on_hold:
            return False, "deterministic_hold"
        last = self.last_ai_advisory_at.get(symbol, 0)
        if now - last < self.settings.ai_advisory_cooldown_seconds:
            return False, "ai_advisory_cooldown"
        return True, "ai_advisory_allowed"

    @staticmethod
    def _finite(value):
        try:
            value = float(value)
            return value if math.isfinite(value) else None
        except (TypeError, ValueError):
            return None

    def _orderbook_context(self, response: dict, last: float) -> dict:
        row = (response.get("data") or [{}])[0]
        bids = row.get("bids") or []
        asks = row.get("asks") or []
        bid_depth = sum(self._finite(level[1]) or 0 for level in bids if len(level) >= 2)
        ask_depth = sum(self._finite(level[1]) or 0 for level in asks if len(level) >= 2)
        total_depth = bid_depth + ask_depth
        quantity = self.broker.cash * self.settings.max_position_pct / max(last, 0.000001)
        return {
            "bid_depth_top20": bid_depth,
            "ask_depth_top20": ask_depth,
            "depth_imbalance": (bid_depth - ask_depth) / total_depth if total_depth else None,
            "estimated_buy_slippage_pct": estimated_slippage(asks, quantity) if asks and quantity > 0 else None,
            "estimated_sell_slippage_pct": estimated_slippage(bids, quantity) if bids and quantity > 0 else None,
            "levels": {"bids": len(bids), "asks": len(asks)},
            "data_quality": "good" if bids and asks else "missing",
        }

    def _portfolio_context(self, prices: dict[str, float]) -> dict:
        if getattr(self, "exchange_portfolio", None) is not None:
            return self.exchange_portfolio
        equity = self.broker.equity(prices)
        positions = {}
        exposure = {}
        now = time.time()
        for symbol, position in self.broker.positions.items():
            mark = prices.get(symbol, position.entry_price)
            value = mark * position.quantity
            opened_at = getattr(position, "opened_at", None)
            positions[symbol] = {
                "side": "long",
                "quantity": position.quantity,
                "entry_price": position.entry_price,
                "mark_price": mark,
                "position_value": value,
                "unrealized_pnl": (mark - position.entry_price) * position.quantity,
                "unrealized_pnl_pct": (mark / position.entry_price - 1) if position.entry_price else None,
                "stop_loss": position.stop_loss,
                "take_profit": position.take_profit,
                "stop_distance_pct": (position.stop_loss / mark - 1) if mark and position.stop_loss else None,
                "target_distance_pct": (position.take_profit / mark - 1) if mark and position.take_profit else None,
                "opened_at": opened_at,
                "age_seconds": round(now - opened_at, 3) if opened_at else None,
                "liquidation_price": None,
                "liquidation_note": "not_applicable_spot_paper",
                "protection_status": "stop_loss_take_profit_configured",
            }
            exposure[symbol] = value / equity if equity else 0
        return {
            "cash": self.broker.cash,
            "equity": equity,
            "positions": positions,
            "exposure_pct": exposure,
            "total_exposure_pct": sum(exposure.values()),
            "concentration_pct": max(exposure.values()) if exposure else 0,
            "position_count": len(positions),
            "correlation": self._correlation(),
            "execution": self._fills_context(),
            "data_quality": "good",
        }

    async def _sync_exchange_portfolio(self, force: bool = False) -> dict | None:
        """Read the real OKX account without enabling any trading operation."""
        if not getattr(self.settings, "okx_account_sync", False):
            self.exchange_sync_step = "disabled"
            return None
        if not all((
            getattr(self.settings, "okx_api_key", ""),
            getattr(self.settings, "okx_secret_key", ""),
            getattr(self.settings, "okx_passphrase", ""),
        )):
            self.exchange_sync_error = "okx_account_credentials_missing"
            self.exchange_sync_step = "credentials_missing"
            return None
        if not force and time.time() - self.exchange_sync_at < self.interval:
            return self.exchange_portfolio
        async with self.exchange_sync_lock:
            if not force and time.time() - self.exchange_sync_at < self.interval:
                return self.exchange_portfolio
            try:
                self.exchange_sync_attempts += 1
                self.exchange_sync_step = "requesting_private_api"
                balance_response, positions_response = await asyncio.gather(
                    self.client.balances(), self.client.positions()
                )
                self.exchange_sync_step = "parsing_response"
                balance = (balance_response.get("data") or [{}])[0]
                details = balance.get("details") or []
                usdt = next((item for item in details if item.get("ccy") == "USDT"), {})
                positions = {}
                exposure = {}
                total_unrealized = 0.0
                for raw in positions_response.get("data") or []:
                    quantity = self._finite(raw.get("pos")) or 0.0
                    if abs(quantity) <= 0:
                        continue
                    symbol = str(raw.get("instId") or "")
                    mark = self._finite(raw.get("markPx"))
                    entry = self._finite(raw.get("avgPx"))
                    upl = self._finite(raw.get("upl")) or 0.0
                    notional = self._finite(raw.get("notionalUsd"))
                    if notional is None and mark is not None:
                        notional = abs(quantity * mark)
                    total_unrealized += upl
                    opened_ms = self._finite(raw.get("cTime"))
                    opened_at = (
                        datetime.fromtimestamp(opened_ms / 1000, UTC).isoformat(timespec="seconds")
                        if opened_ms
                        else None
                    )
                    margin = self._finite(raw.get("imr"))
                    if margin is None:
                        margin = self._finite(raw.get("margin"))
                    positions[symbol] = {
                        "symbol": symbol,
                        "side": raw.get("posSide") or ("short" if quantity < 0 else "long"),
                        "quantity": quantity,
                        "entry_price": entry,
                        "mark_price": mark,
                        "position_value": notional,
                        "unrealized_pnl": upl,
                        "unrealized_pnl_pct": self._finite(raw.get("uplRatio")),
                        "stop_loss": None,
                        "take_profit": None,
                        "stop_distance_pct": None,
                        "target_distance_pct": None,
                        "opened_at": opened_at,
                        "age_seconds": round(time.time() - opened_ms / 1000, 3) if opened_ms else None,
                        "liquidation_price": self._finite(raw.get("liqPx")),
                        "liquidation_note": "from_okx_account_positions",
                        "protection_status": "exchange_position_read_only",
                        "inst_type": raw.get("instType"),
                        "margin": margin,
                        "leverage": self._finite(raw.get("lever")),
                    }
                    if notional is not None:
                        exposure[symbol] = notional
                total_equity = self._finite(balance.get("totalEq"))
                cash = self._finite(usdt.get("availEq"))
                if cash is None:
                    cash = self._finite(usdt.get("availBal")) or self._finite(usdt.get("cashBal"))
                equity = total_equity if total_equity is not None else (self._finite(usdt.get("eq")) or cash)
                if equity is None:
                    raise ValueError("okx_balance_equity_missing")
                margin_used = sum(item["margin"] or 0.0 for item in positions.values())
                self.exchange_portfolio = {
                    "cash": cash or 0.0,
                    "available_cash": cash or 0.0,
                    "equity": equity,
                    "positions": positions,
                    "exposure_pct": {key: value / equity for key, value in exposure.items()},
                    "total_exposure_pct": sum(exposure.values()) / equity if equity else 0.0,
                    "concentration_pct": max(exposure.values()) / equity if exposure and equity else 0.0,
                    "position_count": len(positions),
                    "unrealized_pnl": total_unrealized,
                    "margin_used": margin_used,
                    "correlation": self._correlation(),
                    "execution": {"count": None, "recent": [], "fee_pct": None, "last_fill": None, "data_quality": "not_requested", "realized_pnl": None},
                    "source": "okx_private_account_read_only",
                    "data_quality": "good",
                    "synced_at": datetime.now(UTC).isoformat(timespec="seconds"),
                }
                self.exchange_sync_at = time.time()
                self.exchange_sync_error = ""
                self.exchange_sync_step = "synced"
                return self.exchange_portfolio
            except (httpx.HTTPError, KeyError, TypeError, ValueError, OSError) as exc:
                self.exchange_sync_error = f"{type(exc).__name__}: {exc}"
                self.exchange_sync_step = "failed"
                log.warning("okx_account_sync_failed", extra={"error_type": type(exc).__name__, "error": str(exc)[:200]})
                return self.exchange_portfolio

    def _risk_context(self, equity: float, symbol: str, spread: float, slippage: float | None) -> dict:
        return {
            "risk_per_trade_pct": self.settings.risk_per_trade_pct,
            "max_position_pct": self.settings.max_position_pct,
            "max_total_exposure_pct": self.settings.max_total_exposure_pct,
            "daily_loss_pct": self.risk_state.daily_loss(equity),
            "drawdown_pct": self.risk_state.drawdown(equity),
            "cooling_down": self.risk_state.cooling_down(symbol),
            "spread_pct": spread,
            "estimated_slippage_pct": slippage,
            "api_healthy": True,
            "liquidity_ok": slippage is None or slippage <= self.settings.max_slippage_pct,
            "data_quality": "good",
        }

    @classmethod
    def _regime_context(cls, values: dict) -> dict:
        close = cls._finite(values.get("close"))
        ema20, ema50, ema200 = (cls._finite(values.get(key)) for key in ("ema20", "ema50", "ema200"))
        rsi, macd, macd_signal = (cls._finite(values.get(key)) for key in ("rsi", "macd", "macd_signal"))
        atr, volatility = cls._finite(values.get("atr")), cls._finite(values.get("volatility"))
        trend = "unknown"
        if None not in (close, ema20, ema50, ema200):
            if close > ema20 > ema50 > ema200:
                trend = "strong_uptrend"
            elif close > ema20 > ema50:
                trend = "uptrend"
            elif close < ema20 < ema50 < ema200:
                trend = "strong_downtrend"
            elif close < ema20 < ema50:
                trend = "downtrend"
            else:
                trend = "range"
        momentum = "unknown"
        if None not in (rsi, macd, macd_signal):
            if rsi >= 60 and macd > macd_signal:
                momentum = "bullish"
            elif rsi <= 40 and macd < macd_signal:
                momentum = "bearish"
            else:
                momentum = "neutral"
        volatility_regime = "unknown"
        if volatility is not None:
            volatility_regime = "high" if volatility > 0.004 else "low" if volatility < 0.001 else "normal"
        known = trend != "unknown" and momentum != "unknown"
        return {
            "trend": trend,
            "momentum": momentum,
            "volatility": volatility_regime,
            "atr_pct": (atr / close) if atr is not None and close else None,
            "rsi_zone": "overbought" if rsi is not None and rsi > 70 else "oversold" if rsi is not None and rsi < 30 else "neutral",
            "data_quality": "good" if known else "missing",
        }

    def _structure_context(self, candles, snapshot, values: dict) -> dict:
        empty = {
            "vwap": None, "vwap_deviation_pct": None, "bollinger_position_pct": None,
            "support": None, "resistance": None, "distance_to_support_pct": None,
            "distance_to_resistance_pct": None, "range_high": None, "range_low": None,
            "lookback_candles": 0, "data_quality": "missing",
        }
        if candles is None or candles.empty:
            return empty
        last = self._finite(snapshot.last)
        close, volume = candles["close"].astype(float), candles["volume"].astype(float)
        total_volume = float(volume.sum())
        vwap = float((close * volume).sum() / total_volume) if total_volume > 0 else None
        recent, window = candles.tail(20), candles.tail(100)
        support, resistance = float(recent["low"].min()), float(recent["high"].max())
        bb_upper, bb_lower = self._finite(values.get("bb_upper")), self._finite(values.get("bb_lower"))
        bollinger_position = None
        if None not in (bb_upper, bb_lower, last) and bb_upper > bb_lower:
            bollinger_position = (last - bb_lower) / (bb_upper - bb_lower)
        return {
            "vwap": vwap,
            "vwap_deviation_pct": ((last - vwap) / vwap) if vwap and last else None,
            "bollinger_position_pct": bollinger_position,
            "support": support,
            "resistance": resistance,
            "distance_to_support_pct": ((last - support) / last) if last and support else None,
            "distance_to_resistance_pct": ((resistance - last) / last) if last and resistance else None,
            "range_high": float(window["high"].max()),
            "range_low": float(window["low"].min()),
            "lookback_candles": {"recent": len(recent), "window": len(window)},
            "data_quality": "good" if vwap is not None else "missing",
        }

    def _correlation(self) -> dict:
        series = {symbol: closes for symbol, closes in self.close_history.items() if len(closes) >= 30}
        if len(series) < 2:
            return {"pair": None, "value": None, "window": 0, "data_quality": "unavailable", "reason": "insufficient_history"}
        (symbol_a, closes_a), (symbol_b, closes_b) = sorted(series.items())[:2]
        length = min(len(closes_a), len(closes_b), 200)
        first, second = np.asarray(closes_a[-length:], dtype=float), np.asarray(closes_b[-length:], dtype=float)
        usable = (first[:-1] > 0) & (second[:-1] > 0)
        returns_a, returns_b = np.diff(first)[usable] / first[:-1][usable], np.diff(second)[usable] / second[:-1][usable]
        finite = np.isfinite(returns_a) & np.isfinite(returns_b)
        returns_a, returns_b = returns_a[finite], returns_b[finite]
        if returns_a.size < 2 or float(np.std(returns_a)) == 0 or float(np.std(returns_b)) == 0:
            return {"pair": f"{symbol_a}_{symbol_b}", "value": None, "window": length, "data_quality": "unavailable", "reason": "zero_variance"}
        return {
            "pair": f"{symbol_a}_{symbol_b}",
            "value": round(float(np.corrcoef(returns_a, returns_b)[0, 1]), 4),
            "window": length,
            "data_quality": "good",
        }

    @staticmethod
    def _realized_pnl(fills: list[dict]) -> float | None:
        inventory: dict[str, dict[str, float]] = {}
        realized = 0.0
        try:
            for fill in fills:
                symbol, quantity, price = fill["symbol"], float(fill["quantity"]), float(fill["price"])
                fee = float(fill.get("fee") or 0)
                book = inventory.setdefault(symbol, {"quantity": 0.0, "cost": 0.0})
                if fill.get("side") == "buy":
                    book["quantity"] += quantity
                    book["cost"] += price * quantity
                    realized -= fee
                    continue
                matched = min(quantity, book["quantity"])
                if matched > 0:
                    realized += (price - book["cost"] / book["quantity"]) * matched
                    book["quantity"] -= matched
                    book["cost"] = (book["cost"] / (book["quantity"] + matched)) * book["quantity"]
                realized -= fee
            return round(realized, 8)
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            return None

    def _fills_context(self) -> dict:
        fills = list(getattr(self.broker, "fills", []))[-20:]
        return {
            "recent": fills,
            "count": len(getattr(self.broker, "fills", [])),
            "last_fill": fills[-1] if fills else None,
            "realized_pnl": self._realized_pnl(fills),
            "fee_pct": self.broker.fee_pct,
            "data_quality": "good",
        }

    def _proposal_context(self, snapshot, decision: dict, equity: float, buy_slippage: float | None) -> dict:
        entry = self._finite(snapshot.last)
        stop, target = self._finite(decision.get("stop_loss")), self._finite(decision.get("take_profit"))
        action = decision.get("action")
        quantity = notional = position_pct = risk_reward = None
        if action == "buy" and entry and stop and entry > stop:
            risk_amount = equity * self.settings.risk_per_trade_pct
            quantity = min(risk_amount / (entry - stop), self.broker.cash * self.settings.max_position_pct / entry)
            notional = quantity * entry
            position_pct = notional / equity if equity else None
            if target and target > entry:
                risk_reward = (target - entry) / (entry - stop)
        executable = action in ("buy", "sell")
        return {
            "source": "deterministic_strategy",
            "action": action,
            "reason": decision.get("reason"),
            "entry_price": entry if executable else None,
            "stop_loss": stop,
            "take_profit": target,
            "risk_reward_ratio": risk_reward,
            "quantity": quantity,
            "notional": notional,
            "position_pct": position_pct,
            "max_position_pct": self.settings.max_position_pct,
            "risk_per_trade_pct": self.settings.risk_per_trade_pct,
            "slippage_pct": buy_slippage,
            "execution_enabled": self.settings.enable_paper_execution,
            "order_type": "market",
            "data_quality": "good" if executable else "not_applicable",
        }

    def _agent_snapshot(self, symbol, snapshot, values, ticker_row, orderbook, spread, portfolio, risk, news, proposal, candles):
        """Assemble the per-call context shipped to all eight agents."""
        features = {}
        for key, value in values.items():
            clean = self._finite(value)
            if clean is not None:
                features[key] = clean
        regime = self._regime_context(values)
        structure = self._structure_context(candles, snapshot, values)
        return {
            "symbol": symbol,
            "market": {
                "last": snapshot.last,
                "bid": snapshot.bid,
                "ask": snapshot.ask,
                "mid_price": (snapshot.bid + snapshot.ask) / 2,
                "spread_pct": spread,
                "volume_24h": self._finite(ticker_row.get("vol24h")),
                "volume_currency_24h": self._finite(ticker_row.get("volCcy24h")),
                "timestamp_ms": snapshot.timestamp_ms,
                "data_quality": "good",
            },
            "features": features,
            "regime": self._regime_context(values),
            "structure": self._structure_context(candles, snapshot, values),
            "orderbook": orderbook,
            "news": news,
            "portfolio": portfolio,
            "risk": risk,
            "proposal": proposal,
            "as_of": datetime.now(UTC).isoformat(timespec="seconds"),
            "timeframe": "1m",
            "data_quality": {
                "market": "good",
                "features": "good" if features else "missing",
                "regime": regime["data_quality"],
                "structure": structure["data_quality"],
                "orderbook": orderbook.get("data_quality"),
                "news": news["data_quality"],
                "portfolio": portfolio["data_quality"],
                "risk": risk["data_quality"],
                "proposal": proposal["data_quality"],
            },
        }

    async def _fetch_news(self, symbol: str) -> dict:
        try:
            return await self.news.fetch(symbol)
        except Exception as exc:  # noqa: BLE001 - never let a news outage break scanning
            log.warning("news_fetch_failed", extra={"symbol": symbol, "error": f"{type(exc).__name__}: {exc}"})
            return NewsService.unavailable("news_fetch_exception", symbol)

    async def _ai_round(self, symbol, snapshot, values, row, orderbook_response, spread, decision, candles):
        """Run one advisory round for all eight agents and persist decisions plus usage totals."""
        round_id = uuid.uuid4().hex[:12]
        prices = {symbol: snapshot.last}
        prices.update({item_symbol: position.entry_price for item_symbol, position in self.broker.positions.items()})
        portfolio = self._portfolio_context(prices)
        orderbook = self._orderbook_context(orderbook_response, snapshot.last)
        slippage = orderbook.get("estimated_buy_slippage_pct")
        risk = self._risk_context(portfolio["equity"], symbol, spread, slippage)
        news = await self._fetch_news(symbol)
        proposal = self._proposal_context(snapshot, decision, portfolio["equity"], slippage)
        agent_snapshot = self._agent_snapshot(
            symbol, snapshot, values, row, orderbook, spread, portfolio, risk, news, proposal, candles
        )
        ai_audit_events = []

        def audit_agent_decision(decision_event):
            decision_event["called_at"] = datetime.fromtimestamp(decision_event["ts"], UTC).isoformat(timespec="milliseconds")
            decision_event["round_id"] = round_id
            decision_event["input_context"] = agent_snapshot
            ai_audit_events.append(decision_event)
            log.info("agent_decision", extra=decision_event)

        consensus = await self.orchestrator.decision(agent_snapshot, audit_agent_decision)
        for decision_event in ai_audit_events:
            await self.audit.append("agent_decision", decision_event)
        self.last_ai_advisory_at[symbol] = time.time()
        consensus_event = consensus.model_dump()
        consensus_event["round_id"] = round_id
        consensus_event["deterministic_decision"] = decision
        consensus_event["ai_usage"] = {
            "agent_count": len(ai_audit_events),
            "input_tokens": sum(item.get("input_tokens", 0) for item in ai_audit_events),
            "output_tokens": sum(item.get("output_tokens", 0) for item in ai_audit_events),
            "total_tokens": sum(item.get("total_tokens", 0) for item in ai_audit_events),
            "estimated_cost_usd": round(sum(item.get("estimated_cost_usd", 0.0) for item in ai_audit_events), 10),
            "model": self.settings.openai_model,
        }
        await self.audit.append("consensus", consensus_event)
        return consensus, ai_audit_events, agent_snapshot

    async def ai_probe(self, symbol: str) -> dict:
        """Operator-triggered single AI round on live data; bypasses the advisory cooldown."""
        await self._sync_exchange_portfolio(force=True)
        result, candle_response, orderbook_response = await asyncio.gather(
            self.client.ticker(symbol), self.client.candles(symbol), self.client.order_book(symbol), return_exceptions=True
        )
        for response in (result, candle_response):
            if isinstance(response, Exception):
                raise response
        if isinstance(orderbook_response, Exception):
            orderbook_response = {"data": []}
        row = result["data"][0]
        snapshot = Snapshot(symbol, int(row["ts"]), float(row["bidPx"]), float(row["askPx"]), float(row["last"]))
        candles = candles_frame(candle_response.get("data", []))
        features = compute_features(candles) if len(candles) >= 200 else None
        values = features.iloc[-1].to_dict() if features is not None and not features.empty else {}
        spread = (snapshot.ask - snapshot.bid) / snapshot.ask
        decision = signal(values, spread, self.settings.max_spread_pct)
        consensus, ai_audit_events, _ = await self._ai_round(
            symbol, snapshot, values, row, orderbook_response, spread, decision, candles
        )
        return {
            "symbol": symbol,
            "price": snapshot.last,
            "deterministic": decision,
            "action": consensus.action,
            "score": consensus.score,
            "approved": consensus.approved,
            "reason_codes": consensus.reason_codes,
            "ai_usage": {
                "agent_count": len(ai_audit_events),
                "input_tokens": sum(item.get("input_tokens", 0) for item in ai_audit_events),
                "output_tokens": sum(item.get("output_tokens", 0) for item in ai_audit_events),
                "total_tokens": sum(item.get("total_tokens", 0) for item in ai_audit_events),
                "estimated_cost_usd": round(sum(item.get("estimated_cost_usd", 0.0) for item in ai_audit_events), 10),
                "model": self.settings.openai_model,
            },
            "agents": [
                {
                    "agent": event["agent_name"], "action": event["action"], "confidence": event["confidence"],
                    "data_quality": event["data_quality"], "veto": event["veto"], "status": event["status"],
                    "reason_codes": event["reason_codes"], "validation_error": event["validation_error"],
                    "input_tokens": event["input_tokens"], "output_tokens": event["output_tokens"],
                    "estimated_cost_usd": event["estimated_cost_usd"],
                }
                for event in ai_audit_events
            ],
        }

    def should_persist_tick(self, symbol: str, event: dict, now: float) -> bool:
        if event.get("action") != "hold":
            return True
        if event.get("paper_fill") or event.get("exit_fill"):
            return True
        if event.get("reason") in {"market_data_error", "invalid_market_data"}:
            return True
        consensus = event.get("agent_consensus", {})
        if not consensus.get("skipped", False):
            return True
        sample_seconds = self.settings.audit_paper_tick_sample_seconds
        if sample_seconds <= 0:
            return True
        return now - self.last_audit_tick_at.get(symbol, 0) >= sample_seconds

    async def maintain_audit_storage(self, now: float):
        if now - self.last_cleanup_at < self.settings.audit_cleanup_interval_seconds:
            return
        aggregate = getattr(self.audit, "aggregate_hourly", None)
        cleanup = getattr(self.audit, "cleanup", None)
        if aggregate:
            await aggregate(self.settings.audit_paper_tick_retention_days)
        if cleanup:
            await cleanup(self.settings.audit_paper_tick_retention_days)
        self.last_cleanup_at = now

    async def tick(self, symbol: str) -> dict:
        persisted = False
        try:
            await self._sync_exchange_portfolio()
            result, candle_response, orderbook_response = await asyncio.gather(
                self.client.ticker(symbol), self.client.candles(symbol), self.client.order_book(symbol), return_exceptions=True
            )
            if isinstance(result, Exception) or isinstance(candle_response, Exception):
                raise result if isinstance(result, Exception) else candle_response
            if isinstance(orderbook_response, Exception):
                orderbook_response = {"data": []}
            row = result["data"][0]
            now = int(time.time() * 1000)
            snapshot = Snapshot(symbol, int(row["ts"]), float(row["bidPx"]), float(row["askPx"]), float(row["last"]))
            if not validate_snapshot(snapshot, now):
                event: dict[str, Any] = {"symbol": symbol, "action": "hold", "reason": "invalid_market_data"}
            else:
                spread = (snapshot.ask - snapshot.bid) / snapshot.ask
                candles = candles_frame(candle_response.get("data", []))
                if len(candles) >= 30:
                    self.close_history[symbol] = [float(value) for value in candles["close"].tail(200)]
                features = compute_features(candles) if len(candles) >= 200 else None
                latest = features.iloc[-1] if features is not None and not features.empty else None
                values = latest.to_dict() if latest is not None else {}
                decision = signal(values, spread, self.settings.max_spread_pct)
                event = {"symbol": symbol, "price": snapshot.last, "spread_pct": spread, "candle_count": len(candles), "ema20": float(values["ema20"]) if values.get("ema20") is not None else None, "rsi": float(values["rsi"]) if values.get("rsi") is not None else None, **decision}
                exit_fill = self.broker.mark(symbol, snapshot.last)
                if exit_fill:
                    event["exit_fill"] = exit_fill
                    if exit_fill["reason"] == "stop_or_target" and snapshot.last <= self.risk_state.peak_equity:
                        self.risk_state.record_stop(symbol)
                if decision["action"] == "buy" and symbol not in self.broker.positions and self.settings.enable_paper_execution:
                    if self.risk_state.cooling_down(symbol): event.update(action="hold",reason="stop_loss_cooldown")
                    else:
                        size = min(self.broker.cash * self.settings.max_position_pct / snapshot.last, self.broker.cash * self.settings.risk_per_trade_pct / max(snapshot.last - decision["stop_loss"], .01))
                        fill = self.broker.buy(symbol, snapshot.last, size, decision["stop_loss"], decision["take_profit"])
                        if fill: event["paper_fill"] = fill
                elif decision["action"] == "buy" and not self.settings.enable_paper_execution:
                    event["paper_execution_skipped"] = True
                # GPT agents are advisory only and are cost-gated by deterministic filters/cooldown.
                should_call, ai_reason = self.should_call_ai(symbol, decision, time.time())
                if should_call:
                    consensus, _, _ = await self._ai_round(
                        symbol, snapshot, values, row, orderbook_response, spread, decision, candles
                    )
                    event["agent_consensus"] = {"action":consensus.action,"score":consensus.score,"approved":consensus.approved,"reason_codes":consensus.reason_codes}
                else:
                    event["agent_consensus"] = {"action":"hold","score":0,"approved":False,"reason_codes":[ai_reason],"skipped":True}
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            event = {"symbol": symbol, "action": "hold", "reason": "market_data_error", "error_type": type(exc).__name__}
        now = time.time()
        if self.should_persist_tick(symbol, event, now):
            await self.audit.append("paper_tick", event)
            self.last_audit_tick_at[symbol] = now
            persisted = True
        await self.maintain_audit_storage(now)
        self.last_tick_at = now
        self.last_error = ""
        event["audit_persisted"] = persisted
        self.risk_state.peak_equity=max(self.risk_state.peak_equity,self.broker.cash)
        self.state_store.save(self.broker.snapshot())
        log.info("paper_tick", extra=event)
        return event

    async def run(self):
        self.running = True
        try:
            while self.running:
                await asyncio.gather(*(self.tick(symbol) for symbol in self.settings.allowed_symbols))
                await asyncio.sleep(self.interval)
        except Exception as exc:
            self.running = False
            self.last_error = f"{type(exc).__name__}: {exc}"
            log.exception("paper_worker_crashed")
            raise
        finally:
            close = getattr(self.audit, "close", None)
            if close:
                await close()

    def healthy(self, max_stale_seconds: int = 120) -> bool:
        return self.running and self.last_tick_at > 0 and time.time() - self.last_tick_at <= max_stale_seconds

    def stop(self): self.running = False
