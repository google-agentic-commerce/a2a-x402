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

import os
import uuid

from a2a.types import (
    Artifact,
    Message,
    Task,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)

# Local imports
from ._remote_agent_connection import (
    TaskCallbackArg
)


class TaskStore:
    """A class that manages task state.

    This class is responsible for processing task updates, managing task state,
    and handling artifact events. It maintains the state of tasks and their
    associated messages.
    """

    def __init__(self, api_key: str = "", uses_vertex_ai: bool = False):
        self._tasks: list[Task] = []
        self._artifact_chunks: dict[str, list[Artifact]] = {}
        self._task_map: dict[str, str] = {}

        # Set environment variables based on auth method
        if uses_vertex_ai:
            os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "TRUE"
        elif api_key:
            # Use API key authentication
            os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "FALSE"
            os.environ["GOOGLE_API_KEY"] = api_key

    def _add_task(self, task: Task):
        self._tasks.append(task)

    def _update_task(self, task: Task):
        for i, t in enumerate(self._tasks):
            if t.id == task.id:
                self._tasks[i] = task
                return

    def update_task(self, task: TaskCallbackArg):
        if isinstance(task, TaskStatusUpdateEvent):
            current_task = self._add_or_get_task(task)
            current_task.status = task.status
            self._attach_message_to_task(task.status.message, current_task.id)
            self._insert_message_history(current_task, task.status.message)
            self._update_task(current_task)
            return current_task
        elif isinstance(task, TaskArtifactUpdateEvent):
            # This is where the streaming updates are handled.
            # We'll print the content of any text parts to the console.
            for part in task.artifact.parts:
                if part.root and hasattr(part.root, "text"):
                    print(part.root.text)

            current_task = self._add_or_get_task(task)
            self._process_artifact_event(current_task, task)
            self._update_task(current_task)
            return current_task
        # Otherwise this is a Task, either new or updated
        elif not any(filter(lambda x: x and x.id == task.id, self._tasks)):
            self._attach_message_to_task(task.status.message, task.id)
            self._add_task(task)
            return task
        else:
            self._attach_message_to_task(task.status.message, task.id)
            self._update_task(task)
            return task

    def _attach_message_to_task(self, message: Message | None, task_id: str):
        if message:
            self._task_map[message.message_id] = task_id

    def _insert_message_history(self, task: Task, message: Message | None):
        if not message:
            return
        if task.history is None:
            task.history = []
        message_id = message.message_id
        if not message_id:
            return
        if task.history and (
            task.status.message
            and task.status.message.message_id not in [x.message_id for x in task.history]
        ):
            task.history.append(task.status.message)
        elif not task.history and task.status.message:
            task.history = [task.status.message]
        else:
            print(
                "Message id already in history",
                task.status.message.messageId if task.status.message else "",
                task.history,
            )

    def _add_or_get_task(self, event: TaskCallbackArg):
        task_id = None
        if isinstance(event, Message):
            task_id = event.task_id
        elif isinstance(event, Task):
            task_id = event.id
        else:
            task_id = event.task_id
        if not task_id:
            task_id = str(uuid.uuid4())
        current_task = next(filter(lambda x: x.id == task_id, self._tasks), None)
        if not current_task:
            context_id = event.context_id
            current_task = Task(
                id=task_id,
                # initialize with submitted
                status=TaskStatus(state=TaskState.submitted),
                artifacts=[],
                contextId=context_id,
            )
            self._add_task(current_task)
            return current_task
        return current_task

    def _process_artifact_event(
        self, current_task: Task, task_update_event: TaskArtifactUpdateEvent
    ):
        artifact = task_update_event.artifact
        if not task_update_event.append:
            # received the first chunk or entire payload for an artifact
            if task_update_event.last_chunk is None or task_update_event.last_chunk:
                # last_chunk bit is missing or is set to true, so this is the entire payload
                # add this to artifacts
                if not current_task.artifacts:
                    current_task.artifacts = []
                current_task.artifacts.append(artifact)
            else:
                # this is a chunk of an artifact, stash it in temp store for assemling
                if artifact.artifactId not in self._artifact_chunks:
                    self._artifact_chunks[artifact.artifactId] = []
                self._artifact_chunks[artifact.artifactId].append(artifact)
        else:
            # we received an append chunk, add to the existing temp artifact
            current_temp_artifact = self._artifact_chunks[artifact.artifactId][-1]
            # TODO handle if current_temp_artifact is missing
            current_temp_artifact.parts.extend(artifact.parts)
            if task_update_event.last_chunk:
                if current_task.artifacts:
                    current_task.artifacts.append(current_temp_artifact)
                else:
                    current_task.artifacts = [current_temp_artifact]
                del self._artifact_chunks[artifact.artifactId][-1]
