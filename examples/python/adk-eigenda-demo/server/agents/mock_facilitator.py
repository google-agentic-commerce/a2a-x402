import logging
from typing import override

from x402_a2a.types import (
    ExactPaymentPayload,
    PaymentPayload,
    PaymentRequirements,
    SettleResponse,
    VerifyResponse,
)
from x402_a2a import FacilitatorClient


class MockFacilitator(FacilitatorClient):
    """
    A mock facilitator that can be swapped in for testing.
    It bypasses any real network calls and allows for predictable responses.
    """

    def __init__(self, is_valid: bool = True, is_settled: bool = True):
        self._is_valid = is_valid
        self._is_settled = is_settled

    @override
    async def verify(
        self, payload: PaymentPayload, requirements: PaymentRequirements
    ) -> VerifyResponse:
        """Mocks the verification step."""
        logging.info("--- MOCK FACILITATOR: VERIFY ---")
        logging.info(f"Received payload:\n{payload.model_dump_json(indent=2)}")

        payer = None
        # The top-level object is PaymentPayload, the nested is ExactPaymentPayload
        if isinstance(payload.payload, ExactPaymentPayload):
            payer = payload.payload.authorization.from_
        else:
            raise TypeError(f"Unsupported payload type: {type(payload.payload)}")

        if self._is_valid:
            return VerifyResponse(is_valid=True, payer=payer)
        return VerifyResponse(is_valid=False, invalid_reason="mock_invalid_payload")

    @override
    async def settle(
        self, payload: PaymentPayload, requirements: PaymentRequirements
    ) -> SettleResponse:
        """Mocks the settlement step."""
        logging.info("--- MOCK FACILITATOR: SETTLE ---")
        if self._is_settled:
            return SettleResponse(success=True, network="mock-network")
        return SettleResponse(success=False, error_reason="mock_settlement_failed")
