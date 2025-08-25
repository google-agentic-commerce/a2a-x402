import asyncio
import json
import logging
from collections import namedtuple
from collections.abc import AsyncGenerator
from urllib.parse import parse_qs, urlparse

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
from a2a.utils.message import new_agent_text_message
from google.adk import Runner
from google.adk.auth import AuthConfig
from google.adk.events import Event
from google.genai import types

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

ADKAuthDetails = namedtuple(
    "ADKAuthDetails",
    ["state", "uri", "future", "auth_config", "auth_request_function_call_id"],
)

# 1 minute timeout to keep the demo moving.
auth_receive_timeout_seconds = 60


class ADKAgentExecutor(AgentExecutor):
    """An AgentExecutor that runs an ADK-based Agent."""

    _awaiting_auth: dict[str, asyncio.Future]

    def __init__(self, runner: Runner, card: AgentCard):
        self.runner = runner
        self._card = card
        self._awaiting_auth = {}
        self._running_sessions = {}

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
        """Process a request using the ADK agent.

        Args:
            new_message: The message to process
            session_id: Session ID
            task_updater: Task updater for streaming responses
        """
        session = await self._upsert_session(session_id)
        session_id = session.id
        auth_details = None

        print("[adk_executor] Starting request processing")
        print(f"[adk_executor] Message: {new_message}")
        print(f"[adk_executor] Session: {session}")

        async for event in self._run_agent(session_id, new_message):
            print(f"[adk_executor] Processing event: {event}")
            # This only handles effectively two cases:
            # 1. The agent was able to run to completion.
            # 2. The function call required authorization.
            if auth_request_function_call := get_auth_request_function_call(event):
                print("[adk_executor] Got auth request")
                # Gather details, then suspend.
                auth_details = self._prepare_auth_request(auth_request_function_call)

                task_updater.update_status(
                    TaskState.auth_required,
                    message=new_agent_text_message(
                        f"Authorization is required to continue. Visit {auth_details.uri}"
                    ),
                )
                # Break out of event handling loop -- no more work will be done until the authorization
                # is received.
                break

            if event.is_final_response():
                print("[adk_executor] Got final response")
                parts = []
                if event.content and event.content.parts:
                    parts = convert_genai_parts_to_a2a(event.content.parts)
                    print(f"[adk_executor] Converted parts: {parts}")

                if parts:
                    await task_updater.add_artifact(parts)
                    print("[adk_executor] Added artifact")
                
                await task_updater.complete()
                print("[adk_executor] Completed task")
                break

            if not event.get_function_calls():
                print("[adk_executor] Updating status with message")
                task_updater.update_status(
                    TaskState.working,
                    message=task_updater.new_agent_message(
                        convert_genai_parts_to_a2a(event.content.parts),
                    ),
                )
            else:
                print("[adk_executor] Processing function calls")
                # Execute each function call and continue processing
                for function_call in event.get_function_calls():
                    try:
                        print(f"[adk_executor] Processing function call: {function_call}")
                        # Find the tool by name
                        tool = None
                        for t in self.runner.agent.tools:
                            if hasattr(t, '__name__') and t.__name__ == function_call.name:
                                tool = t
                                break
                        
                        if tool:
                            print(f"[adk_executor] Found tool: {tool.__name__}")
                            # Execute the tool with the provided arguments
                            result = await tool(**function_call.args)
                            print(f"[adk_executor] Tool result: {result}")
                            
                            # For merchant agent's get_product_details_and_payment_info, return structured data directly
                            if function_call.name == 'get_product_details_and_payment_info' and isinstance(result, dict) and 'payment_requirements' in result:
                                print("[adk_executor] Creating DataPart for product details")
                                # Create a DataPart with the payment requirements
                                data_part = Part(root=DataPart(data=result))
                                print(f"[adk_executor] Created DataPart: {data_part}")
                                await task_updater.add_artifact([data_part])
                                print("[adk_executor] Added artifact")
                                await task_updater.complete()
                                print("[adk_executor] Completed task")
                                return
                            
                            # Create a function response
                            function_response = types.FunctionResponse(
                                id=function_call.id,
                                name=function_call.name,
                                response=result
                            )
                            print(f"[adk_executor] Created function response: {function_response}")
                            
                            # Continue processing with the function response
                            response_content = types.UserContent(
                                parts=[types.Part(function_response=function_response)]
                            )
                            print(f"[adk_executor] Created response content: {response_content}")
                            
                            # Process the response in a new iteration
                            async for response_event in self._run_agent(session_id, response_content):
                                print(f"[adk_executor] Processing response event: {response_event}")
                                if response_event.is_final_response():
                                    parts = []
                                    if response_event.content and response_event.content.parts:
                                        parts = convert_genai_parts_to_a2a(response_event.content.parts)
                                        print(f"[adk_executor] Converted response parts: {parts}")

                                    if parts:
                                        await task_updater.add_artifact(parts)
                                        print("[adk_executor] Added response artifact")
                                    
                                    await task_updater.complete()
                                    print("[adk_executor] Completed response task")
                                    return
                        else:
                            print(f"[adk_executor] Tool not found: {function_call.name}")
                            logger.error("Tool not found: %s", function_call.name)
                    except Exception as e:
                        print(f"[adk_executor] Error executing function call: {e}")
                        logger.error("Error executing function call %s: %s", function_call.name, e)
                        # Continue with other function calls if any

        if auth_details:
            print("[adk_executor] Completing auth processing")
            # After auth is received, we can continue processing this request.
            self._complete_auth_processing(session_id, auth_details, task_updater)

    async def _preprocess_and_find_payment_payload(self, context: RequestContext) -> tuple[str | None, dict | None]:
        """
        Inspects incoming message parts to find a JSON string containing an
        x402_payment_object and original_payment_requirements, extracting both values.
        """
        for part in context.message.parts:
            part = part.root
            # The payload arrives as a TextPart containing a JSON string
            if isinstance(part, DataPart):
                try:
                    # Attempt to parse the text as JSON
                    data = part.data
                    # Check if the parsed dict contains our key
                    if isinstance(data, dict) and "x_payment_header" in data:
                        # Return both the base64 encoded payload string and original requirements
                        payment_payload = data["x_payment_header"]
                        original_requirements = data.get("original_payment_requirements")
                        return payment_payload, original_requirements
                except (json.JSONDecodeError, TypeError):
                    continue
        return None, None

    def _prepare_auth_request(
        self, auth_request_function_call: types.FunctionCall
    ) -> ADKAuthDetails:
        # Following ADK's authentication documentation:
        # https://google.github.io/adk-docs/tools/authentication/#2-handling-the-interactive-oauthoidc-flow-client-side
        if not (auth_request_function_call_id := auth_request_function_call.id):
            raise ValueError(
                f"Cannot get function call id from function call: {auth_request_function_call}"
            )
        auth_config = get_auth_config(auth_request_function_call)
        if not (auth_config and auth_request_function_call_id):
            raise ValueError(
                f"Cannot get auth config from function call: {auth_request_function_call}"
            )
        oauth2_config = auth_config.exchanged_auth_credential.oauth2
        base_auth_uri = oauth2_config.auth_uri
        if not base_auth_uri:
            raise ValueError(f"Cannot get auth uri from auth config: {auth_config}")
        redirect_uri = f"{self._card.url}authenticate"
        oauth2_config.redirect_uri = redirect_uri
        parsed_auth_uri = urlparse(base_auth_uri)
        query_params_dict = parse_qs(parsed_auth_uri.query)
        state_token = query_params_dict["state"][0]
        future = asyncio.get_running_loop().create_future()
        self._awaiting_auth[state_token] = future
        auth_request_uri = base_auth_uri + f"&redirect_uri={redirect_uri}"
        return ADKAuthDetails(
            state=state_token,
            uri=auth_request_uri,
            future=future,
            auth_config=auth_config,
            auth_request_function_call_id=auth_request_function_call_id,
        )

    async def _complete_auth_processing(
        self,
        session_id: str,
        auth_details: ADKAuthDetails,
        task_updater: TaskUpdater,
    ) -> None:

        try:
            auth_uri = await asyncio.wait_for(
                auth_details.future, timeout=auth_receive_timeout_seconds
            )
        except TimeoutError:
            await task_updater.update_status(
                TaskState.failed,
                message=new_agent_text_message(
                    "Timed out waiting for authorization.",
                    context_id=session_id,
                ),
            )
            return

        await task_updater.update_status(
            TaskState.working,
            message=new_agent_text_message(
                "Auth received, continuing...", context_id=session_id
            ),
        )
        del self._awaiting_auth[auth_details.state]
        oauth2_config = auth_details.auth_config.exchanged_auth_credential.oauth2
        oauth2_config.auth_response_uri = auth_uri
        auth_content = types.UserContent(
            parts=[
                types.Part(
                    function_response=types.FunctionResponse(
                        id=auth_details.auth_request_function_call_id,
                        name="adk_request_credential",
                        response=auth_details.auth_config.model_dump(),
                    ),
                )
            ]
        )
        self._process_request(auth_content, session_id, task_updater)

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ):
        # Run the agent until either complete or the task is suspended.
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        session = await self._upsert_session(context.context_id)
        payment_payload_str, original_requirements = await self._preprocess_and_find_payment_payload(context)


        if payment_payload_str and not 'payment_state' in session.state:
            # STATE: Awaiting Payment & Payload Received
            # Bypass the LLM and process the payment directly.
            await updater.start_work()
            session.state['payment_state'] = 'PAYLOAD_FOUND'
            
            result = await self.runner.agent.tools[1](payment_payload_str, original_requirements)
            
            if "error" in result:
                summary_for_llm = f"Payment processing failed: {result['error']}. Please inform the user."
            else:
                summary_for_llm = f"Payment was successful. Confirmation: {json.dumps(result)}. Please thank the user and confirm their purchase. No more actions are required."
            
            await self._process_request(types.UserContent(parts=[types.Part(text=summary_for_llm)]), session.id, updater)
        
        else:
            # Immediately notify that the task is submitted.
            if not context.current_task:
                await updater.submit()
            await updater.start_work()
            await self._process_request(
                types.UserContent(
                    parts=convert_a2a_parts_to_genai(context.message.parts),
                ),
                context.context_id,
                updater,
            )


    async def cancel(self, context: RequestContext, event_queue: EventQueue):
        # Ideally: kill any ongoing tasks.
        raise ServerError(error=UnsupportedOperationError())

    async def on_auth_callback(self, state: str, uri: str):
        self._awaiting_auth[state].set_result(uri)

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
        return types.Part(text=f"Received structured data:\n```json\n{json_string}\n```")
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
        return Part(
            root=DataPart(data=part.function_response.response)
        )
    raise ValueError(f"Unsupported part type: {part}")


def get_auth_request_function_call(event: Event) -> types.FunctionCall:
    """Get the special auth request function call from the event."""
    if not (event.content and event.content.parts):
        return None
    for part in event.content.parts:
        if (
            part
            and part.function_call
            and part.function_call.name == "adk_request_credential"
            and event.long_running_tool_ids
            and part.function_call.id in event.long_running_tool_ids
        ):
            return part.function_call
    return None


def get_auth_config(
    auth_request_function_call: types.FunctionCall,
) -> AuthConfig:
    """Extracts the AuthConfig object from the arguments of the auth request function call."""
    if not auth_request_function_call.args or not (
        auth_config := auth_request_function_call.args.get("auth_config")
    ):
        raise ValueError(
            f"Cannot get auth config from function call: {auth_request_function_call}"
        )
    return AuthConfig.model_validate(auth_config)
