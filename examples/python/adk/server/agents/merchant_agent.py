"""A Lowes merchant agent for the ADK demo."""

import json
import os
import hashlib
import traceback
from typing import Dict, Any, List
from abc import ABC
from dotenv import load_dotenv

# ADK imports for LLM integration
from google.adk.agents import LlmAgent
from google.adk.tools.tool_context import ToolContext
from a2a.types import AgentSkill, AgentCard

# a2a_x402 imports
from a2a_x402.core import (
    X402Protocol,
    create_agent_card,
    create_payment_requirements,
    settle_payment,
    SETTLE_PAYMENT_SKILL,
    PaymentRequirementsConfig
)
from a2a_x402.types import (
    X402A2AMessage,
    PaymentPayload,
    PaymentRequired,
    PaymentRequirements,
    SettleResponse,
    X402ExtensionConfig,
    X402MessageMetadata
)
from a2a_x402.extension import X402Extension

class LowesMerchantAgent(ABC):
    """A Lowes merchant agent for the ADK demo."""

    def __init__(
        self,
        merchant_address: str,
        network: str = "base-sepolia"
    ):
        """Initialize the Lowes merchant agent.

        Args:
            merchant_address: The merchant's Ethereum address
            network: The network to use (e.g. 'base-sepolia')
        """
        # Store merchant info
        self.merchant_address = merchant_address
        self.network = network
        self.name = "lowes_merchant_agent"
        self.description = "A Lowes merchant that accepts x402 payments"

        # Initialize x402 config
        self.config = X402ExtensionConfig(
            scheme="exact",
            version=X402Extension.VERSION,
            x402_version=X402Protocol.VERSION
        )

        # Load product data
        self.product_data = self._load_product_data()

    def _load_product_data(self) -> Dict[str, Any]:
        """Load product data from products.json file.

        Returns:
            Dictionary containing product data
        """
        try:
            products_path = os.path.join(os.path.dirname(__file__), "..", "products.json")
            print(f"[merchant_agent] Loading products from: {products_path}")
            print(f"[merchant_agent] Current directory: {os.getcwd()}")
            print(f"[merchant_agent] __file__: {__file__}")
            
            with open(products_path, 'r') as f:
                data = json.load(f)
                print(f"[merchant_agent] Loaded {len(data.get('products', []))} products")
                return data
        except Exception as e:
            print(f"[merchant_agent] Failed to load products.json: {e}")
            print(f"[merchant_agent] Stack trace: {traceback.format_exc()}")
            return {"products": []}

    def create_agent_card(self, url: str) -> AgentCard:
        """Create the AgentCard metadata for discovery.
        
        Args:
            url: The URL where this agent can be reached
            
        Returns:
            AgentCard with x402 extension capabilities
        """
        return create_agent_card(
            name=self.name,
            description=self.description,
            url=url,
            config=self.config,
            skills=[
                # Payment capability
                SETTLE_PAYMENT_SKILL,
                
                # Lowes-specific capabilities
                AgentSkill(
                    id="get_product_details_and_payment_info",
                    name="Get Product Details and Payment Info",
                    description="Get price and payment requirements for Lowes products",
                    tags=["lowes", "product", "price", "x402"],
                    examples=[
                        "How much for a DeWalt drill?",
                        "I want to buy a Nest thermostat",
                        "Get me the price for the Samsung refrigerator"
                    ]
                )
            ]
        )

    def create_agent(self) -> LlmAgent:
        """Create the LlmAgent instance for the merchant."""
        # Convert product data to a string format for context
        product_context = "\n".join([
            f"- {p['name']} by {p['brand']}: ${p['price']:.2f}"
            for p in self.product_data.get("products", [])
        ])

        return LlmAgent(
            model="gemini-1.5-flash-latest",
            name=self.name,
            description="A Lowes merchant that can sell products using x402 payments.",
            instruction=f"""You are a helpful Lowes merchant agent.

Available Products:
{product_context}

When helping customers:
1. Only recommend products from the available catalog above
2. Use exact product names and prices from the catalog
3. When a user wants to buy something, use get_product_details_and_payment_info with the exact product name
4. When you receive payment data, return it exactly as received
5. For successful payments, relay the confirmation message
6. For failed payments, explain the error clearly

Remember:
- If a user asks about a product not in the catalog, politely explain we only have the listed items
- Always use exact product names when calling get_product_details_and_payment_info
- Be helpful and professional in explaining product features
""",
            tools=[
                self.settle_payment,
                self.get_product_details_and_payment_info
            ]
        )

    async def settle_payment(
        self,
        payment_data: str,
        tool_context: ToolContext = None
    ) -> Dict[str, Any]:
        """Process an x402 payment authorization.

        Expects a JSON string containing an X402A2AMessage[PaymentPayload]:
        {
            "metadata": {
                "type": "PAYMENT_PAYLOAD",
                "requirements": {
                    "scheme": "exact",
                    "network": "base-sepolia",
                    "asset": "0x...",
                    "payTo": "0x...",
                    "maxAmountRequired": "1000000",
                    "resource": "https://lowes.com/products/...",
                    "description": "Product description",
                    "maxTimeoutSeconds": 1200,
                    "mimeType": "application/json",
                    "outputSchema": {},
                    "extra": {}
                }
            },
            "data": {
                "scheme": "exact",
                "network": "base-sepolia",
                "asset": "0x...",
                "payTo": "0x...",
                "amount": "1000000",
                "signature": "0x...",
                "signedMessage": "0x..."
            }
        }

        Args:
            payment_data: JSON string containing X402A2AMessage[PaymentPayload]
            tool_context: Optional context for controlling tool behavior

        Returns:
            Dict containing:
            - status: 'success' or 'error'
            - message: Human readable description
            - data: Settlement data if successful
            - error: Error message if status is 'error'
        """
        try:
            # Parse and process the payment
            payment_message = X402A2AMessage[PaymentPayload].model_validate_json(payment_data)
            result = await settle_payment(payment_message, None)  # No facilitator config for demo
            
            # Skip LLM summarization since this is structured data
            if tool_context:
                tool_context.actions.skip_summarization = True
            
            return {
                "status": "success",
                "message": "Payment processed successfully",
                "data": result.model_dump()
            }
        except Exception as e:
            return {
                "status": "error",
                "message": str(e),
                "data": None
            }

    def create_payment_requirements(
        self,
        price: str,
        resource: str,
        description: str = "",
        mime_type: str = "",
        max_timeout_seconds: int = 60,
        output_schema: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Create payment requirements for a resource.
        
        Args:
            price: Price in USD (e.g. "$0.10")
            resource: Resource identifier
            description: Description of what's being purchased
            mime_type: MIME type of the resource
            max_timeout_seconds: Payment timeout in seconds
            output_schema: Optional schema for the response
            
        Returns:
            Dictionary containing payment requirements
        """
        config = PaymentRequirementsConfig(
            price=price,
            resource=resource,
            merchant_address=self.merchant_address,
            network=self.network,
            description=description,
            mime_type=mime_type,
            max_timeout_seconds=max_timeout_seconds,
            output_schema=output_schema
        )
        requirements = create_payment_requirements(config, self.config)
        return requirements.model_dump()

    async def get_product_details_and_payment_info(
        self,
        product_name: str,
        tool_context: ToolContext = None
    ) -> Dict[str, Any]:
        """Get product details and payment requirements.

        Args:
            product_name: Name of the product
            tool_context: Optional tool context

        Returns:
            Dict containing:
            - status: 'success' or 'error'
            - sku: Product SKU
            - price: Price in USD
            - payment_requirements: Payment requirements data
        """
        try:
            print(f"[merchant_agent] Looking up product: {product_name}")
            print(f"[merchant_agent] Available products: {[p['name'] for p in self.product_data.get('products', [])]}")
            
            if not product_name:
                print("[merchant_agent] Product name is empty")
                return {
                    "status": "error",
                    "message": "Product name cannot be empty.",
                    "data": None
                }

            # Find the product in our catalog
            product = next(
                (p for p in self.product_data.get("products", [])
                 if p["name"].lower() == product_name.lower()),
                None
            )

            if not product:
                print(f"[merchant_agent] Product not found: {product_name}")
                return {
                    "status": "error",
                    "message": f"Product not found: {product_name}",
                    "data": None
                }

            print(f"[merchant_agent] Found product: {product}")

            # Format the price
            price = f"${product['price']:.2f}"

            # Generate a simple SKU
            safe_product_name = product_name.upper().replace(" ", "-")
            sku = f"SKU-{safe_product_name}"

            # Create payment requirements
            payment_requirements = self.create_payment_requirements(
                price=price,
                resource=f"https://lowes.com/products/{safe_product_name}",
                description=f"{product['brand']} {product['name']}",
                mime_type="application/json",
                max_timeout_seconds=1200,  # 20 minutes
                output_schema={}
            )

            # Format as X402A2AMessage[PaymentRequired]
            payment_message = X402A2AMessage[PaymentRequired](
                metadata=X402MessageMetadata(
                    type="PAYMENT_REQUIRED",
                    requirements=payment_requirements
                ),
                data=PaymentRequired(
                    amount=product['price'],
                    item=product['name']
                )
            )

            print(f"[merchant_agent] Created payment requirements: {payment_requirements}")

            # Skip LLM summarization since this is structured data
            if tool_context:
                tool_context.actions.skip_summarization = True

            result = {
                "status": "success",
                "sku": sku,
                "price": price,
                "payment_requirements": payment_message.model_dump()
            }
            print(f"[merchant_agent] Returning result: {result}")
            return result

        except Exception as e:
            print(f"[merchant_agent] Error getting product details: {e}")
            traceback.print_exc()
            return {
                "status": "error",
                "message": f"Failed to get product details: {str(e)}",
                "data": None
            }
