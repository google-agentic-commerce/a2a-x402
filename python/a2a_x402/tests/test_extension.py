"""Unit tests for a2a_x402.extension module."""

import pytest
from a2a_x402.extension import (
    get_extension_declaration,
    check_extension_activation,
    add_extension_activation_header
)
from a2a_x402.types.config import X402_EXTENSION_URI


class TestExtensionDeclaration:
    """Test extension declaration functionality."""
    
    def test_get_extension_declaration_defaults(self):
        """Test extension declaration with default values."""
        declaration = get_extension_declaration()
        
        assert declaration["uri"] == X402_EXTENSION_URI
        assert declaration["description"] == "Supports x402 payments"
        assert declaration["required"] is True
    
    def test_get_extension_declaration_custom(self):
        """Test extension declaration with custom values."""
        declaration = get_extension_declaration(
            description="Custom x402 payment support",
            required=False
        )
        
        assert declaration["uri"] == X402_EXTENSION_URI
        assert declaration["description"] == "Custom x402 payment support"
        assert declaration["required"] is False
    
    def test_extension_declaration_format(self):
        """Test that extension declaration has correct format for AgentCard."""
        declaration = get_extension_declaration()
        
        # Should have all required fields for AgentCard.extensions
        required_fields = ["uri", "description", "required"]
        for field in required_fields:
            assert field in declaration
        
        assert isinstance(declaration["uri"], str)
        assert isinstance(declaration["description"], str)
        assert isinstance(declaration["required"], bool)


class TestExtensionActivation:
    """Test extension activation functionality."""
    
    def test_check_extension_activation_present(self):
        """Test extension activation when header contains URI."""
        headers = {
            "X-A2A-Extensions": X402_EXTENSION_URI
        }
        
        assert check_extension_activation(headers) is True
    
    def test_check_extension_activation_multiple_extensions(self):
        """Test extension activation with multiple extensions in header."""
        headers = {
            "X-A2A-Extensions": f"other-ext, {X402_EXTENSION_URI}, another-ext"
        }
        
        assert check_extension_activation(headers) is True
    
    def test_check_extension_activation_missing(self):
        """Test extension activation when header is missing."""
        headers = {}
        assert check_extension_activation(headers) is False
        
        headers = {"X-A2A-Extensions": ""}
        assert check_extension_activation(headers) is False
    
    def test_check_extension_activation_wrong_extension(self):
        """Test extension activation with different extension URI."""
        headers = {
            "X-A2A-Extensions": "https://example.com/other-extension"
        }
        
        assert check_extension_activation(headers) is False
    
    def test_add_extension_activation_header_new(self):
        """Test adding extension header to empty headers."""
        headers = {}
        result = add_extension_activation_header(headers)
        
        assert result["X-A2A-Extensions"] == X402_EXTENSION_URI
        assert result is headers  # Should modify original dict
    
    def test_add_extension_activation_header_existing(self):
        """Test adding extension header when header already exists."""
        headers = {"X-A2A-Extensions": "existing-ext"}
        result = add_extension_activation_header(headers)
        
        # Should overwrite existing value (as per spec requirement to echo)
        assert result["X-A2A-Extensions"] == X402_EXTENSION_URI
    
    def test_add_extension_activation_header_preserves_other_headers(self):
        """Test that adding extension header preserves other headers."""
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer token"
        }
        
        result = add_extension_activation_header(headers)
        
        assert result["X-A2A-Extensions"] == X402_EXTENSION_URI
        assert result["Content-Type"] == "application/json"
        assert result["Authorization"] == "Bearer token"
