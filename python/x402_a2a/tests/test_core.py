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
import pytest
from unittest.mock import AsyncMock, MagicMock

from a2a.types import Task, Message, TaskState, TaskStatus, TextPart
from x402_a2a.executors.server import x402ServerExecutor
from x402_a2a.types import (
    PaymentStatus,
    x402Metadata,
    x402PaymentRequiredResponse,
    PaymentPayload,
    PaymentRequirements,
    VerifyResponse,
    SettleResponse,
    ExactSparkPaymentPayload,
    SparkPaymentType,
)
from x402_a2a.core.utils import x402Utils, create_payment_submission_message
from x402_a2a.core.protocol import verify_payment, settle_payment
from x402_a2a.core.wallet import (
    create_spark_payment_payload,
    encode_spark_payment_header,
    decode_spark_payment_header,
    get_spark_payment_payload,
    dump_payment_payload,
)


def _spark_hex(seed: int) -> str:
    """Return a deterministic 32-byte hex string for Spark fixtures."""

    return bytes([seed % 256] * 32).hex()

# --- Fixtures ---

@pytest.fixture
def utils():
    """Returns an instance of x402Utils."""
    return x402Utils()

@pytest.fixture
def sample_task():
    """Returns a sample Task object."""
    return Task(id="task-123", contextId="context-456", status=TaskStatus(state=TaskState.working))

@pytest.fixture
def sample_payment_requirements():
    """Returns a sample PaymentRequirements object."""
    return PaymentRequirements(
        scheme="exact",
        network="base-sepolia",
        pay_to="0x123",
        max_amount_required="100",
        asset="0x456",
        description="Test Payment",
        resource="/test",
        mime_type="application/json",
        max_timeout_seconds=600,
    )

@pytest.fixture
def sample_payment_payload():
    """Returns a sample PaymentPayload object."""
    return PaymentPayload(
        x402_version=1,
        scheme="exact",
        network="base-sepolia",
        payload={
            "signature": "0xabc",
            "authorization": {
                "from": "0x789",
                "to": "0x123",
                "value": "100",
                "valid_after": "0",
                "valid_before": "9999999999",
                "nonce": "0xdef",
            },
        },
    )

# --- Tests for x402Utils ---

def test_create_payment_required_task(utils, sample_task, sample_payment_requirements):
    """
    Tests that `create_payment_required_task` correctly updates the task's
    status and metadata.
    """
    payment_required_response = x402PaymentRequiredResponse(
        x402_version=1, accepts=[sample_payment_requirements], error="Payment is required"
    )
    
    updated_task = utils.create_payment_required_task(sample_task, payment_required_response)

    assert updated_task.status.state == TaskState.input_required
    assert updated_task.status.message.metadata[x402Metadata.STATUS_KEY] == PaymentStatus.PAYMENT_REQUIRED.value
    assert updated_task.status.message.metadata[x402Metadata.REQUIRED_KEY] is not None

def test_get_payment_payload_from_message(utils, sample_payment_payload):
    """
    Tests that `get_payment_payload_from_message` correctly parses a
    PaymentPayload from a message's metadata.
    """
    message = Message(
        messageId="msg-1",
        role="user",
        parts=[TextPart(text="test")],
        metadata={
            x402Metadata.PAYLOAD_KEY: dump_payment_payload(sample_payment_payload)
        }
    )

    extracted_payload = utils.get_payment_payload_from_message(message)
    assert isinstance(extracted_payload, PaymentPayload)
    assert extracted_payload.scheme == "exact"
    assert extracted_payload.payload.signature == "0xabc"

# --- Tests for x402ServerExecutor ---

class MockConcreteExecutor(x402ServerExecutor):
    """A concrete implementation of the abstract x402ServerExecutor for testing."""
    async def verify_payment(self, payload, requirements):
        return VerifyResponse(is_valid=True, payer="0x789")

    async def settle_payment(self, payload, requirements):
        return SettleResponse(success=True)

