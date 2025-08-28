#!/usr/bin/env python3
"""
Core A2A-compliant merchant agent implementation with X402 payment integration.
"""

import asyncio
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from a2a.server.agent_execution import AgentExecutor
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import AgentCard, AgentSkill, AgentCapabilities, TaskState
from a2a.utils.message import new_agent_text_message

from a2a_x402.extension import get_extension_declaration
from a2a_x402.executors.base import X402BaseExecutor
from a2a_x402.types import X402_EXTENSION_URI
from a2a_x402.types import (
    X402ExtensionConfig, X402ServerConfig, PaymentStatus,
    x402PaymentRequiredResponse, PaymentRequirements, SettleResponse,
    FacilitatorClient, X402ErrorCode
)
from a2a_x402.core import create_payment_requirements, verify_payment, settle_payment
from x402.common import find_matching_payment_requirements


@dataclass
class MerchantConfig:
    """Configuration for a merchant."""
    name: str
    description: str
    products: List[Dict[str, Any]]


class MerchantAgent:
    """Core merchant business logic."""

    def __init__(self, config: MerchantConfig):
        self.config = config

    def list_products(self) -> str:
        products = "\n".join([
            f"• {p['name']} - ${p['price']:.3f}"
            for p in self.config.products
        ])
        return f"📦 **{self.config.description} Catalog**\n\n{products}\n\n💡 To purchase an item, use the exact product name from this list!"

    def purchase_product(self, request: str) -> str:
        """Process purchase request and return message."""
        return f"🛒 Processing your purchase request at {self.config.description}.\n\nYour order: {request}\n\n✅ Payment verified! Your products will be shipped to you soon."


class MerchantExecutor(AgentExecutor):

    def __init__(self, merchant_agent: MerchantAgent):
        self.merchant = merchant_agent

    async def execute(self, context: RequestContext, event_queue: EventQueue):
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        response = self.merchant.list_products()

        await updater.update_status(
            TaskState.completed,
            message=new_agent_text_message(response)
        )

    async def cancel(self):
        pass


