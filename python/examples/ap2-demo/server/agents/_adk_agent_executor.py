# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import json
import logging
import inspect
from collections.abc import AsyncGenerator

from a2a.server.agent_execution import AgentExecutor
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import (
    AgentCard,
    DataPart,
    FilePart,
    FileWithBytes,
    FileWithUri,
    Part,
    TaskState,
    TextPart,
    UnsupportedOperationError,
)
from a2a.utils.errors import ServerError
from google.adk import Runner
from google.adk.events import Event
from google.genai import types

from x402_a2a.core.utils import x402Utils
from x402_a2a.types import x402PaymentRequiredException

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class ADKAgentExecutor(AgentExecutor):
    """An AgentExecutor that runs an ADK-based Agent."""

    def __init__(self, runner: Runner, card: AgentCard):
        self.runner = runner
        self._card = card
        self._running_sessions = {}
        self.x402 = x402Utils()

    def _run_agent(
        self, session_id, new_message: types.Content
    ) -> AsyncGenerator[Event, None]:
        return self.runner.run_async(
            session_id=session_id, user_id="self", new_message=new_message
        )

    async def _process_request(
        self,
        new_message: types.Content,
        session_id: str,
        task_updater: TaskUpdater,
    ) -> None:
        session = await self._upsert_session(session_id)
        session_id = session.id

        current_message = new_message

        # The ADK agent can have multiple turns (e.g., tool call -> tool response -> final answer)
        # We need to loop until the agent gives a final response.
        while True:
            # Get the stream of events from the agent for the current turn
            event_stream = self._run_agent(session_id, current_message)

            function_calls_to_execute = []

            async for event in event_stream:
                if event.is_final_response():
                    # The agent is done, send the final result and terminate.
                    parts = []
                    if event.content and event.content.parts:
                        parts = convert_genai_parts_to_a2a(event.content.parts)

                    logger.debug("Yielding final response: %s", parts)
                    if parts:
                        await task_updater.add_artifact(parts)

                    await task_updater.complete()
                    return  # Exit the loop and the method

                if event.get_function_calls():
                    # The agent wants to call a tool. Collect all calls for this turn.
                    function_calls_to_execute.extend(event.get_function_calls())
                elif event.content and event.content.parts:
                    # --- Custom Artifact Interception ---
                    # Check if the content part is a function response containing our artifact
                    logger.debug("Yielding update response: %s", event.content.parts)
                    is_artifact_response = False
                    for part in event.content.parts:
                        if part.function_response:
                            response_data = part.function_response.response
                            if (
                                isinstance(response_data, dict)
                                and "artifact" in response_data
                                and "artifactId" in response_data["artifact"]
                                and "parts" in response_data["artifact"]
                            ):
                                logger.info(
                                    "Intercepted artifact in function response."
                                )
                                artifact_parts = [
                                    Part(root=DataPart(**p))
                                    for p in response_data["artifact"].get("parts", [])
                                    if "data" in p
                                ]
                                if artifact_parts:
                                    logger.debug("Adding artifact: %s", artifact_parts)
                                    await task_updater.add_artifact(
                                        parts=artifact_parts,
                                        artifact_id=response_data["artifact"][
                                            "artifactId"
                                        ],
                                        name=response_data["artifact"].get("name"),
                                        metadata=response_data["artifact"].get(
                                            "metadata"
                                        ),
                                        extensions=response_data["artifact"].get(
                                            "extensions"
                                        ),
                                    )
                                    await task_updater.complete()
                                    return  # Task complete, exit.
                                is_artifact_response = True
                                break  # Found it, no need to check other parts.

                    if not is_artifact_response:
                        # This is a standard intermediate response from the agent.
                        logger.debug(
                            "Yielding update response: %s", event.content.parts
                        )
                        await task_updater.update_status(
                            TaskState.working,
                            message=task_updater.new_agent_message(
                                convert_genai_parts_to_a2a(event.content.parts),
                            ),
                        )
                else:
                    logger.debug("Skipping empty event: %s", event)

            if not function_calls_to_execute:
                # The stream ended without a final response or a tool call.
                # This indicates an unexpected state. We'll complete the task to avoid hanging.
                logger.warning("ADK agent stream ended unexpectedly. Completing task.")
                await task_updater.complete()
                return

            # --- Execute Tools ---
            tool_outputs = []
            for call in function_calls_to_execute:
                tool_name = call.name
                tool_args = dict(call.args)

                logger.debug(
                    f"Attempting to execute tool '{tool_name}' with args: {tool_args}"
                )

                # Find the corresponding tool function registered with the agent
                target_tool = next(
                    (
                        t
                        for t in self.runner.agent.tools
                        if getattr(t, "__name__", None) == tool_name
                    ),
                    None,
                )

                if not target_tool:
                    raise ValueError(
                        f"Tool '{tool_name}' requested by the LLM but not found on the agent."
                    )

                try:
                    # Execute the tool. This can raise x402PaymentRequiredException or return an artifact.
                    # Support both async and sync tools.
                    if inspect.iscoroutinefunction(target_tool):
                        tool_result = await target_tool(**tool_args)
                    else:
                        tool_result = target_tool(**tool_args)

                    # --- Context Saving ---
                    # Check if the tool returned context to be saved for future turns.
                    if (
                        isinstance(tool_result, dict)
                        and "context_to_save" in tool_result
                    ):
                        context_to_save = tool_result.get("context_to_save")
                        if context_to_save:
                            logger.info(f"Saving context to session: {context_to_save}")
                            session.state.update(context_to_save)
                            await self.runner.session_service.update_session(session)
                        # The actual result for the LLM is the 'artifact' part.
                        tool_result = tool_result.get(
                            "artifact",
                            {"status": "Context saved, no artifact returned."},
                        )

                    # The tool result is always wrapped in a FunctionResponse and sent back to the agent.
                    # The event loop will inspect this response to see if it's a final artifact.
                    tool_outputs.append(
                        types.Part(
                            function_response=types.FunctionResponse(
                                name=tool_name, response=tool_result
                            )
                        )
                    )
                except x402PaymentRequiredException:
                    # This special exception must propagate up to the x402ServerExecutor.
                    raise
                except Exception as e:
                    # Any other tool error should be reported back to the LLM.
                    logger.error(
                        f"Tool '{tool_name}' execution failed: {e}", exc_info=True
                    )
                    tool_outputs.append(
                        types.Part(
                            function_response=types.FunctionResponse(
                                name=tool_name, response={"error": str(e)}
                            )
                        )
                    )

            # Prepare the next message to send to the agent, containing the tool results.
            current_message = types.Content(parts=tool_outputs, role="tool")

    async def _preprocess_and_find_payment_payload(
        self, context: RequestContext
    ) -> str | None:
        """
        Inspects incoming message parts to find a JSON string containing an
        x402_payment_object and extracts the object's value.
        """
        for part in context.message.parts:
            part = part.root
            # The payload arrives as a TextPart containing a JSON string
            if isinstance(part, DataPart):
                try:
                    # Attempt to parse the text as JSON
                    data = part.data
                    # Check if the parsed dict contains our key
                    if isinstance(data, dict) and "x402_payment_object" in data:
                        # Return the base64 encoded payload string
                        return data["x402_payment_object"]
                except (json.JSONDecodeError, TypeError):
                    # Not a valid JSON string or not a dict, so we ignore it
                    continue
        return None

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ):
        task_updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        session = await self._upsert_session(context.context_id)

        # Check if the x402 wrapper has verified a payment by looking at the task metadata.
        if context.current_task and context.current_task.metadata.get(
            "x402_payment_verified", False
        ):
            # If payment is verified, write structured data to the session state.
            # The agent's `before_agent_callback` will read this.
            product_name = (
                context.current_task.status.message.metadata.get(
                    "x402.payment.required", {}
                )
                .get("accepts", [{}])[0]
                .get("extra", {})
                .get("name", "the item")
            )
            session.state["payment_verified_data"] = {
                "product": product_name,
                "status": "SUCCESS",
            }
            # We still need to send a message to trigger the agent's turn.
            # The content doesn't matter as much, as the callback will intercept it.
            user_message = types.UserContent(
                parts=[types.Part(text="Payment verified. Please proceed.")]
            )
            # We must re-fetch the session here to ensure the state changes
            # from the x402 executor are reflected before the agent's
            # `before_agent_callback` is invoked.
            session = await self._upsert_session(session.id)
        else:
            # No payment verification; process the original user message.
            user_message = types.UserContent(
                parts=convert_a2a_parts_to_genai(context.message.parts)
            )

        await self._process_request(
            user_message,
            session.id,
            task_updater,
        )

        logger.debug(f"[{self._card.name}] execute exiting")

    async def cancel(self, context: RequestContext, event_queue: EventQueue):
        # Ideally: kill any ongoing tasks.
        raise ServerError(error=UnsupportedOperationError())

    async def _upsert_session(self, session_id: str):
        session = await self.runner.session_service.get_session(
            app_name=self.runner.app_name, user_id="self", session_id=session_id
        )
        if session:
            return session
        return await self.runner.session_service.create_session(
            app_name=self.runner.app_name, user_id="self", session_id=session_id
        )


