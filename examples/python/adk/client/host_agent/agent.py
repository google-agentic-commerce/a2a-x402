"""ADK agent configuration for the x402 payment demo client."""

import os
from typing import List, Dict, Any

from adk.executor import AdkExecutor
from adk.core import create_agent_kit_agent

from .host_agent import PaymentEnabledHostAgent


# Create payment-enabled host agent
payment_host = PaymentEnabledHostAgent()


def get_agent_executor() -> AdkExecutor:
    """Get the ADK executor for the client agent."""
    return payment_host


# ADK Agent Configuration
AGENT_CONFIG = {
    "model": "gemini-2.0-flash-exp",
    "name": "Market Intelligence Client",
    "description": "AI client agent with automatic x402 payment capabilities for market intelligence services",
    "instructions": [
        "You are a smart client agent that can automatically purchase market intelligence services.",
        "You have access to a remote market intelligence service that offers both free and paid analysis.",
        "When users request paid services, you automatically handle the payment using your built-in wallet.",
        "Available services include basic analysis ($1.50), premium AI analysis ($5.00), custom reports ($3.00), and alerts setup ($2.50).",
        "You can also access free services like service catalogs, system status, and quick market summaries.",
        "Always inform users about successful payments and service delivery.",
        "Be helpful and guide users to appropriate services based on their needs."
    ],
    "extensions": payment_host.get_extensions(),
    "tools": []
}


def create_agent():
    """Create the ADK agent with payment capabilities."""
    return create_agent_kit_agent(
        executor=get_agent_executor(),
        **AGENT_CONFIG
    )