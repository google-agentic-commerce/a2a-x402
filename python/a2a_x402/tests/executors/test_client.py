"""Unit tests for a2a_x402.executors.client module."""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from eth_account import Account
from a2a_x402.executors.client import X402ClientExecutor
from a2a_x402.types import (
    Task,
    TaskState,
    TaskStatus,
    PaymentStatus,
    X402ExtensionConfig,
    X402_EXTENSION_URI,
    x402PaymentRequiredResponse,
    PaymentPayload,
    SettleResponse,
    X402ErrorCode
)


class TestX402ClientExecutor:
    """Test X402ClientExecutor interceptor middleware."""
    
    def test_client_executor_initialization(self, test_account):
        """Test client executor initialization."""
        mock_delegate = Mock()
        config = X402ExtensionConfig()
        
        executor = X402ClientExecutor(mock_delegate, config, test_account)
        
        assert executor._delegate == mock_delegate
        assert executor.config == config
        assert executor.account == test_account
        assert executor.max_value is None
        assert executor.auto_pay is True
    
    def test_client_executor_with_options(self, test_account):
        """Test client executor initialization with options."""
        mock_delegate = Mock()
        config = X402ExtensionConfig()
        
        executor = X402ClientExecutor(
            mock_delegate, 
            config, 
            test_account,
            max_value=5000000,
            auto_pay=False
        )
        
        assert executor.max_value == 5000000
        assert executor.auto_pay is False
    
    @pytest.mark.asyncio
    async def test_execute_when_extension_not_active(self, test_account):
        """Test execution when x402 extension is not active."""
        mock_delegate = Mock()
        mock_delegate.execute = AsyncMock(return_value="normal_result")
        
        config = X402ExtensionConfig(required=False)
        executor = X402ClientExecutor(mock_delegate, config, test_account)
        
        # Context without x402 extension
        mock_context = Mock()
        mock_context.headers = {}
        mock_event_queue = Mock()
        
        result = await executor.execute(mock_context, mock_event_queue)
        
        # Should delegate directly
        mock_delegate.execute.assert_called_once_with(mock_context, mock_event_queue)
        assert result == "normal_result"
    
    @pytest.mark.asyncio
    async def test_execute_normal_request(self, test_account, sample_task):
        """Test execution with normal request (no payment required)."""
        mock_delegate = Mock()
        mock_delegate.execute = AsyncMock(return_value="service_result")
        
        config = X402ExtensionConfig()
        executor = X402ClientExecutor(mock_delegate, config, test_account)
        
        # Context with normal task (no payment required)
        mock_context = Mock()
        mock_context.headers = {"X-A2A-Extensions": X402_EXTENSION_URI}
        mock_context.current_task = sample_task  # Task without payment status
        mock_event_queue = Mock()
        
        result = await executor.execute(mock_context, mock_event_queue)
        
        # Should execute delegate and return result
        mock_delegate.execute.assert_called_once()
        assert result == "service_result"
    
    @pytest.mark.asyncio
    async def test_execute_with_payment_required_auto_pay(self, test_account, sample_task, sample_payment_required_response):
        """Test execution when payment required with auto_pay enabled."""
        mock_delegate = Mock()
        mock_delegate.execute = AsyncMock(return_value="initial_result")
        
        config = X402ExtensionConfig()
        executor = X402ClientExecutor(mock_delegate, config, test_account, auto_pay=True)
        
        # Setup task with payment required
        task_with_payment_required = executor.utils.create_payment_required_task(
            sample_task, 
            sample_payment_required_response
        )
        
        mock_context = Mock()
        mock_context.headers = {"X-A2A-Extensions": X402_EXTENSION_URI}
        mock_context.current_task = task_with_payment_required
        mock_event_queue = Mock()
        mock_event_queue.enqueue_event = AsyncMock()
        
        # Mock payment processing
        with patch('a2a_x402.executors.client.process_payment_required') as mock_process_payment:
            from a2a_x402.types import PaymentPayload, ExactPaymentPayload, EIP3009Authorization
            mock_payload = PaymentPayload(
                x402_version=1,
                scheme="exact",
                network="base",
                payload=ExactPaymentPayload(
                    signature="0x" + "a" * 130,
                    authorization=EIP3009Authorization(
                        from_=test_account.address,
                        to="0xmerchant123",
                        value="1000000",
                        valid_after="1640995200",
                        valid_before="1640998800",
                        nonce="0x" + "1" * 64
                    )
                )
            )
            # Use PaymentPayload directly per new spec
            mock_payment_payload = mock_payload
            mock_process_payment.return_value = mock_payment_payload
            
            # Execute
            await executor.execute(mock_context, mock_event_queue)
            
            # Should process payment automatically
            mock_process_payment.assert_called_once_with(
                sample_payment_required_response,
                test_account,
                executor.max_value
            )
            
            # Should enqueue payment submission
            mock_event_queue.enqueue_event.assert_called_once()
            
            # Check final task state
            final_task = mock_event_queue.enqueue_event.call_args[0][0]
            final_status = executor.utils.get_payment_status(final_task)
            assert final_status == PaymentStatus.PAYMENT_SUBMITTED
    
    @pytest.mark.asyncio
    async def test_execute_with_payment_required_auto_pay_disabled(self, test_account, sample_task, sample_payment_required_response):
        """Test execution when payment required but auto_pay is disabled."""
        mock_delegate = Mock()
        mock_delegate.execute = AsyncMock(return_value="payment_required_result")
        
        config = X402ExtensionConfig()
        executor = X402ClientExecutor(mock_delegate, config, test_account, auto_pay=False)
        
        # Setup task with payment required
        task_with_payment_required = executor.utils.create_payment_required_task(
            sample_task,
            sample_payment_required_response
        )
        
        mock_context = Mock()
        mock_context.headers = {"X-A2A-Extensions": X402_EXTENSION_URI}
        mock_context.current_task = task_with_payment_required
        mock_event_queue = Mock()
        
        result = await executor.execute(mock_context, mock_event_queue)
        
        # Should NOT process payment automatically
        # Should just return the delegate result
        mock_delegate.execute.assert_called_once()
        assert result == "payment_required_result"
    
    @pytest.mark.asyncio
    async def test_execute_with_payment_processing_exception(self, test_account, sample_task, sample_payment_required_response):
        """Test execution when payment processing raises an exception."""
        mock_delegate = Mock()
        mock_delegate.execute = AsyncMock(return_value="initial_result")
        
        config = X402ExtensionConfig()
        executor = X402ClientExecutor(mock_delegate, config, test_account)
        
        # Setup task with payment required
        task_with_payment_required = executor.utils.create_payment_required_task(
            sample_task,
            sample_payment_required_response
        )
        
        mock_context = Mock()
        mock_context.headers = {"X-A2A-Extensions": X402_EXTENSION_URI}
        mock_context.current_task = task_with_payment_required
        mock_event_queue = Mock()
        mock_event_queue.enqueue_event = AsyncMock()
        
        # Mock payment processing exception
        with patch('a2a_x402.executors.client.process_payment_required') as mock_process_payment:
            mock_process_payment.side_effect = Exception("Signing failed")
            
            # Execute
            await executor.execute(mock_context, mock_event_queue)
            
            # Should handle exception gracefully
            mock_event_queue.enqueue_event.assert_called_once()
            
            # Check task failure state
            final_task = mock_event_queue.enqueue_event.call_args[0][0]
            final_status = executor.utils.get_payment_status(final_task)
            assert final_status == PaymentStatus.PAYMENT_FAILED
            assert final_task.status.message.metadata[executor.utils.ERROR_KEY] == X402ErrorCode.INVALID_SIGNATURE
            assert "Payment failed: Signing failed" in final_task.status.message.metadata[executor.utils.RECEIPTS_KEY][0]["errorReason"]
    
    @pytest.mark.asyncio
    async def test_execute_with_no_current_task(self, test_account):
        """Test execution when context has no current task."""
        mock_delegate = Mock()
        mock_delegate.execute = AsyncMock(return_value="no_task_result")
        
        config = X402ExtensionConfig()
        executor = X402ClientExecutor(mock_delegate, config, test_account)
        
        mock_context = Mock()
        mock_context.headers = {"X-A2A-Extensions": X402_EXTENSION_URI}
        mock_context.current_task = None
        mock_event_queue = Mock()
        
        result = await executor.execute(mock_context, mock_event_queue)
        
        # Should delegate normally
        mock_delegate.execute.assert_called_once_with(mock_context, mock_event_queue)
        assert result == "no_task_result"
    
    @pytest.mark.asyncio
    async def test_execute_with_missing_payment_requirements(self, test_account, sample_task):
        """Test execution when payment required but no requirements in metadata."""
        mock_delegate = Mock()
        mock_delegate.execute = AsyncMock(return_value="initial_result")
        
        config = X402ExtensionConfig()
        executor = X402ClientExecutor(mock_delegate, config, test_account)
        
        # Setup task with payment required status but no actual requirements
        from a2a_x402.types import Message
        from a2a.types import TextPart
        sample_task.status.message = Message(
            messageId="test-msg",
            role="agent",
            parts=[TextPart(kind="text", text="test")],
            metadata={executor.utils.STATUS_KEY: PaymentStatus.PAYMENT_REQUIRED.value}
        )
        
        mock_context = Mock()
        mock_context.headers = {"X-A2A-Extensions": X402_EXTENSION_URI}
        mock_context.current_task = sample_task
        mock_event_queue = Mock()
        
        result = await executor.execute(mock_context, mock_event_queue)
        
        # Should execute delegate first, then try to handle payment (but fail silently)
        mock_delegate.execute.assert_called_once()
        # When payment processing fails due to missing requirements, returns None
        assert result is None
