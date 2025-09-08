from abc import ABC, abstractmethod

from a2a.types import AgentCard


class BaseAgent(ABC):
    @abstractmethod
    def create_agent(self):
        raise NotImplementedError("Subclasses must implement this method")

    @abstractmethod
    def create_agent_card(self, url: str) -> AgentCard:
        raise NotImplementedError("Subclasses must implement this method")
