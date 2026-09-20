from app.agents.all import build_agents
from app.pipeline import analyze


class Orchestrator:
    def __init__(self, settings):
        self.agents = build_agents(
            settings.openai_api_key,
            settings.openai_model,
            settings.ai_input_cost_per_million,
            settings.ai_output_cost_per_million,
        )
    async def decision(self, snapshot, on_agent_decision=None): return await analyze(snapshot,self.agents,on_agent_decision)
