from app.execution.guards import assert_execution_mode


class DemoExecutor:
    def __init__(self, client, settings): self.client,self.settings=client,settings
    async def submit(self, proposal):
        assert_execution_mode(self.settings.trading_mode,self.settings.enable_live_trading,False)
        if self.settings.trading_mode.value!="okx_demo": raise PermissionError("demo mode required")
        return await self.client.create_order(proposal)
