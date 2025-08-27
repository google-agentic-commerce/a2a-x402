"""Unit tests for a2a_x402.types.messages module."""

from a2a_x402.types import (
    X402MessageType,
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

