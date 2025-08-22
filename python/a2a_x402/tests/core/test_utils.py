"""Unit tests for a2a_x402.core.utils module."""

import pytest
from a2a_x402.core.utils import (
    X402Utils,
    create_payment_submission_message,
    extract_task_correlation
)
from a2a_x402.types import (
    PaymentStatus,
    X402Metadata,
    Message
)
from a2a.types import TextPart


class TestX402Utils:
    """Test X402Utils state management class."""
    
    def test_utils_metadata_keys(self):
        """Test that utils uses correct metadata keys."""
        utils = X402Utils()
        
        assert utils.STATUS_KEY == "x402.payment.status"
        assert utils.REQUIRED_KEY == "x402.payment.required"
        assert utils.PAYLOAD_KEY == "x402.payment.payload"
        assert utils.RECEIPT_KEY == "x402.payment.receipt"
        assert utils.ERROR_KEY == "x402.payment.error"
    
    def test_get_payment_status_success(self, sample_task):
        """Test getting payment status from task metadata."""
        utils = X402Utils()
        
        # Add payment status to task
        sample_task.metadata[utils.STATUS_KEY] = PaymentStatus.PAYMENT_REQUIRED.value
        
        status = utils.get_payment_status(sample_task)
        assert status == PaymentStatus.PAYMENT_REQUIRED
    
    def test_get_payment_status_none_cases(self):
        """Test payment status returns None for edge cases."""
        utils = X402Utils()
        
        # Test with None task
        assert utils.get_payment_status(None) is None
        
        # Test with task without metadata
        task_no_metadata = type('Task', (), {'metadata': None})()
        assert utils.get_payment_status(task_no_metadata) is None
        
        # Test with empty metadata
        task_empty = type('Task', (), {'metadata': {}})()
        assert utils.get_payment_status(task_empty) is None
    
    def test_get_payment_status_invalid_value(self, sample_task):
        """Test payment status with invalid status value."""
        utils = X402Utils()
        
        # Add invalid status
        sample_task.metadata[utils.STATUS_KEY] = "invalid-status"
        
        status = utils.get_payment_status(sample_task)
        assert status is None
    
    def test_create_payment_required_task(self, sample_task, sample_payment_required_response):
        """Test creating payment required task."""
        utils = X402Utils()
        
        task = utils.create_payment_required_task(sample_task, sample_payment_required_response)
        
        assert task.metadata[utils.STATUS_KEY] == PaymentStatus.PAYMENT_REQUIRED.value
        assert utils.REQUIRED_KEY in task.metadata
        
        # Verify we can extract the requirements back
        extracted = utils.get_payment_requirements(task)
        assert extracted is not None
        assert extracted.x402_version == sample_payment_required_response.x402_version
    
    def test_record_payment_submission(self, sample_task, sample_settle_request):
        """Test recording payment submission."""
        utils = X402Utils()
        
        task = utils.record_payment_submission(sample_task, sample_settle_request)
        
        assert task.metadata[utils.STATUS_KEY] == PaymentStatus.PAYMENT_SUBMITTED.value
        assert utils.PAYLOAD_KEY in task.metadata
        
        # Verify we can extract the settle request back
        extracted = utils.get_settle_request(task)
        assert extracted is not None
        assert extracted.payment_requirements.scheme == sample_settle_request.payment_requirements.scheme
    
    def test_record_payment_success(self, sample_task, sample_settle_response):
        """Test recording successful payment."""
        utils = X402Utils()
        
        task = utils.record_payment_success(sample_task, sample_settle_response)
        
        assert task.metadata[utils.STATUS_KEY] == PaymentStatus.PAYMENT_COMPLETED.value
        assert utils.RECEIPT_KEY in task.metadata
        
        # Should clean up payload data
        assert utils.PAYLOAD_KEY not in task.metadata
    
    def test_record_payment_failure(self, sample_task, sample_settle_response):
        """Test recording payment failure."""
        utils = X402Utils()
        
        # Create failure response
        failure_response = sample_settle_response.model_copy()
        failure_response.success = False
        failure_response.error_reason = "Insufficient funds"
        
        task = utils.record_payment_failure(sample_task, "INSUFFICIENT_FUNDS", failure_response)
        
        assert task.metadata[utils.STATUS_KEY] == PaymentStatus.PAYMENT_FAILED.value
        assert task.metadata[utils.ERROR_KEY] == "INSUFFICIENT_FUNDS"
        assert utils.RECEIPT_KEY in task.metadata
        
        # Should clean up payload data
        assert utils.PAYLOAD_KEY not in task.metadata
    
    def test_metadata_cleanup_flow(self, sample_task, sample_payment_required_response, sample_settle_request, sample_settle_response):
        """Test that metadata is properly cleaned up through the payment flow."""
        utils = X402Utils()
        
        # Step 1: Payment required
        task = utils.create_payment_required_task(sample_task, sample_payment_required_response)
        assert utils.REQUIRED_KEY in task.metadata
        assert utils.PAYLOAD_KEY not in task.metadata
        
        # Step 2: Payment submitted (should clean up requirements)
        task = utils.record_payment_submission(task, sample_settle_request)
        assert utils.REQUIRED_KEY not in task.metadata  # Cleaned up
        assert utils.PAYLOAD_KEY in task.metadata
        
        # Step 3: Payment completed (should clean up payload)
        task = utils.record_payment_success(task, sample_settle_response)
        assert utils.PAYLOAD_KEY not in task.metadata  # Cleaned up
        assert utils.RECEIPT_KEY in task.metadata
    
    def test_get_payment_requirements_success(self, sample_task, sample_payment_required_response):
        """Test successfully extracting payment requirements."""
        utils = X402Utils()
        
        # Add payment requirements to task
        sample_task.metadata[utils.REQUIRED_KEY] = sample_payment_required_response.model_dump(by_alias=True)
        
        requirements = utils.get_payment_requirements(sample_task)
        assert requirements is not None
        assert requirements.x402_version == sample_payment_required_response.x402_version
        
    def test_get_payment_requirements_invalid_data(self, sample_task):
        """Test extracting payment requirements with invalid data."""
        utils = X402Utils()
        
        # Add invalid data
        sample_task.metadata[utils.REQUIRED_KEY] = {"invalid": "data"}
        
        requirements = utils.get_payment_requirements(sample_task)
        assert requirements is None
        
    def test_get_settle_request_success(self, sample_task, sample_settle_request):
        """Test successfully extracting settle request."""
        utils = X402Utils()
        
        # Add settle request to task
        sample_task.metadata[utils.PAYLOAD_KEY] = sample_settle_request.model_dump(by_alias=True)
        
        settle_request = utils.get_settle_request(sample_task)
        assert settle_request is not None
        assert settle_request.payment_requirements.scheme == sample_settle_request.payment_requirements.scheme
        
    def test_get_settle_request_invalid_data(self, sample_task):
        """Test extracting settle request with invalid data."""
        utils = X402Utils()
        
        # Add invalid data
        sample_task.metadata[utils.PAYLOAD_KEY] = {"invalid": "data"}
        
        settle_request = utils.get_settle_request(sample_task)
        assert settle_request is None
        
    def test_metadata_none_handling(self, sample_payment_required_response, sample_settle_request, sample_settle_response):
        """Test handling tasks with None metadata."""
        utils = X402Utils()
        
        # Create task with None metadata
        task_no_metadata = type('Task', (), {'metadata': None})()
        
        # Test all methods handle None metadata gracefully
        task = utils.create_payment_required_task(task_no_metadata, sample_payment_required_response)
        assert task.metadata is not None
        assert utils.STATUS_KEY in task.metadata
        
        task_no_metadata2 = type('Task', (), {'metadata': None})()
        task = utils.record_payment_submission(task_no_metadata2, sample_settle_request)
        assert task.metadata is not None
        assert utils.STATUS_KEY in task.metadata
        
        task_no_metadata3 = type('Task', (), {'metadata': None})()
        task = utils.record_payment_success(task_no_metadata3, sample_settle_response)
        assert task.metadata is not None
        assert utils.STATUS_KEY in task.metadata
        
        task_no_metadata4 = type('Task', (), {'metadata': None})()
        task = utils.record_payment_failure(task_no_metadata4, "ERROR_CODE", sample_settle_response)
        assert task.metadata is not None
        assert utils.STATUS_KEY in task.metadata


