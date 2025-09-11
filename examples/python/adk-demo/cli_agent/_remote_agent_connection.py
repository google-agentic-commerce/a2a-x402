from typing import Callable

from numpy import number

import httpx
from a2a.client import A2AClient
from a2a.types import (
    AgentCard,
    JSONRPCErrorResponse,
    Message,
    MessageSendParams,
    SendMessageRequest,
    SendStreamingMessageRequest,
    Task,
    TaskArtifactUpdateEvent,
    TaskStatusUpdateEvent,
)

type TaskCallbackArg = Task | TaskStatusUpdateEvent | TaskArtifactUpdateEvent
TaskUpdateCallback = Callable[[TaskCallbackArg], Task]


class RemoteAgentConnections:
    """A class to hold the connections to the remote agents."""

    def __init__(self, client: httpx.AsyncClient, agent_card: AgentCard):
        self.agent_client = A2AClient(client, agent_card)
        self.card = agent_card
        self.pending_tasks = set()

    def get_agent(self) -> AgentCard:
        return self.card

    async def send_message(
        self,
        id: number | str,
        request: MessageSendParams,
        task_callback: TaskUpdateCallback | None,
    ) -> Task | Message | None:
        if self.card.capabilities.streaming:
            task = None
            async for response in self.agent_client.send_message_streaming(
                SendStreamingMessageRequest(id=id, params=request)
            ):
                print(f"THE RESULT RESPONSE {response}")
                if not response.root.result:
                    return response.root.error
                # In the case a message is returned, that is the end of the interaction.
                event = response.root.result
                if isinstance(event, Message):
                    return event

                # Otherwise we are in the Task + TaskUpdate cycle.
                if task_callback and event:
                    task = task_callback(event)
                if hasattr(event, 'final') and event.final:
                    break
            return task
        else:  # Non-streaming
            response = await self.agent_client.send_message(
                SendMessageRequest(id=id, params=request)
            )
            if isinstance(response.root, JSONRPCErrorResponse):
                return response.root.error
            if isinstance(response.root.result, Message):
                return response.root.result

            if task_callback:
                task_callback(response.root.result)
            return response.root.result