class MerchantX402Executor(X402BaseExecutor):

    def __init__(
        self,
        base_merchant_executor: MerchantExecutor,
        config: X402ExtensionConfig,
        server_config: X402ServerConfig,
        facilitator_client: Optional[FacilitatorClient] = None
    ):
        super().__init__(base_merchant_executor, config)
        self.server_config = server_config
        self.facilitator_client = facilitator_client or FacilitatorClient()
        self.merchant = base_merchant_executor.merchant
        
        self._payment_requirements_store: Dict[str, List[PaymentRequirements]] = {}
        self._task_requests: Dict[str, str] = {}


    def _is_purchase_request(self, user_message: str) -> bool:
        purchase_keywords = [
            'buy', 'purchase', 'order', 'checkout', 'pay for',
            'i want to buy', 'i need to buy', 'i\'ll take', 'i\'d like to buy'
        ]
        return any(keyword in user_message.lower() for keyword in purchase_keywords)

    def _find_requested_product(self, user_message: str) -> Optional[Dict[str, Any]]:
        """Find the product mentioned in the user's purchase request."""
        user_message_lower = user_message.lower()
        
        # Try to find product by exact name match first
        for product in self.merchant.config.products:
            product_name_lower = product['name'].lower()
            if product_name_lower in user_message_lower:
                return product
        
        # If no exact match, return None and we'll use default price
        return None

    async def execute(self, context: RequestContext, event_queue: EventQueue):
        correlated_task_id = None
        if context.message:
            correlated_task_id = getattr(context.message, 'task_id', None)

        task_id_to_use = correlated_task_id or getattr(context, 'task_id', None)

        task = getattr(context, 'current_task', None) or getattr(context, 'task', None)
        if not task and task_id_to_use:
            from a2a.types import Task, TaskStatus, TaskState
            task = Task(
                id=task_id_to_use,
                contextId=getattr(context, 'context_id', 'unknown'),
                status=TaskStatus(state=TaskState.working)
            )

        if not task:
            return await self._delegate.execute(context, event_queue)

        status = self.utils.get_payment_status(task)
        if not status and context.message:
            status = self.utils.get_payment_status_from_message(context.message)

        if status == PaymentStatus.PAYMENT_SUBMITTED:
            return await self._process_paid_request(task, context, event_queue)

        user_message = ""
        if context.message and context.message.parts:
            for part in context.message.parts:
                if hasattr(part, 'root') and hasattr(part.root, 'text'):
                    user_message = part.root.text
                elif hasattr(part, 'text'):
                    user_message = part.text

        if self._is_purchase_request(user_message):
            x402_active = (
                hasattr(context, 'requested_extensions') and
                context.requested_extensions and
                X402_EXTENSION_URI in context.requested_extensions
            )

            if x402_active:
                return await self._require_payment(task, context, event_queue, user_message)
            else:
                purchase_response = self.merchant.purchase_product(user_message)
                await TaskUpdater(event_queue, task.id, getattr(context, 'context_id', 'unknown')).update_status(
                    TaskState.completed,
                    message=new_agent_text_message(purchase_response)
                )
        else:
            return await self._delegate.execute(context, event_queue)

    async def _require_payment(self, task, context: RequestContext, event_queue: EventQueue, user_message: str):
        self._task_requests[task.id] = user_message
        
        # Find the requested product and fail if not found
        requested_product = self._find_requested_product(user_message)
        if not requested_product:
            error_message = f"❌ Product not found in our catalog. Please check the product name and try again.\n\n💡 Use exact product names from our catalog. Ask 'What products do you have?' to see available items."
            await TaskUpdater(event_queue, task.id, getattr(context, 'context_id', 'unknown')).update_status(
                TaskState.completed,
                message=new_agent_text_message(error_message)
            )
            return
        
        product_price = str(requested_product['price'])
        
        requirements = create_payment_requirements(
            price=product_price,
            pay_to_address=self.server_config.pay_to_address,
            resource=self.server_config.resource,
            network=self.server_config.network,
            description=f"Purchase: {user_message}",
            mime_type=self.server_config.mime_type,
            max_timeout_seconds=self.server_config.max_timeout_seconds,
            extra={"nonce": task.id}
        )

        accepts_array = [requirements]
        self._payment_requirements_store[task.id] = accepts_array
        payment_required = x402PaymentRequiredResponse(
            x402_version=1,
            accepts=accepts_array,
            error=""
        )

        task = self.utils.create_payment_required_task(task, payment_required)
        await event_queue.enqueue_event(task)

    async def _process_paid_request(self, task, context: RequestContext, event_queue: EventQueue):
        payment_payload = self.utils.get_payment_payload(task)

        if not payment_payload and context.message:
            payment_payload = self.utils.get_payment_payload_from_message(context.message)

        if not payment_payload:
            return await self._fail_payment(task, X402ErrorCode.SETTLEMENT_FAILED, "Missing payment data", event_queue)

        accepts_array = self._payment_requirements_store.get(task.id)
        if not accepts_array:
            return await self._fail_payment(task, X402ErrorCode.SETTLEMENT_FAILED, "Missing payment requirements", event_queue)

        requirements = find_matching_payment_requirements(accepts_array, payment_payload)
        if not requirements:
            return await self._fail_payment(task, X402ErrorCode.INVALID_AMOUNT, "No matching payment requirements", event_queue)

        try:
            try:
                verify_response = await asyncio.wait_for(
                    verify_payment(payment_payload, requirements, self.facilitator_client),
                    timeout=15.0
                )
                if not verify_response.is_valid:
                    return await self._fail_payment(task, X402ErrorCode.INVALID_SIGNATURE, verify_response.invalid_reason or "Invalid payment", event_queue)
            except asyncio.TimeoutError:
                return await self._fail_payment(task, X402ErrorCode.SETTLEMENT_FAILED, "Verification timeout", event_queue)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return await self._fail_payment(task, X402ErrorCode.SETTLEMENT_FAILED, f"Verification failed: {e}", event_queue)

        if not hasattr(task.status, 'message') or not task.status.message:
            from a2a.types import Message, TextPart
            task.status.message = Message(
                messageId=f"{task.id}-status",
                role="agent",
                parts=[TextPart(kind="text", text="Payment is being processed.")],
                metadata={}
            )

        if not hasattr(task.status.message, 'metadata') or not task.status.message.metadata:
            task.status.message.metadata = {}

        task.status.message.metadata[self.utils.STATUS_KEY] = PaymentStatus.PAYMENT_PENDING.value

        try:
            original_request = self._task_requests.get(task.id, "")
            purchase_response = self.merchant.purchase_product(original_request)

            await TaskUpdater(event_queue, task.id, getattr(context, 'context_id', 'unknown')).update_status(
                TaskState.working,
                message=new_agent_text_message(purchase_response)
            )

        except Exception as e:
            return await self._fail_payment(task, X402ErrorCode.SETTLEMENT_FAILED, f"Service failed: {e}", event_queue)

        try:
            settle_response = await settle_payment(payment_payload, requirements, self.facilitator_client)

            if settle_response.success:
                task = self.utils.record_payment_success(task, settle_response)
                paid_amount = float(requirements.max_amount_required) / 1_000_000  # Convert from microdollars to dollars
                final_response = f"🛒 Purchase completed successfully!\n\nYour order: {original_request}\n💰 Price Paid: ${paid_amount:.3f}\n\n✅ Payment verified and processed."
                self._payment_requirements_store.pop(task.id, None)
                self._task_requests.pop(task.id, None)
                
                await TaskUpdater(event_queue, task.id, getattr(context, 'context_id', 'unknown')).update_status(
                    TaskState.completed,
                    message=new_agent_text_message(final_response)
                )
            else:
                error_code = X402ErrorCode.INSUFFICIENT_FUNDS if "insufficient" in (settle_response.error_reason or "").lower() else X402ErrorCode.SETTLEMENT_FAILED
                task = self.utils.record_payment_failure(task, error_code, settle_response)
                self._payment_requirements_store.pop(task.id, None)
                self._task_requests.pop(task.id, None)
                await event_queue.enqueue_event(task)
        except Exception as e:
            await self._fail_payment(task, X402ErrorCode.SETTLEMENT_FAILED, f"Settlement failed: {e}", event_queue)

    async def _fail_payment(self, task, error_code: str, error_reason: str, event_queue: EventQueue):
        failure_response = SettleResponse(success=False, network=self.server_config.network, error_reason=error_reason)
        task = self.utils.record_payment_failure(task, error_code, failure_response)
        self._payment_requirements_store.pop(task.id, None)
        self._task_requests.pop(task.id, None)
        await event_queue.enqueue_event(task)


