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
"""
NeverminedFacilitator - Implements X402 payment verification and settlement
using the Nevermined network via payments-py SDK.
"""
import logging
from typing import override

from .types import (
    SessionKeyPayload,
    PaymentPayload,
    PaymentRequirements,
    SettleResponse,
    VerifyResponse,
)
from x402.facilitator import FacilitatorClient
from payments_py.payments import Payments
from payments_py.common.types import PaymentOptions


logger = logging.getLogger(__name__)


class NeverminedFacilitator(FacilitatorClient):
    """
    A Nevermined-based facilitator that verifies and settles payments using
    the Nevermined network through the payments-py SDK.
    
    This facilitator uses X402 access tokens to verify subscriber permissions
    and settle (burn) credits on-chain.
    """

    def __init__(
        self,
        nvm_api_key: str,
        environment: str = "sandbox",
    ):
        """
        Initialize the NeverminedFacilitator.
        
        Args:
            nvm_api_key: The Nevermined API key for authentication
            environment: The environment to use ('sandbox', 'staging', or 'production')
        """
        self.payments = Payments.get_instance(
            PaymentOptions(
                nvm_api_key=nvm_api_key,
                environment=environment
            )
        )
        logger.info(f"Initialized NeverminedFacilitator for environment: {environment}")

    @override
    async def verify(
        self, payload: PaymentPayload, requirements: PaymentRequirements
    ) -> VerifyResponse:
        """
        Verifies the payment using Nevermined's X402 access token.
        
        This checks if the subscriber has sufficient permissions/credits
        without actually burning them.
        
        Args:
            payload: The payment payload containing the X402 access token
            requirements: The payment requirements (plan_id, agent_id, max_amount)
            
        Returns:
            VerifyResponse indicating if the payment is valid
        """
        logger.info("=== NEVERMINED FACILITATOR: VERIFY ===")
        
        try:
            # Extract X402 access token from payload
            if not isinstance(payload.payload, SessionKeyPayload):
                return VerifyResponse(
                    is_valid=False,
                    invalid_reason="Unsupported payload type - expected SessionKeyPayload"
                )
            
            x402_access_token = payload.payload.session_key
            
            # Extract subscriber address from the payload metadata if available
            # For now, we'll extract it from the token or require it in the requirements
            subscriber_address = requirements.extra.get("subscriber_address") if requirements.extra else None
            
            if not subscriber_address:
                return VerifyResponse(
                    is_valid=False,
                    invalid_reason="Missing subscriber_address in payment requirements"
                )
            
            logger.info(
                f"Verifying permissions for plan: {requirements.plan_id}, "
                f"max_amount: {requirements.max_amount}, "
                f"subscriber: {subscriber_address}"
            )
            
            # Call Nevermined API to verify permissions
            verification = self.payments.facilitator.verify_permissions(
                plan_id=requirements.plan_id,
                max_amount=requirements.max_amount,
                x402_access_token=x402_access_token,
                subscriber_address=subscriber_address,
            )
            
            if verification.get("success"):
                logger.info("✅ Payment verification successful")
                return VerifyResponse(
                    is_valid=True,
                    session_key=x402_access_token
                )
            else:
                error_msg = verification.get("message", "Verification failed")
                logger.warning(f"⛔ Payment verification failed: {error_msg}")
                return VerifyResponse(
                    is_valid=False,
                    invalid_reason=error_msg
                )
                
        except Exception as e:
            logger.error(f"Error during payment verification: {e}", exc_info=True)
            return VerifyResponse(
                is_valid=False,
                invalid_reason=f"Verification error: {str(e)}"
            )

    @override
    async def settle(
        self, payload: PaymentPayload, requirements: PaymentRequirements
    ) -> SettleResponse:
        """
        Settles the payment by burning credits on the Nevermined network.
        
        This executes the actual credit consumption. If the subscriber doesn't
        have enough credits, it will attempt to order more before settling.
        
        Args:
            payload: The payment payload containing the X402 access token
            requirements: The payment requirements (plan_id, agent_id, max_amount)
            
        Returns:
            SettleResponse indicating if the settlement was successful
        """
        logger.info("=== NEVERMINED FACILITATOR: SETTLE ===")
        
        try:
            # Extract X402 access token from payload
            if not isinstance(payload.payload, SessionKeyPayload):
                return SettleResponse(
                    success=False,
                    error_reason="Unsupported payload type - expected SessionKeyPayload"
                )
            
            x402_access_token = payload.payload.session_key
            
            # Extract subscriber address
            subscriber_address = requirements.extra.get("subscriber_address") if requirements.extra else None
            
            if not subscriber_address:
                return SettleResponse(
                    success=False,
                    error_reason="Missing subscriber_address in payment requirements"
                )
            
            logger.info(
                f"Settling permissions for plan: {requirements.plan_id}, "
                f"max_amount: {requirements.max_amount}, "
                f"subscriber: {subscriber_address}"
            )
            
            # Call Nevermined API to settle permissions (burn credits)
            settlement = self.payments.facilitator.settle_permissions(
                plan_id=requirements.plan_id,
                max_amount=requirements.max_amount,
                x402_access_token=x402_access_token,
                subscriber_address=subscriber_address,
            )
            
            if settlement.get("success"):
                tx_hash = settlement.get("txHash")
                credits_burned = settlement.get("data", {}).get("creditsBurned", requirements.max_amount)
                
                logger.info(f"✅ Payment settled successfully! Credits burned: {credits_burned}")
                logger.info(f"Transaction hash: {tx_hash}")
                
                return SettleResponse(
                    success=True,
                    transaction=tx_hash,
                    network=requirements.network
                )
            else:
                error_msg = settlement.get("message", "Settlement failed")
                logger.warning(f"⛔ Payment settlement failed: {error_msg}")
                return SettleResponse(
                    success=False,
                    error_reason=error_msg
                )
                
        except Exception as e:
            logger.error(f"Error during payment settlement: {e}", exc_info=True)
            return SettleResponse(
                success=False,
                error_reason=f"Settlement error: {str(e)}"
            )

