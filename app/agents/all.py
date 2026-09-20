from .base import AGENT_NAMES
from .openai_adapter import OpenAIAgent


def build_agents(api_key, model): return {n:OpenAIAgent(n,api_key,model) for n in AGENT_NAMES}
