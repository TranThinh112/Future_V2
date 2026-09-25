import time
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class RiskState:
    peak_equity: float; daily_start_equity: float; stop_cooldowns: dict[str,float] = field(default_factory=dict)
    source: str = "paper"; day: str = ""
    def drawdown(self, equity): return max(0, (self.peak_equity-equity)/self.peak_equity) if self.peak_equity else 0
    def daily_loss(self, equity): return max(0, (self.daily_start_equity-equity)/self.daily_start_equity) if self.daily_start_equity else 0
    def cooling_down(self, symbol): return self.stop_cooldowns.get(symbol,0)>time.time()
    def record_stop(self, symbol, seconds=900): self.stop_cooldowns[symbol]=time.time()+seconds
    def rebase(self, equity, source, now=None):
        """Anchor drawdown and daily loss to the funded account instead of a stale paper ledger."""
        try: equity=float(equity)
        except (TypeError, ValueError): return
        if not equity>0: return
        day=(now or datetime.now(UTC)).strftime("%Y-%m-%d")
        if source!=self.source or not self.daily_start_equity>0:
            self.source, self.day, self.peak_equity, self.daily_start_equity = source, day, equity, equity
        elif day!=self.day:
            self.day, self.daily_start_equity = day, equity
        self.peak_equity=max(self.peak_equity, equity)
