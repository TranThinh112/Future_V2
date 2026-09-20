import time
from dataclasses import dataclass, field


@dataclass
class RiskState:
    peak_equity: float; daily_start_equity: float; stop_cooldowns: dict[str,float] = field(default_factory=dict)
    def drawdown(self, equity): return max(0, (self.peak_equity-equity)/self.peak_equity) if self.peak_equity else 0
    def daily_loss(self, equity): return max(0, (self.daily_start_equity-equity)/self.daily_start_equity) if self.daily_start_equity else 0
    def cooling_down(self, symbol): return self.stop_cooldowns.get(symbol,0)>time.time()
    def record_stop(self, symbol, seconds=900): self.stop_cooldowns[symbol]=time.time()+seconds
