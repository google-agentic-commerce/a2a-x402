"""Unit tests for a2a_x402.core.protocol module."""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from a2a_x402.core.protocol import verify_payment, settle_payment
from a2a_x402.types import (
    VerifyResponse,
    SettleResponse,
    SettleResponse,
    FacilitatorClient
)


class TestVerifyPayment:
    """Test verify_payment function."""
    
    @pytest.mark.asyncio
    async def test_verify_payment_with_client(self, sample_payment_payload, sample_payment_requirements):
        """Test verify_payment with provided facilitator client."""
        # Mock facilitator client
        mock_client = Mock(spec=FacilitatorClient)
        mock_verify_response = VerifyResponse(
            is_valid=True,
            invalid_reason=None,
            payer="0xclient456"
        )
        mock_client.verify = AsyncMock(return_value=mock_verify_response)
        
        # Call verify_payment
        result = await verify_payment(sample_payment_payload, sample_payment_requirements, mock_client)
        
        # Verify the call was made correctly
        mock_client.verify.assert_called_once_with(
            sample_payment_payload,
            sample_payment_requirements
        )
        
        assert result == mock_verify_response
        assert result.is_valid is True
    
    @pytest.mark.asyncio 
    async def test_verify_payment_without_client(self, sample_payment_payload, sample_payment_requirements):
        """Test verify_payment creates default facilitator client."""
        mock_verify_response = VerifyResponse(
            is_valid=False,
            invalid_reason="Invalid signature",
            payer=None
        )
        
        with patch('a2a_x402.core.protocol.FacilitatorClient') as mock_facilitator_class:
            mock_client = Mock()
            mock_client.verify = AsyncMock(return_value=mock_verify_response)
            mock_facilitator_class.return_value = mock_client
            
            # Call verify_payment without client
            result = await verify_payment(sample_payment_payload, sample_payment_requirements)
            
            # Verify default client was created and used
            mock_facilitator_class.assert_called_once()
            mock_client.verify.assert_called_once_with(
                sample_payment_payload,
                sample_payment_requirements
            )
            
            assert result == mock_verify_response
            assert result.is_valid is False
            assert result.invalid_reason == "Invalid signature"


class TestSettlePayment:
    """Test settle_payment function."""
    
    @pytest.mark.asyncio
    async def test_settle_payment_with_client_success(self, sample_payment_payload, sample_payment_requirements):
        """Test settle_payment with provided facilitator client - success case."""
        # Mock facilitator client
        mock_client = Mock(spec=FacilitatorClient)
        mock_settle_response = SettleResponse(
            success=True,
            transaction="0xtxhash123",
            network="base",
            payer="0xclient456",
            error_reason=None
        )
        mock_client.settle = AsyncMock(return_value=mock_settle_response)
        
        # Call settle_payment
        result = await settle_payment(sample_payment_payload, sample_payment_requirements, mock_client)
        
        # Verify the call was made correctly
        mock_client.settle.assert_called_once_with(
            sample_payment_payload,
            sample_payment_requirements
        )
        
        # Verify conversion to A2A format
        assert isinstance(result, SettleResponse)
        assert result.success is True
        assert result.transaction == "0xtxhash123"
        assert result.network == "base"
        assert result.payer == "0xclient456"
        assert result.error_reason is None
    
    @pytest.mark.asyncio
    async def test_settle_payment_with_client_failure(self, sample_payment_payload, sample_payment_requirements):
        """Test settle_payment with provided facilitator client - failure case."""
        mock_client = Mock(spec=FacilitatorClient)
        mock_settle_response = SettleResponse(
            success=False,
            transaction=None,
            network=None,
            payer=None,
            error_reason="Insufficient funds"
        )
        mock_client.settle = AsyncMock(return_value=mock_settle_response)
        
        result = await settle_payment(sample_payment_payload, sample_payment_requirements, mock_client)
        
        assert isinstance(result, SettleResponse)
        assert result.success is False
        assert result.transaction is None
        assert result.network == sample_payment_requirements.network  # Fallback
        assert result.payer is None
        assert result.error_reason == "Insufficient funds"
    
    @pytest.mark.asyncio
    async def test_settle_payment_without_client(self, sample_payment_payload, sample_payment_requirements):
        """Test settle_payment creates default facilitator client."""
        mock_settle_response = SettleResponse(
            success=True,
            transaction="0xtxhash456",
            network="base",
            payer="0xclient789",
            error_reason=None
        )
        
        with patch('a2a_x402.core.protocol.FacilitatorClient') as mock_facilitator_class:
            mock_client = Mock()
            mock_client.settle = AsyncMock(return_value=mock_settle_response)
            mock_facilitator_class.return_value = mock_client
            
            # Call settle_payment without client
            result = await settle_payment(sample_payment_payload, sample_payment_requirements)
            
            # Verify default client was created and used
            mock_facilitator_class.assert_called_once()
            mock_client.settle.assert_called_once_with(
                sample_payment_payload,
                sample_payment_requirements
            )
            
            assert isinstance(result, SettleResponse)
            assert result.success is True
            assert result.transaction == "0xtxhash456"
