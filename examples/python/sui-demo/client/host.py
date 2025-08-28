#!/usr/bin/env python3
"""
A2A-compliant host agent that can discover and communicate with merchants.
"""

import os
import httpx
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

from a2a.client import A2AClient, A2ACardResolver
from a2a.types import Message, MessageSendParams, MessageSendConfiguration, TextPart, SendMessageRequest, Task, TaskStatus

# X402 imports
from a2a_x402.core.wallet import process_payment_required
from a2a_x402.core.utils import X402Utils
from a2a_x402.types import PaymentStatus, x402PaymentRequiredResponse

# Import merchant configuration to dynamically discover all merchants
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'server'))
from merchants import MERCHANTS

# Sui imports for wallet
try:
    from pysui import SyncClient, handle_result
    from pysui.sui.sui_types.address import SuiAddress
    from pysui.sui.sui_config import SuiConfig
    PYSUI_AVAILABLE = True
except ImportError as e:
    PYSUI_AVAILABLE = False

# X402 extension URI constant
X402_EXTENSION_URI = "https://github.com/google-a2a/a2a-x402/v0.1"

# Load environment
load_dotenv()


class A2AHostAgent:
    """A2A-compliant host agent with merchant discovery and X402 payment support."""
    
    def __init__(self):
        # Create HTTP client with X402 extension header
        headers = {"X-A2A-Extensions": X402_EXTENSION_URI}
        self.http_client = httpx.AsyncClient(timeout=30.0, headers=headers)
        self.merchants = {}
        self.merchant_clients = {}
        
        # X402 utilities
        self.x402_utils = X402Utils()
        
        # Initialize Sui wallet if available
        self.sui_client = None
        if PYSUI_AVAILABLE:
            try:
                # Get Sui configuration from environment
                sui_private_key = os.getenv("SUI_PRIVATE_KEY")
                sui_rpc_url = os.getenv("SUI_RPC_URL", "https://fullnode.testnet.sui.io:443")
                
                if sui_private_key:
                    # Create Sui config and client
                    config = SuiConfig.user_config(
                        rpc_url=sui_rpc_url,
                        prv_keys=[sui_private_key]
                    )
                    self.sui_client = SyncClient(config)
                else:
                    pass
            except Exception as e:
                pass
        
        # Max payment value from environment
        self.max_payment_value = int(os.getenv("WALLET_MAX_VALUE", "1000000000"))
        
        # Dynamically generate merchant URLs from configuration
        server_base = os.getenv("MERCHANT_SERVER_URL", "http://localhost:8001")
        self.merchant_urls = [
            f"{server_base}/agents/{merchant_id}"
            for merchant_id in MERCHANTS.keys()
        ]
    
    async def discover_merchants(self) -> Dict[str, Any]:
        """Discover available merchants using A2A protocol."""
        discovered = []
        
        for url in self.merchant_urls:
            try:
                # Use A2ACardResolver to get agent card
                resolver = A2ACardResolver(self.http_client, url)
                card = await resolver.get_agent_card()
                
                # Store merchant info
                self.merchants[card.name] = card
                self.merchant_clients[card.name] = A2AClient(self.http_client, card)
                
                # Extract skills for display
                skills = []
                if card.skills:
                    skills = [skill.name for skill in card.skills]
                
                discovered.append({
                    "name": card.name,
                    "description": card.description,
                    "url": url,
                    "skills": skills
                })
                
                
            except Exception as e:
                import traceback
                traceback.print_exc()
        
        return {
            "status": "success",
            "discovered_merchants": discovered,
            "total_found": len(discovered)
        }
    
    async def ask_merchant(self, merchant_name: str, question: str) -> Dict[str, Any]:
        """Ask a merchant a question using A2A protocol with X402 payment support."""
        if merchant_name not in self.merchant_clients:
            return {
                "status": "error",
                "message": f"Merchant '{merchant_name}' not found. Try discovering merchants first."
            }
        
        try:
            client = self.merchant_clients[merchant_name]
            
            # Create A2A message following protocol
            import uuid
            
            msg_id = str(uuid.uuid4())
            send_request = SendMessageRequest(
                id=msg_id,
                params=MessageSendParams(
                    id=msg_id,
                    message=Message(
                        messageId=msg_id,
                        role="user",
                        parts=[TextPart(text=question)]
                    ),
                    configuration=MessageSendConfiguration(
                        acceptedOutputModes=["text/plain", "text"]
                    )
                )
            )
            
            # Send message to merchant
            response = await client.send_message(send_request)
            
            # Extract task from response
            task = None
            if hasattr(response, 'root') and hasattr(response.root, 'result'):
                task = response.root.result
            
            if task:
                # Check if payment is required
                payment_status = self.x402_utils.get_payment_status(task)
                
                if payment_status == PaymentStatus.PAYMENT_REQUIRED:
                    
                    # Handle payment if wallet is available
                    if self.sui_client:
                        paid_task = await self._handle_payment_required(task, client, merchant_name)
                        if paid_task:
                            task = paid_task
                    else:
                        return {
                            "status": "payment_required",
                            "message": "Payment is required but wallet is not configured",
                            "merchant": merchant_name
                        }
            
            # Extract the final message content to return to ADK
            if task:
                final_message = None
                
                # Add transaction explorer link if task completed with payment
                if task.status.state == "completed":
                    # Look for payment receipts in task history (where the actual payment completion is stored)
                    transaction_hash = None
                    network = 'sui-testnet'
                    
                    if hasattr(task, 'history') and task.history:
                        for message in task.history:
                            if (hasattr(message, 'metadata') and 
                                message.metadata and 
                                'x402.payment.receipts' in message.metadata):
                                
                                payment_receipts = message.metadata.get('x402.payment.receipts', [])
                                if payment_receipts and len(payment_receipts) > 0:
                                    receipt = payment_receipts[0]  # Get first receipt
                                    if isinstance(receipt, dict) and 'transaction' in receipt:
                                        transaction_hash = receipt['transaction']
                                        network = receipt.get('network', 'sui-testnet')
                                        break
                    
                    # Get the base message from task status
                    if (hasattr(task.status, 'message') and 
                        hasattr(task.status.message, 'parts') and 
                        task.status.message.parts):
                        try:
                            base_message = task.status.message.parts[0].root.text
                        except Exception as e:
                            # Try alternative access patterns
                            try:
                                base_message = task.status.message.parts[0].text
                            except:
                                base_message = str(task.status.message.parts[0])
                        
                        # If we found a transaction, enhance the message with transaction details
                        if transaction_hash:
                            # Create explorer link based on network
                            explorer_link = None
                            if network == 'sui-testnet':
                                explorer_link = f"https://testnet.suivision.xyz/txblock/{transaction_hash}"
                            elif network == 'sui-mainnet':
                                explorer_link = f"https://suivision.xyz/txblock/{transaction_hash}"
                            
                            if explorer_link:
                                final_message = f"{base_message}\n\n🔗 **Transaction Details**\nHash: `{transaction_hash}`\n📋 View on Explorer: {explorer_link}"
                            else:
                                final_message = base_message
                        else:
                            final_message = base_message
                
                # Return the enhanced message content directly
                if final_message:
                    return {
                        "status": "success",
                        "message": final_message,
                        "task_state": task.status.state,
                        "merchant": merchant_name
                    }
                else:
                    return {
                        "status": "success", 
                        "message": "Task completed but no message available",
                        "task_state": task.status.state if task.status else "unknown",
                        "merchant": merchant_name
                    }
            else:
                # Fallback to dictionary format if no task
                return {
                    "status": "error",
                    "message": "No task returned from merchant",
                    "merchant": merchant_name
                }
                
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {
                "status": "error",
                "message": f"Failed to communicate with {merchant_name}: {str(e)}"
            }
    
    async def _handle_payment_required(self, task: Task, client: A2AClient, merchant_name: str) -> Optional[Task]:
        """Handle payment required response from merchant."""
        try:
            # Extract payment requirements from task
            payment_required = self.x402_utils.get_payment_requirements(task)
            if not payment_required:
                return None
            
            # Process payment using wallet (creates signed PaymentPayload)
            payment_payload = process_payment_required(
                payment_required, 
                self.sui_client,  # Pass Sui client as account
                self.max_payment_value
            )
            
            # Use the proper correlation method from a2a_x402
            from a2a_x402.core.utils import create_payment_submission_message
            
            # Create properly correlated payment submission message
            payment_message = create_payment_submission_message(
                task_id=task.id,  # CRITICAL: Original task ID for correlation
                payment_payload=payment_payload,
                text="Payment authorization provided"
            )
            # Fix the context_id manually since create_payment_submission_message doesn't set it
            payment_message.context_id = task.context_id
            
            # Submit payment with correlated message
            import uuid
            msg_id = str(uuid.uuid4())
            send_request = SendMessageRequest(
                id=msg_id,
                params=MessageSendParams(
                    id=msg_id,  # This is the message ID, not task ID
                    message=payment_message,
                    configuration=MessageSendConfiguration(
                        acceptedOutputModes=["text/plain", "text"]
                    )
                )
            )
            
            # Send payment and get updated task
            payment_response = await client.send_message(send_request)
            
            # Extract and return updated task
            if hasattr(payment_response, 'root') and hasattr(payment_response.root, 'result'):
                return payment_response.root.result
            
            return None
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return None
    
    def get_merchant_list(self) -> List[str]:
        """Get list of discovered merchants."""
        return list(self.merchants.keys())


# Create global instance for ADK integration
host_agent = A2AHostAgent()