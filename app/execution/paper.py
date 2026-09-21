import time
from dataclasses import dataclass, field


@dataclass
class PaperPosition:
    symbol: str; quantity: float; entry_price: float; stop_loss: float; take_profit: float; opened_at: float | None = None
@dataclass
class PaperBroker:
    cash: float = 10_000.0; fee_pct: float = .001; positions: dict[str, PaperPosition] = field(default_factory=dict); fills: list[dict] = field(default_factory=list)
    def buy(self, symbol, price, quantity, stop_loss, take_profit):
        cost=price*quantity*(1+self.fee_pct)
        if cost>self.cash or quantity<=0: return None
        self.cash-=cost; position=PaperPosition(symbol,quantity,price,stop_loss,take_profit,time.time()); self.positions[symbol]=position
        fill={"symbol":symbol,"side":"buy","price":price,"quantity":quantity,"fee":price*quantity*self.fee_pct}; self.fills.append(fill); return fill
    def mark(self, symbol, price):
        position=self.positions.get(symbol)
        if not position: return None
        if price <= position.stop_loss or price >= position.take_profit:
            proceeds=price*position.quantity*(1-self.fee_pct); self.cash+=proceeds; del self.positions[symbol]
            fill={"symbol":symbol,"side":"sell","price":price,"quantity":position.quantity,"fee":price*position.quantity*self.fee_pct,"reason":"stop_or_target"}; self.fills.append(fill); return fill
        return None
    def equity(self, prices): return self.cash+sum(p.quantity*prices.get(s,p.entry_price) for s,p in self.positions.items())
    def snapshot(self):
        return {"cash":self.cash,"fee_pct":self.fee_pct,"positions":{s:vars(p) for s,p in self.positions.items()},"fills":self.fills}
    @classmethod
    def restore(cls, value):
        broker=cls(float(value.get("cash",10000)),float(value.get("fee_pct",.001)))
        broker.positions={s:PaperPosition(**p) for s,p in value.get("positions",{}).items()}; broker.fills=value.get("fills",[])
        return broker