def convert_a2a_parts_to_genai(parts: list[Part]) -> list[types.Part]:
    """Convert a list of A2A Part types into a list of Google Gen AI Part types."""
    return [convert_a2a_part_to_genai(part) for part in parts]


def convert_a2a_part_to_genai(part: Part) -> types.Part:
    """Convert a single A2A Part type into a Google Gen AI Part type."""
    part = part.root
    if isinstance(part, TextPart):
        return types.Part(text=part.text)
    if isinstance(part, DataPart):
        json_string = json.dumps(part.data)
        return types.Part(
            text=f"Received structured data:\n```json\n{json_string}\n```"
        )
    if isinstance(part, FilePart):
        if isinstance(part.file, FileWithUri):
            return types.Part(
                file_data=types.FileData(
                    file_uri=part.file.uri, mime_type=part.file.mimeType
                )
            )
        if isinstance(part.file, FileWithBytes):
            return types.Part(
                inline_data=types.Blob(
                    data=part.file.bytes, mime_type=part.file.mimeType
                )
            )
        raise ValueError(f"Unsupported file type: {type(part.file)}")
    raise ValueError(f"Unsupported part type: {type(part)}")


def convert_genai_parts_to_a2a(parts: list[types.Part]) -> list[Part]:
    """Convert a list of Google Gen AI Part types into a list of A2A Part types."""
    return [
        convert_genai_part_to_a2a(part)
        for part in parts
        if (part.text or part.file_data or part.inline_data or part.function_response)
    ]


def convert_genai_part_to_a2a(part: types.Part) -> Part:
    """Convert a single Google Gen AI Part type into an A2A Part type."""
    if part.text:
        return Part(root=TextPart(text=part.text))
    if part.file_data:
        return Part(
            root=FilePart(
                file=FileWithUri(
                    uri=part.file_data.file_uri,
                    mimeType=part.file_data.mime_type,
                )
            )
        )
    if part.inline_data:
        return Part(
            root=FilePart(
                file=FileWithBytes(
                    bytes=part.inline_data.data,
                    mimeType=part.inline_data.mime_type,
                )
            )
        )
    if part.function_response:
        if "artifact" in part.function_response.response:
            logger.debug("found a generated artifact ")
            return Part(root=DataPart(data=part.function_response.response["artifact"]))
        return Part(root=DataPart(data=part.function_response.response))
    raise ValueError(f"Unsupported part type: {part}")
