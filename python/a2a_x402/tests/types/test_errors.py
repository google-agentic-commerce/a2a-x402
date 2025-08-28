"""Unit tests for a2a_x402.types.errors module."""

import pytest
from a2a_x402.types.errors import (
    X402Error,
    MessageError,
    ValidationError,
    PaymentError,
    StateError,
    X402PaymentRequiredException,
    X402ErrorCode,
    map_error_to_code
)
from a2a_x402.core.merchant import create_payment_requirements


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
        payment_required_error = X402PaymentRequiredException.for_service(
            price="$1.00", pay_to_address="0xtest", resource="/test"
        )
        
        assert isinstance(message_error, X402Error)
        assert isinstance(validation_error, X402Error)
        assert isinstance(payment_error, X402Error)
        assert isinstance(state_error, X402Error)
        assert isinstance(payment_required_error, X402Error)
    
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


class TestX402PaymentRequiredException:
    """Test X402PaymentRequiredException functionality."""
    
    def test_single_payment_requirement_init(self, sample_payment_requirements):
        """Test initialization with single payment requirement."""
        exception = X402PaymentRequiredException(
            "Payment required for premium service",
            payment_requirements=sample_payment_requirements
        )
        
        assert str(exception) == "Payment required for premium service"
        assert len(exception.payment_requirements) == 1
        assert exception.payment_requirements[0] == sample_payment_requirements
        assert exception.error_code is None
    
    def test_multiple_payment_requirements_init(self, sample_payment_requirements):
        """Test initialization with multiple payment requirements."""
        req1 = sample_payment_requirements
        req2 = create_payment_requirements(
            price="$5.00",
            pay_to_address="0xmerchant789",
            resource="/premium-service"
        )
        
        exception = X402PaymentRequiredException(
            "Choose payment tier",
            payment_requirements=[req1, req2],
            error_code="TIER_SELECTION"
        )
        
        assert str(exception) == "Choose payment tier"
        assert len(exception.payment_requirements) == 2
        assert exception.payment_requirements[0] == req1
        assert exception.payment_requirements[1] == req2
        assert exception.error_code == "TIER_SELECTION"
    
    def test_get_accepts_array(self, sample_payment_requirements):
        """Test get_accepts_array method."""
        req1 = sample_payment_requirements
        req2 = create_payment_requirements(
            price="$2.00",
            pay_to_address="0xmerchant456",
            resource="/another-service"
        )
        
        exception = X402PaymentRequiredException(
            "Multiple options",
            payment_requirements=[req1, req2]
        )
        
        accepts = exception.get_accepts_array()
        assert len(accepts) == 2
        assert accepts[0] == req1
        assert accepts[1] == req2
    
    def test_for_service_classmethod(self):
        """Test for_service class method."""
        exception = X402PaymentRequiredException.for_service(
            price="$3.00",
            pay_to_address="0xtest123",
            resource="/api/generate",
            network="base-sepolia",
            description="API service access"
        )
        
        assert str(exception) == "API service access"
        assert len(exception.payment_requirements) == 1
        
        req = exception.payment_requirements[0]
        assert req.pay_to == "0xtest123"
        assert req.resource == "/api/generate"
        assert req.network == "base-sepolia"
        assert req.description == "API service access"
    
    def test_for_service_with_custom_message(self):
        """Test for_service with custom message."""
        exception = X402PaymentRequiredException.for_service(
            price="$1.50",
            pay_to_address="0xtest456",
            resource="/custom",
            message="Custom payment message"
        )
        
        assert str(exception) == "Custom payment message"
        req = exception.payment_requirements[0]
        assert req.description == "Payment required for this service"  # Default description
    
    def test_inherits_from_x402_error(self):
        """Test that X402PaymentRequiredException inherits from X402Error."""
        exception = X402PaymentRequiredException.for_service(
            price="$1.00",
            pay_to_address="0xtest",
            resource="/test"
        )
        
        assert isinstance(exception, X402Error)
        assert isinstance(exception, Exception)
    
    def test_can_be_raised_and_caught(self):
        """Test that X402PaymentRequiredException can be raised and caught."""
        exception = X402PaymentRequiredException.for_service(
            price="$2.00",
            pay_to_address="0xtest",
            resource="/test"
        )
        
        # Test raising as specific type
        with pytest.raises(X402PaymentRequiredException):
            raise exception
        
        # Test catching as base X402Error
        with pytest.raises(X402Error):
            raise exception
    
    def test_list_normalization(self, sample_payment_requirements):
        """Test that single requirement gets normalized to list."""
        exception = X402PaymentRequiredException(
            "Test message",
            payment_requirements=sample_payment_requirements  # Single requirement
        )
        
        # Should be normalized to list
        assert isinstance(exception.payment_requirements, list)
        assert len(exception.payment_requirements) == 1
        assert exception.payment_requirements[0] == sample_payment_requirements
