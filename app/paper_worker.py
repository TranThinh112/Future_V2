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
from app.execution.live import LiveFuturesExecutor
from app.features.indicators import compute_features
from app.market_data.okx import OKXClient
from app.market_data.orderbook import estimated_slippage
from app.market_data.service import Snapshot, candles_frame, validate_snapshot
from app.news.service import NewsService
from app.orchestrator import Orchestrator
from app.risk.state import RiskState
from app.schemas import Consensus
from app.storage.json_store import JsonStore
from app.storage.repository import repository_from_url
from app.strategy import signal

log = logging.getLogger(__name__)

class PaperWorker:
    def __init__(self, settings: Settings, interval_seconds: int = 30):
        if settings.trading_mode not in (TradingMode.paper, TradingMode.live):
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
        self.live_executor = LiveFuturesExecutor(self.client, settings)
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
        self.live_trade_plans: dict[str, dict] = {}

    def _account_equity(self) -> tuple[float | None, str]:
        """Funded equity when the read-only exchange sync is live, else the paper ledger."""
        portfolio = getattr(self, "exchange_portfolio", None)
        if portfolio:
            equity = self._finite(portfolio.get("equity"))
            if equity and equity > 0:
                return equity, "exchange"
        return self._finite(self.broker.cash), "paper"

    def _orderbook_budget(self, portfolio: dict) -> float | None:
        """Sample slippage at the size the funded account could actually take."""
        equity = self._finite(portfolio.get("equity"))
        if not equity or equity <= 0:
            return None
        return equity * self.settings.max_position_pct * self.settings.position_size_headroom

    def _rebase_risk_state(self) -> None:
        """Keep drawdown and daily loss anchored to the funded account, never the paper ledger."""
        equity, source = self._account_equity()
        self.risk_state.rebase(equity, source)

    def should_call_ai(self, symbol: str, decision: dict, now: float) -> tuple[bool, str]:
        if not self.settings.enable_ai_advisory:
            return False, "ai_advisory_disabled"
        if decision.get("action") == "hold" and not self.settings.ai_advisory_on_hold:
            return False, "deterministic_hold"
        last = self.last_ai_advisory_at.get(symbol, 0)
        cooldown = self.settings.ai_advisory_cooldown_seconds
        if decision.get("action") in ("buy", "sell"):
            cooldown = max(300, cooldown // 2)
        if now - last < cooldown:
            return False, "ai_advisory_cooldown"
        return True, "ai_advisory_allowed"

    @staticmethod
    def _finite(value):
        try:
            value = float(value)
            return value if math.isfinite(value) else None
        except (TypeError, ValueError):
            return None

    def _orderbook_context(self, response: dict, last: float, notional_budget: float | None = None) -> dict:
        row = (response.get("data") or [{}])[0]
        bids = row.get("bids") or []
        asks = row.get("asks") or []
        bid_depth = sum(self._finite(level[1]) or 0 for level in bids if len(level) >= 2)
        ask_depth = sum(self._finite(level[1]) or 0 for level in asks if len(level) >= 2)
        total_depth = bid_depth + ask_depth
        budget = notional_budget if notional_budget and notional_budget > 0 else self.broker.cash * self.settings.max_position_pct
        quantity = budget / max(last, 0.000001)
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
                previous_positions = dict((self.exchange_portfolio or {}).get("positions") or {})
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
                await self._audit_closed_live_trades(previous_positions, positions)
                await self._manage_live_trailing_stops(positions)
                for s, p_data in positions.items():
                    p_plan = self.live_trade_plans.get(s)
                    if p_plan:
                        p_data["stop_loss"] = p_plan.get("current_sl") or p_plan.get("stop_loss")
                        p_data["take_profit"] = p_plan.get("current_tp") or p_plan.get("take_profit")
                        p_data["trailing_stage"] = p_plan.get("trailing_stage", 0)
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
                    "execution": {"count": 0, "recent": [], "fee_pct": 0, "last_fill": 0, "data_quality": "good", "realized_pnl": 0},
                    "source": "okx_private_account_read_only",
                    "data_quality": "good",
                    "synced_at": datetime.now(UTC).isoformat(timespec="seconds"),
                }
                self.exchange_sync_at = time.time()
                self.exchange_sync_error = ""
                self.exchange_sync_step = "synced"
                self._rebase_risk_state()
                return self.exchange_portfolio
            except (httpx.HTTPError, KeyError, TypeError, ValueError, OSError) as exc:
                self.exchange_sync_error = f"{type(exc).__name__}: {exc}"
                self.exchange_sync_step = "failed"
                log.warning("okx_account_sync_failed", extra={"error_type": type(exc).__name__, "error": str(exc)[:200]})
                return self.exchange_portfolio

    async def _audit_closed_live_trades(self, previous_positions: dict, current_positions: dict) -> None:
        """Persist an exact OKX closing result for each bot-opened position that disappears."""
        for symbol, previous in previous_positions.items():
            plan = self.live_trade_plans.get(symbol)
            if symbol in current_positions or not plan:
                continue
            self.live_trade_plans.pop(symbol, None)
            try:
                history = await self.client.orders_history(symbol, begin=plan["opened_at_ms"])
                candidates = [
                    order for order in (history.get("data") or [])
                    if str(order.get("reduceOnly")).lower() == "true"
                    and order.get("posSide") == plan.get("pos_side")
                ]
                if not candidates:
                    raise ValueError("okx_closing_order_not_found")
                closing = max(candidates, key=lambda order: self._finite(order.get("uTime")) or 0)
                exit_price = self._finite(closing.get("avgPx"))
                gross_pnl = self._finite(closing.get("pnl")) or 0.0
                fee = self._finite(closing.get("fee")) or 0.0
                target = self._finite(plan.get("current_tp", plan.get("take_profit")))
                stop = self._finite(plan.get("current_sl", plan.get("stop_loss")))
                stage = plan.get("trailing_stage", 0)
                side = plan.get("pos_side")
                reason = "other_exit"
                if exit_price is not None and target is not None:
                    if (side == "long" and exit_price >= target) or (side == "short" and exit_price <= target):
                        reason = "take_profit"
                if exit_price is not None and stop is not None:
                    if (side == "long" and exit_price <= stop) or (side == "short" and exit_price >= stop):
                        if stage == 1:
                            reason = "breakeven_exit"
                        elif stage == 2:
                            reason = "trailing_profit_exit"
                        else:
                            reason = "stop_loss"
                await self.audit.append("live_trade_closed", {
                    "symbol": symbol,
                    "order_id": plan.get("order_id"),
                    "close_order_id": closing.get("ordId"),
                    "side": side,
                    "entry_price": plan.get("entry_price"),
                    "exit_price": exit_price,
                    "initial_stop_loss": plan.get("stop_loss"),
                    "final_stop_loss": stop,
                    "take_profit": target,
                    "trailing_stage": stage,
                    "close_reason": reason,
                    "gross_pnl_usdt": gross_pnl,
                    "fee_usdt": fee,
                    "net_pnl_usdt": round(gross_pnl + fee, 10),
                    "closed_at_ms": self._finite(closing.get("uTime")),
                    "okx_source": closing.get("source"),
                    "position_before_close": previous,
                })
            except (httpx.HTTPError, KeyError, TypeError, ValueError, OSError) as exc:
                log.warning("okx_trade_close_audit_failed", extra={"symbol": symbol, "error_type": type(exc).__name__})

    async def _manage_live_trailing_stops(self, current_positions: dict) -> None:
        """Evaluate open live positions against TP milestones and amend OKX SL orders dynamically."""
        if not getattr(self.settings, "live_trailing_stop_enabled", True):
            return
        if getattr(self.settings, "trading_mode", None) != TradingMode.live or getattr(self.settings, "live_dry_run", False):
            return
        if not current_positions:
            return

        for symbol, pos in current_positions.items():
            try:
                plan = self.live_trade_plans.get(symbol)
                pos_side = pos.get("side") or "long"
                entry_px = self._finite(pos.get("entry_price"))
                mark_px = self._finite(pos.get("mark_price"))
                if not entry_px or not mark_px or mark_px <= 0:
                    continue

                decimals = 1 if "BTC" in symbol else 2

                if not plan or not plan.get("algo_id"):
                    algo_res = await self.client.pending_algo_orders(symbol, ord_type="oco")
                    algos = (algo_res.get("data") or []) if isinstance(algo_res, dict) else []
                    matching = [a for a in algos if a.get("instId") == symbol and a.get("posSide") == pos_side]
                    if not matching:
                        continue
                    algo = matching[0]
                    current_sl = self._finite(algo.get("slTriggerPx")) or 0.0
                    current_tp = self._finite(algo.get("tpTriggerPx")) or 0.0
                    tp1_pct = getattr(self.settings, "tp1_pct", 0.008)
                    tp2_pct = getattr(self.settings, "tp2_pct", 0.016)
                    tp1 = round(entry_px * (1 + tp1_pct if pos_side == "long" else 1 - tp1_pct), decimals)
                    tp2 = round(entry_px * (1 + tp2_pct if pos_side == "long" else 1 - tp2_pct), decimals)

                    stage = 0
                    if pos_side == "long":
                        if current_sl >= tp1 and tp1 > entry_px:
                            stage = 2
                        elif current_sl >= entry_px:
                            stage = 1
                    else:
                        if current_sl <= tp1 and tp1 < entry_px and current_sl > 0:
                            stage = 2
                        elif current_sl <= entry_px and current_sl > 0:
                            stage = 1

                    plan = {
                        "symbol": symbol,
                        "order_id": algo.get("ordId") or algo.get("algoId"),
                        "algo_id": algo.get("algoId"),
                        "side": "buy" if pos_side == "long" else "sell",
                        "pos_side": pos_side,
                        "entry_price": entry_px,
                        "stop_loss": current_sl,
                        "current_sl": current_sl,
                        "take_profit": current_tp,
                        "current_tp": current_tp,
                        "tp1": tp1,
                        "tp2": tp2,
                        "trailing_stage": stage,
                        "opened_at_ms": int(time.time() * 1000),
                        "size": str(pos.get("quantity") or "0"),
                    }
                    self.live_trade_plans[symbol] = plan

                if not plan.get("algo_id"):
                    continue

                if not plan.get("tp1") or not plan.get("tp2"):
                    tp1_pct = getattr(self.settings, "tp1_pct", 0.008)
                    tp2_pct = getattr(self.settings, "tp2_pct", 0.016)
                    plan["tp1"] = round(entry_px * (1 + tp1_pct if pos_side == "long" else 1 - tp1_pct), decimals)
                    plan["tp2"] = round(entry_px * (1 + tp2_pct if pos_side == "long" else 1 - tp2_pct), decimals)

                stage = plan.get("trailing_stage", 0)
                target_stage = stage
                new_sl = None
                reason = ""

                if pos_side == "long":
                    if stage < 1 and mark_px >= plan["tp1"]:
                        target_stage = 1
                        new_sl = round(entry_px, decimals)
                        reason = "hit_tp1_moved_sl_to_breakeven"
                    if mark_px >= plan["tp2"]:
                        target_stage = 2
                        new_sl = round(plan["tp1"], decimals)
                        reason = "hit_tp2_locked_profit_at_tp1"
                else:
                    if stage < 1 and mark_px <= plan["tp1"]:
                        target_stage = 1
                        new_sl = round(entry_px, decimals)
                        reason = "hit_tp1_moved_sl_to_breakeven"
                    if mark_px <= plan["tp2"]:
                        target_stage = 2
                        new_sl = round(plan["tp1"], decimals)
                        reason = "hit_tp2_locked_profit_at_tp1"

                if new_sl is not None and target_stage > stage:
                    old_sl = plan.get("current_sl") or plan.get("stop_loss")
                    amend_body = {
                        "instId": symbol,
                        "algoId": plan["algo_id"],
                        "newSlTriggerPx": str(new_sl),
                        "newSlOrdPx": "-1",
                        "newTpTriggerPx": str(plan.get("current_tp") or plan.get("take_profit")),
                        "newTpOrdPx": "-1",
                    }
                    res = await self.client.amend_algo_order(amend_body)
                    data = (res.get("data") or [{}])[0] if isinstance(res, dict) else {}
                    if str(data.get("sCode", "0")) == "0":
                        plan["trailing_stage"] = target_stage
                        plan["current_sl"] = new_sl
                        log.info(
                            "live_trade_trailing_stop_updated",
                            extra={
                                "symbol": symbol,
                                "stage": target_stage,
                                "reason": reason,
                                "entry_price": entry_px,
                                "mark_price": mark_px,
                                "old_sl": old_sl,
                                "new_sl": new_sl,
                            },
                        )
                        await self.audit.append("live_trade_trailing_stop", {
                            "symbol": symbol,
                            "order_id": plan.get("order_id"),
                            "algo_id": plan.get("algo_id"),
                            "pos_side": pos_side,
                            "stage": target_stage,
                            "reason": reason,
                            "entry_price": entry_px,
                            "mark_price": mark_px,
                            "old_sl": old_sl,
                            "new_sl": new_sl,
                            "tp1": plan["tp1"],
                            "tp2": plan["tp2"],
                            "current_tp": plan.get("current_tp") or plan.get("take_profit"),
                        })
                    else:
                        log.warning(
                            "amend_algo_order_failed",
                            extra={"symbol": symbol, "sCode": data.get("sCode"), "sMsg": data.get("sMsg")},
                        )
            except Exception as exc:
                log.warning("manage_live_trailing_stops_error", extra={"symbol": symbol, "error": str(exc)[:200]})

    def _risk_context(self, equity: float, symbol: str, spread: float, slippage: float | None) -> dict:
        effective_max_pos_pct = 1.0 if (getattr(self.settings, "trading_mode", None) == TradingMode.live and equity and equity < 50.0) else self.settings.max_position_pct
        return {
            "risk_per_trade_pct": self.settings.risk_per_trade_pct,
            "max_position_pct": effective_max_pos_pct,
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

    def _htf_trend(self, htf_candle_response) -> str:
        if not htf_candle_response or isinstance(htf_candle_response, Exception):
            return "neutral"
        htf_candles = candles_frame(htf_candle_response.get("data", []))
        if len(htf_candles) < 30:
            return "neutral"
        htf_close = htf_candles["close"].astype(float)
        htf_ema50 = htf_close.ewm(span=50, adjust=False).mean().iloc[-1]
        last_px = htf_close.iloc[-1]
        if last_px > htf_ema50:
            return "bullish"
        elif last_px < htf_ema50:
            return "bearish"
        return "neutral"

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

    def _proposal_context(self, snapshot, decision: dict, portfolio: dict, buy_slippage: float | None, symbol: str | None = None) -> dict:
        """Size the proposal against the funded account, not the paper ledger."""
        entry = self._finite(snapshot.last)
        stop, target = self._finite(decision.get("stop_loss")), self._finite(decision.get("take_profit"))
        action = decision.get("action")
        equity = self._finite(portfolio.get("equity"))
        available = self._finite(portfolio.get("available_cash"))
        if available is None:
            available = self._finite(portfolio.get("cash"))
        is_small_account = bool(getattr(self.settings, "trading_mode", None) == TradingMode.live and equity and equity < 50.0)
        effective_max_pos_pct = 1.0 if is_small_account else self.settings.max_position_pct
        cap_pct = effective_max_pos_pct * self.settings.position_size_headroom
        capital_cap = equity * cap_pct if equity else None
        if available is not None:
            capital_cap = available if capital_cap is None else min(capital_cap, available)
        quantity = notional = position_pct = risk_reward = None
        if action == "buy" and entry and stop and entry > stop and capital_cap:
            risk_amount = (equity or 0.0) * self.settings.risk_per_trade_pct
            if is_small_account and capital_cap and capital_cap >= getattr(self.settings, "target_margin_usdt", 3.5):
                target_notional = getattr(self.settings, "target_margin_usdt", 3.5) * getattr(self.settings, "target_leverage", 20)
                quantity = target_notional / entry
                notional = target_notional
            else:
                quantity = min(risk_amount / (entry - stop), capital_cap / entry)
                notional = quantity * entry
            position_pct = (getattr(self.settings, "target_margin_usdt", 3.5) / equity) if (is_small_account and equity) else (notional / equity if equity else None)
            if target and target > entry:
                risk_reward = (target - entry) / (entry - stop)
        elif action == "sell" and entry and stop and stop > entry and capital_cap:
            risk_amount = (equity or 0.0) * self.settings.risk_per_trade_pct
            if is_small_account and capital_cap and capital_cap >= getattr(self.settings, "target_margin_usdt", 3.5):
                target_notional = getattr(self.settings, "target_margin_usdt", 3.5) * getattr(self.settings, "target_leverage", 20)
                quantity = target_notional / entry
                notional = target_notional
            else:
                quantity = min(risk_amount / (stop - entry), capital_cap / entry)
                notional = quantity * entry
            position_pct = (getattr(self.settings, "target_margin_usdt", 3.5) / equity) if (is_small_account and equity) else (notional / equity if equity else None)
            if target and entry > target:
                risk_reward = (entry - target) / (stop - entry)
        executable = action in ("buy", "sell")
        return {
            "source": "deterministic_strategy",
            "symbol": symbol or getattr(snapshot, "symbol", None),
            "action": action,
            "reason": decision.get("reason"),
            "entry_price": entry if executable else None,
            "stop_loss": stop,
            "take_profit": target,
            "take_profit_ladder": decision.get("take_profit_ladder"),
            "risk_reward_ratio": risk_reward,
            "quantity": quantity,
            "notional": notional,
            "position_pct": position_pct,
            "max_position_pct": effective_max_pos_pct,
            "risk_per_trade_pct": self.settings.risk_per_trade_pct,
            "target_margin_usdt": getattr(self.settings, "target_margin_usdt", 3.5),
            "target_leverage": getattr(self.settings, "target_leverage", 20),
            "target_notional_usdt": getattr(self.settings, "target_margin_usdt", 3.5) * getattr(self.settings, "target_leverage", 20),
            "slippage_pct": buy_slippage,
            "execution_enabled": (getattr(self.settings, "enable_paper_execution", False) if getattr(self.settings, "trading_mode", None) == TradingMode.paper else (getattr(self.settings, "enable_live_trading", False) and getattr(self.settings, "live_execution_enabled", False))),
            "order_type": "market",
            "data_quality": "good" if executable else "not_applicable",
        }

    def _agent_snapshot(self, symbol, snapshot, values, ticker_row, orderbook, spread, portfolio, risk, news, proposal, candles, htf_trend: str = "neutral"):
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
            "timeframe": getattr(getattr(self, "settings", None), "strategy_bar", "15m"),
            "htf_timeframe": getattr(getattr(self, "settings", None), "strategy_htf_bar", "1H"),
            "htf_trend": htf_trend,
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


    def _ai_precheck_reason(self, proposal: dict, portfolio: dict, orderbook: dict, risk: dict) -> str:
        if not getattr(self.settings, "ai_precheck_enabled", True):
            return ""
        if proposal.get("action") == "hold":
            return str(proposal.get("reason") or "deterministic_hold")
        symbol = proposal.get("symbol")
        positions = portfolio.get("positions", {})
        if symbol and any(symbol == p or p.startswith(symbol) or symbol.startswith(p) for p in positions):
            return "position_already_exists"
        if proposal.get("data_quality") != "good":
            return f"proposal_data_quality_{proposal.get('data_quality')}"
        if orderbook.get("data_quality") != "good":
            return f"orderbook_data_quality_{orderbook.get('data_quality')}"
        if risk.get("data_quality") != "good":
            return f"risk_data_quality_{risk.get('data_quality')}"
        if risk.get("api_healthy") is False:
            return "api_unhealthy"
        if risk.get("liquidity_ok") is False:
            return "orderbook_liquidity_bad"
        notional = self._finite(proposal.get("notional")) or 0.0
        available_cash = self._finite(portfolio.get("available_cash"))
        if available_cash is None:
            available_cash = self._finite(portfolio.get("cash"))
        required_margin = self._finite(proposal.get("target_margin_usdt")) or getattr(self.settings, "target_margin_usdt", 3.5)
        if proposal.get("action") in ("buy", "sell") and available_cash is not None and required_margin > max(available_cash, 0):
            return "proposal_required_margin_exceeds_available_cash"
        position_pct = self._finite(proposal.get("position_pct"))
        max_position_pct = self._finite(proposal.get("max_position_pct")) or self.settings.max_position_pct
        if position_pct is not None and max_position_pct is not None and position_pct > max_position_pct:
            return "proposal_position_pct_exceeds_max_position_pct"
        return ""

    async def _persist_precheck_consensus(self, round_id: str, symbol: str, decision: dict, agent_snapshot: dict, reason: str):
        consensus = Consensus(symbol=symbol, action="hold", score=0, approved=False, votes=[], reason_codes=["ai_precheck_skipped", reason])
        event = (consensus.model_dump() if hasattr(consensus, "model_dump") else consensus.dict())
        event["round_id"] = round_id
        event["deterministic_decision"] = decision
        event["input_context"] = agent_snapshot
        event["early_stop"] = {
            "precheck": True,
            "reason": reason,
            "called_agents": [],
            "skipped_agents": ["RUNE", "OKAPI", "ZEPHR", "LUMEN", "TIDAL", "NORO", "VESKA", "MARIN"],
        }
        event["ai_usage"] = {
            "agent_count": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "estimated_cost_usd": 0.0,
            "model": self.settings.openai_model,
        }
        await self.audit.append("consensus", event)
        return consensus, [], agent_snapshot

    async def _fetch_news(self, symbol: str) -> dict:
        try:
            return await self.news.fetch(symbol)
        except Exception as exc:  # noqa: BLE001 - never let a news outage break scanning
            log.warning("news_fetch_failed", extra={"symbol": symbol, "error": f"{type(exc).__name__}: {exc}"})
            return NewsService.unavailable("news_fetch_exception", symbol)

    async def _ai_round(self, symbol, snapshot, values, row, orderbook_response, spread, decision, candles, htf_trend: str = "neutral"):
        """Run one advisory round for all eight agents and persist decisions plus usage totals."""
        round_id = uuid.uuid4().hex[:12]
        prices = {symbol: snapshot.last}
        prices.update({item_symbol: position.entry_price for item_symbol, position in self.broker.positions.items()})
        portfolio = self._portfolio_context(prices)
        orderbook = self._orderbook_context(orderbook_response, snapshot.last, self._orderbook_budget(portfolio))
        slippage = orderbook.get("estimated_buy_slippage_pct")
        risk = self._risk_context(portfolio["equity"], symbol, spread, slippage)
        news = await self._fetch_news(symbol)
        proposal = self._proposal_context(snapshot, decision, portfolio, slippage, symbol=symbol)
        agent_snapshot = self._agent_snapshot(
            symbol, snapshot, values, row, orderbook, spread, portfolio, risk, news, proposal, candles, htf_trend=htf_trend
        )
        precheck_reason = self._ai_precheck_reason(proposal, portfolio, orderbook, risk)
        if precheck_reason:
            self.last_ai_advisory_at[symbol] = time.time()
            return await self._persist_precheck_consensus(round_id, symbol, decision, agent_snapshot, precheck_reason)
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
        consensus_event = (consensus.model_dump() if hasattr(consensus, "model_dump") else consensus.dict())
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

    async def ai_probe(self, symbol: str, force: bool = False) -> dict:
        """Operator-triggered single AI round on live data; bypasses the advisory cooldown."""
        await self._sync_exchange_portfolio(force=True)
        bar = getattr(self.settings, "strategy_bar", "15m")
        htf_bar = getattr(self.settings, "strategy_htf_bar", "1H")
        result, candle_response, orderbook_response, htf_candle_response = await asyncio.gather(
            self.client.ticker(symbol), self.client.candles(symbol, bar=bar), self.client.order_book(symbol), self.client.candles(symbol, bar=htf_bar, limit=100), return_exceptions=True
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
        htf_trend = self._htf_trend(htf_candle_response)
        decision = signal(
                    values,
                    spread,
                    self.settings.max_spread_pct,
                    getattr(self.settings, "strategy_min_stop_pct", 0.012),
                    getattr(self.settings, "strategy_risk_reward", 2.0),
                    getattr(self.settings, "tp1_pct", 0.008),
                    getattr(self.settings, "tp1_close_pct", 0.30),
                    getattr(self.settings, "tp2_pct", 0.016),
                    getattr(self.settings, "tp2_close_pct", 0.30),
                    getattr(self.settings, "tp3_pct", 0.024),
                    getattr(self.settings, "tp3_close_pct", 0.40),
                    htf_trend=htf_trend,
                    candles=candles,
                )
        consensus, ai_audit_events, _ = await self._ai_round(
            symbol, snapshot, values, row, orderbook_response, spread, decision, candles, htf_trend=htf_trend
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
            self._rebase_risk_state()
            bar = getattr(self.settings, "strategy_bar", "15m")
            htf_bar = getattr(self.settings, "strategy_htf_bar", "1H")
            result, candle_response, orderbook_response, htf_candle_response = await asyncio.gather(
                self.client.ticker(symbol), self.client.candles(symbol, bar=bar), self.client.order_book(symbol), self.client.candles(symbol, bar=htf_bar, limit=100), return_exceptions=True
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
                htf_trend = self._htf_trend(htf_candle_response)
                decision = signal(
                    values,
                    spread,
                    self.settings.max_spread_pct,
                    getattr(self.settings, "strategy_min_stop_pct", 0.012),
                    getattr(self.settings, "strategy_risk_reward", 2.0),
                    getattr(self.settings, "tp1_pct", 0.008),
                    getattr(self.settings, "tp1_close_pct", 0.30),
                    getattr(self.settings, "tp2_pct", 0.016),
                    getattr(self.settings, "tp2_close_pct", 0.30),
                    getattr(self.settings, "tp3_pct", 0.024),
                    getattr(self.settings, "tp3_close_pct", 0.40),
                    htf_trend=htf_trend,
                    candles=candles,
                )
                event = {"symbol": symbol, "price": snapshot.last, "spread_pct": spread, "candle_count": len(candles), "timeframe": bar, "htf_trend": htf_trend, "ema20": float(values["ema20"]) if values.get("ema20") is not None else None, "rsi": float(values["rsi"]) if values.get("rsi") is not None else None, **decision}
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
                        symbol, snapshot, values, row, orderbook_response, spread, decision, candles, htf_trend=htf_trend
                    )
                    event["agent_consensus"] = {"action":consensus.action,"score":consensus.score,"approved":consensus.approved,"reason_codes":consensus.reason_codes}
                    if consensus.approved and consensus.action in ("buy", "sell") and getattr(self.settings, "trading_mode", None) == TradingMode.live:
                        try:
                            proposal_data = self._proposal_context(snapshot, decision, self._portfolio_context({symbol: snapshot.last}), spread, symbol=symbol)
                            live_res = await self.live_executor.submit(proposal_data, (consensus.model_dump() if hasattr(consensus, "model_dump") else consensus.dict()))
                            event["live_execution"] = live_res
                            response = live_res.get("response") or {}
                            result = (response.get("data") or [{}])[0]
                            if str(result.get("sCode")) == "0":
                                plan = live_res.get("order_body") or {}
                                entry_px = proposal_data.get("entry_price") or snapshot.last
                                decimals = 1 if "BTC" in symbol else 2
                                pos_side = plan.get("posSide", "long")
                                tp1_pct = getattr(self.settings, "tp1_pct", 0.008)
                                tp2_pct = getattr(self.settings, "tp2_pct", 0.016)
                                trade = {
                                    "symbol": plan.get("instId"),
                                    "order_id": result.get("ordId"),
                                    "side": plan.get("side"),
                                    "pos_side": pos_side,
                                    "entry_price": entry_px,
                                    "stop_loss": proposal_data.get("stop_loss"),
                                    "take_profit": proposal_data.get("take_profit"),
                                    "current_sl": proposal_data.get("stop_loss"),
                                    "current_tp": proposal_data.get("take_profit"),
                                    "tp1": round(entry_px * (1 + tp1_pct if pos_side == "long" else 1 - tp1_pct), decimals),
                                    "tp2": round(entry_px * (1 + tp2_pct if pos_side == "long" else 1 - tp2_pct), decimals),
                                    "trailing_stage": 0,
                                    "opened_at_ms": int(time.time() * 1000),
                                    "size": plan.get("sz"),
                                }
                                self.live_trade_plans[trade["symbol"]] = trade
                                await self.audit.append("live_trade_open", trade)
                        except Exception as exc:
                            event["live_execution_error"] = str(exc)
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
        self._rebase_risk_state()
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
