from .base_agent import BaseAgent
from a2a.types import AgentCard

class AgentRoutes(BaseAgent):
    def create_agent(self):
        pass

    def create_agent_card(self, url: str) -> AgentCard:
        pass