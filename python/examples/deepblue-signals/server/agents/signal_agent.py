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
DeepBlue Signal Agent — sells live 5-minute BTC/ETH/SOL/XRP directional signals
from the DeepBlue autonomous Polymarket trading bot via x402 A2A payments.

Signal source: https://api.deepbluebase.xyz
Price: 2000 USDC atomic units = $0.002 USDC (6 decimals) on Base Sepolia
"""
import os
from typing import override

import httpx
from a2a.types import AgentCard, AgentCapabilities, AgentSkill
from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.genai import types
from x402_a2a import get_extension_declaration, x402Utils
from x402_a2a.types import PaymentRequirements, x402PaymentRequiredException

# The abstract agent factory interface
from .base_agent import BaseAgent

# Supported coins and their display names
SUPPORTED_COINS = {"BTC", "ETH", "SOL", "XRP"}

# Price in USDC atomic units (6 decimals). 2000 = $0.002 USDC.
SIGNAL_PRICE_ATOMIC = "2000"

# USDC contract on Base Sepolia
USDC_BASE_SEPOLIA = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"

# Default DeepBlue API endpoint (overridable via env)
DEEPBLUE_API_URL = os.getenv("DEEPBLUE_API_URL", "https://api.deepbluebase.xyz")


class DeepBlueSignalAgent(BaseAgent):
    """
    A merchant agent that sells live 5-minute directional trading signals for
    BTC, ETH, SOL, and XRP. Payment is collected via the x402 A2A protocol
    before the signal data is delivered.

    Architecture:
    - `get_trading_signal(coin)` raises x402PaymentRequiredException to trigger
      the x402 payment flow managed by x402MerchantExecutor.
    - After payment verification, `before_agent_callback` injects the live signal
      fetched from api.deepbluebase.xyz into the session so the LLM can deliver it.
    """

    def __init__(
        self,
        wallet_address: str | None = None,
    ):
        self._wallet_address = wallet_address or os.getenv(
            "MERCHANT_WALLET_ADDRESS",
            "0x47ffc880cfF2e8F18fD9567faB5a1fBD217B5552",
        )
        self.x402 = x402Utils()

    # ------------------------------------------------------------------
    # Agent tools
    # ------------------------------------------------------------------

    def get_trading_signal(self, coin: str) -> dict:
        """
        Returns a live 5-minute directional trading signal (UP/DOWN) with a
        confidence score for the requested coin.

        Payment of $0.002 USDC is required before the signal is delivered.

        Args:
            coin: The ticker symbol to fetch a signal for. Must be one of:
                  BTC, ETH, SOL, XRP (case-insensitive).

        Raises:
            x402PaymentRequiredException: Always — signals require payment.
            ValueError: If the coin is not supported.
        """
        coin = coin.upper().strip()
        if coin not in SUPPORTED_COINS:
            return {
                "error": f"Unsupported coin '{coin}'. Supported: {', '.join(sorted(SUPPORTED_COINS))}."
            }

        requirements = PaymentRequirements(
            scheme="exact",
            network="base-sepolia",
            asset=USDC_BASE_SEPOLIA,
            pay_to=self._wallet_address,
            max_amount_required=SIGNAL_PRICE_ATOMIC,
            description=f"{coin} 5-min trading signal from DeepBlue",
            resource=f"{DEEPBLUE_API_URL}/signals?coin={coin}",
            mime_type="application/json",
            max_timeout_seconds=1200,
            extra={
                "name": "USDC",
                "version": "2",
                "signal": {
                    "coin": coin,
                    "interval": "5m",
                    "source": "DeepBlue autonomous trading bot",
                },
            },
        )

        # Signal to x402MerchantExecutor that payment is required.
        # The wrapper intercepts this exception and manages the full A2A flow.
        raise x402PaymentRequiredException(coin, requirements)

    # ------------------------------------------------------------------
    # Payment callback — fetch and inject signal after payment verified
    # ------------------------------------------------------------------

    def before_agent_callback(self, callback_context: CallbackContext):
        """
        After x402MerchantExecutor verifies payment, it writes
        ``payment_verified_data`` into the session state. This callback reads
        that data, fetches the live signal from the DeepBlue API, and injects
        the result as a virtual tool response so the LLM can present it to the
        client agent without asking for payment again.
        """
        payment_data = callback_context.state.get("payment_verified_data")
        if not payment_data:
            return

        # Consume the payment data so it is only acted on once per session.
        del callback_context.state["payment_verified_data"]

        coin = payment_data.get("coin", "BTC")
        signal_payload = _fetch_signal(coin)

        # Build a virtual tool-response content object. The LLM will see this
        # as the return value of `get_trading_signal` and present the signal.
        tool_response = types.Part(
            function_response=types.FunctionResponse(
                name="get_trading_signal",
                response={
                    "coin": coin,
                    "signal": signal_payload,
                    "payment_status": "SUCCESS",
                },
            )
        )
        callback_context.new_user_message = types.Content(parts=[tool_response])

    # ------------------------------------------------------------------
    # BaseAgent interface
    # ------------------------------------------------------------------

    @override
    def create_agent(self) -> LlmAgent:
        """Creates the LlmAgent instance for the DeepBlue signal merchant."""
        return LlmAgent(
            model="gemini-2.5-flash",
            name="deepblue_signal_agent",
            description=(
                "Sells live BTC/ETH/SOL/XRP 5-minute directional signals from the "
                "DeepBlue autonomous Polymarket trading bot."
            ),
            instruction="""You are the DeepBlue Signal Agent — a merchant that sells live crypto trading signals.

