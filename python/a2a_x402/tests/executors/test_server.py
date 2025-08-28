"""Unit tests for a2a_x402.executors.server module."""

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
    Task,
    TaskStatus,
    TaskState
)


class TestX402ServerExecutor:
    """Test X402ServerExecutor middleware."""
    
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
    
    def test_server_executor_initialization(self, sample_server_config):
        """Test server executor initialization."""
        mock_delegate = Mock()
        config = X402ExtensionConfig()
        
        executor = X402ServerExecutor(mock_delegate, config, sample_server_config)
        
        assert executor._delegate == mock_delegate
        assert executor.config == config
        assert executor.server_config == sample_server_config
        assert executor.facilitator_client is not None
    
    def test_server_executor_with_custom_facilitator(self, sample_server_config):
        """Test server executor with custom facilitator client."""
        mock_delegate = Mock()
        config = X402ExtensionConfig()
        mock_facilitator = Mock()
        
        executor = X402ServerExecutor(mock_delegate, config, sample_server_config, mock_facilitator)
        
        assert executor.facilitator_client == mock_facilitator
    
    @pytest.mark.asyncio
    async def test_execute_when_extension_not_active(self, sample_server_config):
        """Test execution when x402 extension is not active."""
        mock_delegate = Mock()
        mock_delegate.execute = AsyncMock(return_value="business_result")
        
        config = X402ExtensionConfig(required=False)
        executor = X402ServerExecutor(mock_delegate, config, sample_server_config)
        
        # Context without x402 extension
        mock_context = Mock()
        mock_context.headers = {}
        mock_event_queue = Mock()
        
        result = await executor.execute(mock_context, mock_event_queue)
        
        # Should delegate directly without payment processing
        mock_delegate.execute.assert_called_once_with(mock_context, mock_event_queue)
        assert result == "business_result"
    
    @pytest.mark.asyncio
    async def test_execute_with_non_payment_task(self, sample_task, sample_server_config):
        """Test execution with task that doesn't require payment processing."""
        mock_delegate = Mock()
        mock_delegate.execute = AsyncMock(return_value="normal_result")
        
        config = X402ExtensionConfig()
        executor = X402ServerExecutor(mock_delegate, config, sample_server_config)
        
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
    async def test_execute_with_payment_submitted_success(self, sample_task, sample_payment_payload, sample_payment_requirements, sample_server_config):
        """Test execution with successful payment submission."""
        mock_delegate = Mock()
        mock_delegate.execute = AsyncMock(return_value="service_result")
        
        config = X402ExtensionConfig()
        executor = X402ServerExecutor(mock_delegate, config, sample_server_config)
        
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
    async def test_execute_with_verification_failure(self, sample_task, sample_payment_payload, sample_payment_requirements, sample_server_config):
        """Test execution when payment verification fails."""
        mock_delegate = Mock()
        config = X402ExtensionConfig()
        executor = X402ServerExecutor(mock_delegate, config, sample_server_config)
        
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
    
    @pytest.mark.asyncio
    async def test_execute_with_settlement_failure(self, sample_task, sample_payment_payload, sample_payment_requirements, sample_server_config):
        """Test execution when payment settlement fails."""
        mock_delegate = Mock()
        mock_delegate.execute = AsyncMock(return_value="service_result")
        
        config = X402ExtensionConfig()
        executor = X402ServerExecutor(mock_delegate, config, sample_server_config)
        
        # Setup task with payment using helper
        task_with_payment = self._setup_payment_task(executor, sample_task, sample_payment_payload, sample_payment_requirements)
        
        mock_context = Mock()
        mock_context.headers = {"X-A2A-Extensions": X402_EXTENSION_URI}
        mock_context.current_task = task_with_payment
        mock_event_queue = Mock()
        mock_event_queue.enqueue_event = AsyncMock()
        
        # Mock successful verification but failed settlement
        mock_verify_response = VerifyResponse(is_valid=True, payer="0xclient456")
        mock_settle_response = SettleResponse(
            success=False,
            transaction=None,
            network="base",
            payer="0xclient456",
            error_reason="Network congestion"
        )
        
        executor.facilitator_client.verify = AsyncMock(return_value=mock_verify_response)
        executor.facilitator_client.settle = AsyncMock(return_value=mock_settle_response)
        
        # Execute
        await executor.execute(mock_context, mock_event_queue)
        
        # Both verify and settle should be called
        executor.facilitator_client.verify.assert_called_once()
        mock_delegate.execute.assert_called_once()
        executor.facilitator_client.settle.assert_called_once()
        
        # Task should be marked as failed
        final_task = mock_event_queue.enqueue_event.call_args[0][0]
        final_status = executor.utils.get_payment_status(final_task)
        assert final_status == PaymentStatus.PAYMENT_FAILED
        assert final_task.status.message.metadata[executor.utils.ERROR_KEY] == X402ErrorCode.SETTLEMENT_FAILED
    
    @pytest.mark.asyncio
    async def test_execute_with_no_payment_data(self, sample_task, sample_server_config):
        """Test execution when task has no payment data."""
        mock_delegate = Mock()
        config = X402ExtensionConfig()
        executor = X402ServerExecutor(mock_delegate, config, sample_server_config)
        
        # Setup task with payment submitted status but no actual payment data
        from a2a_x402.types import Message
        from a2a.types import TextPart
        sample_task.status.message = Message(
            messageId="test-msg",
            role="agent",
            parts=[TextPart(kind="text", text="test")],
            metadata={executor.utils.STATUS_KEY: PaymentStatus.PAYMENT_SUBMITTED.value}
        )
        
        mock_context = Mock()
        mock_context.headers = {"X-A2A-Extensions": X402_EXTENSION_URI}
        mock_context.current_task = sample_task
        mock_event_queue = Mock()
        mock_event_queue.enqueue_event = AsyncMock()
        
        # Execute
        await executor.execute(mock_context, mock_event_queue)
        
        # Should fail due to missing payment data
        final_task = mock_event_queue.enqueue_event.call_args[0][0]
        final_status = executor.utils.get_payment_status(final_task)
        assert final_status == PaymentStatus.PAYMENT_FAILED
        assert final_task.status.message.metadata[executor.utils.ERROR_KEY] == X402ErrorCode.INVALID_SIGNATURE
    
    @pytest.mark.asyncio
    async def test_execute_with_verification_exception(self, sample_task, sample_payment_payload, sample_payment_requirements, sample_server_config):
        """Test execution when verification raises an exception."""
        mock_delegate = Mock()
        config = X402ExtensionConfig()
        executor = X402ServerExecutor(mock_delegate, config, sample_server_config)
        
        # Setup task with payment using helper
        task_with_payment = self._setup_payment_task(executor, sample_task, sample_payment_payload, sample_payment_requirements)
        
        mock_context = Mock()
        mock_context.headers = {"X-A2A-Extensions": X402_EXTENSION_URI}
        mock_context.current_task = task_with_payment
        mock_event_queue = Mock()
        mock_event_queue.enqueue_event = AsyncMock()
        
        # Mock verification exception
        executor.facilitator_client.verify = AsyncMock(side_effect=Exception("Network error"))
        
        # Execute
        await executor.execute(mock_context, mock_event_queue)
        
        # Should handle exception gracefully
        final_task = mock_event_queue.enqueue_event.call_args[0][0]
        final_status = executor.utils.get_payment_status(final_task)
        assert final_status == PaymentStatus.PAYMENT_FAILED
        assert "Verification failed: Network error" in final_task.status.message.metadata[executor.utils.RECEIPTS_KEY][0]["errorReason"]
    
    @pytest.mark.asyncio
    async def test_execute_with_no_task_coverage(self, sample_server_config):
        """Test execution path when context has no current_task (line 63)."""
        mock_delegate = Mock()
        mock_delegate.execute = AsyncMock(return_value="no_task_result")
        
        config = X402ExtensionConfig()
        executor = X402ServerExecutor(mock_delegate, config, sample_server_config)
        
        # Context without current_task
        mock_context = Mock()
        mock_context.headers = {"X-A2A-Extensions": X402_EXTENSION_URI}
        mock_context.current_task = None
        mock_event_queue = Mock()
        
        result = await executor.execute(mock_context, mock_event_queue)
        
        # Should delegate directly
        mock_delegate.execute.assert_called_once_with(mock_context, mock_event_queue)
        assert result == "no_task_result"
    
    @pytest.mark.asyncio
    async def test_execute_with_business_logic_exception(self, sample_task, sample_payment_payload, sample_payment_requirements, sample_server_config):
        """Test execution when business logic raises exception (line 126-127)."""
        mock_delegate = Mock()
        mock_delegate.execute = AsyncMock(side_effect=Exception("Business logic failed"))
        
        config = X402ExtensionConfig()
        executor = X402ServerExecutor(mock_delegate, config, sample_server_config)
        
        # Setup task with payment using helper
        task_with_payment = self._setup_payment_task(executor, sample_task, sample_payment_payload, sample_payment_requirements)
        
        mock_context = Mock()
        mock_context.headers = {"X-A2A-Extensions": X402_EXTENSION_URI}
        mock_context.current_task = task_with_payment
        mock_event_queue = Mock()
        mock_event_queue.enqueue_event = AsyncMock()
        
        # Mock successful verification
        mock_verify_response = VerifyResponse(is_valid=True, payer="0xclient456")
        executor.facilitator_client.verify = AsyncMock(return_value=mock_verify_response)
        
        # Execute
        await executor.execute(mock_context, mock_event_queue)
        
        # Should fail due to business logic exception
        final_task = mock_event_queue.enqueue_event.call_args[0][0]
        final_status = executor.utils.get_payment_status(final_task)
        assert final_status == PaymentStatus.PAYMENT_FAILED
        assert "Service failed: Business logic failed" in final_task.status.message.metadata[executor.utils.RECEIPTS_KEY][0]["errorReason"]
    
    @pytest.mark.asyncio
    async def test_execute_with_settlement_exception(self, sample_task, sample_payment_payload, sample_payment_requirements, sample_server_config):
        """Test execution when settlement raises exception (lines 156-157)."""
        mock_delegate = Mock()
        mock_delegate.execute = AsyncMock(return_value="service_success")
        
        config = X402ExtensionConfig()
        executor = X402ServerExecutor(mock_delegate, config, sample_server_config)
        
        # Setup task with payment using helper
        task_with_payment = self._setup_payment_task(executor, sample_task, sample_payment_payload, sample_payment_requirements)
        
        mock_context = Mock()
        mock_context.headers = {"X-A2A-Extensions": X402_EXTENSION_URI}
        mock_context.current_task = task_with_payment
        mock_event_queue = Mock()
        mock_event_queue.enqueue_event = AsyncMock()
        
        # Mock successful verification but settlement exception
        mock_verify_response = VerifyResponse(is_valid=True, payer="0xclient456")
        executor.facilitator_client.verify = AsyncMock(return_value=mock_verify_response)
        executor.facilitator_client.settle = AsyncMock(side_effect=Exception("Settlement network error"))
        
        # Execute
        await executor.execute(mock_context, mock_event_queue)
        
        # Should handle settlement exception
        final_task = mock_event_queue.enqueue_event.call_args[0][0]
        final_status = executor.utils.get_payment_status(final_task)
        assert final_status == PaymentStatus.PAYMENT_FAILED
        assert "Settlement failed: Settlement network error" in final_task.status.message.metadata[executor.utils.RECEIPTS_KEY][0]["errorReason"]
    
    @pytest.mark.asyncio
    async def test_insufficient_funds_error_code(self, sample_task, sample_payment_payload, sample_payment_requirements, sample_server_config):
        """Test that insufficient funds error gets proper error code (line 151)."""
        mock_delegate = Mock()
        mock_delegate.execute = AsyncMock(return_value="service_success")
        
        config = X402ExtensionConfig()
        executor = X402ServerExecutor(mock_delegate, config, sample_server_config)
        
        # Setup task with payment using helper
        task_with_payment = self._setup_payment_task(executor, sample_task, sample_payment_payload, sample_payment_requirements)
        
        mock_context = Mock()
        mock_context.headers = {"X-A2A-Extensions": X402_EXTENSION_URI}
        mock_context.current_task = task_with_payment
        mock_event_queue = Mock()
        mock_event_queue.enqueue_event = AsyncMock()
        
        # Mock successful verification but settlement failure with insufficient funds
        mock_verify_response = VerifyResponse(is_valid=True, payer="0xclient456")
        mock_settle_response = SettleResponse(
            success=False,
            transaction=None,
            network="base",
            payer="0xclient456",
            error_reason="insufficient funds available"
        )
        
        executor.facilitator_client.verify = AsyncMock(return_value=mock_verify_response)
        executor.facilitator_client.settle = AsyncMock(return_value=mock_settle_response)
        
        # Execute
        await executor.execute(mock_context, mock_event_queue)
        
        # Should use INSUFFICIENT_FUNDS error code
        final_task = mock_event_queue.enqueue_event.call_args[0][0]
        assert final_task.status.message.metadata[executor.utils.ERROR_KEY] == X402ErrorCode.INSUFFICIENT_FUNDS
    
    @pytest.mark.asyncio
    async def test_execute_with_no_payment_requirements_in_context(self, sample_task, sample_payment_payload, sample_server_config):
        """Test execution when payment requirements are missing from context (line 86)."""
        mock_delegate = Mock()
        config = X402ExtensionConfig()
        executor = X402ServerExecutor(mock_delegate, config, sample_server_config)
        
        # Setup task with payment submitted but no payment requirements available
        from a2a_x402.types import Message
        from a2a.types import TextPart
        sample_task.status.message = Message(
            messageId="test-msg",
            role="agent",
            parts=[TextPart(kind="text", text="test")],
            metadata={
                executor.utils.STATUS_KEY: PaymentStatus.PAYMENT_SUBMITTED.value,
                executor.utils.PAYLOAD_KEY: sample_payment_payload.model_dump(by_alias=True)
                # Deliberately omitting REQUIRED_KEY to trigger missing requirements scenario
            }
        )
        
        mock_context = Mock()
        mock_context.headers = {"X-A2A-Extensions": X402_EXTENSION_URI}
        mock_context.current_task = sample_task
        mock_event_queue = Mock()
        mock_event_queue.enqueue_event = AsyncMock()
        
        # Execute
        await executor.execute(mock_context, mock_event_queue)
        
        # Should fail with INVALID_SIGNATURE due to missing payment requirements
        final_task = mock_event_queue.enqueue_event.call_args[0][0]
        assert final_task.status.message.metadata[executor.utils.STATUS_KEY] == PaymentStatus.PAYMENT_FAILED.value
        assert final_task.status.message.metadata[executor.utils.ERROR_KEY] == X402ErrorCode.INVALID_SIGNATURE
        assert "Missing payment requirements" in final_task.status.message.metadata[executor.utils.RECEIPTS_KEY][0]["errorReason"]
        
    def test_message_metadata_initialization(self, sample_task, sample_server_config):
        """Test that message metadata is properly initialized in the new structure."""
        config = X402ExtensionConfig()
        executor = X402ServerExecutor(Mock(), config, sample_server_config)
        
        # Test that the new metadata structure is properly created
        # This simulates what happens when server.py keeps PAYMENT_SUBMITTED status
        from a2a_x402.types import Message
        from a2a.types import TextPart
        sample_task.status.message = Message(
            messageId=f"{sample_task.id}-status",
            role="agent",
            parts=[TextPart(kind="text", text="Payment is being processed.")],
            metadata={}
        )
        
        # Set PAYMENT_SUBMITTED status using new structure
        sample_task.status.message.metadata[executor.utils.STATUS_KEY] = PaymentStatus.PAYMENT_SUBMITTED.value
        
        # Verify the new structure works correctly
        assert sample_task.status.message.metadata is not None
        assert isinstance(sample_task.status.message.metadata, dict)
        assert sample_task.status.message.metadata[executor.utils.STATUS_KEY] == PaymentStatus.PAYMENT_SUBMITTED.value
        
    def test_extract_payment_requirements_from_context_no_payment_required(self, sample_task, sample_server_config):
        """Test _extract_payment_requirements_from_context when no payment required found (line 130)."""
        mock_delegate = Mock()
        config = X402ExtensionConfig()
        executor = X402ServerExecutor(mock_delegate, config, sample_server_config)
        
        # Setup task without payment required data
        from a2a_x402.types import Message
        from a2a.types import TextPart
        sample_task.status.message = Message(
            messageId="test-msg",
            role="agent", 
            parts=[TextPart(kind="text", text="test")],
            metadata={}  # No REQUIRED_KEY
        )
        
        # Should return None when no payment requirements available
        result = executor._extract_payment_requirements_from_context(sample_task)
        assert result is None
    
    @pytest.mark.asyncio
    async def test_execute_with_exception_when_extension_not_active(self, sample_server_config):
        """Test exception handling when extension is not active (lines 64-67)."""
        mock_delegate = Mock()
        mock_delegate.execute = AsyncMock(side_effect=Exception("Payment required"))
        
        config = X402ExtensionConfig()
        executor = X402ServerExecutor(mock_delegate, config, sample_server_config)
        
        mock_context = Mock()
        mock_context.headers = {}  # No extension header
        mock_context.current_task = None
        mock_context.context_id = "test-context"
        mock_event_queue = Mock()
        mock_event_queue.enqueue_event = AsyncMock()
        
        # Execute should handle exception and create payment requirement
        await executor.execute(mock_context, mock_event_queue)
        
        # Should have created a payment required task
        mock_event_queue.enqueue_event.assert_called_once()
        created_task = mock_event_queue.enqueue_event.call_args[0][0]
        assert executor.utils.get_payment_status(created_task) == PaymentStatus.PAYMENT_REQUIRED
        assert created_task.id in executor._payment_requirements_store
    
    @pytest.mark.asyncio
    async def test_execute_with_exception_no_task_context(self, sample_server_config):
        """Test exception handling when no task context exists (lines 73-76)."""
        mock_delegate = Mock()
        mock_delegate.execute = AsyncMock(side_effect=Exception("Service needs payment"))
        
        config = X402ExtensionConfig()
        executor = X402ServerExecutor(mock_delegate, config, sample_server_config)
        
        mock_context = Mock()
        mock_context.headers = {"X-A2A-Extensions": X402_EXTENSION_URI}
        mock_context.current_task = None  # No task
        mock_context.context_id = "test-context-2"
        mock_event_queue = Mock()
        mock_event_queue.enqueue_event = AsyncMock()
        
        # Execute should handle exception and create payment requirement
        await executor.execute(mock_context, mock_event_queue)
        
        # Should have created a payment required task
        mock_event_queue.enqueue_event.assert_called_once()
        created_task = mock_event_queue.enqueue_event.call_args[0][0]
        assert executor.utils.get_payment_status(created_task) == PaymentStatus.PAYMENT_REQUIRED
    
    @pytest.mark.asyncio
    async def test_execute_with_exception_during_normal_execution(self, sample_task, sample_server_config):
        """Test exception handling during normal execution (lines 87-90)."""
        mock_delegate = Mock()
        mock_delegate.execute = AsyncMock(side_effect=Exception("Upgrade required"))
        
        config = X402ExtensionConfig()
        executor = X402ServerExecutor(mock_delegate, config, sample_server_config)
        
        mock_context = Mock()
        mock_context.headers = {"X-A2A-Extensions": X402_EXTENSION_URI}
        mock_context.current_task = sample_task  # Has task but not payment
        mock_event_queue = Mock()
        mock_event_queue.enqueue_event = AsyncMock()
        
        # Execute should handle exception and create payment requirement
        await executor.execute(mock_context, mock_event_queue)
        
        # Should have updated the task to payment required
        mock_event_queue.enqueue_event.assert_called_once()
        updated_task = mock_event_queue.enqueue_event.call_args[0][0]
        assert executor.utils.get_payment_status(updated_task) == PaymentStatus.PAYMENT_REQUIRED
    
    @pytest.mark.asyncio
    async def test_process_paid_request_without_status_message(self, sample_payment_payload, sample_payment_requirements, sample_server_config):
        """Test message creation during payment processing (lines 122-124, 133)."""
        mock_delegate = Mock()
        mock_delegate.execute = AsyncMock(return_value="service_result")
        
        config = X402ExtensionConfig()
        executor = X402ServerExecutor(mock_delegate, config, sample_server_config)
        
        # Create a task that has payment metadata but no message
        task = Task(
            id="task-no-msg",
            contextId="context-123",
            status=TaskStatus(state=TaskState.working, message=None)
        )
        
        # Manually set up the task as if it had gone through payment submission
        # but somehow lost its message
        executor._payment_requirements_store[task.id] = [sample_payment_requirements]
        
        # Mock the utils to return payment data
        executor.utils.get_payment_status = Mock(return_value=PaymentStatus.PAYMENT_SUBMITTED)
        executor.utils.get_payment_payload = Mock(return_value=sample_payment_payload)
        
        mock_context = Mock()
        mock_context.headers = {"X-A2A-Extensions": X402_EXTENSION_URI}
        mock_context.current_task = task
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
        
        # Execute - this should trigger _process_paid_request
        await executor.execute(mock_context, mock_event_queue)
        
        # Verify the message was created during processing
        assert task.status.message is not None
        assert task.status.message.metadata is not None
        assert task.status.message.message_id == f"{task.id}-status"
        assert executor.utils.STATUS_KEY in task.status.message.metadata
    
    def test_create_payment_requirements_from_config_with_context(self, sample_server_config):
        """Test _create_payment_requirements_from_config with different context scenarios."""
        config = X402ExtensionConfig()
        executor = X402ServerExecutor(Mock(), config, sample_server_config)
        
        # Test 1: With config resource
        requirements = executor._create_payment_requirements_from_config()
        assert requirements.resource == "/test-service"  # From sample_server_config
        
        # Test 2: Without config resource but with context path
        executor.server_config.resource = None
        mock_context = Mock()
        mock_context.request = Mock()
        mock_context.request.url = Mock()
        mock_context.request.url.path = "/api/generate"
        
        requirements = executor._create_payment_requirements_from_config(context=mock_context)
        assert requirements.resource == "/api/generate"
        
        # Test 3: No config resource and no context
        requirements = executor._create_payment_requirements_from_config()
        assert requirements.resource == "/service"  # Default
        
        # Test 4: Context without proper attributes
        mock_bad_context = Mock()
        mock_bad_context.request = None
        requirements = executor._create_payment_requirements_from_config(context=mock_bad_context)
        assert requirements.resource == "/service"  # Default
    
    def test_extract_payment_requirements_no_payload(self, sample_task, sample_payment_requirements, sample_server_config):
        """Test _extract_payment_requirements_from_context when payment payload is missing."""
        config = X402ExtensionConfig()
        executor = X402ServerExecutor(Mock(), config, sample_server_config)
        
        # Store requirements but task has no payment payload
        executor._payment_requirements_store[sample_task.id] = [sample_payment_requirements]
        
        # Mock utils to return None for payment payload
        executor.utils.get_payment_payload = Mock(return_value=None)
        
        result = executor._extract_payment_requirements_from_context(sample_task)
        assert result is None
    
    @pytest.mark.asyncio
    async def test_handle_payment_required_exception_creates_task(self, sample_server_config):
        """Test _handle_payment_required_exception creates task when none exists."""
        config = X402ExtensionConfig()
        executor = X402ServerExecutor(Mock(), config, sample_server_config)
        
        exception = Exception("Premium feature requires payment")
        mock_context = Mock()
        mock_context.current_task = None
        mock_context.context_id = "new-context"
        mock_event_queue = Mock()
        mock_event_queue.enqueue_event = AsyncMock()
        
        await executor._handle_payment_required_exception(exception, mock_context, mock_event_queue)
        
        # Should create and send payment required task
        mock_event_queue.enqueue_event.assert_called_once()
        created_task = mock_event_queue.enqueue_event.call_args[0][0]
        
        # Verify task properties
        assert created_task.id.startswith("payment-task-")
        assert created_task.context_id == "new-context"
        assert executor.utils.get_payment_status(created_task) == PaymentStatus.PAYMENT_REQUIRED
        
        # Verify requirements were stored
        assert created_task.id in executor._payment_requirements_store
        stored_requirements = executor._payment_requirements_store[created_task.id]
        assert len(stored_requirements) == 1
        assert stored_requirements[0].pay_to == sample_server_config.pay_to_address
