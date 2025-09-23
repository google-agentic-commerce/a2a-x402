import os
import docker
import time
import requests
import logging
import json
from typing import override
from datetime import datetime

from a2a.types import AgentCard, AgentCapabilities, AgentSkill
from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.genai import types
from x402.types import PaymentRequirements

from .base_agent import BaseAgent
from x402_a2a.types import x402PaymentRequiredException
from x402_a2a import (
    x402ExtensionConfig,
    PaymentStatus,
    x402Utils,
    get_extension_declaration
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EigenDAService:
    """Service for managing EigenDA Docker container and operations"""
    
    def __init__(self, payment_key: str, eth_rpc_url: str, port: int = 3100):
        self.port = port
        self.base_url = f"http://127.0.0.1:{port}"
        self.container_name = "eigenda-proxy"
        self.payment_key = payment_key
        self.eth_rpc_url = eth_rpc_url
        self.client = docker.from_env()
        self.container = None
        self._initialized = False

    def ensure_started_sync(self) -> None:
        """Ensure the EigenDA service is running (synchronous version)"""
        if self._initialized:
            return
            
        try:
            # Check if container already exists
            try:
                existing = self.client.containers.get(self.container_name)
                if existing.status == "running":
                    print(f"EigenDA container already running on port {self.port}")
                    self._initialized = True
                    return
                else:
                    print(f"Removing stopped container {self.container_name}")
                    existing.remove()
            except docker.errors.NotFound:
                pass

            print(f"Starting EigenDA Proxy on port {self.port}...")
            self.container = self.client.containers.run(
                "ghcr.io/layr-labs/eigenda-proxy:latest",
                command=["--eigenda.v2.network", "sepolia_testnet", 
                "--eigenda.v2.signer-payment-key-hex", self.payment_key,
                "--storage.backends-to-enable", "V2",
                "--eigenda.v2.cert-verifier-router-or-immutable-verifier-addr", "0x17ec4112c4BbD540E2c1fE0A49D264a280176F0D",
                "--eigenda.v2.eth-rpc", self.eth_rpc_url,
                "--storage.dispersal-backend", "V2",
                "--port", str(self.port)],
                name=self.container_name,
                ports={f"{self.port}/tcp": self.port},
                detach=True,
                remove=False,
            )
            print(f"Container started: {self.container.short_id}")

            # Wait for container to be ready
            print("Waiting for container to be ready...")
            self.container.reload()
            while self.container.status != "running":
                time.sleep(1)
                self.container.reload()

            # Wait for service to be ready
            print("Waiting for service to be ready...")
            start_time = time.time()
            timeout = 30
            while True:
                try:
                    test_response = requests.get(f"{self.base_url}/health", timeout=1)
                    if test_response.status_code == 200:
                        print("EigenDA service is ready!")
                        self._initialized = True
                        break
                except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
                    if time.time() - start_time > timeout:
                        raise Exception(f"Service failed to become ready within {timeout} seconds")
                    time.sleep(1)
                    continue
        except Exception as e:
            print(f"Error starting EigenDA service: {e}")
            raise

    def submit(self, payload: str) -> str:
        """Submit data to EigenDA and return certificate"""
        if not self._initialized:
            raise Exception("EigenDA service not initialized. Call ensure_started() first.")
            
        print(f"Submitting payload to EigenDA: '{payload[:50]}...'")
        response = requests.post(
            f"{self.base_url}/put",
            params={"commitment_mode": "standard"},
            data=payload.encode("utf-8"),
        )
        cert_hex = response.content.hex()
        print(f"Data stored with certificate: {cert_hex[:64]}...")
        return cert_hex

    def retrieve(self, certificate_hex: str) -> str:
        """Retrieve data from EigenDA using certificate"""
        if not self._initialized:
            raise Exception("EigenDA service not initialized. Call ensure_started() first.")
            
        print(f"Retrieving data from EigenDA with certificate: {certificate_hex[:64]}...")
        response = requests.get(
            f"{self.base_url}/get/{certificate_hex}",
            params={"commitment_mode": "standard"},
        )
        return response.text


# Single instance of EigenDA service
eigenda_service = EigenDAService(os.environ.get("PAYMENT_PRIVATE_KEY"), os.environ.get("ETH_RPC_URL"))


class EigenDAAgent(BaseAgent):
    """
    Agent that stores text data on EigenDA for $0.01 per string
    """

    def __init__(self, wallet_address: str = "0x3B9b10B8a63B93Ae8F447A907FD1EF067153c4e5"):
        self._wallet_address = wallet_address
        self.x402 = x402Utils()
        self.storage_price = "10000"  # 0.01 USDC (USDC has 6 decimals)
        self.stored_data = {}  # In-memory store for certificates

    def store_text_and_request_payment(self, text_data: str) -> dict:
        """
        Store text data on EigenDA and request payment.
        This is the agent's main tool that requires payment.
        """
        logger.info(f"Store request received for {len(text_data) if text_data else 0} characters")
        
        # Validate input
        if not text_data:
            logger.warning("Empty text data provided")
            return {"error": "Text data cannot be empty. Please provide some text to store."}
        
        if not isinstance(text_data, str):
            logger.warning(f"Invalid data type: {type(text_data)}")
            return {"error": "Text data must be a string."}
        
        # Check byte limit of 16,252,897 bytes
        byte_length = len(text_data.encode('utf-8'))
        if byte_length > 16252897:
            logger.warning(f"Text too large: {byte_length} bytes (maximum allowed is 16,252,897 bytes)")
            return {"error": f"Text is too large ({byte_length} bytes). Maximum allowed is 16,252,897 bytes."}

        # Ensure EigenDA service is running (synchronously)
        try:
            eigenda_service.ensure_started_sync()
            logger.info("EigenDA service is ready")
        except Exception as e:
            logger.error(f"Failed to start EigenDA service: {e}")
            return {"error": f"Storage service temporarily unavailable. Please try again in a moment."}

        # Store the data in EigenDA first
        try:
            certificate = eigenda_service.submit(text_data)
            logger.info(f"=== EIGENDA STORAGE ===")
            logger.info(f"Full certificate received: {certificate[:128]}...")
            logger.info(f"Certificate length: {len(certificate)} chars")
            
            # Store certificate with enhanced metadata
            cert_id = certificate[:64]
            logger.info(f"Using certificate prefix (first 64 chars): {cert_id}")
            
            self.stored_data[cert_id] = {
                "full_certificate": certificate,
                "text": text_data,  # Store full text for retrieval
                "preview": text_data[:100] + "..." if len(text_data) > 100 else text_data,
                "timestamp": time.time(),
                "datetime": datetime.now().isoformat(),
                "size": len(text_data)
            }
            
            # Log for debugging
            logger.info(f"Certificate mapping stored: {cert_id} -> {len(text_data)} chars")
            logger.info(f"Stored data keys: {list(self.stored_data.keys())}")
            logger.info(f"=== END EIGENDA STORAGE ===")
            
            # Create payment requirements with enhanced metadata
            requirements = PaymentRequirements(
                scheme="exact",
                network="base-sepolia",
                asset="0x036CbD53842c5426634e7929541eC2318f3dCF7e",
                pay_to=self._wallet_address,
                max_amount_required=self.storage_price,
                description=f"Storage fee for {len(text_data)} characters on EigenDA",
                resource=f"eigenda://certificate/{cert_id}",
                mime_type="text/plain",
                max_timeout_seconds=1200,
                extra={
                    "certificate_prefix": cert_id,
                    "full_certificate": certificate,  # Include full certificate
                    "data_length": len(text_data),
                    "action": "store_text",
                    "timestamp": time.time()
                }
            )

            # Signal that payment is required
            logger.info(f"Payment requested for certificate {cert_id}")
            raise x402PaymentRequiredException(f"eigenda_storage_{cert_id}", requirements)
            
        except x402PaymentRequiredException:
            raise  # Re-raise payment exception
        except Exception as e:
            logger.error(f"Failed to store data: {e}", exc_info=True)
            return {"error": f"Storage operation failed: {str(e)}. Please try again."}

    def retrieve_text(self, certificate: str) -> dict:
        """
        Retrieve text data from EigenDA using a certificate.
        This is a free operation.
        """
        logger.info(f"Retrieve request for certificate: {certificate[:64] if certificate else 'empty'}")
        
        # Validate input
        if not certificate:
            logger.warning("Empty certificate provided")
            return {"error": "Certificate cannot be empty. Please provide a valid certificate ID."}
        
        if not isinstance(certificate, str):
            logger.warning(f"Invalid certificate type: {type(certificate)}")
            return {"error": "Certificate must be a string."}
        
        # Clean the certificate (remove any whitespace or newlines)
        certificate = certificate.strip()
        
        try:
            # Check our local cache first for the full certificate
            cert_prefix = certificate[:64] if len(certificate) >= 64 else certificate
            full_cert = None
            
            # Try to find in our stored data
            if cert_prefix in self.stored_data:
                logger.info(f"Certificate found in local cache: {cert_prefix}")
                stored_info = self.stored_data[cert_prefix]
                full_cert = stored_info["full_certificate"]
                
                # Try to get from local cache first (faster)
                if "text" in stored_info and stored_info["text"]:
                    logger.info(f"Returning cached text for {cert_prefix}")
                    return {
                        "success": True,
                        "data": stored_info["text"],
                        "certificate": cert_prefix,
                        "cached": True,
                        "stored_at": stored_info.get("datetime", "unknown")
                    }
            else:
                # Check if it might be a full certificate
                if len(certificate) > 64:
                    logger.info("Using provided certificate as full certificate")
                    full_cert = certificate
                    cert_prefix = certificate[:64]
                else:
                    logger.warning(f"Certificate {cert_prefix} not found in local store")
                    return {
                        "error": f"Certificate '{certificate}' not found. Please check the certificate ID and try again.",
                        "hint": "Use 'list_stored_certificates' to see available certificates."
                    }

            # Retrieve from EigenDA
            logger.info(f"Retrieving from EigenDA with certificate: {cert_prefix}")
            text_data = eigenda_service.retrieve(full_cert)
            
            # Update local cache with retrieved data
            if cert_prefix in self.stored_data:
                self.stored_data[cert_prefix]["text"] = text_data
                self.stored_data[cert_prefix]["last_retrieved"] = time.time()
            
            logger.info(f"Successfully retrieved {len(text_data)} characters")
            return {
                "success": True,
                "data": text_data,
                "certificate": cert_prefix,
                "cached": False
            }
            
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error retrieving data: {e}")
            if "404" in str(e):
                return {
                    "error": f"Certificate '{certificate[:64]}' not found on EigenDA.",
                    "hint": "The certificate may be invalid or the data may have expired."
                }
            return {"error": f"Network error retrieving data: {str(e)}"}
        except Exception as e:
            logger.error(f"Failed to retrieve data: {e}", exc_info=True)
            return {"error": f"Failed to retrieve data: {str(e)}. Please check the certificate and try again."}

    def list_stored_certificates(self) -> dict:
        """
        List all stored certificates (for demonstration).
        This is a free operation.
        """
        logger.info(f"List request - {len(self.stored_data)} certificates available")
        
        if not self.stored_data:
            return {
                "message": "No certificates stored yet.",
                "hint": "Store some text first using 'store' command.",
                "certificates": []
            }
        
        # Sort by timestamp (most recent first)
        sorted_certs = sorted(
            self.stored_data.items(),
            key=lambda x: x[1].get("timestamp", 0),
            reverse=True
        )
        
        certificates_list = []
        for cert_id, data in sorted_certs:
            cert_info = {
                "certificate_id": cert_id,
                "preview": data.get("preview", "N/A"),
                "size": data.get("size", 0),
                "stored_at": data.get("datetime", "unknown"),
                "timestamp": data.get("timestamp", 0)
            }
            
            # Add retrieval info if available
            if "last_retrieved" in data:
                cert_info["last_retrieved"] = datetime.fromtimestamp(data["last_retrieved"]).isoformat()
            
            certificates_list.append(cert_info)
        
        logger.info(f"Returning {len(certificates_list)} certificates")
        return {
            "total": len(certificates_list),
            "certificates": certificates_list,
            "message": f"Found {len(certificates_list)} stored certificate(s)"
        }

    def before_agent_callback(self, callback_context: CallbackContext):
        """
        Injects a 'virtual' tool response if payment has been verified.
        """
        payment_data = callback_context.state.get('payment_verified_data')
        if payment_data:
            cert_id = payment_data.get('certificate_id')
            logger.info(f"=== PAYMENT VERIFICATION CALLBACK ===")
            logger.info(f"Processing payment verification for certificate: {cert_id if cert_id else 'NOT PROVIDED'}")
            logger.info(f"Full payment data received: {payment_data}")
            
            # Consume the data so it's not used again
            del callback_context.state['payment_verified_data']
            
            # Enhance payment data with additional info
            if cert_id and cert_id in self.stored_data:
                stored_info = self.stored_data[cert_id]
                payment_data['data_size'] = stored_info.get('size', 0)
                payment_data['stored_at'] = stored_info.get('datetime', 'unknown')
                payment_data['full_text'] = stored_info.get('text', '')[:100]  # Include preview
                logger.info(f"Enhanced payment data with storage info for {cert_id}")
                logger.info(f"Certificate {cert_id} found in local storage with {stored_info.get('size', 0)} chars")
            elif cert_id:
                logger.warning(f"Certificate {cert_id} not found in local storage - may need to retrieve from EigenDA")
            else:
                logger.error("No certificate_id in payment_data - this should not happen!")
            
            # Create a tool response indicating successful payment
            tool_response = types.Part(
                function_response=types.FunctionResponse(
                    name="payment_verification",  # Changed from check_payment_status
                    response=payment_data,
                )
            )
            callback_context.new_user_message = types.Content(parts=[tool_response])
            logger.info(f"Payment verification injected with certificate_id: {cert_id}")
            logger.info("=== END PAYMENT VERIFICATION CALLBACK ===")

    @override
    def create_agent(self) -> LlmAgent:
        """Creates the LlmAgent instance for EigenDA storage."""
        
        return LlmAgent(
            model="gemini-2.5-flash",
            name="eigenda_storage_agent",
            description="An agent that stores text data on EigenDA for $0.01 per string.",
            instruction="""You are an EigenDA storage agent that helps users store and retrieve text data on decentralized storage.

## Core Responsibilities:
1. Store text data on EigenDA blockchain storage (costs $0.01 per operation)
2. Retrieve stored text using certificates (free operation)
3. List stored certificates for the user (free operation)

## How to Handle Requests:

### STORING TEXT:
- When a user wants to store text, be flexible in understanding their request:
  - "store this: Hello" → extract "Hello"
  - "store hello world" → extract "hello world"
  - "save my message: test" → extract "test"
  - "hello world" (if context suggests storage) → extract "hello world"
  1. Use the `store_text_and_request_payment` tool with the extracted text
  2. The system will request payment of $0.01
  3. Wait for user confirmation
  4. After payment confirmation, you'll receive payment verification data

### RETRIEVING TEXT:
- When a user wants to retrieve text (e.g., "get certificate abc123", "retrieve my data", "fetch stored text"):
  1. Use the `retrieve_text` tool with the certificate ID
  2. Return the exact stored text to the user
  3. This operation is always free

### LISTING CERTIFICATES:
- When a user wants to see stored items (e.g., "list", "show certificates", "what have I stored"):
  1. Use the `list_stored_certificates` tool
  2. Display all certificates with previews and timestamps

## CRITICAL RESPONSE FORMATS:

### After Successful Payment:
- You will receive a function_response with payment verification data
- Simply confirm the successful storage without mentioning the certificate ID (since it was already shown during payment request)
- ALWAYS respond with EXACTLY this format:
  "✅ Payment successful! Your data has been stored on EigenDA."

### For Retrieval Success:
- Return the exact text that was stored
- Format: "Retrieved data: [exact_stored_text]"

### For Errors:
- Be specific about what went wrong
- Suggest corrective actions
- Never use placeholder values or fake certificate IDs

## Important Rules:
1. NEVER generate fake or placeholder certificate IDs
2. The certificate ID is shown to the user during the payment request
3. Do NOT repeat the certificate ID in the success message after payment
4. Be consistent in response formatting
5. Preserve exact text when storing and retrieving
6. The certificate ID is a 64-character hexadecimal string
7. Keep the success message simple and clean
8. Be flexible in understanding storage requests - extract the text to store
9. Don't expose internal processing or errors unless absolutely necessary
""",
            tools=[self.store_text_and_request_payment, self.retrieve_text, self.list_stored_certificates],
            before_agent_callback=self.before_agent_callback,
        )

    @override
    def create_agent_card(self, url: str) -> AgentCard:
        """Creates the AgentCard for this agent."""
        skills = [
            AgentSkill(
                id="store_text",
                name="Store Text on EigenDA",
                description="Stores text data on EigenDA decentralized storage for $0.01 per operation.",
                tags=["storage", "eigenda", "x402", "text"],
                examples=[
                    "Store this message: Hello, EigenDA!",
                    "I want to save this text on EigenDA",
                    "Can you store my document on decentralized storage?",
                ],
            ),
            AgentSkill(
                id="retrieve_text",
                name="Retrieve Text from EigenDA",
                description="Retrieves previously stored text using a certificate ID.",
                tags=["storage", "eigenda", "retrieval"],
                examples=[
                    "Get the text with certificate abc123",
                    "Retrieve my stored data",
                    "Show me what's stored under this certificate",
                ],
            )
        ]
        return AgentCard(
            name="EigenDA Storage Agent",
            description="This agent stores and retrieves text data on EigenDA for $0.01 per storage operation.",
            url=url,
            version="1.0.0",
            defaultInputModes=["text", "text/plain"],
            defaultOutputModes=["text", "text/plain"],
            capabilities=AgentCapabilities(
                streaming=False,
                extensions=[
                    get_extension_declaration(
                        description="Supports payments using the x402 protocol for storage operations.",
                        required=True,
                    )
                ],
            ),
            skills=skills,
        )