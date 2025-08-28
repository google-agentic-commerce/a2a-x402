"""Unit tests for a2a_x402.types.state module."""

import pytest
from a2a_x402.types.state import PaymentStatus, X402Metadata


class TestPaymentStatus:
    """Test PaymentStatus enum."""
    
    def test_payment_status_values(self):
        """Test that all payment status values match spec."""
        assert PaymentStatus.PAYMENT_REQUIRED == "payment-required"
        assert PaymentStatus.PAYMENT_SUBMITTED == "payment-submitted"
        assert PaymentStatus.PAYMENT_REJECTED == "payment-rejected"
        assert PaymentStatus.PAYMENT_COMPLETED == "payment-completed"
        assert PaymentStatus.PAYMENT_FAILED == "payment-failed"
    
    def test_payment_status_enum_behavior(self):
        """Test enum behavior and conversion."""
        status = PaymentStatus.PAYMENT_REQUIRED
        assert status.value == "payment-required"
        
        # Test enum from string
        assert PaymentStatus("payment-required") == PaymentStatus.PAYMENT_REQUIRED
    
    def test_all_states_defined(self):
        """Test that all 5 spec-required states are defined."""
        all_statuses = list(PaymentStatus)
        assert len(all_statuses) == 5
        
        expected_states = [
            "payment-required",
            "payment-submitted",
            "payment-rejected",
            "payment-completed",
            "payment-failed"
        ]
        
        actual_states = [status.value for status in all_statuses]
        for expected in expected_states:
            assert expected in actual_states


class TestX402Metadata:
    """Test X402Metadata constants."""
    
    def test_metadata_keys_match_spec(self):
        """Test that metadata keys match spec exactly."""
        assert X402Metadata.STATUS_KEY == "x402.payment.status"
        assert X402Metadata.REQUIRED_KEY == "x402.payment.required"
        assert X402Metadata.PAYLOAD_KEY == "x402.payment.payload"
        assert X402Metadata.RECEIPTS_KEY == "x402.payment.receipts"
        assert X402Metadata.ERROR_KEY == "x402.payment.error"
    
    def test_all_metadata_keys_defined(self):
        """Test that all 5 spec-required metadata keys are defined."""
        expected_keys = [
            "x402.payment.status",
            "x402.payment.required",
            "x402.payment.payload", 
            "x402.payment.receipts",
            "x402.payment.error"
        ]
        
        actual_keys = [
            X402Metadata.STATUS_KEY,
            X402Metadata.REQUIRED_KEY,
            X402Metadata.PAYLOAD_KEY,
            X402Metadata.RECEIPTS_KEY,
            X402Metadata.ERROR_KEY
        ]
        
        assert len(actual_keys) == 5
        for expected in expected_keys:
            assert expected in actual_keys
    
    def test_metadata_keys_immutable(self):
        """Test that metadata keys are string constants."""
        assert isinstance(X402Metadata.STATUS_KEY, str)
        assert isinstance(X402Metadata.REQUIRED_KEY, str)
        assert isinstance(X402Metadata.PAYLOAD_KEY, str)
        assert isinstance(X402Metadata.RECEIPTS_KEY, str)
        assert isinstance(X402Metadata.ERROR_KEY, str)