- When a user asks for a trading signal, use the `get_trading_signal` tool with the coin they specified (BTC, ETH, SOL, or XRP).
- If you receive a successful result from `get_trading_signal` (via check_payment_status), present the signal clearly:
  * Show the coin, direction (UP or DOWN), confidence score, and any supporting context.
  * Do NOT ask for payment again — it has already been collected.
- If the payment fails, relay the error clearly and politely.
- Only BTC, ETH, SOL, and XRP are supported. Politely decline other requests.
""",
            tools=[self.get_trading_signal],
            before_agent_callback=self.before_agent_callback,
        )

    @override
    def create_agent_card(self, url: str) -> AgentCard:
        """Creates the AgentCard describing this agent to A2A clients."""
        skills = [
            AgentSkill(
                id="get_trading_signal",
                name="Get 5-Min Trading Signal",
                description=(
                    "Returns a live UP/DOWN directional signal with confidence score "
                    "for BTC, ETH, SOL, or XRP. Signal is generated by the DeepBlue "
                    "autonomous Polymarket trading bot using real-time Binance data."
                ),
                tags=["crypto", "trading", "signals", "BTC", "ETH", "SOL", "XRP", "x402"],
                examples=[
                    "Give me a BTC signal.",
                    "What's the ETH 5-minute signal?",
                    "Should I go long or short SOL right now?",
                    "Get me a trading signal for XRP.",
                ],
            )
        ]
        return AgentCard(
            name="DeepBlue Signal Agent",
            description=(
                "Sells live BTC/ETH/SOL/XRP 5-minute directional signals from the "
                "DeepBlue autonomous Polymarket trading bot. "
                "Signals include direction (UP/DOWN) and a confidence score derived "
                "from real-time Binance websocket data. "
                "Payment is $0.002 USDC per signal via the x402 A2A protocol."
            ),
            url=url,
            version="1.0.0",
            defaultInputModes=["text", "text/plain"],
            defaultOutputModes=["text", "text/plain"],
            capabilities=AgentCapabilities(
                streaming=False,
                extensions=[
                    get_extension_declaration(
                        description="Supports per-signal micropayments using the x402 protocol.",
                        required=True,
                    )
                ],
            ),
            skills=skills,
        )


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _fetch_signal(coin: str) -> dict:
    """
    Fetches a live trading signal from the DeepBlue API.

    Returns the signal dict on success, or a dict with an ``error`` key if
    the API is unreachable. A fallback placeholder is returned so the agent
    can still respond gracefully during development or API downtime.
    """
    coin = coin.upper()
    url = f"{DEEPBLUE_API_URL}/signals"
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(url, params={"coin": coin})
            response.raise_for_status()
            data = response.json()
            # Normalize: the API may return the signal directly or nested
            if isinstance(data, dict):
                return data
            return {"raw": data}
    except httpx.HTTPStatusError as exc:
        return {
            "error": f"DeepBlue API returned HTTP {exc.response.status_code}",
            "coin": coin,
            "fallback": True,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "error": f"Could not reach DeepBlue API: {exc}",
            "coin": coin,
            "fallback": True,
            "note": "Run `curl https://api.deepbluebase.xyz/signals?coin=BTC` to verify API status.",
        }
