from decimal import Decimal

from app.execution.proposal import Instrument, normalize_order
from app.execution.reconcile import reconcile


def test_order_rounding():
    p,s=normalize_order(100.019,1.234,Instrument(Decimal('.01'),Decimal('.1'),Decimal('.1'),Decimal(5))); assert str(p)=='100.01' and s==Decimal('1.2')
def test_reconcile(): assert reconcile({'BTC-USDT':1},{'BTC-USDT':0})==['BTC-USDT']