@pytest.mark.asyncio
async def test_server_executor_payment_flow():
    """
    Tests that the x402ServerExecutor correctly calls verify and settle
    when it receives a payment-submitted message.
    """
    delegate = AsyncMock()
    facilitator = MagicMock() # Not used directly, but required by constructor in some versions
    
    # In a real scenario, the executor would be subclassed and these methods implemented.
    # For this test, we can mock them directly on an instance.
    executor = MockConcreteExecutor(delegate=delegate, config=MagicMock())
    executor.verify_payment = AsyncMock(return_value=VerifyResponse(is_valid=True, payer="0x789"))
    executor.settle_payment = AsyncMock(return_value=SettleResponse(success=True))
    
    # Simulate the context and event queue
    context = MagicMock()
    context.task_id = "task-123"
    context.context_id = "context-456"
    event_queue = AsyncMock()

    # Create a message with a payment payload
    payment_payload = PaymentPayload(
        x402_version=1,
        scheme="exact",
        network="base-sepolia",
        payload={"signature": "0xabc", "authorization": {"from": "0x789", "to": "0x123", "value": "100", "valid_after": "0", "valid_before": "9999999999", "nonce": "0xdef"}}
    )
    context.message = Message(
        messageId="msg-1",
        role="user",
        parts=[TextPart(text="test")],
        metadata={
            x402Metadata.STATUS_KEY: PaymentStatus.PAYMENT_SUBMITTED.value,
            x402Metadata.PAYLOAD_KEY: dump_payment_payload(payment_payload)
        }
    )
    context.current_task = Task(id="task-123", contextId="context-456", status=TaskStatus(state=TaskState.working), metadata={})
    
    # Mock the internal requirement store to simulate a pending payment
    executor._payment_requirements_store[context.current_task.id] = [
        PaymentRequirements(scheme="exact", network="base-sepolia", max_amount_required="100", resource="/test", description="Test", mime_type="text/plain", pay_to="0x123", max_timeout_seconds=60, asset="0x456")
    ]

    # Execute the flow
    await executor.execute(context, event_queue)

    # Assert that the correct methods were called
    executor.verify_payment.assert_called_once()
    delegate.execute.assert_called_once()
    executor.settle_payment.assert_called_once()


@pytest.mark.unit
def test_exact_spark_payment_payload_validation():
    """Spark payload enforces transport-specific required fields."""

    spark_payload = ExactSparkPaymentPayload(
        payment_type=SparkPaymentType.SPARK,
        transfer_id="abc123"
    )
    assert spark_payload.transfer_id == "abc123"

    lightning_payload = ExactSparkPaymentPayload(
        payment_type=SparkPaymentType.LIGHTNING,
        preimage="00ff"
    )
    assert lightning_payload.preimage == "00ff"

    l1_payload = ExactSparkPaymentPayload(
        payment_type=SparkPaymentType.L1,
        txid=_spark_hex(0x42)
    )
    assert l1_payload.txid == _spark_hex(0x42)

    with pytest.raises(ValueError):
        ExactSparkPaymentPayload(payment_type=SparkPaymentType.SPARK)


@pytest.mark.unit
def test_spark_payment_header_roundtrip():
    """Encoding and decoding the Spark header preserves payload data."""

    payment_payload = create_spark_payment_payload(
        SparkPaymentType.SPARK,
        transfer_id="transfer-123"
    )

    header_value = encode_spark_payment_header(payment_payload)
    decoded_payload = decode_spark_payment_header(header_value)

    spark_payload = get_spark_payment_payload(decoded_payload)
    assert spark_payload.transfer_id == "transfer-123"

    dumped_payload = dump_payment_payload(decoded_payload)
    assert dumped_payload["payload"]["paymentType"] == "SPARK"
    assert dumped_payload["payload"]["transfer_id"] == "transfer-123"
    assert "preimage" not in dumped_payload["payload"]


@pytest.mark.unit
def test_spark_payload_preserved_in_message_metadata(utils):
    """Spark metadata dumped into messages keeps transport-specific details."""

    payment_payload = create_spark_payment_payload(
        SparkPaymentType.LIGHTNING,
        preimage=_spark_hex(0x24)
    )

    message = create_payment_submission_message("task-99", payment_payload)
    metadata = message.metadata[x402Metadata.PAYLOAD_KEY]

    assert metadata["payload"]["paymentType"] == "LIGHTNING"
    assert metadata["payload"]["preimage"] == _spark_hex(0x24)
    assert "transfer_id" not in metadata["payload"]


@pytest.mark.asyncio
async def test_facilitator_preserves_spark_payload(sample_payment_requirements):
    """Facilitator requests see Spark-specific fields during verify/settle."""

    verify_payload = create_spark_payment_payload(
        SparkPaymentType.LIGHTNING,
        preimage=_spark_hex(0x11)
    )
    settle_payload = create_spark_payment_payload(
        SparkPaymentType.SPARK,
        transfer_id="spark-transfer-001"
    )

    class RecordingFacilitator:
        def __init__(self):
            self.seen_verify = None
            self.seen_settle = None

        async def verify(self, payload, requirements):
            self.seen_verify = payload
            return VerifyResponse(is_valid=True, payer="spark")

        async def settle(self, payload, requirements):
            self.seen_settle = payload
            return SettleResponse(success=True, network=requirements.network)

    facilitator = RecordingFacilitator()

    verify_response = await verify_payment(
        verify_payload,
        sample_payment_requirements,
        facilitator_client=facilitator
    )
    assert verify_response.is_valid is True

    settle_response = await settle_payment(
        settle_payload,
        sample_payment_requirements,
        facilitator_client=facilitator
    )
    assert settle_response.success is True

    assert isinstance(facilitator.seen_verify, PaymentPayload)
    verify_dump = facilitator.seen_verify.model_dump(by_alias=True)
    assert verify_dump["payload"]["preimage"] == _spark_hex(0x11)

    assert isinstance(facilitator.seen_settle, PaymentPayload)
    settle_dump = facilitator.seen_settle.model_dump(by_alias=True)
    assert settle_dump["payload"]["transfer_id"] == "spark-transfer-001"
