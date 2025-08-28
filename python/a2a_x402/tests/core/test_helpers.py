"""Tests for a2a_x402.core.helpers module."""

import pytest
from unittest.mock import Mock
from a2a_x402.core.helpers import (
    require_payment,
    require_payment_choice,
    paid_service,
    smart_paid_service,
    create_tiered_payment_options,
    check_payment_context
)
from a2a_x402.types.errors import X402PaymentRequiredException
from a2a_x402.core.merchant import create_payment_requirements


class TestRequirePayment:
    """Test require_payment helper function."""
    
    def test_require_payment_basic(self):
        """Test basic require_payment functionality."""
        exception = require_payment(
            price="$5.00",
            pay_to_address="0xtest123",
            resource="/premium-service",
            description="Premium feature access"
        )
        
        assert isinstance(exception, X402PaymentRequiredException)
        assert str(exception) == "Premium feature access"
        assert len(exception.payment_requirements) == 1
        
        req = exception.payment_requirements[0]
        assert req.pay_to == "0xtest123"
        assert req.resource == "/premium-service"
        assert req.description == "Premium feature access"
        assert req.network == "base"  # default
    
    def test_require_payment_with_custom_network(self):
        """Test require_payment with custom network."""
        exception = require_payment(
            price="$2.00",
            pay_to_address="0xtest456",
            network="base-sepolia",
            description="Test service"
        )
        
        req = exception.payment_requirements[0]
        assert req.network == "base-sepolia"
        assert req.resource == "/service"  # default when None provided
    
    def test_require_payment_with_custom_message(self):
        """Test require_payment with custom message."""
        exception = require_payment(
            price="$1.00",
            pay_to_address="0xtest",
            resource="/test",
            description="Service description",
            message="Custom error message"
        )
        
        assert str(exception) == "Custom error message"
        assert exception.payment_requirements[0].description == "Service description"


class TestRequirePaymentChoice:
    """Test require_payment_choice helper function."""
    
    def test_require_payment_choice(self):
        """Test require_payment_choice with multiple options."""
        basic_req = create_payment_requirements(
            price="$1.00",
            pay_to_address="0xtest123",
            resource="/basic"
        )
        premium_req = create_payment_requirements(
            price="$5.00", 
            pay_to_address="0xtest123",
            resource="/premium"
        )
        
        exception = require_payment_choice(
            [basic_req, premium_req],
            "Choose your service tier"
        )
        
        assert isinstance(exception, X402PaymentRequiredException)
        assert str(exception) == "Choose your service tier"
        assert len(exception.payment_requirements) == 2
        assert exception.payment_requirements[0] == basic_req
        assert exception.payment_requirements[1] == premium_req
    
    def test_require_payment_choice_default_message(self):
        """Test require_payment_choice with default message."""
        req = create_payment_requirements(
            price="$1.00",
            pay_to_address="0xtest",
            resource="/test"
        )
        
        exception = require_payment_choice([req])
        assert str(exception) == "Multiple payment options available"


class TestPaidServiceDecorator:
    """Test paid_service decorator."""
    
    def test_paid_service_decorator(self):
        """Test that paid_service decorator raises payment exception."""
        @paid_service(
            price="$2.00",
            pay_to_address="0xtest123",
            description="Premium image generation"
        )
        def generate_image(prompt: str):
            return f"Generated image for: {prompt}"
        
        # Should raise payment exception
        with pytest.raises(X402PaymentRequiredException) as exc_info:
            generate_image("test prompt")
        
        exception = exc_info.value
        assert str(exception) == "Premium image generation"
        assert len(exception.payment_requirements) == 1
        
        req = exception.payment_requirements[0]
        assert req.pay_to == "0xtest123"
        assert req.resource == "/generate_image"  # Function name
        assert req.description == "Premium image generation"
    
    def test_paid_service_with_custom_resource(self):
        """Test paid_service with custom resource."""
        @paid_service(
            price="$1.00",
            pay_to_address="0xtest",
            resource="/custom-endpoint"
        )
        def my_function():
            pass
        
        with pytest.raises(X402PaymentRequiredException) as exc_info:
            my_function()
        
        req = exc_info.value.payment_requirements[0]
        assert req.resource == "/custom-endpoint"


