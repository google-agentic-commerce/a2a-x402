"""Agent utilities for creating x402-enabled agent cards."""

from typing import List, Optional
from a2a.types import AgentCard, AgentCapabilities

from ..types import X402ExtensionConfig, get_extension_declaration


def create_x402_agent_card(
    name: str,
    description: str,
    url: str,
    version: str = "1.0.0",
    extensions_config: Optional[X402ExtensionConfig] = None,
    skills: Optional[List] = None,
    instructions: Optional[List[str]] = None,
    model: Optional[str] = None,
    default_input_modes: Optional[List[str]] = None,
    default_output_modes: Optional[List[str]] = None,
    streaming: bool = True
) -> AgentCard:
    """Create an AgentCard with x402 extension capabilities.
    
    Args:
        name: Name of the agent
        description: Description of the agent
        url: The URL where this agent can be reached
        version: Agent version (default: "1.0.0")
        extensions_config: x402 extension configuration (optional)
        skills: List of agent skills (optional)
        instructions: List of agent instructions (optional)
        model: Model name (optional)
        default_input_modes: Supported input modes
        default_output_modes: Supported output modes
        streaming: Whether streaming is supported
        
    Returns:
        AgentCard with x402 extension capabilities
    """
    # Default input/output modes
    if default_input_modes is None:
        default_input_modes = ["text", "text/plain"]
    if default_output_modes is None:
        default_output_modes = ["text", "text/plain"]
    if skills is None:
        skills = []
    
    # Create base capabilities
    capabilities = AgentCapabilities(
        streaming=streaming,
        extensions=[get_extension_declaration()]
    )
    
    # Create the agent card data
    card_data = {
        "name": name,
        "description": description,
        "url": url,
        "version": version,
        "defaultInputModes": default_input_modes,
        "defaultOutputModes": default_output_modes,
        "capabilities": capabilities,
        "skills": skills
    }
    
    # Add optional fields if provided
    if instructions:
        card_data["instructions"] = instructions
    if model:
        card_data["model"] = model
    
    return AgentCard(**card_data)


def create_merchant_agent_card(
    merchant_address: str,
    name: str = "Market Intelligence Agent",
    description: str = "AI-powered market analysis and data intelligence service with x402 payments",
    url: str = "http://localhost:10000/agents/market-intelligence",
    instructions: Optional[List[str]] = None,
    model: str = "gemini-2.0-flash-exp"
) -> AgentCard:
    """Create a pre-configured merchant agent card for demos.
    
    Args:
        merchant_address: Ethereum address for receiving payments
        name: Agent name
        description: Agent description
        url: Agent URL
        instructions: Custom instructions (optional)
        model: Model to use
        
    Returns:
        Configured AgentCard for merchant agent
    """
    if instructions is None:
        instructions = [
            "You are a professional market intelligence agent that provides data analysis services.",
            "You offer both free and paid services through secure x402 payments.",
            "Free services include service catalog, system status, and quick market summaries.",
            "Paid services include basic analysis ($1.50), premium AI analysis ($5.00), custom reports ($3.00), and alerts setup ($2.50).",
            "Always be helpful and guide users to the appropriate services.",
            "When providing paid services, ensure payment is completed before delivering detailed analysis."
        ]
    
    return create_x402_agent_card(
        name=name,
        description=description,
        url=url,
        instructions=instructions,
        model=model
    )
