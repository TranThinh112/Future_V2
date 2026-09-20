"""Safe paper worker: public market data only and no exchange order submission."""
import asyncio
import logging
import time
from datetime import UTC, datetime
from typing import Any

import httpx

from app.config import Settings, TradingMode
from app.execution.paper import PaperBroker
from app.features.indicators import compute_features
from app.market_data.okx import OKXClient
from app.market_data.service import Snapshot, candles_frame, validate_snapshot
from app.orchestrator import Orchestrator
from app.risk.state import RiskState
from app.storage.json_store import JsonStore
from app.storage.repository import AuditRepository
from app.strategy import signal

log = logging.getLogger(__name__)

class PaperWorker:
    def __init__(self, settings: Settings, interval_seconds: int = 30):
        if settings.trading_mode != TradingMode.paper:
            raise ValueError("PaperWorker can only run in paper mode")
        self.settings, self.interval, self.running = settings, interval_seconds, False
        self.client, self.audit = OKXClient(demo=False), AuditRepository()
        self.state_store = JsonStore()
        self.broker = PaperBroker.restore(self.state_store.load({}))
        self.risk_state = RiskState(self.broker.cash, self.broker.cash)
        self.orchestrator = Orchestrator(settings)
        self.last_ai_advisory_at: dict[str, float] = {}

    def should_call_ai(self, symbol: str, decision: dict, now: float) -> tuple[bool, str]:
        if not self.settings.enable_ai_advisory:
            return False, "ai_advisory_disabled"
        if decision.get("action") == "hold" and not self.settings.ai_advisory_on_hold:
            return False, "deterministic_hold"
        last = self.last_ai_advisory_at.get(symbol, 0)
        if now - last < self.settings.ai_advisory_cooldown_seconds:
            return False, "ai_advisory_cooldown"
        return True, "ai_advisory_allowed"

    async def tick(self, symbol: str) -> dict:
        try:
            result, candle_response = await asyncio.gather(self.client.ticker(symbol), self.client.candles(symbol))
            row = result["data"][0]
            now = int(time.time() * 1000)
            snapshot = Snapshot(symbol, int(row["ts"]), float(row["bidPx"]), float(row["askPx"]), float(row["last"]))
            if not validate_snapshot(snapshot, now):
                event: dict[str, Any] = {"symbol": symbol, "action": "hold", "reason": "invalid_market_data"}
            else:
                spread = (snapshot.ask - snapshot.bid) / snapshot.ask
                candles = candles_frame(candle_response.get("data", []))
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
                    agent_snapshot = {"symbol":symbol,"last":snapshot.last,"bid":snapshot.bid,"ask":snapshot.ask,"spread_pct":spread,"features":{k:(float(v) if hasattr(v,"__float__") else v) for k,v in values.items() if k in ("ema20","ema50","rsi","macd","macd_signal","atr")}}
                    ai_audit_events = []
                    def audit_agent_decision(decision_event):
                        decision_event["called_at"] = datetime.fromtimestamp(decision_event["ts"], UTC).isoformat(timespec="milliseconds")
                        ai_audit_events.append(decision_event)
                        self.audit.append("agent_decision", decision_event)
                        log.info("agent_decision", extra=decision_event)

                    consensus = await self.orchestrator.decision(agent_snapshot, audit_agent_decision)
                    self.last_ai_advisory_at[symbol] = time.time()
                    event["agent_consensus"] = {"action":consensus.action,"score":consensus.score,"approved":consensus.approved,"reason_codes":consensus.reason_codes}
                    consensus_event = consensus.model_dump()
                    consensus_event["ai_usage"] = {
                        "agent_count": len(ai_audit_events),
                        "input_tokens": sum(item.get("input_tokens", 0) for item in ai_audit_events),
                        "output_tokens": sum(item.get("output_tokens", 0) for item in ai_audit_events),
                        "total_tokens": sum(item.get("total_tokens", 0) for item in ai_audit_events),
                        "estimated_cost_usd": round(sum(item.get("estimated_cost_usd", 0.0) for item in ai_audit_events), 10),
                        "model": self.settings.openai_model,
                    }
                    self.audit.append("consensus", consensus_event)
                else:
                    event["agent_consensus"] = {"action":"hold","score":0,"approved":False,"reason_codes":[ai_reason],"skipped":True}
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            event = {"symbol": symbol, "action": "hold", "reason": "market_data_error", "error_type": type(exc).__name__}
        self.audit.append("paper_tick", event)
        self.risk_state.peak_equity=max(self.risk_state.peak_equity,self.broker.cash)
        self.state_store.save(self.broker.snapshot())
        log.info("paper_tick", extra=event)
        return event

    async def run(self):
        self.running = True
        while self.running:
            await asyncio.gather(*(self.tick(s) for s in self.settings.allowed_symbols))
            await asyncio.sleep(self.interval)

    def stop(self): self.running = False
