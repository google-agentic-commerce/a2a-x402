"""Shared pytest fixtures for a2a_x402 tests."""

import pytest
from eth_account import Account
from a2a_x402.types import (
    Task,
    TaskState,
    TaskStatus,
    PaymentRequirements,
    x402PaymentRequiredResponse,
    x402SettleResponse,
    PaymentPayload,
    ExactPaymentPayload,
    EIP3009Authorization
)


@pytest.fixture
def sample_task():
    """Create a sample A2A Task for testing."""
    return Task(
        id="task-123",
        contextId="context-456",
        status=TaskStatus(state=TaskState.input_required),
        metadata={}
    )


@pytest.fixture
def sample_payment_requirements():
    """Create sample PaymentRequirements for testing."""
    return PaymentRequirements(
        scheme="exact",
        network="base",
        asset="0x833589fCD6eDb6E08f4c7C32D4f71b54bda02913",
        pay_to="0xmerchant123",
        max_amount_required="1000000",
        resource="/test-service",
        description="Test payment",
        mime_type="application/json",
        max_timeout_seconds=600
    )


@pytest.fixture
def sample_payment_required_response(sample_payment_requirements):
    """Create sample x402PaymentRequiredResponse for testing."""
    return x402PaymentRequiredResponse(
        x402_version=1,
        accepts=[sample_payment_requirements],
        error=""
    )


@pytest.fixture
def test_account():
    """Create a test Ethereum account."""
    # Use a deterministic private key for consistent testing
    private_key = "0x" + "1" * 64
    return Account.from_key(private_key)


@pytest.fixture
def sample_payment_payload():
    """Create sample PaymentPayload for testing."""
    authorization = EIP3009Authorization(
        from_="0xclient456",
        to="0xmerchant123", 
        value="1000000",
        valid_after="1640995200",
        valid_before="1640998800",
        nonce="0x" + "1" * 64
    )
    
    exact_payload = ExactPaymentPayload(
        signature="0x" + "a" * 130,
        authorization=authorization
    )
    
    return PaymentPayload(
        x402_version=1,
        scheme="exact",
        network="base",
        payload=exact_payload
    )


@pytest.fixture
def sample_settle_response():
    """Create sample x402SettleResponse for testing."""
    return x402SettleResponse(
        success=True,
        transaction="0xtxhash123",
        network="base",
        payer="0xclient456",
        error_reason=None
    )
