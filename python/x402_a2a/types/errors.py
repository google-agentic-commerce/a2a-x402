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
"""Protocol error types and error code mapping."""

from typing import List, Union, Optional, TYPE_CHECKING
from x402.types import PaymentRequirements, TokenAmount

if TYPE_CHECKING:
    from payments_py.x402 import X402PaymentRequired


class x402Error(Exception):
    """Base error for x402 protocol."""

    pass


class MessageError(x402Error):
    """Message validation errors."""

    pass


class ValidationError(x402Error):
    """Payment validation errors."""

    pass


class PaymentError(x402Error):
    """Payment processing errors."""

    pass


class StateError(x402Error):
    """State transition errors."""

    pass


class x402PaymentRequiredException(x402Error):
    """Exception thrown by delegate agents to request payment.

    Uses X402PaymentRequired with nvm:erc4337 scheme in accepts array.

    Example:
        from x402_a2a.types import x402PaymentRequiredException
        from payments_py.x402 import X402PaymentRequired, X402Resource, X402Scheme, X402SchemeExtra

        payment_required = X402PaymentRequired(
            x402_version=2,
            resource=X402Resource(url="/product"),
            accepts=[
                X402Scheme(
                    scheme="nvm:erc4337",
                    network="eip155:84532",
                    plan_id="...",
                    extra=X402SchemeExtra(agent_id="...")
                )
            ],
            extensions={}
        )

        raise x402PaymentRequiredException(
            "Premium feature requires payment",
            payment_required=payment_required
        )
    """

    def __init__(
        self,
        message: str,
        payment_required: Optional["X402PaymentRequired"] = None,
        error_code: Optional[str] = None,
    ):
        """Initialize payment required exception.

        Args:
            message: Human-readable error message
            payment_required: X402PaymentRequired with nvm:erc4337 scheme
            error_code: Optional x402 error code for the failure
        """
        super().__init__(message)

        self.payment_required = payment_required
        self.version = 2
        self.error_code = error_code


class x402ErrorCode:
    """Standard error codes from spec Section 8.1."""

    INSUFFICIENT_FUNDS = "INSUFFICIENT_FUNDS"
    INVALID_SIGNATURE = "INVALID_SIGNATURE"
    EXPIRED_PAYMENT = "EXPIRED_PAYMENT"
    DUPLICATE_NONCE = "DUPLICATE_NONCE"
    NETWORK_MISMATCH = "NETWORK_MISMATCH"
    INVALID_AMOUNT = "INVALID_AMOUNT"
    SETTLEMENT_FAILED = "SETTLEMENT_FAILED"

    @classmethod
    def get_all_codes(cls) -> list[str]:
        """Returns all defined error codes."""
        return [
            cls.INSUFFICIENT_FUNDS,
            cls.INVALID_SIGNATURE,
            cls.EXPIRED_PAYMENT,
            cls.DUPLICATE_NONCE,
            cls.NETWORK_MISMATCH,
            cls.INVALID_AMOUNT,
            cls.SETTLEMENT_FAILED,
        ]


def map_error_to_code(error: Exception) -> str:
    """Maps implementation errors to spec error codes."""
    error_mapping = {
        ValidationError: x402ErrorCode.INVALID_SIGNATURE,
        PaymentError: x402ErrorCode.SETTLEMENT_FAILED,
        # Add more mappings as needed
    }
    return error_mapping.get(type(error), "UNKNOWN_ERROR")
