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
"""Extension declaration and constants for A2A x402 protocol."""

from .types.config import X402_EXTENSION_URI


def get_extension_declaration(
    description: str = "Supports x402 payments", 
    required: bool = True
) -> dict:
    """Creates extension declaration for AgentCard."""
    return {
        "uri": X402_EXTENSION_URI,
        "description": description,
        "required": required
    }

def check_extension_activation(request_headers: dict) -> bool:
    """Check if x402 extension is activated via HTTP headers."""
    extensions = request_headers.get("X-A2A-Extensions", "")
    return X402_EXTENSION_URI in extensions


def add_extension_activation_header(response_headers: dict) -> dict:
    """Echo extension URI in response header to confirm activation."""
    response_headers["X-A2A-Extensions"] = X402_EXTENSION_URI
    return response_headers
