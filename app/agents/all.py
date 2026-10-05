from .base import AGENT_NAMES
from .openai_adapter import OpenAIAgent


def build_agents(api_key, model, input_cost_per_million=0.0, output_cost_per_million=0.0, base_url="https://api.openai.com/v1"):
    return {
        n: OpenAIAgent(
            n,
            api_key,
            model,
            base_url=base_url,
            input_cost_per_million=input_cost_per_million,
            output_cost_per_million=output_cost_per_million,
        )
        for n in AGENT_NAMES
    }
