#!/usr/bin/env python3
"""
Simplified A2A Host Agent with minimal complexity.
"""

import asyncio
import uuid
import os
from typing import Dict, Any, List, Optional

from a2a.client import A2AClient
from a2a.types import Message, TextPart, SendMessageRequest, MessageSendParams, MessageSendConfiguration
from a2a_x402.core.utils import X402Utils
from a2a_x402.types import PaymentStatus
from a2a_x402.core import process_payment_required, process_batch_payment

class SimpleHostAgent:
    """Simplified host agent for A2A communications with batch payment support."""

    def __init__(self):
        self.merchants: Dict[str, Any] = {}
        self.x402_utils = X402Utils()

        # Batch payment state
        self.pending_payments: Dict[str, Any] = {}  # task_id -> {payment_required, context, merchant}
        self.pending_tasks: Dict[str, Any] = {}  # task_id -> (task, client, merchant_name)
        self._task_requests: Dict[str, str] = {}  # task_id -> original_request

        # HTTP client for A2A communications with X402 extension header
        import httpx
        X402_EXTENSION_URI = "https://github.com/google-a2a/a2a-x402/v0.1"
        headers = {"X-A2A-Extensions": X402_EXTENSION_URI}
        self.http_client = httpx.AsyncClient(timeout=30.0, headers=headers)

        # Initialize SUI client for payments
        self._init_sui_client()

        print(f"[Host] Initialized with batch payment processing")

    def _init_sui_client(self):
        """Initialize SUI client from environment."""
        try:
            from pysui import SyncClient
            from pysui.sui.sui_config import SuiConfig

            private_key = os.getenv("SUI_PRIVATE_KEY", "")
            rpc_url = os.getenv("SUI_RPC_URL", "https://fullnode.testnet.sui.io:443")

            if not private_key:
                print("[Host] Warning: SUI_PRIVATE_KEY not set")
                self.sui_client = None
                return

            # Create SUI config and client
            sui_config = SuiConfig.user_config(rpc_url=rpc_url, prv_keys=[private_key])
            self.sui_client = SyncClient(sui_config)

            active_address = self.sui_client.config.active_address
            print(f"[Host] SUI wallet initialized: {active_address}")

        except Exception as e:
            print(f"[Host] Failed to initialize SUI wallet: {e}")
            self.sui_client = None

    async def discover_merchants(self) -> Dict[str, Any]:
        """Discover available A2A merchants."""
        discovered = []

        # Discovery URLs from environment
        discovery_urls = [
            "http://localhost:8001/agents/penny_snacks",
            "http://localhost:8001/agents/tiny_tools",
            "http://localhost:8001/agents/digital_bits"
        ]

        for base_url in discovery_urls:
            try:
                # Get agent card first
                card_url = f"{base_url}/.well-known/agent-card.json"
                response = await self.http_client.get(card_url)
                if response.status_code == 200:
                    card_data = response.json()

                    # Create A2AClient with the httpx_client and url
                    client = A2AClient(httpx_client=self.http_client, url=base_url)

                    merchant_info = {
                        "name": card_data["name"],
                        "description": card_data.get("description", ""),
                        "url": base_url,
                        "skills": [skill["name"] for skill in card_data.get("skills", [])]
                    }

                    discovered.append(merchant_info)
                    self.merchants[card_data["name"]] = {
                        "client": client,
                        "info": merchant_info
                    }

            except Exception as e:
                print(f"[Host] Failed to discover {base_url}: {e}")

        return {
            "status": "success",
            "discovered_merchants": discovered,
            "total_found": len(discovered)
        }

    async def ask_merchant(self, merchant_name: str, question: str) -> Dict[str, Any]:
        """Ask a merchant a question and handle any payment requirements."""
        if merchant_name not in self.merchants:
            return {
                "status": "error",
                "message": f"Merchant '{merchant_name}' not found. Try discovering merchants first."
            }

        try:
            client = self.merchants[merchant_name]["client"]

            # Send message to merchant
            message_id = str(uuid.uuid4())
            message_content = Message(
                messageId=message_id,
                role="user",
                parts=[TextPart(text=question)]
            )
            context_id = str(uuid.uuid4())

            send_request = SendMessageRequest(
                id=str(uuid.uuid4()),
                params=MessageSendParams(
                    id=str(uuid.uuid4()),
                    message=message_content,
                    context_id=context_id,
                    configuration=MessageSendConfiguration(
                        acceptedOutputModes=["text/plain", "text"]
                    )
                )
            )

            response = await client.send_message(send_request)

            # Extract task from response
            task = None
            if hasattr(response, 'root') and hasattr(response.root, 'result'):
                task = response.root.result

            if not task:
                return {"status": "error", "message": "No task returned from merchant"}

            # Check if payment is required
            payment_status = self.x402_utils.get_payment_status(task)
            print(f"[Host] Payment status for {merchant_name}: {payment_status}")

            if payment_status == PaymentStatus.PAYMENT_REQUIRED:
                return await self._handle_payment_required(task, client, merchant_name, question)
            else:
                # Return the actual A2A task object for non-payment cases too
                # This preserves all task metadata and state information
                return task

        except Exception as e:
            import traceback
            traceback.print_exc()
            return {
                "status": "error",
                "message": f"Failed to communicate with {merchant_name}: {str(e)}"
            }

    async def _handle_payment_required(self, task, client, merchant_name: str, original_question: str = ""):
        """Handle payment required response."""
        try:
            # Extract payment requirements using X402Utils
            payment_required = self.x402_utils.get_payment_requirements(task)
            if not payment_required:
                return {"status": "error", "message": "No payment requirements found"}

            payment_context = {
                "task_id": task.id,
                "context_id": task.context_id,
                "merchant": merchant_name,
                "original_request": original_question  # Store the original question for product extraction
            }

            # Collect for batch processing (default behavior)
            # payment_required is an x402PaymentRequiredResponse with accepts[] list
            first_requirement = payment_required.accepts[0] if hasattr(payment_required, 'accepts') else payment_required
            amount_dollars = float(first_requirement.max_amount_required) / 1_000_000
            print(f"[Host] Collecting payment: {merchant_name} - ${amount_dollars:.2f}")

            # Store the original request for this task
            original_request = payment_context.get("original_request", "")
            self._task_requests[task.id] = original_request

            self.pending_payments[task.id] = {
                "payment_required": first_requirement,
                "context": payment_context,
                "merchant": merchant_name
            }
            self.pending_tasks[task.id] = (task, client, merchant_name)

            print(f"[Host] Payment requirement collected for batch processing")
            return {
                "status": "success",
                "message": f"Payment requirement collected: ${amount_dollars:.2f}",
                "task_state": "pending",
                "merchant": merchant_name
            }

        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"status": "error", "message": f"Payment handling failed: {str(e)}"}

    async def process_batch_payments(self) -> Dict[str, Any]:
        """Process all collected payment requirements in batch using proper batch payment transaction."""
        if not self.pending_payments:
            return {"error": "No pending payments"}

        print(f"[Host] Processing batch of {len(self.pending_payments)} payments")

        # Collect all payment requirements for batch processing
        payment_requirements_list = []
        task_mapping = {}  # requirement_index -> (task, client, merchant_name)

        for i, (task_id, data) in enumerate(self.pending_payments.items()):
            payment_requirement = data["payment_required"]
            payment_requirements_list.append(payment_requirement)

            if task_id in self.pending_tasks:
                task, client, merchant_name = self.pending_tasks[task_id]
                task_mapping[i] = (task, client, merchant_name)

        if not payment_requirements_list:
            return {"error": "No valid payment requirements"}

        total_amount = sum(float(req.max_amount_required) / 1_000_000 for req in payment_requirements_list)
        print(f"[Host] Creating batch payment transaction for total: ${total_amount:.2f}")

        # Create batch payment using the new batch payment function
        try:
            payment_payload = process_batch_payment(payment_requirements_list, self.sui_client)
            if not payment_payload:
                return {"error": "Failed to create batch payment"}
        except Exception as e:
            print(f"[Host] Batch payment creation failed: {e}")
            return {"error": f"Failed to create batch payment: {str(e)}"}

        # Submit the batch payment to all pending tasks
        results = []

        for i, (task_id, data) in enumerate(self.pending_payments.items()):
            if i not in task_mapping:
                continue

            task, client, merchant_name = task_mapping[i]
            print(f"[Host] Submitting batch payment to {merchant_name}...")

            try:
                result_task = await self._submit_payment(task, client, merchant_name, payment_payload)
                # Extract info from the returned A2A task object
                if hasattr(result_task, 'status') and hasattr(result_task.status, 'state'):
                    status = "success" if result_task.status.state == "completed" else "partial"
                    message = self._extract_task_message(result_task)
                    transaction_hash = self._extract_tx_hash(message)
                else:
                    # Handle error case where result might still be a dict
                    status = result_task.get("status", "error") if isinstance(result_task, dict) else "error"
                    message = result_task.get("message", "Unknown error") if isinstance(result_task, dict) else "Unknown error"
                    transaction_hash = None

                results.append({
                    "task_id": task_id,
                    "merchant": merchant_name,
                    "status": status,
                    "message": message,
                    "transaction_hash": transaction_hash,
                    "task": result_task  # Include the actual task object for reference
                })
            except Exception as e:
                results.append({
                    "task_id": task_id,
                    "merchant": merchant_name,
                    "status": "error",
                    "error": str(e),
                    "task": None
                })

        successful = [r for r in results if r["status"] == "success"]
        failed = [r for r in results if r["status"] == "error"]

        # Get transaction hash from first successful payment (all should have same hash for batch)
        transaction_hash = None
        if successful:
            transaction_hash = successful[0].get("transaction_hash")

        # Build purchase details before clearing pending payments
        purchase_details = []
        for i, (task_id, data) in enumerate(self.pending_payments.items()):
            if i < len(results):
                merchant = results[i]['merchant']
                amount = float(data["payment_required"].max_amount_required) / 1_000_000

                # Try to extract product details from original request
                product_name = "Product Purchase"
                try:
                    # Get the original request from the task mapping
                    if task_id in self._task_requests:
                        original_request = self._task_requests.get(task_id, "")
                        # Simple extraction - look for product names after "buy", "purchase", etc.
                        import re
                        # This is a simplified extraction - in a real system you'd have structured data
                        match = re.search(r'(?:buy|purchase|order|get)\s+(?:a\s+|an\s+|the\s+)?([^,.!?]+)', original_request.lower())
                        if match:
                            product_name = match.group(1).strip().title()
                except:
                    pass

                purchase_details.append({
                    "merchant": merchant,
                    "amount": amount,
                    "product": product_name,
                    "status": results[i]["status"]
                })

        # Clear pending
        self.pending_payments.clear()
        self.pending_tasks.clear()
        self._task_requests.clear()

        # Create a chat-friendly receipt summary
        if len(successful) == len(results):
            # All payments successful - create receipt
            summary = f"🧾 **Purchase Receipt**\\n\\n"

            # Group by merchant and show items
            merchant_totals = {}
            for detail in purchase_details:
                if detail["status"] == "success":
                    merchant = detail["merchant"]
                    merchant_name = merchant.replace('_merchant', '').replace('_', ' ').title()

                    if merchant not in merchant_totals:
                        merchant_totals[merchant] = {"name": merchant_name, "amount": 0, "items": []}

                    merchant_totals[merchant]["amount"] += detail["amount"]
                    merchant_totals[merchant]["items"].append({
                        "name": detail["product"],
                        "price": detail["amount"]
                    })

            # Display each store section
            for merchant, info in merchant_totals.items():
                summary += f"**{info['name']}**\\n"
                for item in info["items"]:
                    summary += f"• {item['name']}: ${item['price']:.2f}\\n"
                summary += f"Subtotal: ${info['amount']:.2f}\\n\\n"

            # Grand total section
            summary += f"**Total: ${total_amount:.2f}**\\n"
            summary += f"Items: {len(results)}\\n\\n"

            # Transaction details
            if transaction_hash:
                summary += f"🔗 Transaction: `{transaction_hash[:16]}...`\\n"
                summary += f"[View Details](https://testnet.suivision.xyz/txblock/{transaction_hash})\\n\\n"

            summary += f"✅ Batch payment successful\\n"
            summary += f"⚡ Single transaction for all {len(results)} purchases"
        else:
            # Some payments failed - show partial receipt
            summary = f"⚠️ **Partial Purchase Receipt**\\n\\n"

            # Show successful purchases
            if successful:
                summary += f"**✅ Completed:**\\n"
                successful_total = 0
                for detail in purchase_details:
                    if detail["status"] == "success":
                        merchant_name = detail["merchant"].replace('_merchant', '').replace('_', ' ').title()
                        summary += f"• {merchant_name} - {detail['product']}: ${detail['amount']:.2f}\\n"
                        successful_total += detail["amount"]

                summary += f"\\nTotal charged: ${successful_total:.2f}\\n\\n"

            # Show failed purchases
            if failed:
                summary += f"**❌ Failed:**\\n"
                for detail in purchase_details:
                    if detail["status"] != "success":
                        merchant_name = detail["merchant"].replace('_merchant', '').replace('_', ' ').title()
                        summary += f"• {merchant_name} - {detail['product']}\\n"

        return {
            "status": "success",
            "message": summary,
            "processed_count": len(results),
            "successful_count": len(successful),
            "failed_count": len(failed),
            "total_amount": total_amount,
            "results": results
        }

    async def _submit_payment(self, task, client, merchant_name: str, payment_payload):
        """Submit payment to merchant and return updated task."""
        from a2a_x402.core.utils import create_payment_submission_message

        payment_message = create_payment_submission_message(
            task_id=task.id,
            payment_payload=payment_payload,
            text="Payment authorization provided"
        )
        payment_message.context_id = task.context_id

        send_request = SendMessageRequest(
            id=str(uuid.uuid4()),
            params=MessageSendParams(
                id=str(uuid.uuid4()),
                message=payment_message,
                configuration=MessageSendConfiguration(
                    acceptedOutputModes=["text/plain", "text"]
                )
            )
        )

        payment_response = await client.send_message(send_request)

        if hasattr(payment_response, 'root') and hasattr(payment_response.root, 'result'):
            final_task = payment_response.root.result
            # Return the actual A2A task object instead of a dictionary
            # This preserves all X402 metadata including payment receipts, transaction hashes, etc.
            return final_task
        else:
            # For error cases, still return a dictionary since there's no task
            return {"status": "error", "message": "No task returned from payment submission"}

    def _extract_task_message(self, task) -> str:
        """Extract message from task with transaction details."""
        base_message = "Task completed"
        transaction_hash = None

        # Try to get message text
        try:
            if (hasattr(task.status, 'message') and
                hasattr(task.status.message, 'parts') and
                task.status.message.parts):

                first_part = task.status.message.parts[0]
                if hasattr(first_part, 'root') and hasattr(first_part.root, 'text'):
                    base_message = first_part.root.text
                elif hasattr(first_part, 'text'):
                    base_message = str(first_part.text)
                else:
                    base_message = str(first_part)
        except:
            pass

        # Try to get transaction hash from history
        try:
            if hasattr(task, 'history') and task.history:
                for message in task.history:
                    if (hasattr(message, 'metadata') and
                        message.metadata and
                        'x402.payment.receipts' in message.metadata):

                        receipts = message.metadata.get('x402.payment.receipts', [])
                        if receipts and len(receipts) > 0:
                            receipt = receipts[0]
                            if isinstance(receipt, dict) and 'transaction' in receipt:
                                transaction_hash = receipt['transaction']
                                break
        except:
            pass

        # Add transaction details if available
        if transaction_hash:
            explorer_link = f"https://testnet.suivision.xyz/txblock/{transaction_hash}"
            base_message = f"{base_message}\\n\\n🔗 **Transaction Details**\\nHash: `{transaction_hash}`\\n📋 View on Explorer: {explorer_link}"

        return base_message

    def _extract_tx_hash(self, message: str) -> Optional[str]:
        """Extract transaction hash from message."""
        if "Hash: `" in message:
            start = message.find("Hash: `") + 7
            end = message.find("`", start)
            if end > start:
                return message[start:end]
        return None

    def get_merchant_list(self) -> List[str]:
        """Get list of discovered merchants."""
        return list(self.merchants.keys())


# Create global instance for ADK integration
host_agent = SimpleHostAgent()
