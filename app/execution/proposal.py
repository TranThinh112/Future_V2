from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal


@dataclass
class Instrument:
    tick_size: Decimal; lot_size: Decimal; min_size: Decimal; max_size: Decimal
def round_down(value: float, step: Decimal) -> Decimal:
    return (Decimal(str(value))/step).to_integral_value(rounding=ROUND_DOWN)*step
def normalize_order(price, size, instrument: Instrument):
    p=round_down(price,instrument.tick_size); s=round_down(size,instrument.lot_size)
    if s<instrument.min_size: raise ValueError("below_min_size")
    return p,min(s,instrument.max_size)
