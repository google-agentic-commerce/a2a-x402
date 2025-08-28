"""Unit tests for a2a_x402.executors.server module (exception-based approach)."""

import pytest
from unittest.mock import Mock, AsyncMock
from a2a_x402.executors.server import X402ServerExecutor
from a2a_x402.types import (
    PaymentStatus,
    X402ExtensionConfig,
    X402_EXTENSION_URI,
    x402PaymentRequiredResponse,
    VerifyResponse,
    SettleResponse,
    X402ErrorCode,
    X402PaymentRequiredException,
    Task,
    TaskStatus,
    TaskState
)


class TestX402ServerExecutor:
    """Test X402ServerExecutor middleware with exception-based approach."""
    
    def _setup_payment_task(self, executor, sample_task, sample_payment_payload, sample_payment_requirements):
        """Helper to setup a task with payment requirements and store them in executor."""
        payment_required = x402PaymentRequiredResponse(
            x402_version=1,
            accepts=[sample_payment_requirements],
            error=""
        )
        task_with_requirements = executor.utils.create_payment_required_task(sample_task, payment_required)
        
        # Store the payment requirements in the executor's store (simulating _handle_payment_required_exception)
        executor._payment_requirements_store[task_with_requirements.id] = [sample_payment_requirements]
        
        # Then record payment submission
        task_with_payment = executor.utils.record_payment_submission(task_with_requirements, sample_payment_payload)
        
        return task_with_payment
    
    def test_server_executor_initialization(self):
        """Test server executor initialization."""
        mock_delegate = Mock()
        config = X402ExtensionConfig()
        
        executor = X402ServerExecutor(mock_delegate, config)
        
        assert executor._delegate == mock_delegate
        assert executor.config == config
        assert executor.facilitator_client is not None
    
    def test_server_executor_with_custom_facilitator(self):
        """Test server executor with custom facilitator client."""
        mock_delegate = Mock()
        config = X402ExtensionConfig()
        mock_facilitator = Mock()
        
        executor = X402ServerExecutor(mock_delegate, config, mock_facilitator)
        
        assert executor.facilitator_client == mock_facilitator
    
    @pytest.mark.asyncio
    async def test_execute_when_extension_not_active(self):
        """Test execution when x402 extension is not active."""
        mock_delegate = Mock()
        mock_delegate.execute = AsyncMock(return_value="business_result")
        
        config = X402ExtensionConfig(required=False)
        executor = X402ServerExecutor(mock_delegate, config)
        
        # Context without x402 extension
        mock_context = Mock()
        mock_context.headers = {}
        mock_event_queue = Mock()
        
        result = await executor.execute(mock_context, mock_event_queue)
        
        # Should delegate directly without payment processing
        mock_delegate.execute.assert_called_once_with(mock_context, mock_event_queue)
        assert result == "business_result"
    
    @pytest.mark.asyncio
    async def test_execute_with_non_payment_task(self, sample_task):
        """Test execution with task that doesn't require payment processing."""
        mock_delegate = Mock()
        mock_delegate.execute = AsyncMock(return_value="normal_result")
        
        config = X402ExtensionConfig()
        executor = X402ServerExecutor(mock_delegate, config)
        
        # Context with extension but no payment status
        mock_context = Mock()
        mock_context.headers = {"X-A2A-Extensions": X402_EXTENSION_URI}
        mock_context.current_task = sample_task
        mock_event_queue = Mock()
        
        result = await executor.execute(mock_context, mock_event_queue)
        
        # Should delegate to business logic
        mock_delegate.execute.assert_called_once_with(mock_context, mock_event_queue)
        assert result == "normal_result"
    
    @pytest.mark.asyncio
    async def test_execute_with_payment_submitted_success(self, sample_task, sample_payment_payload, sample_payment_requirements):
        """Test execution with successful payment submission."""
        mock_delegate = Mock()
        mock_delegate.execute = AsyncMock(return_value="service_result")
        
        config = X402ExtensionConfig()
        executor = X402ServerExecutor(mock_delegate, config)
        
        # Setup task with payment using helper
        task_with_payment = self._setup_payment_task(executor, sample_task, sample_payment_payload, sample_payment_requirements)
        
        mock_context = Mock()
        mock_context.headers = {"X-A2A-Extensions": X402_EXTENSION_URI}
        mock_context.current_task = task_with_payment
        mock_event_queue = Mock()
        mock_event_queue.enqueue_event = AsyncMock()
        
        # Mock successful verification and settlement
        mock_verify_response = VerifyResponse(is_valid=True, payer="0xclient456")
        mock_settle_response = SettleResponse(
            success=True,
            transaction="0xsuccess123",
            network="base",
            payer="0xclient456"
        )
        
        executor.facilitator_client.verify = AsyncMock(return_value=mock_verify_response)
        executor.facilitator_client.settle = AsyncMock(return_value=mock_settle_response)
        
        # Execute
        await executor.execute(mock_context, mock_event_queue)
        
        # Verify payment flow
        executor.facilitator_client.verify.assert_called_once_with(
            sample_payment_payload,
            sample_payment_requirements
        )
        
        # Business logic should be executed
        mock_delegate.execute.assert_called_once_with(mock_context, mock_event_queue)
        
        # Settlement should be called
        executor.facilitator_client.settle.assert_called_once_with(
            sample_payment_payload,
            sample_payment_requirements
        )
        
        # Final task should be enqueued
        mock_event_queue.enqueue_event.assert_called()
        
        # Check final task state
        final_task = mock_event_queue.enqueue_event.call_args[0][0]
        final_status = executor.utils.get_payment_status(final_task)
        assert final_status == PaymentStatus.PAYMENT_COMPLETED
    
    @pytest.mark.asyncio
    async def test_handle_x402_payment_required_exception(self):
        """Test handling of X402PaymentRequiredException."""
        config = X402ExtensionConfig()
        executor = X402ServerExecutor(Mock(), config)
        
        # Create X402PaymentRequiredException with custom payment requirements
        payment_exception = X402PaymentRequiredException.for_service(
            price="$10.00",
            pay_to_address="0xcustom123",
            resource="/premium-feature",
            description="Premium feature requires payment"
        )
        
        mock_context = Mock()
        mock_context.current_task = None
        mock_context.context_id = "exception-test"
        mock_event_queue = Mock()
        mock_event_queue.enqueue_event = AsyncMock()
        
        # Handle the exception
        await executor._handle_payment_required_exception(payment_exception, mock_context, mock_event_queue)
        
        # Verify task was created and sent
        mock_event_queue.enqueue_event.assert_called_once()
        created_task = mock_event_queue.enqueue_event.call_args[0][0]
        
        # Verify payment required status
        assert executor.utils.get_payment_status(created_task) == PaymentStatus.PAYMENT_REQUIRED
        
        # Verify requirements from exception
        stored_requirements = executor._payment_requirements_store[created_task.id]
        assert len(stored_requirements) == 1
        req = stored_requirements[0]
        assert req.pay_to == "0xcustom123"
        assert req.resource == "/premium-feature"
        assert req.description == "Premium feature requires payment"
    
    @pytest.mark.asyncio
    async def test_handle_x402_payment_required_exception_multiple_options(self):
        """Test handling of X402PaymentRequiredException with multiple payment options."""
        config = X402ExtensionConfig()
        executor = X402ServerExecutor(Mock(), config)
        
        from a2a_x402.core.merchant import create_payment_requirements
        
        # Create multiple payment options
        basic_req = create_payment_requirements(
            price="$5.00",
            pay_to_address="0xbasic123",
            resource="/basic-feature"
        )
        premium_req = create_payment_requirements(
            price="$15.00",
            pay_to_address="0xpremium456",
            resource="/premium-feature"
        )
        
        payment_exception = X402PaymentRequiredException(
            "Choose your service tier",
            payment_requirements=[basic_req, premium_req]
        )
        
        mock_context = Mock()
        mock_context.current_task = None
        mock_context.context_id = "multi-option-test"
        mock_event_queue = Mock()
        mock_event_queue.enqueue_event = AsyncMock()
        
        # Handle the exception
        await executor._handle_payment_required_exception(payment_exception, mock_context, mock_event_queue)
        
        # Verify multiple requirements stored
        mock_event_queue.enqueue_event.assert_called_once()
        created_task = mock_event_queue.enqueue_event.call_args[0][0]
        stored_requirements = executor._payment_requirements_store[created_task.id]
        
        assert len(stored_requirements) == 2
        assert stored_requirements[0].pay_to == "0xbasic123"
        assert stored_requirements[1].pay_to == "0xpremium456"
    
    @pytest.mark.asyncio
    async def test_execute_with_x402_exception_during_normal_execution(self, sample_task):
        """Test X402PaymentRequiredException during normal execution."""
        mock_delegate = Mock()
        
        # Delegate throws X402PaymentRequiredException
        payment_exception = X402PaymentRequiredException.for_service(
            price="$7.50",
            pay_to_address="0xdynamic789",
            resource="/dynamic-service",
            description="Dynamic payment required"
        )
        mock_delegate.execute = AsyncMock(side_effect=payment_exception)
        
        config = X402ExtensionConfig()
        executor = X402ServerExecutor(mock_delegate, config)
        
        mock_context = Mock()
        mock_context.headers = {"X-A2A-Extensions": X402_EXTENSION_URI}
        mock_context.current_task = sample_task
        mock_event_queue = Mock()
        mock_event_queue.enqueue_event = AsyncMock()
        
        # Execute should handle exception and create payment requirement
        await executor.execute(mock_context, mock_event_queue)
        
        # Should have updated the task to payment required
        mock_event_queue.enqueue_event.assert_called_once()
        updated_task = mock_event_queue.enqueue_event.call_args[0][0]
        assert executor.utils.get_payment_status(updated_task) == PaymentStatus.PAYMENT_REQUIRED
        
        # Requirements should come from exception
        stored_requirements = executor._payment_requirements_store[updated_task.id]
        assert stored_requirements[0].pay_to == "0xdynamic789"
        assert stored_requirements[0].resource == "/dynamic-service"
    
    @pytest.mark.asyncio 
    async def test_server_executor_exception_based_only(self):
        """Test server executor works with exception-based approach only."""
        mock_delegate = Mock()
        
        # Create exception-based payment
        payment_exception = X402PaymentRequiredException.for_service(
            price="$3.00",
            pay_to_address="0xpayment123",
            resource="/service"
        )
        mock_delegate.execute = AsyncMock(side_effect=payment_exception)
        
        config = X402ExtensionConfig()
        # No server_config provided - works with exception-based approach
        executor = X402ServerExecutor(mock_delegate, config)
        
        mock_context = Mock()
        mock_context.headers = {"X-A2A-Extensions": X402_EXTENSION_URI}
        mock_context.current_task = None
        mock_context.context_id = "exception-only-test"
        mock_event_queue = Mock()
        mock_event_queue.enqueue_event = AsyncMock()
        
        # Should work fine with exception-based payment
        await executor.execute(mock_context, mock_event_queue)
        
        # Should have created payment requirement from exception
        mock_event_queue.enqueue_event.assert_called_once()
        created_task = mock_event_queue.enqueue_event.call_args[0][0]
        assert executor.utils.get_payment_status(created_task) == PaymentStatus.PAYMENT_REQUIRED
        
        stored_requirements = executor._payment_requirements_store[created_task.id]
        assert stored_requirements[0].pay_to == "0xpayment123"
    
    @pytest.mark.asyncio
    async def test_execute_with_verification_failure(self, sample_task, sample_payment_payload, sample_payment_requirements):
        """Test execution when payment verification fails."""
        mock_delegate = Mock()
        config = X402ExtensionConfig()
        executor = X402ServerExecutor(mock_delegate, config)
        
        # Setup task with payment using helper
        task_with_payment = self._setup_payment_task(executor, sample_task, sample_payment_payload, sample_payment_requirements)
        
        mock_context = Mock()
        mock_context.headers = {"X-A2A-Extensions": X402_EXTENSION_URI}
        mock_context.current_task = task_with_payment
        mock_event_queue = Mock()
        mock_event_queue.enqueue_event = AsyncMock()
        
        # Mock verification failure
        mock_verify_response = VerifyResponse(
            is_valid=False,
            invalid_reason="Signature expired",
            payer=None
        )
        
        executor.facilitator_client.verify = AsyncMock(return_value=mock_verify_response)
        
        # Execute
        await executor.execute(mock_context, mock_event_queue)
        
        # Verification should be called
        executor.facilitator_client.verify.assert_called_once()
        
        # Business logic should NOT be executed
        mock_delegate.execute.assert_not_called()
        
        # Task should be marked as failed
        mock_event_queue.enqueue_event.assert_called_once()
        final_task = mock_event_queue.enqueue_event.call_args[0][0]
        final_status = executor.utils.get_payment_status(final_task)
        assert final_status == PaymentStatus.PAYMENT_FAILED
        assert final_task.status.message.metadata[executor.utils.ERROR_KEY] == X402ErrorCode.INVALID_SIGNATURE