def create_merchant_card(name: str, config: MerchantConfig, url: str) -> AgentCard:
    """Create A2A-compliant agent card with X402 payment support."""
    skills = [
        AgentSkill(
            id="list_products",
            name="List Products",
            description="Browse available products and prices (free)",
            tags=["products", "catalog", "browse"],
            inputModes=["text/plain"],
            outputModes=["text/plain"],
            examples=[
                "What do you have?",
                "Show me your products",
                "What's available?",
                "List your inventory"
            ]
        ),
        AgentSkill(
            id="purchase_products",
            name="Purchase Products",
            description="Buy products from this store (requires payment)",
            tags=["purchase", "buy", "payment", "x402"],
            inputModes=["text/plain"],
            outputModes=["text/plain"],
            examples=[
                "I want to buy a [product name]",
                "Purchase the [specific item]",
                "Buy the [item] for $[price]",
                "I'd like to purchase [item description]"
            ]
        )
    ]

    capabilities = AgentCapabilities(
        skills=skills,
        extensions=[
            get_extension_declaration(
                description="Supports x402 payments for product purchases",
                required=True
            )
        ]
    )

    return AgentCard(
        name=f"{name}_merchant",
        description=config.description,
        url=url,
        version="1.0.0",
        skills=skills,
        capabilities=capabilities,
        defaultInputModes=["text/plain"],
        defaultOutputModes=["text/plain"]
    )