"""Unit tests for a2a_x402.types.errors module."""

import pytest
from a2a_x402.types.errors import (
    X402Error,
    MessageError,
    ValidationError,
    PaymentError,
    StateError,
    X402ErrorCode,
    map_error_to_code
)


class TestErrorHierarchy:
    """Test error class hierarchy."""
    
    def test_base_error(self):
        """Test X402Error base exception."""
        error = X402Error("Test error")
        assert str(error) == "Test error"
        assert isinstance(error, Exception)
    
    def test_error_inheritance(self):
        """Test that all errors inherit from X402Error."""
        message_error = MessageError("Message error")
        validation_error = ValidationError("Validation error")
        payment_error = PaymentError("Payment error")
        state_error = StateError("State error")
        
        assert isinstance(message_error, X402Error)
        assert isinstance(validation_error, X402Error)
        assert isinstance(payment_error, X402Error)
        assert isinstance(state_error, X402Error)
    
    def test_error_can_be_raised(self):
        """Test that errors can be raised and caught."""
        with pytest.raises(X402Error):
            raise X402Error("Test")
        
        with pytest.raises(ValidationError):
            raise ValidationError("Validation failed")
        
        with pytest.raises(PaymentError):
            raise PaymentError("Payment failed")


class TestX402ErrorCode:
    """Test X402ErrorCode constants."""
    
    def test_error_codes_match_spec(self):
        """Test that error codes match spec Section 8.1 exactly."""
        assert X402ErrorCode.INSUFFICIENT_FUNDS == "INSUFFICIENT_FUNDS"
        assert X402ErrorCode.INVALID_SIGNATURE == "INVALID_SIGNATURE"
        assert X402ErrorCode.EXPIRED_PAYMENT == "EXPIRED_PAYMENT"
        assert X402ErrorCode.DUPLICATE_NONCE == "DUPLICATE_NONCE"
        assert X402ErrorCode.NETWORK_MISMATCH == "NETWORK_MISMATCH"
        assert X402ErrorCode.INVALID_AMOUNT == "INVALID_AMOUNT"
        assert X402ErrorCode.SETTLEMENT_FAILED == "SETTLEMENT_FAILED"
    
    def test_all_error_codes_defined(self):
        """Test that all 7 spec-required error codes are defined."""
        all_codes = X402ErrorCode.get_all_codes()
        assert len(all_codes) == 7
        
        expected_codes = [
            "INSUFFICIENT_FUNDS",
            "INVALID_SIGNATURE",
            "EXPIRED_PAYMENT",
            "DUPLICATE_NONCE",
            "NETWORK_MISMATCH",
            "INVALID_AMOUNT",
            "SETTLEMENT_FAILED"
        ]
        
        for expected in expected_codes:
            assert expected in all_codes
    
    def test_get_all_codes_returns_list(self):
        """Test that get_all_codes returns a list of strings."""
        codes = X402ErrorCode.get_all_codes()
        assert isinstance(codes, list)
        assert all(isinstance(code, str) for code in codes)


class TestErrorMapping:
    """Test error mapping functionality."""
    
    def test_map_error_to_code_known_errors(self):
        """Test mapping of known error types."""
        validation_error = ValidationError("Invalid signature")
        payment_error = PaymentError("Settlement failed")
        
        assert map_error_to_code(validation_error) == X402ErrorCode.INVALID_SIGNATURE
        assert map_error_to_code(payment_error) == X402ErrorCode.SETTLEMENT_FAILED
    
    def test_map_error_to_code_unknown_error(self):
        """Test mapping of unknown error types."""
        unknown_error = RuntimeError("Unknown error")
        assert map_error_to_code(unknown_error) == "UNKNOWN_ERROR"
    
    def test_map_error_to_code_with_base_error(self):
        """Test mapping with base X402Error."""
        base_error = X402Error("Base error")
        # Should return unknown since X402Error itself isn't mapped
        assert map_error_to_code(base_error) == "UNKNOWN_ERROR"
