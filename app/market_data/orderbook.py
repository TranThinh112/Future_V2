def spread_pct(bid: float, ask: float) -> float:
    if bid <= 0 or ask < bid: raise ValueError("invalid_book")
    return (ask-bid)/ask
def estimated_slippage(levels, quantity):
    """Estimate buy-side slippage against supplied [price, quantity] levels."""
    remaining=float(quantity); cost=0.; first=float(levels[0][0]) if levels else 0
    for price,size,*_ in levels:
        taken=min(remaining,float(size)); cost+=taken*float(price); remaining-=taken
        if remaining<=0: return cost/quantity/first-1
    return None
