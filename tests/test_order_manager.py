import asyncio
from decimal import Decimal

import pytest

from app.execution.manager import OrderManager
from app.execution.proposal import Instrument


def test_duplicate_order_is_rejected():
    manager=OrderManager(); proposal={"symbol":"BTC-USDT","side":"buy","client_order_id":"same","size":1}
    asyncio.run(manager.submit(proposal))
    with pytest.raises(ValueError): asyncio.run(manager.submit(proposal))

def test_order_manager_rounds_and_returns_audit_linkage():
    instrument = Instrument(Decimal(".01"), Decimal(".1"), Decimal(".1"), Decimal(5))
    manager = OrderManager()
    result = asyncio.run(manager.submit({
        "symbol": "BTC-USDT",
        "side": "buy",
        "client_order_id": "rounded",
        "decision_id": "decision-1",
        "price": 100.019,
        "size": 1.234,
        "agent_votes": [{"agent_name": "RUNE"}],
        "consensus": {"score": .8},
        "risk_result": {"status": "APPROVED"},
    }, instrument=instrument))
    assert result["proposal"]["price"] == 100.01
    assert result["proposal"]["size"] == 1.2
    assert result["audit"]["decision_id"] == "decision-1"
    assert result["audit"]["order_id"] == result["order_id"]