class TestHelperFunctions:
    """Test helper functions in utils module."""
    
    def test_create_payment_submission_message(self, sample_settle_request):
        """Test creating payment submission message."""
        task_id = "task-789"
        message = create_payment_submission_message(task_id, sample_settle_request)
        
        assert isinstance(message, Message)
        assert message.task_id == task_id
        assert message.role == "user"
        assert len(message.parts) == 1
        
        # Check metadata
        assert message.metadata[X402Metadata.STATUS_KEY] == PaymentStatus.PAYMENT_SUBMITTED.value
        assert X402Metadata.PAYLOAD_KEY in message.metadata
    
    def test_create_payment_submission_message_custom_text(self, sample_settle_request):
        """Test creating payment submission message with custom text."""
        message = create_payment_submission_message(
            "task-456", 
            sample_settle_request,
            text="Custom payment message"
        )
        
        # Just verify message was created successfully
        assert isinstance(message, Message)
        assert message.task_id == "task-456"
    
    def test_extract_task_correlation_success(self):
        """Test extracting task correlation from message."""
        message = Message(
            messageId="msg-123",
            task_id="task-correlation-123",
            role="user",
            parts=[TextPart(kind="text", text="test")],
            metadata={}
        )
        
        task_id = extract_task_correlation(message)
        assert task_id == "task-correlation-123"
    
    def test_extract_task_correlation_missing(self):
        """Test extracting task correlation when not present."""
        message = Message(
            messageId="msg-456",
            role="user",
            parts=[TextPart(kind="text", text="test")],
            metadata={}
        )
        
        task_id = extract_task_correlation(message)
        assert task_id is None
    
    def test_extract_task_correlation_dict_fallback(self):
        """Test extracting task correlation from dict message."""
        # Test dict message format (fallback compatibility)
        dict_message = {
            "messageId": "msg-dict-123",
            "task_id": "task-dict-456",
            "role": "user",
            "parts": [],
            "metadata": {}
        }
        
        task_id = extract_task_correlation(dict_message)
        assert task_id == "task-dict-456"
    
    def test_extract_task_correlation_dict_missing(self):
        """Test extracting task correlation from dict without task_id."""
        dict_message = {
            "messageId": "msg-dict-789",
            "role": "user",
            "parts": [],
            "metadata": {}
        }
        
        task_id = extract_task_correlation(dict_message)
        assert task_id is None
    
    def test_edge_cases_for_coverage(self, sample_task):
        """Test edge cases to achieve 100% coverage."""
        utils = X402Utils()
        
        # Test get_payment_status with empty status value (line 63)
        sample_task.metadata[utils.STATUS_KEY] = ""
        status = utils.get_payment_status(sample_task)
        assert status is None
        
        # Test get_payment_requirements with missing key (line 76)
        sample_task.metadata.pop(utils.REQUIRED_KEY, None)
        requirements = utils.get_payment_requirements(sample_task)
        assert requirements is None
        
        # Test get_settle_request with missing key (line 89)
        sample_task.metadata.pop(utils.PAYLOAD_KEY, None)
        settle_request = utils.get_settle_request(sample_task)
        assert settle_request is None
        
        # Test get_payment_requirements with None task (line 68)
        requirements = utils.get_payment_requirements(None)
        assert requirements is None
        
        # Test get_settle_request with None task (line 81)
        settle_request = utils.get_settle_request(None)
        assert settle_request is None
