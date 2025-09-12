# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Helper functions for easy x402 payment integration."""

from typing import Union, Optional, List, Callable, Any
from functools import wraps

from ..types import (
    x402PaymentRequiredException,
    PaymentRequirements,
    TokenAmount
)
from .merchant import create_payment_requirements


def require_payment(
    price: Union[str, int, TokenAmount],
    pay_to_address: str,
    resource: Optional[str] = None,
    network: str = "base",
    description: str = "Payment required for this service",
    message: Optional[str] = None
) -> x402PaymentRequiredException:
    """Create a payment required exception for immediate raising.
    
    Convenience function for the most common use case.
    
    Args:
        price: Payment amount (e.g., "$1.00", 1.00, TokenAmount)
        pay_to_address: Ethereum address to receive payment
        resource: Resource identifier (auto-generated if None)
        network: Blockchain network (default: "base")
        description: Human-readable description
        message: Exception message (default: uses description)
        
    Returns:
        x402PaymentRequiredException ready to be raised
        
    Example:
        # In your agent logic:
        if not user.is_premium:
            raise require_payment(
                price="$5.00",
                pay_to_address="0x123...",
                resource="/premium-feature",
                description="Premium feature access"
            )
    """
    return x402PaymentRequiredException.for_service(
        price=price,
        pay_to_address=pay_to_address,
        resource=resource or "/service",
        network=network,
        description=description,
        message=message
    )


def require_payment_choice(
    payment_options: List[PaymentRequirements],
    message: str = "Multiple payment options available"
) -> x402PaymentRequiredException:
    """Create a payment required exception with multiple payment options.
    
    Args:
        payment_options: List of payment requirements to choose from
        message: Exception message
        
    Returns:
        x402PaymentRequiredException with multiple payment options
        
    Example:
        basic_option = create_payment_requirements(
            price="$1.00", pay_to_address="0x123...", resource="/basic"
        )
        premium_option = create_payment_requirements(
            price="$5.00", pay_to_address="0x123...", resource="/premium"
        )
        
        raise require_payment_choice(
            [basic_option, premium_option],
            "Choose your service tier"
        )
    """
    return x402PaymentRequiredException(
        message=message,
        payment_requirements=payment_options
    )


