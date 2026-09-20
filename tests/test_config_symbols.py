import pytest

from app.config import Settings


def test_symbol_allowlist():
    with pytest.raises(ValueError): Settings(allowed_symbols=("SOL-USDT",))
