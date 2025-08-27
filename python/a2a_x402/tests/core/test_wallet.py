"""Unit tests for a2a_x402.core.wallet module."""

import pytest
from unittest.mock import Mock, patch
from eth_account import Account
from a2a_x402.core.wallet import (
    process_payment_required,
    process_payment,
    _generate_nonce
)
from a2a_x402.types import (
    PaymentRequirements,
    x402PaymentRequiredResponse,
    PaymentPayload,
    ExactEvmPaymentPayload,
    EIP3009Authorization
)


class TestProcessPaymentRequired:
    """Test process_payment_required function."""
    
    def test_process_payment_required_success(self, sample_payment_required_response, test_account):
        """Test processing payment required response successfully."""
        with patch('a2a_x402.core.wallet.x402Client') as mock_client_class:
            # Mock x402Client
            mock_client = Mock()
            mock_client.select_payment_requirements.return_value = sample_payment_required_response.accepts[0]
            mock_client_class.return_value = mock_client
            
            # Mock process_payment function
            with patch('a2a_x402.core.wallet.process_payment') as mock_process_payment:
                mock_payload = PaymentPayload(
                    x402_version=1,
                    scheme="exact",
                    network="base",
                    payload=ExactEvmPaymentPayload(
                        signature="0x" + "a" * 130,
                        authorization=EIP3009Authorization(
                            from_=test_account.address,
                            to="0xmerchant123",
                            value="1000000",
                            valid_after="1640995200",
                            valid_before="1640998800",
                            nonce="0x" + "1" * 64
                        )
                    )
                )
                mock_process_payment.return_value = mock_payload
                
                # Call function (not async)
                result = process_payment_required(
                    sample_payment_required_response,
                    test_account,
                    max_value=5000000
                )
                
                # Verify x402Client was used correctly
                mock_client_class.assert_called_once_with(account=test_account, max_value=5000000)
                mock_client.select_payment_requirements.assert_called_once_with(sample_payment_required_response.accepts)
                
                # Verify result
                assert isinstance(result, PaymentPayload)
                assert result == mock_payload


class TestProcessPayment:
    """Test process_payment function."""
    
    def test_process_payment_creates_payload(self, sample_payment_requirements, test_account):
        """Test that process_payment creates a proper PaymentPayload."""
        with patch('a2a_x402.core.wallet._generate_nonce') as mock_nonce:
            mock_nonce.return_value = "0x" + "1" * 64
            
            with patch('time.time') as mock_time:
                mock_time.return_value = 1640995200
                
                result = process_payment(sample_payment_requirements, test_account)
                
                assert isinstance(result, PaymentPayload)
                assert result.x402_version == 1
                assert result.scheme == sample_payment_requirements.scheme
                assert result.network == sample_payment_requirements.network
                
                # Check payload structure
                assert isinstance(result.payload, ExactEvmPaymentPayload)
                assert result.payload.signature.startswith("0x")
                assert len(result.payload.signature) == 132  # 0x + 130 chars
                
                # Check authorization
                auth = result.payload.authorization
                assert auth.from_ == test_account.address
                assert auth.to == sample_payment_requirements.pay_to
                assert auth.value == sample_payment_requirements.max_amount_required
                assert auth.nonce == "0x" + "1" * 64


class TestGenerateNonce:
    """Test _generate_nonce helper function."""
    
    def test_generate_nonce_format(self):
        """Test that generated nonce has correct format."""
        nonce = _generate_nonce()
        
        # Should be 64 hex characters (32 bytes)
        assert len(nonce) == 64
        assert all(c in '0123456789abcdef' for c in nonce.lower())
    
    def test_generate_nonce_uniqueness(self):
        """Test that generated nonces are unique."""
        nonces = set()
        for _ in range(10):
            nonce = _generate_nonce()
            assert nonce not in nonces
            nonces.add(nonce)
