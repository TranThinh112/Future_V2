from enum import StrEnum

from pydantic import Field, model_validator

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
except ImportError:  # Keep tests/imports usable before optional settings dependency is installed.
    import os

    from dotenv import dotenv_values
    from pydantic import BaseModel
    class BaseSettings(BaseModel):  # type: ignore[no-redef]
        def __init__(self, **values):
            file_values = dotenv_values(".env")
            for name in self.__class__.model_fields:
                env = name.upper()
                if name not in values:
                    if env in os.environ:
                        values[name] = os.environ[env]
                    elif env in file_values and file_values[env] is not None:
                        values[name] = file_values[env]
            super().__init__(**values)
    def SettingsConfigDict(**kwargs): return kwargs  # type: ignore[no-redef]

class TradingMode(StrEnum):
    backtest = "backtest"; paper = "paper"; okx_demo = "okx_demo"; live = "live"

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    okx_api_key: str = ""; okx_secret_key: str = ""; okx_passphrase: str = ""
    okx_demo_trading: bool = True; openai_api_key: str = ""; openai_model: str = "gpt-5.4-mini"
    trading_mode: TradingMode = TradingMode.paper
    database_url: str = "sqlite+aiosqlite:///./crypto.db"; redis_url: str = "redis://localhost:6379/0"
    max_position_pct: float = Field(.10, ge=0, le=1); position_size_headroom: float = Field(.95, gt=0, le=1)
    max_total_exposure_pct: float = Field(.30, ge=0, le=1)
    risk_per_trade_pct: float = Field(.005, ge=0, le=1); daily_loss_limit_pct: float = Field(.02, ge=0, le=1)
    max_drawdown_pct: float = Field(.10, ge=0, le=1); max_spread_pct: float = Field(.001, ge=0)
    max_slippage_pct: float = Field(.002, ge=0); enable_live_trading: bool = False
    allowed_symbols: tuple[str, ...] = ("BTC-USDT", "ETH-USDT")
    discord_webhook_url: str = ""
    otel_service_name: str = "crypto-agent"
    otel_exporter_otlp_endpoint: str = ""
    enable_ai_advisory: bool = False
    ai_advisory_cooldown_seconds: int = Field(900, ge=0)
    ai_advisory_on_hold: bool = False
    ai_precheck_enabled: bool = True
    ai_early_stop_enabled: bool = True
    ai_early_stop_on_degraded: bool = True
    ai_early_stop_on_hard_hold: bool = True
    enable_paper_execution: bool = False
    okx_account_sync: bool = True
    okx_read_only: bool = True
    ai_input_cost_per_million: float = Field(0.75, ge=0)
    ai_output_cost_per_million: float = Field(4.50, ge=0)
    audit_paper_tick_sample_seconds: int = Field(300, ge=0)
    audit_paper_tick_retention_days: int = Field(30, ge=1)
    audit_cleanup_interval_seconds: int = Field(3600, ge=60)
    news_provider_url: str = ""
    news_api_key: str = ""
    news_lookback_minutes: int = Field(180, ge=1, le=1440)
    news_max_items: int = Field(10, ge=1, le=50)

    @model_validator(mode="after")
    def guard_live(self):
        if any(symbol not in ("BTC-USDT", "ETH-USDT") for symbol in self.allowed_symbols):
            raise ValueError("only BTC-USDT and ETH-USDT spot symbols are supported")
        if self.trading_mode == TradingMode.live and not self.enable_live_trading:
            raise ValueError("live mode requires ENABLE_LIVE_TRADING=true")
        if self.trading_mode == TradingMode.live and not (self.okx_api_key and self.okx_secret_key and self.okx_passphrase):
            raise ValueError("live mode requires OKX credentials")
        return self
