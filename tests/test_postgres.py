import asyncio

from app.storage.postgres import migration_sql


def test_migrations_include_indexes(): assert "idx_market_candles" in "".join(asyncio.run(migration_sql()))
