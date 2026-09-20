from dataclasses import dataclass


@dataclass
class RiskResult:
    status: str; position_size: float = 0.0; reasons: list[str] | None = None

def check_trade(*, equity, entry, stop_loss, current_exposure, position_value=0, spread_pct=0, slippage_pct=0, settings, daily_loss_pct=0, drawdown_pct=0, liquidity_ok=True, cooling_down=False, averaging_down=False, api_healthy=True):
    reasons=[]
    if not liquidity_ok: reasons.append("insufficient_liquidity")
    if not api_healthy: reasons.append("api_or_data_unhealthy")
    if cooling_down: reasons.append("stop_loss_cooldown")
    if averaging_down: reasons.append("averaging_down_forbidden")
    if spread_pct > settings.max_spread_pct: reasons.append("spread_limit")
    if slippage_pct > settings.max_slippage_pct: reasons.append("slippage_limit")
    if daily_loss_pct >= settings.daily_loss_limit_pct: reasons.append("daily_loss_limit")
    if drawdown_pct >= settings.max_drawdown_pct: reasons.append("drawdown_limit")
    distance=abs(entry-stop_loss) if stop_loss is not None else 0
    if distance <= 0: reasons.append("invalid_stop")
    if current_exposure + position_value > equity*settings.max_total_exposure_pct: reasons.append("exposure_limit")
    if reasons: return RiskResult("REJECTED",0,reasons)
    size=min(equity*settings.risk_per_trade_pct/distance, equity*settings.max_position_pct/entry, equity*settings.max_total_exposure_pct/entry-current_exposure/entry)
    return RiskResult("APPROVED",max(0,size),[])