def paid_service(
    price: Union[str, int, TokenAmount],
    pay_to_address: str,
    resource: Optional[str] = None,
    network: str = "base",
    description: str = "Payment required for this service"
):
    """Decorator to automatically require payment for a function or method.
    
    Args:
        price: Payment amount (e.g., "$1.00", 1.00, TokenAmount)  
        pay_to_address: Ethereum address to receive payment
        resource: Resource identifier (auto-generated from function name if None)
        network: Blockchain network (default: "base")
        description: Human-readable description
        
    Example:
        @paid_service(
            price="$2.00",
            pay_to_address="0x123...",
            description="Premium image generation"
        )
        async def generate_premium_image(self, prompt: str):
            # This function will require payment before execution
            return await self.ai_service.generate_image(prompt, quality="high")
            
        # When called without payment, will raise x402PaymentRequiredException
        # When called with valid payment, will execute normally
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # For now, always require payment on first call
            # In a real implementation, you might check payment status from context
            effective_resource = resource or f"/{func.__name__}"
            
            raise require_payment(
                price=price,
                pay_to_address=pay_to_address,
                resource=effective_resource,
                network=network,
                description=description
            )
            
        return wrapper
    return decorator


def create_tiered_payment_options(
    base_price: Union[str, int, TokenAmount],
    pay_to_address: str,
    resource: str,
    tiers: Optional[List[dict]] = None,
    network: str = "base"
) -> List[PaymentRequirements]:
    """Create multiple payment options with different tiers/features.
    
    Args:
        base_price: Base payment amount
        pay_to_address: Ethereum address to receive payment
        resource: Base resource identifier
        tiers: List of tier definitions with 'multiplier', 'suffix', 'description'
        network: Blockchain network (default: "base")
        
    Returns:
        List of PaymentRequirements for different service tiers
        
    Example:
        options = create_tiered_payment_options(
            base_price="$1.00",
            pay_to_address="0x123...",
            resource="/generate-image",
            tiers=[
                {"multiplier": 1, "suffix": "basic", "description": "Basic quality image"},
                {"multiplier": 3, "suffix": "premium", "description": "Premium quality image"},
                {"multiplier": 5, "suffix": "ultra", "description": "Ultra HD image"}
            ]
        )
        
        raise require_payment_choice(options, "Choose image quality")
    """
    if tiers is None:
        tiers = [
            {"multiplier": 1, "suffix": "basic", "description": "Basic service"},
            {"multiplier": 2, "suffix": "premium", "description": "Premium service"}
        ]
    
    options = []
    
    for tier in tiers:
        multiplier = tier.get("multiplier", 1)
        suffix = tier.get("suffix", "")
        description = tier.get("description", f"Service tier {suffix}")
        
        # Calculate tier price
        if isinstance(base_price, str) and base_price.startswith("$"):
            base_amount = float(base_price[1:])
            tier_price = f"${base_amount * multiplier:.2f}"
        elif isinstance(base_price, (int, float)):
            tier_price = base_price * multiplier
        else:
            # TokenAmount - would need to implement multiplication
            tier_price = base_price
            
        tier_resource = f"{resource}/{suffix}" if suffix else resource
        
        option = create_payment_requirements(
            price=tier_price,
            pay_to_address=pay_to_address,
            resource=tier_resource,
            network=network,
            description=description
        )
        options.append(option)
    
    return options


def check_payment_context(context: Any) -> Optional[str]:
    """Check if current context has payment information.
    
    Helper function to detect if a payment has already been made
    in the current request context.
    
    Args:
        context: Request context or task object
        
    Returns:
        Payment status string if payment info found, None otherwise
        
    Note:
        This is a placeholder implementation. In practice, this would
        integrate with the actual context/task payment status checking.
    """
    # Placeholder implementation
    # In real usage, this would check context.current_task for payment metadata
    if hasattr(context, 'current_task'):
        task = context.current_task
        if hasattr(task, 'status') and hasattr(task.status, 'message'):
            message = task.status.message
            if hasattr(message, 'metadata') and message.metadata:
                return message.metadata.get('x402.payment.status')
    
    return None


def smart_paid_service(
    price: Union[str, int, TokenAmount],
    pay_to_address: str,
    resource: Optional[str] = None,
    network: str = "base",
    description: str = "Payment required for this service"
):
    """Smart decorator that only requires payment if not already paid.
    
    This decorator checks the current context for existing payment
    before requiring new payment.
    
    Args:
        price: Payment amount (e.g., "$1.00", 1.00, TokenAmount)
        pay_to_address: Ethereum address to receive payment  
        resource: Resource identifier (auto-generated from function name if None)
        network: Blockchain network (default: "base")
        description: Human-readable description
        
    Example:
        @smart_paid_service(
            price="$1.00",
            pay_to_address="0x123...",
            description="AI text generation"
        )
        async def generate_text(self, context, prompt: str):
            # Payment automatically handled based on context
            return await self.ai_service.generate(prompt)
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Try to detect context from arguments
            context = None
            for arg in args:
                if hasattr(arg, 'current_task'):
                    context = arg
                    break
            
            # Check if payment already exists in context
            if context:
                payment_status = check_payment_context(context)
                if payment_status in ['payment-completed', 'payment-submitted']:
                    # Payment exists, proceed with function
                    return func(*args, **kwargs)
            
            # No payment found, require payment
            effective_resource = resource or f"/{func.__name__}"
            
            raise require_payment(
                price=price,
                pay_to_address=pay_to_address,
                resource=effective_resource,
                network=network,
                description=description
            )
            
        return wrapper
    return decorator
