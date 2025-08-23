"""Unit tests for a2a_x402.types.messages module."""

import pytest
from pydantic import ValidationError
from a2a_x402.types.messages import (
    X402MessageType,
    x402SettleResponse
)


class TestX402MessageType:
    """Test X402MessageType enum."""
    
    def test_message_type_values(self):
        """Test that message type values are correct."""
        assert X402MessageType.PAYMENT_REQUIRED == "x402.payment.required"
        assert X402MessageType.PAYMENT_PAYLOAD == "x402.payment.payload"
        assert X402MessageType.PAYMENT_SETTLED == "x402.payment.settled"
    
    def test_all_message_types_defined(self):
        """Test that all expected message types are defined."""
        all_types = list(X402MessageType)
        assert len(all_types) == 3
        
        expected_types = [
            "x402.payment.required",
            "x402.payment.payload",
            "x402.payment.settled"
        ]
        
        actual_types = [msg_type.value for msg_type in all_types]
        for expected in expected_types:
            assert expected in actual_types


class TestX402SettleResponse:
    """Test x402SettleResponse data structure."""
    
    def test_settle_response_creation_success(self):
        """Test creating successful x402SettleResponse."""
        response = x402SettleResponse(
            success=True,
            transaction="0xtxhash123",
            network="base",
            payer="0xclient456"
        )
        
        assert response.success is True
        assert response.transaction == "0xtxhash123"
        assert response.network == "base"
        assert response.payer == "0xclient456"
        assert response.error_reason is None
    
    def test_settle_response_creation_failure(self):
        """Test creating failed x402SettleResponse."""
        response = x402SettleResponse(
            success=False,
            network="base",
            error_reason="Insufficient funds"
        )
        
        assert response.success is False
        assert response.network == "base"
        assert response.error_reason == "Insufficient funds"
        assert response.transaction is None
        assert response.payer is None
    
    def test_settle_response_required_fields(self):
        """Test that required fields are enforced."""
        # success and network are required
        with pytest.raises(ValidationError):
            x402SettleResponse()
        
        with pytest.raises(ValidationError):
            x402SettleResponse(success=True)  # Missing network
        
        # This should work
        response = x402SettleResponse(success=True, network="base")
        assert response.success is True
        assert response.network == "base"
    
    def test_settle_response_serialization(self, sample_settle_response):
        """Test that x402SettleResponse serializes correctly with aliases."""
        data = sample_settle_response.model_dump(by_alias=True)
        
        assert "success" in data
        assert "network" in data
        assert "transaction" in data
        assert "payer" in data
        
        # Test with error response to cover the error_reason alias
        error_response = x402SettleResponse(
            success=False,
            network="base",
            error_reason="Test error"
        )
        error_data = error_response.model_dump(by_alias=True)
        
        # These lines were missing coverage
        assert "errorReason" in error_data
        assert "error_reason" not in error_data
    

