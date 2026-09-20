import asyncio

from app.storage.postgres import migration_sql


def test_migrations_are_available(): assert "market_candles" in "".join(asyncio.run(migration_sql()))
