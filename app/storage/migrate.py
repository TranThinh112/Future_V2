import asyncio

from app.storage.postgres import apply_migrations

if __name__ == "__main__":
    asyncio.run(apply_migrations())
