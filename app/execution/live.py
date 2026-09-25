"""Fail-closed OKX futures execution planning. It never bypasses settings gates."""
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
        entry, stop = float(proposal["entry_price"]), float(proposal["stop_loss"])
        if (action == "buy" and stop >= entry) or (action == "sell" and stop <= entry): raise ValueError("invalid_protective_stop")
        symbol = SWAP_BY_SYMBOL.get(proposal.get("symbol"))
        if not symbol: raise ValueError("unsupported_live_symbol")
        return {"instId": symbol, "tdMode": "isolated", "posSide": "long" if action == "buy" else "short", "side": action, "ordType": "market", "target_margin_usdt": self.settings.target_margin_usdt, "lever": self.settings.target_leverage, "target_notional_usdt": self.settings.target_margin_usdt * self.settings.target_leverage, "stop_loss": stop, "take_profit_ladder": proposal.get("take_profit_ladder"), "clOrdId": "bot-" + uuid.uuid4().hex[:28], "created_at_ms": int(time.time() * 1000)}

    async def submit(self, proposal, consensus):
        plan = self.plan(proposal, consensus)
        if self.settings.live_dry_run: return {"status": "dry_run", "plan": plan}
        raise NotImplementedError("live submission remains disabled until contract sizing and position-manager tests pass")
