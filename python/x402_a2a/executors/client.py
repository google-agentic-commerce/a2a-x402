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
"""Client-side executor for wallet implementations."""

from typing import Optional
from eth_account import Account

from .base import x402BaseExecutor
from ..types import (
    AgentExecutor,
    RequestContext,
    EventQueue,
    PaymentStatus,
    x402ExtensionConfig,
    x402PaymentRequiredResponse
)
from ..core import process_payment_required
from ..core.utils import create_payment_submission_message


class x402ClientExecutor(x402BaseExecutor):
    """Client-side payment interceptor for buying agents.
    
    Automatically processes payment requirements when services require payment.
    
    Example:
        client = x402ClientExecutor(my_client, config, account)
        # Your client now pays for services automatically!
    """
    
    def __init__(
        self,
        delegate: AgentExecutor,
        config: x402ExtensionConfig,
        account: Account,
        max_value: Optional[int] = None,
        auto_pay: bool = True
    ):
        """Initialize client executor.
        
        Args:
            delegate: Underlying agent executor for service requests
            config: x402 extension configuration  
            account: Ethereum account for payment signing
            max_value: Maximum payment amount willing to pay (optional)
            auto_pay: Whether to automatically process payments (default: True)
        """
        super().__init__(delegate, config)
        self.account = account
        self.max_value = max_value
        self.auto_pay = auto_pay
    
    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue
    ):
        """Payment interceptor: execute → detect payment required → auto-pay."""
        if not self.is_active(context):
            return await self._delegate.execute(context, event_queue)

        # Execute the service request
        result = await self._delegate.execute(context, event_queue)
        
        # Check if payment is required
        task = getattr(context, 'current_task', None)
        if not task:
            return result
            
        status = self.utils.get_payment_status(task)
        
        if status == PaymentStatus.PAYMENT_REQUIRED and self.auto_pay:
            # Auto-process payment and resubmit
            await self._auto_pay(task, event_queue)
            return
        
        return result
    
    async def _auto_pay(self, task, event_queue: EventQueue):
        """Automatically process payment and submit authorization."""
        payment_required = self.utils.get_payment_requirements(task)
        if not payment_required:
            return  # No payment requirements found
        
        try:
            # Process payment using wallet functions (returns PaymentPayload directly)
            payment_payload = process_payment_required(payment_required, self.account, self.max_value)
            
            # Submit payment authorization
            task = self.utils.record_payment_submission(task, payment_payload)
            await event_queue.enqueue_event(task)
            
        except Exception as e:
            # Payment processing failed
            from ..types import SettleResponse, x402ErrorCode
            failure_response = SettleResponse(success=False, network="base", error_reason=f"Payment failed: {e}")
            task = self.utils.record_payment_failure(task, x402ErrorCode.INVALID_SIGNATURE, failure_response)
            await event_queue.enqueue_event(task)
