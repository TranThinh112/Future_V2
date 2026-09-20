import os
from pathlib import Path


async def migration_sql():
    return [path.read_text(encoding="utf-8") for path in sorted(Path("migrations").glob("*.sql"))]

async def apply_migrations(database_url: str | None = None):
    """Apply checked-in migrations. Requires the optional asyncpg package and an operator DB URL."""
    try:
        import asyncpg
    except ImportError as error:
        raise RuntimeError("install asyncpg to apply PostgreSQL migrations") from error
    url = database_url or os.environ.get("DATABASE_URL", "")
    if not url.startswith("postgresql"):
        raise ValueError("a PostgreSQL DATABASE_URL is required")
    connection = await asyncpg.connect(url.replace("postgresql+asyncpg://", "postgresql://"))
    try:
        for sql in await migration_sql():
            await connection.execute(sql)
    finally:
        await connection.close()
