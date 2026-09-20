from app.config import TradingMode


def assert_execution_mode(mode, enable_live=False, operator_confirmation=False):
    if mode == TradingMode.live and not (enable_live and operator_confirmation): raise PermissionError("live execution requires configuration and operator confirmation")
    if mode not in (TradingMode.paper,TradingMode.okx_demo,TradingMode.live): raise ValueError("execution unavailable in this mode")
