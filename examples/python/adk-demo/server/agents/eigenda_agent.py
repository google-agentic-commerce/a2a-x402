import os
import docker
import time
import requests
from typing import override

from a2a.types import AgentCard, AgentCapabilities, AgentSkill
from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.genai import types
from x402.types import PaymentRequirements

from .base_agent import BaseAgent
from a2a_x402.types import X402PaymentRequiredException
from a2a_x402 import (
    X402ExtensionConfig,
    PaymentStatus,
    X402Utils,
    get_extension_declaration
)


class EigenDAService:
    """Service for managing EigenDA Docker container and operations"""
    
    def __init__(self, port: int = 3100):
        self.port = port
        self.base_url = f"http://127.0.0.1:{port}"
        self.container_name = "eigenda-proxy"
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
                command=["--memstore.enabled", "--port", str(self.port)],
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
eigenda_service = EigenDAService()


class EigenDAAgent(BaseAgent):
    """
    Agent that stores text data on EigenDA for $0.01 per string
    """

    def __init__(self, wallet_address: str = "0x3B9b10B8a63B93Ae8F447A907FD1EF067153c4e5"):
        self._wallet_address = wallet_address
        self.x402 = X402Utils()
        self.storage_price = "10000"  # 0.01 USDC (USDC has 6 decimals)
        self.stored_data = {}  # In-memory store for certificates

    def store_text_and_request_payment(self, text_data: str) -> dict:
        """
        Store text data on EigenDA and request payment.
        This is the agent's main tool that requires payment.
        """
        if not text_data:
            return {"error": "Text data cannot be empty."}

        # Ensure EigenDA service is running (synchronously)
        try:
            eigenda_service.ensure_started_sync()
        except Exception as e:
            return {"error": f"Failed to start EigenDA service: {str(e)}"}

        # Store the data in EigenDA first
        try:
            certificate = eigenda_service.submit(text_data)
            
            # Store certificate temporarily
            self.stored_data[certificate[:64]] = {
                "full_certificate": certificate,
                "text": text_data[:100] + "..." if len(text_data) > 100 else text_data,
                "timestamp": time.time()
            }
            
            # Create payment requirements
            requirements = PaymentRequirements(
                scheme="exact",
                network="base-sepolia",
                asset="0x036CbD53842c5426634e7929541eC2318f3dCF7e",
                pay_to=self._wallet_address,
                max_amount_required=self.storage_price,
                description=f"Storage fee for text on EigenDA ({len(text_data)} characters)",
                resource=f"eigenda://certificate/{certificate[:64]}",
                mime_type="text/plain",
                max_timeout_seconds=1200,
                extra={
                    "certificate_prefix": certificate[:64],
                    "data_length": len(text_data),
                    "action": "store_text"
                }
            )

            # Signal that payment is required
            raise X402PaymentRequiredException(f"eigenda_storage_{certificate[:64]}", requirements)
            
        except X402PaymentRequiredException:
            raise  # Re-raise payment exception
        except Exception as e:
            return {"error": f"Failed to store data in EigenDA: {str(e)}"}

    def retrieve_text(self, certificate: str) -> dict:
        """
        Retrieve text data from EigenDA using a certificate.
        This is a free operation.
        """
        if not certificate:
            return {"error": "Certificate cannot be empty."}

        try:
            # Try to get full certificate if we have it stored
            if certificate in self.stored_data:
                full_cert = self.stored_data[certificate]["full_certificate"]
            else:
                # Assume the provided certificate is complete
                full_cert = certificate

            # Retrieve from EigenDA
            text_data = eigenda_service.retrieve(full_cert)
            return {
                "success": True,
                "data": text_data,
                "certificate": certificate[:64]
            }
        except Exception as e:
            return {"error": f"Failed to retrieve data: {str(e)}"}

    def list_stored_certificates(self) -> dict:
        """
        List all stored certificates (for demonstration).
        This is a free operation.
        """
        return {
            "certificates": [
                {
                    "id": cert_id,
                    "preview": data["text"],
                    "timestamp": data["timestamp"]
                }
                for cert_id, data in self.stored_data.items()
            ]
        }

    def before_agent_callback(self, callback_context: CallbackContext):
        """
        Injects a 'virtual' tool response if payment has been verified.
        """
        payment_data = callback_context.state.get('payment_verified_data')
        if payment_data:
            # Consume the data so it's not used again
            del callback_context.state['payment_verified_data']
            
            # Create a tool response indicating successful payment
            tool_response = types.Part(
                function_response=types.FunctionResponse(
                    name="check_payment_status",
                    response=payment_data,
                )
            )
            callback_context.new_user_message = types.Content(parts=[tool_response])

    @override
    def create_agent(self) -> LlmAgent:
        """Creates the LlmAgent instance for EigenDA storage."""
        
        return LlmAgent(
            model="gemini-2.5-flash",
            name="eigenda_storage_agent",
            description="An agent that stores text data on EigenDA for $0.01 per string.",
            instruction="""You are an EigenDA storage agent that helps users store and retrieve text data.
- When a user wants to store text, use the `store_text_and_request_payment` tool. This costs $0.01 per storage operation.
- When a user wants to retrieve text, use the `retrieve_text` tool with the certificate. This is free.
- You can list stored certificates using the `list_stored_certificates` tool.
- If you receive a successful result from the `check_payment_status` tool, confirm the storage with the certificate ID.
- If payment fails, relay the error clearly and politely.
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