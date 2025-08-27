"""Tests for a2a_x402.executors package exports."""

import pytest
from eth_account import Account
from a2a_x402.executors import (
    X402BaseExecutor,
    X402ServerExecutor,
    X402ClientExecutor
)
from a2a_x402.types import X402ExtensionConfig, X402ServerConfig


class TestExecutorsPackage:
    """Test executors package exports and integration."""
    
    def test_all_executors_importable(self):
        """Test that all executor classes can be imported."""
        assert X402BaseExecutor is not None
        assert X402ServerExecutor is not None  
        assert X402ClientExecutor is not None
    
    def test_executor_inheritance(self):
        """Test that executors inherit from base class."""
        assert issubclass(X402ServerExecutor, X402BaseExecutor)
        assert issubclass(X402ClientExecutor, X402BaseExecutor)
    
    def test_server_executor_creation(self, sample_server_config):
        """Test creating server executor."""
        mock_delegate = object()
        config = X402ExtensionConfig()
        
        executor = X402ServerExecutor(mock_delegate, config, sample_server_config)
        
        assert isinstance(executor, X402BaseExecutor)
        assert isinstance(executor, X402ServerExecutor)
        assert executor._delegate == mock_delegate
        assert executor.config == config
        assert executor.server_config == sample_server_config
    
    def test_client_executor_creation(self):
        """Test creating client executor."""
        mock_delegate = object()
        config = X402ExtensionConfig()
        account = Account.from_key("0x" + "1" * 64)
        
        executor = X402ClientExecutor(mock_delegate, config, account)
        
        assert isinstance(executor, X402BaseExecutor)
        assert isinstance(executor, X402ClientExecutor)
        assert executor._delegate == mock_delegate
        assert executor.config == config
        assert executor.account == account
    
    def test_executors_have_required_methods(self):
        """Test that executors implement required methods."""
        # Check that both executors have execute method
        assert hasattr(X402ServerExecutor, 'execute')
        assert hasattr(X402ClientExecutor, 'execute')
        
        # Check that base executor has required methods
        assert hasattr(X402BaseExecutor, 'is_active')
        assert hasattr(X402BaseExecutor, 'execute')
    
    def test_package_exports_completeness(self):
        """Test that package exports include all necessary classes."""
        from a2a_x402.executors import __all__
        
        expected_exports = [
            "X402BaseExecutor",
            "X402ServerExecutor",
            "X402ClientExecutor"
        ]
        
        for export in expected_exports:
            assert export in __all__
