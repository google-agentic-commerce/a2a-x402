"""A Lowes merchant agent for the ADK demo."""

import json
import os
import asyncio
from typing import Dict, Any, List, Optional
from abc import ABC
from dotenv import load_dotenv

# ADK imports for LLM integration
from google.adk.agents import LlmAgent
from google.adk.tools.tool_context import ToolContext
from a2a.types import AgentSkill, AgentCard

# a2a_x402 imports
from a2a_x402.core import (
    create_payment_requirements,
    settle_payment,
    verify_payment
)
from a2a_x402.types import (
    PaymentRequirements,
    PaymentPayload,
    X402ExtensionConfig,
    AgentSkill,
    FacilitatorConfig,
    FacilitatorClient
)
from a2a_x402.extension import (
    get_extension_declaration,
)

# Load environment variables
load_dotenv()

class LowesMerchantAgent(ABC):
    """A Lowes merchant agent for the ADK demo."""

    def __init__(
        self,
        merchant_address: str,
        network: str = "sui-testnet"
    ):
        """Initialize the Lowes merchant agent.

        Args:
            merchant_address: The merchant's address (Sui or Ethereum format)
            network: The network to use (e.g. 'sui-testnet', 'base-sepolia')
        """
        # Store merchant info
        self.merchant_address = merchant_address
        self.network = network
        self.name = "lowes_merchant_agent"
        self.description = "A Lowes merchant that accepts x402 payments"

        # Initialize x402 config
        self.config = X402ExtensionConfig()

        # Load product data
        self.product_data = self._load_product_data()

        # Cache payment requirements
        self.payment_requirements_store = {}

    def _load_product_data(self) -> Dict[str, Any]:
        """Load product data from products.json file.

        Returns:
            Dictionary containing product data
        """
        try:
            products_path = os.path.join(os.path.dirname(__file__), "..", "products.json")
            print(f"Loading products from: {products_path}")

            with open(products_path, 'r') as f:
                data = json.load(f)
                print(f"Loaded {len(data.get('products', []))} products")
                return data
        except Exception as e:
            print(f"Failed to load products.json: {e}")
            return {"products": []}

    def create_agent_card(self, url: str) -> AgentCard:
        """Create the AgentCard metadata for discovery.

        Args:
            url: The URL where this agent can be reached

        Returns:
            AgentCard with x402 extension capabilities
        """
        # Get the x402 extension declaration
        extension_declaration = get_extension_declaration(self.config)

        from a2a.types import AgentCapabilities

        skills = [
            # Payment capability
            AgentSkill(
                id="settle_payment",
                name="Settle Payment",
                description="Process x402 payment settlements",
                tags=["x402", "payment", "settlement"]
            ),

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

        return AgentCard(
            name=self.name,
            description=self.description,
            url=url,
            version="1.0.0",
            skills=skills,  # skills at top level
            capabilities=AgentCapabilities(
                skills=skills
            ),
            defaultInputModes=["text"],
            defaultOutputModes=["text"],
            extensions=[extension_declaration] if extension_declaration else []
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
1. When a user asks about product details, prices, or wants to purchase something, ALWAYS use get_product_details_and_payment_info with the exact product name
2. Only recommend products from the available catalog above
3. Use exact product names from the catalog when calling tools
4. When you receive a settlement request with JSON data containing "action": "settle_payment", "payment_data", and "original_requirements", ALWAYS use the settle_payment tool with the payment_data and original_requirements from the JSON
5. For successful payments, relay the confirmation message
6. For failed payments, explain the error clearly

Remember:
- ALWAYS call get_product_details_and_payment_info for any product inquiry (price, details, purchase)
- ALWAYS call settle_payment when you receive a settlement request JSON with action "settle_payment"
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
        original_requirements: Optional[Dict[str, Any]] = None,
        tool_context: ToolContext = None
    ) -> Dict[str, Any]:
        """Process an x402 payment authorization using the original working approach.

        Args:
            payment_data: Base64 encoded payment header string or PaymentPayload JSON
            original_requirements: Original payment requirements dict
            tool_context: Optional context for controlling tool behavior

        Returns:
            Dict containing:
            - status: 'success' or 'error'
            - message: Human readable description
            - data: Settlement data if successful
        """
        payment_dict = json.loads(payment_data)

        if ("x402Version" in payment_dict or "x402_version" in payment_dict) and "payload" in payment_dict:
            if "x402_version" in payment_dict and "x402Version" not in payment_dict:
                payment_dict["x402Version"] = payment_dict["x402_version"]

            payment_payload = PaymentPayload(**payment_dict)

            if not payment_payload:
                return {
                    "status": "error",
                    "message": "Invalid payment data format",
                    "data": None
                }

            payment_requirements = None
            if self.payment_requirements_store:
                payment_requirements = list(self.payment_requirements_store.values())[-1]
            else:
                return {
                    "status": "error",
                    "message": "No payment requirements found.",
                    "data": None
                }

            try:
                facilitator_url = os.getenv("FACILITATOR_URL", "https://x402-facilitator-sui.vercel.app")
                facilitator_config = FacilitatorConfig(url=facilitator_url)
                facilitator_client = FacilitatorClient(facilitator_config)

                verify_result = await asyncio.wait_for(
                    verify_payment(
                        payment_payload=payment_payload,
                        payment_requirements=payment_requirements,
                        facilitator_client=facilitator_client
                    ),
                    timeout=15.0
                )

                if not verify_result.is_valid:
                    return {
                        "status": "error",
                        "message": f"Payment verification failed: {verify_result.invalid_reason}",
                        "data": None
                    }

                result = await settle_payment(
                    payment_payload=payment_payload,
                    payment_requirements=payment_requirements,
                    facilitator_client=facilitator_client
                )

                if not result.success:
                    return {
                        "status": "error",
                        "message": f"Payment settlement failed: {result.error_reason or 'Unknown settlement error'}",
                        "data": None
                    }

                success_message = "Payment processed successfully"
                explorer_link = None
                if result.transaction:
                    if payment_requirements.network.lower() in ['sui', 'sui-testnet']:
                        explorer_link = f"https://testnet.suivision.xyz/txblock/{result.transaction}"
                        success_message = f"Thank you for your purchase! Payment confirmed on blockchain."

                if tool_context:
                    tool_context.actions.skip_summarization = True

                return {
                    "status": "success",
                    "message": success_message,
                    "data": {
                        "success": True,
                        "message": "Payment processed successfully on blockchain",
                        "transaction": result.transaction,
                        "explorer_link": explorer_link
                    }
                }

            except Exception as e:
                return {
                    "status": "error",
                    "message": str(e),
                    "data": None
                }

    def create_payment_requirements(
        self,
        price_usd: float,
        resource: str,
        description: str = "",
        mime_type: str = "application/json",
        max_timeout_seconds: int = 60,
        output_schema: Dict[str, Any] = None,
        nonce: str = None
    ) -> PaymentRequirements:
        """Create payment requirements for a resource.

        Args:
            price_usd: Price in USD as float (e.g. 0.10)
            resource: Resource identifier
            description: Description of what's being purchased
            mime_type: MIME type of the resource
            max_timeout_seconds: Payment timeout in seconds
            output_schema: Optional schema for the response
            nonce: Optional nonce for payment uniqueness (taskId for Sui)

        Returns:
            PaymentRequirements object
        """

        extra = None
        if self.network.lower() in ['sui', 'sui-testnet']:
            if nonce:
                extra = {"nonce": nonce}
        else:
            extra = {
                "name": "USD Coin",
                "version": "2"
            }
            if nonce:
                extra["nonce"] = nonce

        payment_req = create_payment_requirements(
            price=str(price_usd),
            pay_to_address=self.merchant_address,
            resource=resource,
            network=self.network,
            description=description,
            mime_type=mime_type,
            max_timeout_seconds=max_timeout_seconds,
            output_schema=output_schema or {},
            extra=extra
        )

        return payment_req

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

            if not product_name:
                return {
                    "status": "error",
                    "message": "Product name cannot be empty.",
                    "data": None
                }

            # Find the best matching product from our catalog using fuzzy matching
            products_list = self.product_data.get("products", [])

            # Use a simple fuzzy matching approach first - find products that contain key words
            product_name_lower = product_name.lower()

            # Try to find exact matches first
            product = None
            for p in products_list:
                full_name = f"{p['name']} by {p['brand']}".lower()
                if product_name_lower == full_name or product_name_lower == p['name'].lower():
                    product = p
                    break

            # If no exact match, try partial matching
            if not product:
                # Split search terms and match against product words
                search_words = set(product_name_lower.replace(' by ', ' ').split())
                best_match = None
                best_score = 0

                for p in products_list:
                    product_words = set((p['name'] + ' ' + p['brand']).lower().split())
                    # Count how many search words match product words
                    match_score = len(search_words.intersection(product_words))
                    if match_score > best_score and match_score > 0:
                        best_score = match_score
                        best_match = p

                product = best_match

            if not product:
                print(f"[merchant_agent] Product not found: {product_name}")
                return {
                    "status": "error",
                    "message": f"Product not found: {product_name}",
                    "data": None
                }

            # Format the price for display
            price_display = f"${product['price']:.2f}"

            # Generate a simple SKU
            safe_product_name = product_name.upper().replace(" ", "-")
            sku = f"SKU-{safe_product_name}"

            nonce = None
            if tool_context and hasattr(tool_context, 'invocation_id'):
                nonce = tool_context.invocation_id

            payment_requirements = self.create_payment_requirements(
                price_usd=product['price'],
                resource=f"https://lowes.com/products/{safe_product_name}",
                description=f"{product['brand']} {product['name']}",
                mime_type="application/json",
                max_timeout_seconds=1200,
                output_schema={},
                nonce=nonce
            )

            # Cache the payment requirements
            if nonce:
                self.payment_requirements_store[nonce] = payment_requirements

            # Skip LLM summarization since this is structured data
            if tool_context:
                tool_context.actions.skip_summarization = True

            return {
                "status": "success",
                "sku": sku,
                "price": price_display,
                "payment_requirements": payment_requirements.model_dump()
            }

        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to get product details: {str(e)}",
                "data": None
            }
