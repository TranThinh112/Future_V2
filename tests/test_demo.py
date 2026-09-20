import asyncio

from app.config import Settings
from app.execution.demo import DemoExecutor


class Client:
    async def create_order(self,p): return p
def test_demo_rejects_paper_mode():
    try: asyncio.run(DemoExecutor(Client(),Settings()).submit({}))
    except PermissionError: assert True
    else: assert False