class TestSmartPaidServiceDecorator:
    """Test smart_paid_service decorator."""
    
    def test_smart_paid_service_no_context(self):
        """Test smart_paid_service without context."""
        @smart_paid_service(
            price="$1.00",
            pay_to_address="0xtest",
            description="Smart service"
        )
        def smart_function():
            return "success"
        
        # Should require payment when no context
        with pytest.raises(X402PaymentRequiredException) as exc_info:
            smart_function()
        
        exception = exc_info.value
        assert str(exception) == "Smart service"
    
    def test_smart_paid_service_with_paid_context(self):
        """Test smart_paid_service with paid context."""
        # Create mock context with payment completed
        mock_context = Mock()
        mock_task = Mock()
        mock_status = Mock()
        mock_message = Mock()
        mock_message.metadata = {"x402.payment.status": "payment-completed"}
        mock_status.message = mock_message
        mock_task.status = mock_status
        mock_context.current_task = mock_task
        
        @smart_paid_service(
            price="$1.00",
            pay_to_address="0xtest",
            description="Smart service"
        )
        def smart_function(context):
            return "success"
        
        # Should execute normally with paid context
        result = smart_function(mock_context)
        assert result == "success"
    
    def test_smart_paid_service_with_unpaid_context(self):
        """Test smart_paid_service with unpaid context."""
        mock_context = Mock()
        mock_context.current_task = None
        
        @smart_paid_service(
            price="$1.00",
            pay_to_address="0xtest",
            description="Smart service"
        )
        def smart_function(context):
            return "success"
        
        # Should require payment when context has no payment
        with pytest.raises(X402PaymentRequiredException):
            smart_function(mock_context)


class TestCreateTieredPaymentOptions:
    """Test create_tiered_payment_options helper."""
    
    def test_create_tiered_payment_options_default_tiers(self):
        """Test create_tiered_payment_options with default tiers."""
        options = create_tiered_payment_options(
            base_price="$1.00",
            pay_to_address="0xtest123",
            resource="/generate-image"
        )
        
        assert len(options) == 2
        
        # Basic tier
        basic = options[0]
        assert basic.pay_to == "0xtest123"
        assert basic.resource == "/generate-image/basic"
        assert basic.description == "Basic service"
        
        # Premium tier  
        premium = options[1]
        assert premium.pay_to == "0xtest123"
        assert premium.resource == "/generate-image/premium"
        assert premium.description == "Premium service"
    
    def test_create_tiered_payment_options_custom_tiers(self):
        """Test create_tiered_payment_options with custom tiers."""
        custom_tiers = [
            {"multiplier": 1, "suffix": "standard", "description": "Standard quality"},
            {"multiplier": 3, "suffix": "hd", "description": "HD quality"},
            {"multiplier": 5, "suffix": "ultra", "description": "Ultra HD quality"}
        ]
        
        options = create_tiered_payment_options(
            base_price="$2.00",
            pay_to_address="0xtest456",
            resource="/render",
            tiers=custom_tiers,
            network="base-sepolia"
        )
        
        assert len(options) == 3
        
        # Standard tier ($2.00 * 1)
        standard = options[0]
        assert standard.resource == "/render/standard"
        assert standard.description == "Standard quality"
        assert standard.network == "base-sepolia"
        
        # HD tier ($2.00 * 3 = $6.00)
        hd = options[1]
        assert hd.resource == "/render/hd"
        assert hd.description == "HD quality"
        
        # Ultra tier ($2.00 * 5 = $10.00)
        ultra = options[2]
        assert ultra.resource == "/render/ultra"
        assert ultra.description == "Ultra HD quality"
    
    def test_create_tiered_payment_options_numeric_price(self):
        """Test create_tiered_payment_options with numeric price."""
        options = create_tiered_payment_options(
            base_price=1.50,  # Numeric price
            pay_to_address="0xtest",
            resource="/service"
        )
        
        assert len(options) == 2
        # Would need to check actual price handling in implementation


class TestCheckPaymentContext:
    """Test check_payment_context helper."""
    
    def test_check_payment_context_with_payment(self):
        """Test check_payment_context with payment metadata."""
        mock_context = Mock()
        mock_task = Mock()
        mock_status = Mock()
        mock_message = Mock()
        mock_message.metadata = {"x402.payment.status": "payment-completed"}
        mock_status.message = mock_message
        mock_task.status = mock_status
        mock_context.current_task = mock_task
        
        status = check_payment_context(mock_context)
        assert status == "payment-completed"
    
    def test_check_payment_context_without_payment(self):
        """Test check_payment_context without payment metadata."""
        mock_context = Mock()
        mock_context.current_task = None
        
        status = check_payment_context(mock_context)
        assert status is None
    
    def test_check_payment_context_incomplete_structure(self):
        """Test check_payment_context with incomplete context structure."""
        mock_context = Mock()
        mock_task = Mock()
        mock_task.status = None  # Incomplete structure
        mock_context.current_task = mock_task
        
        status = check_payment_context(mock_context)
        assert status is None
    
    def test_check_payment_context_no_metadata(self):
        """Test check_payment_context with no metadata."""
        mock_context = Mock()
        mock_task = Mock()
        mock_status = Mock()
        mock_message = Mock()
        mock_message.metadata = None
        mock_status.message = mock_message
        mock_task.status = mock_status
        mock_context.current_task = mock_task
        
        status = check_payment_context(mock_context)
        assert status is None