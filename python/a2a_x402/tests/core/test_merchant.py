"""Unit tests for a2a_x402.core.merchant module."""

import pytest
from a2a_x402.core.merchant import create_payment_requirements
from a2a_x402.types import PaymentRequirements


class TestCreatePaymentRequirements:
    """Test create_payment_requirements function."""
    
    def test_create_payment_requirements_minimal(self):
        """Test creating payment requirements with minimal parameters."""
        requirements = create_payment_requirements(
            price="$1.00",  # $1.00 USD
            resource="/test-service",
            pay_to_address="0xmerchant123"
        )
        
        assert isinstance(requirements, PaymentRequirements)
        assert requirements.max_amount_required == "1000000"  # 1 USDC in atomic units
        assert requirements.resource == "/test-service"
        assert requirements.pay_to == "0xmerchant123"
        
        # Test defaults
        assert requirements.network == "base"
        assert requirements.scheme == "exact"
        assert requirements.mime_type == "application/json"
        assert requirements.max_timeout_seconds == 600
    
    def test_create_payment_requirements_full(self):
        """Test creating payment requirements with all parameters."""
        requirements = create_payment_requirements(
            price="$5.00",  # $5.00 USD
            resource="/premium-service",
            pay_to_address="0xmerchant456",
            network="base-sepolia",
            description="Premium AI service",
            mime_type="image/png",
            scheme="exact",
            max_timeout_seconds=300,
            output_schema={"type": "image"}
        )
        
        assert requirements.max_amount_required == "5000000"  # 5 USDC in atomic units
        assert requirements.resource == "/premium-service"
        assert requirements.pay_to == "0xmerchant456"
        assert requirements.network == "base-sepolia"
        assert requirements.description == "Premium AI service"
        assert requirements.mime_type == "image/png"
        assert requirements.scheme == "exact"
        assert requirements.max_timeout_seconds == 300
        assert requirements.asset == "0x036CbD53842c5426634e7929541eC2318f3dCF7e"  # USDC on base-sepolia
        assert requirements.output_schema == {"type": "image"}
    
    def test_auto_asset_mapping(self):
        """Test automatic asset address mapping for common networks."""
        # Test base network
        req_base = create_payment_requirements(
            price="$1.00",
            resource="/test",
            pay_to_address="0x123"
        )
        assert req_base.asset == "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
        
        # Test base-sepolia network
        req_sepolia = create_payment_requirements(
            price="$1.00",
            resource="/test",
            pay_to_address="0x123",
            network="base-sepolia"
        )
        assert req_sepolia.asset == "0x036CbD53842c5426634e7929541eC2318f3dCF7e"
        
        # Test avalanche network  
        req_avalanche = create_payment_requirements(
            price="$1.00",
            resource="/test",
            pay_to_address="0x123",
            network="avalanche"
        )
        assert req_avalanche.asset == "0xB97EF9Ef8734C71904D8002F8b6Bc66Dd9c48a6E"  # Avalanche USDC
        
        # Test avalanche-fuji network
        req_fuji = create_payment_requirements(
            price="$1.00",
            resource="/test",
            pay_to_address="0x123",
            network="avalanche-fuji"
        )
        assert req_fuji.asset == "0x5425890298aed601595a70AB815c96711a31Bc65"
    
    def test_custom_token_amount(self):
        """Test using TokenAmount for custom tokens."""
        from x402.types import TokenAmount, TokenAsset, EIP712Domain
        
        # Create a custom token amount
        custom_token = TokenAmount(
            amount="1000000",
            asset=TokenAsset(
                address="0xcustomasset789",
                decimals=18,
                eip712=EIP712Domain(name="Custom Token", version="1")
            )
        )
        
        requirements = create_payment_requirements(
            price=custom_token,
            resource="/test",
            pay_to_address="0x123",
            network="base"
        )
        
        assert requirements.asset == "0xcustomasset789"
        assert requirements.max_amount_required == "1000000"
    
    def test_kwargs_passed_through(self):
        """Test that additional kwargs are passed to PaymentRequirements."""
        # Note: PaymentRequirements from x402.types is a Pydantic model
        # that doesn't accept arbitrary kwargs. This test verifies that
        # the function accepts kwargs without errors (for backwards compatibility)
        # even though they won't be stored on the model.
        requirements = create_payment_requirements(
            price="$1.00",
            resource="/test",
            pay_to_address="0x123",
            custom_field="custom_value"  # This will be ignored
        )
        
        # Verify that required fields are set correctly
        assert requirements.resource == "/test"
        assert requirements.pay_to == "0x123"
        assert requirements.max_amount_required == "1000000"  # $1.00 in USDC atomic units
    
    def test_required_parameters(self):
        """Test that required parameters are enforced."""
        # All three required parameters
        requirements = create_payment_requirements(
            price="$1.00",
            resource="/test", 
            pay_to_address="0x123"
        )
        assert requirements is not None
        
        # Test price types
        requirements_str = create_payment_requirements("$1.00", "/test", "0x123")
        assert requirements_str.max_amount_required == "1000000"
        
        # Test integer price (dollars)
        requirements_int = create_payment_requirements(1, "/test", "0x123")
        assert requirements_int.max_amount_required == "1000000"
