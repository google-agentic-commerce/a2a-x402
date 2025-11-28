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
    from payments_py.x402.types_v2 import PaymentRequiredResponseV2


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

    Supports both v1 (PaymentRequirements) and v2 (PaymentRequiredResponseV2) formats.

    V1 Example:
        from x402_a2a.types import x402PaymentRequiredException, PaymentRequirements

        requirements = PaymentRequirements(
            plan_id="...",
            agent_id="...",
            max_amount="2",
            network="base-sepolia",
            scheme="contract"
        )
        raise x402PaymentRequiredException(
            "Premium feature requires payment",
            payment_requirements=requirements
        )

    V2 Example:
        from x402_a2a.types import (
            x402PaymentRequiredException,
            PaymentRequiredResponseV2,
            ResourceInfo,
            declare_nevermined_extension,
            NEVERMINED
        )

        extension = declare_nevermined_extension(
            plan_id="...",
            agent_id="...",
            max_amount="2"
        )
        
        payment_required_v2 = PaymentRequiredResponseV2(
            x402_version=2,
            resource=ResourceInfo(url="/product"),
            accepts=[],
            extensions={NEVERMINED: extension}
        )
        
        raise x402PaymentRequiredException(
            "Premium feature requires payment",
            payment_required_v2=payment_required_v2
        )
    """

    def __init__(
        self,
        message: str,
        payment_requirements: Optional[Union[PaymentRequirements, List[PaymentRequirements]]] = None,
        payment_required_v2: Optional["PaymentRequiredResponseV2"] = None,
        error_code: Optional[str] = None,
    ):
        """Initialize payment required exception.

        Args:
            message: Human-readable error message
            payment_requirements: V1 single requirement or list of payment options
            payment_required_v2: V2 payment required response with extensions
            error_code: Optional x402 error code for the failure
        """
        super().__init__(message)

        # V1 handling - normalize to list format for consistency
        if payment_requirements:
            if isinstance(payment_requirements, list):
                self.payment_requirements = payment_requirements
            else:
                self.payment_requirements = [payment_requirements]
        else:
            self.payment_requirements = []

        # V2 handling
        self.payment_required_v2 = payment_required_v2
        
        # Auto-detect version
        if payment_required_v2:
            self.version = 2
        else:
            self.version = 1

        self.error_code = error_code

    def get_accepts_array(self) -> List[PaymentRequirements]:
        """Get payment requirements in x402PaymentRequiredResponse.accepts format.

        Returns:
            List of PaymentRequirements for the accepts array
        """
        return self.payment_requirements

    @classmethod
    def for_service(
        cls,
        price: Union[str, int, TokenAmount],
        pay_to_address: str,
        resource: str,
        network: str = "base",
        description: str = "Payment required for this service",
        message: Optional[str] = None,
    ) -> "x402PaymentRequiredException":
        """Create payment exception for a simple service.

        Helper method for common use case of single payment requirement.

        Args:
            price: Payment amount (e.g., "$1.00", 1.00, TokenAmount)
            pay_to_address: Ethereum address to receive payment
            resource: Resource identifier (e.g., "/api/generate")
            network: Blockchain network (default: "base")
            description: Human-readable description
            message: Exception message (default: uses description)

        Returns:
            x402PaymentRequiredException with single payment requirement
        """
        # Import here to avoid circular imports
        from ..core.merchant import create_payment_requirements

        requirements = create_payment_requirements(
            price=price,
            pay_to_address=pay_to_address,
            resource=resource,
            network=network,
            description=description,
        )

        return cls(message=message or description, payment_requirements=requirements)


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
