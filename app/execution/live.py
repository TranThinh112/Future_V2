#""Fail-closed OKX futures execution planning. It never bypasses settings gates."""
import time
import uuid

from app.config import TradingMode
from app.execution.guards import assert_execution_mode

CONFIRMATION = "I_UNDERSTAND_LIVE_TRADING_RISK"
SWAP_BY_SYMBOL = {"BTC-USDT": "BTC-USDT-SWAP", "ETH-USDT": "ETH-USDT-SWAP"}


class LiveFuturesExecutor:
    def __init__(self, client, settings):
        self.client, self.settings = client, settings

    def _guard(self):
        assert_execution_mode(self.settings.trading_mode, self.settings.enable_live_trading, self.settings.live_execution_enabled)
        if self.settings.trading_mode != TradingMode.live: raise PermissionError("live_mode_required")
        if self.settings.okx_read_only or self.settings.okx_demo_trading: raise PermissionError("live_client_not_writable")
        if self.settings.live_execution_confirmation != CONFIRMATION: raise PermissionError("live_confirmation_missing")
        if self.settings.target_leverage > self.settings.live_max_leverage: raise ValueError("leverage_exceeds_live_cap")
        if self.settings.live_margin_mode != "isolated": raise ValueError("isolated_margin_required")

    def plan(self, proposal, consensus):
        self._guard()
        if not consensus.get("approved") or consensus.get("action") not in ("buy", "sell"): raise ValueError("consensus_not_approved")
        action = consensus["action"]
        entry, stop = float(proposal["input_price"] if "input_price" in proposal else proposal["entry_price"]), float(proposal["stop_loss"])
        if (action == "buy" and stop >= entry) or (action == "sell" and stop <= entry): raise ValueError("invalid_protective_stop")
        symbol = SWAP_BY_SYMBOL.get(proposal.get("symbol"))
        if not symbol: raise ValueError("unsupported_live_symbol")
        return {"instId": symbol, "tdMode": "isolated", "posSide": "long" if action == "buy" else "short", "side": action, "ordType": "market", "target_margin_usdt": self.settings.target_margin_usdt, "lever": self.settings.target_leverage, "target_notional_usdt": self.settings.target_margin_usdt * self.settings.target_leverage, "stop_loss": stop, "take_profit_ladder": proposal.get("take_profit_ladder"), "clOrdId": "bot-" + uuid.uuid4().hex[:28], "created_at_ms": int(time.time() * 1000)}

    async def submit(self, proposal, consensus):
        plan = self.plan(proposal, consensus)
        if self.settings.live_dry_run: return {"status": "dry_run", "plan": plan}
        swap_symbol = plan["instId"]
        await self.client.set_swap_leverage(swap_symbol, plan["lever"], plan["tdMode"])
        entry_price = float(proposal.get("entry_price", 0.0))
        ct_val = 0.01 if "BTC" in swap_symbol else 0.1
        notional_per_ct = max(entry_price * ct_val, 1e-6)
        contracts = max(1, int(plan["target_notional_usdt"] / notional_per_ct))
        order_body = {
            "instId": swap_symbol,
            "tdMode": plan["tdMode"],
            "side": plan["side"],
            "posSide": plan["posSide"],
            "ordType": "market",
            "sz": str(contracts),
            "clOrdId": plan["clOrdId"],
        }
        algo = {}
        if plan.get("stop_loss"):
            algo["slTriggerPx"] = str(plan["stop_loss"])
            algo["slOrdPx"] = "-1"
            algo["slTriggerPxType"] = "last"
        tp_price = None
        if plan.get("take_profit_ladder") and isinstance(plan.get("take_profit_ladder"), dict) and plan["take_profit_ladder"].get("tp1"):
            tp_price = plan["take_profit_ladder"]["tp1"]
        elif proposal.get("take_profit"):
            tp_price = proposal["take_profit"]
        if tp_price:
            algo["tpTriggerPx"] = str(tp_price)
            algo["tpOrdPx"] = "-1"
            algo["tpTriggerPxType"] = "last"
        if algo:
            order_body["attachAlgoOrds"] = [algo]
        response = await self.client.create_swap_order(order_body)
        return {"status": "submitted", "order_body": order_body, "response": response}
