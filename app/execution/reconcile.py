def reconcile(local_positions, exchange_positions):
    symbols=set(local_positions)|set(exchange_positions)
    return [s for s in symbols if local_positions.get(s,0)!=exchange_positions.get(s,0)]
