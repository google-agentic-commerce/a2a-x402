"""Unit tests for a2a_x402.types.config module."""

import pytest
from pydantic import ValidationError
from a2a_x402.types.config import X402_EXTENSION_URI, X402ExtensionConfig


class TestExtensionURI:
    """Test extension URI constant."""
    
    def test_extension_uri_matches_spec(self):
        """Test that extension URI matches spec Section 2 exactly."""
        expected_uri = "https://google-a2a.github.io/A2A/extensions/payments/x402/v0.1"
        assert X402_EXTENSION_URI == expected_uri
    
    def test_extension_uri_is_string(self):
        """Test that extension URI is a string."""
        assert isinstance(X402_EXTENSION_URI, str)
    
    def test_extension_uri_format(self):
        """Test that extension URI has correct format."""
        assert X402_EXTENSION_URI.startswith("https://")
        assert "google-a2a.github.io" in X402_EXTENSION_URI
        assert "x402" in X402_EXTENSION_URI
        assert "v0.1" in X402_EXTENSION_URI


class TestX402ExtensionConfig:
    """Test X402ExtensionConfig data model."""
    
    def test_default_config(self):
        """Test creating config with default values."""
        config = X402ExtensionConfig()
        
        assert config.extension_uri == X402_EXTENSION_URI
        assert config.version == "0.1"
        assert config.x402_version == 1
        assert config.required is True
    
    def test_custom_config(self):
        """Test creating config with custom values."""
        config = X402ExtensionConfig(
            version="0.2",
            x402_version=2,
            required=False
        )
        
        assert config.extension_uri == X402_EXTENSION_URI  # Should still use default
        assert config.version == "0.2"
        assert config.x402_version == 2
        assert config.required is False
    
    def test_config_validation(self):
        """Test config field validation."""
        # Test invalid x402_version
        with pytest.raises(ValidationError):
            X402ExtensionConfig(x402_version="invalid")
        
        # Test invalid required field
        with pytest.raises(ValidationError):
            X402ExtensionConfig(required="invalid")
    
    def test_config_serialization(self):
        """Test that config serializes correctly."""
        config = X402ExtensionConfig()
        data = config.model_dump()
        
        expected_fields = ["extension_uri", "version", "x402_version", "required"]
        for field in expected_fields:
            assert field in data
        
        assert data["extension_uri"] == X402_EXTENSION_URI
        assert data["version"] == "0.1"
        assert data["x402_version"] == 1
        assert data["required"] is True
