import pytest
from unittest.mock import AsyncMock, MagicMock

from a2a.types import Task, Message, TaskState, TaskStatus, TextPart
from a2a_x402.executors.server import X402ServerExecutor
from a2a_x402.types import (
    PaymentStatus,
    X402Metadata,
    x402PaymentRequiredResponse,
    PaymentPayload,
    PaymentRequirements,
    VerifyResponse,
    SettleResponse,
)
from a2a_x402.core.utils import X402Utils

# --- Fixtures ---

@pytest.fixture
def utils():
    """Returns an instance of X402Utils."""
    return X402Utils()

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

# --- Tests for X402Utils ---

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
    assert updated_task.status.message.metadata[X402Metadata.STATUS_KEY] == PaymentStatus.PAYMENT_REQUIRED.value
    assert updated_task.status.message.metadata[X402Metadata.REQUIRED_KEY] is not None

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
            X402Metadata.PAYLOAD_KEY: sample_payment_payload.model_dump(by_alias=True)
        }
    )

    extracted_payload = utils.get_payment_payload_from_message(message)
    assert isinstance(extracted_payload, PaymentPayload)
    assert extracted_payload.scheme == "exact"
    assert extracted_payload.payload.signature == "0xabc"

# --- Tests for X402ServerExecutor ---

class MockConcreteExecutor(X402ServerExecutor):
    """A concrete implementation of the abstract X402ServerExecutor for testing."""
    async def verify_payment(self, payload, requirements):
        return VerifyResponse(is_valid=True, payer="0x789")

    async def settle_payment(self, payload, requirements):
        return SettleResponse(success=True)

@pytest.mark.asyncio
async def test_server_executor_payment_flow():
    """
    Tests that the X402ServerExecutor correctly calls verify and settle
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
            X402Metadata.STATUS_KEY: PaymentStatus.PAYMENT_SUBMITTED.value,
            X402Metadata.PAYLOAD_KEY: payment_payload.model_dump(by_alias=True)
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
