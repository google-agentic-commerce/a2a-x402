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
import logging
from typing import override

from x402_a2a.types import (
    ExactPaymentPayload,
    PaymentPayload,
    PaymentRequirements,
    SettleResponse,
    VerifyResponse,
    SparkPaymentType,
)
from x402_a2a import FacilitatorClient, get_spark_payment_payload


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
        # The top-level object is PaymentPayload, the nested is scheme-specific
        if isinstance(payload.payload, ExactPaymentPayload):
            payer = payload.payload.authorization.from_
        elif payload.network.lower() == "spark":
            spark_payload = get_spark_payment_payload(payload)
            if spark_payload.payment_type == SparkPaymentType.SPARK:
                payer = spark_payload.transfer_id
            elif spark_payload.payment_type == SparkPaymentType.LIGHTNING:
                payer = spark_payload.preimage
            else:
                payer = spark_payload.txid
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
            transaction = None
            if payload.network.lower() == "spark":
                spark_payload = get_spark_payment_payload(payload)
                transaction = (
                    spark_payload.transfer_id
                    or spark_payload.preimage
                    or spark_payload.txid
                )
            return SettleResponse(
                success=True,
                network=payload.network,
                transaction=transaction
            )

        return SettleResponse(
            success=False,
            network=payload.network,
            error_reason="mock_settlement_failed"
        )
