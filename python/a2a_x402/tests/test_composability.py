"""Composability tests - mixing executors with manual core functions."""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from eth_account import Account

from a2a_x402.executors import X402ServerExecutor, X402ClientExecutor
from a2a_x402.core import (
    create_payment_requirements,
    process_payment_required,
    verify_payment,
    settle_payment,
    X402Utils
)
from a2a_x402.types import (
    Task,
    TaskState,
    TaskStatus,
    PaymentStatus,
    X402ExtensionConfig,
    X402_EXTENSION_URI,
    x402PaymentRequiredResponse,
    x402SettleRequest,
    VerifyResponse,
    SettleResponse
)


class TestComposabilityPatterns:
    """Test that executors and core functions compose well together."""
    
    @pytest.mark.asyncio
    async def test_server_executor_with_manual_client(self):
        """Test server executor receiving payment from manual client processing."""
        # 1. Manual Client Side (using core functions)
        buyer_account = Account.from_key("0x" + "5" * 64)
        utils = X402Utils()
        
        # Client manually creates payment requirements
        requirements = create_payment_requirements(
            price="3000000",
            resource="/manual-client-test",
            merchant_address="0xautoserver456"
        )
        
        payment_required = x402PaymentRequiredResponse(
            x402_version=1,
            accepts=[requirements],
            error=""
        )
        
        # Client manually processes payment
        with patch('a2a_x402.core.wallet.x402Client') as mock_client_class, \
             patch('a2a_x402.core.wallet.process_payment') as mock_process_payment:
            
            mock_client = Mock()
            mock_client.select_payment_requirements.return_value = requirements
            mock_client_class.return_value = mock_client
            
            from a2a_x402.types import PaymentPayload, ExactPaymentPayload, EIP3009Authorization
            mock_payload = PaymentPayload(
                x402_version=1,
                scheme="exact",
                network="base",
                payload=ExactPaymentPayload(
                    signature="0x" + "d" * 130,
                    authorization=EIP3009Authorization(
                        from_=buyer_account.address,
                        to="0xautoserver456",
                        value="3000000",
                        valid_after="1640995200",
                        valid_before="1640998800",
                        nonce="0x" + "5" * 64
                    )
                )
            )
            mock_process_payment.return_value = mock_payload
            
            # Manual client processing
            settle_request = process_payment_required(payment_required, buyer_account)
        
        # 2. Automated Server Side (using executor)
        mock_business_service = Mock()
        mock_business_service.execute = AsyncMock(return_value="auto_server_result")
        
        config = X402ExtensionConfig()
        auto_server = X402ServerExecutor(mock_business_service, config)
        
        # Create task with manual client's payment
        task = Task(
            id="mixed-approach-task",
            contextId="mixed-context",
            status=TaskStatus(state=TaskState.working),
            metadata={}
        )
        
        task = utils.record_payment_submission(task, settle_request)
        
        # Mock facilitator for auto server
        mock_verify_response = VerifyResponse(is_valid=True, payer=buyer_account.address)
        mock_settle_response = SettleResponse(
            success=True,
            transaction="0xcomposed123",
            network="base",
            payer=buyer_account.address
        )
        
        auto_server.facilitator_client.verify = AsyncMock(return_value=mock_verify_response)
        auto_server.facilitator_client.settle = AsyncMock(return_value=mock_settle_response)
        
        # Execute automated server with manual client's payment
        mock_context = Mock()
        mock_context.headers = {"X-A2A-Extensions": X402_EXTENSION_URI}
        mock_context.current_task = task
        mock_event_queue = Mock()
        mock_event_queue.enqueue_event = AsyncMock()
        
        await auto_server.execute(mock_context, mock_event_queue)
        
        # Verify composition works seamlessly
        # Manual client payment + automated server processing = success
        auto_server.facilitator_client.verify.assert_called_once()
        mock_business_service.execute.assert_called_once()
        auto_server.facilitator_client.settle.assert_called_once()
        
        final_task = mock_event_queue.enqueue_event.call_args[0][0]
        final_status = auto_server.utils.get_payment_status(final_task)
        assert final_status == PaymentStatus.PAYMENT_COMPLETED
    
    @pytest.mark.asyncio
    async def test_manual_server_with_client_executor(self):
        """Test manual server processing receiving payment from client executor."""
        # 1. Automated Client Side (using executor)
        mock_service_client = Mock()
        mock_service_client.execute = AsyncMock()
        
        config = X402ExtensionConfig()
        buyer_account = Account.from_key("0x" + "6" * 64)
        auto_client = X402ClientExecutor(mock_service_client, config, buyer_account)
        
        # Setup payment required scenario
        requirements = create_payment_requirements(
            price="1800000",
            resource="/manual-server-test",
            merchant_address="0xmanualserver789"
        )
        
        payment_required = x402PaymentRequiredResponse(
            x402_version=1,
            accepts=[requirements],
            error=""
        )
        
        task = Task(
            id="auto-client-task",
            contextId="auto-client-context",
            status=TaskStatus(state=TaskState.submitted),
            metadata={}
        )
        
        task = auto_client.utils.create_payment_required_task(task, payment_required)
        
        # Mock client executor's automatic payment processing
        with patch('a2a_x402.executors.client.process_payment_required') as mock_auto_payment:
            from a2a_x402.types import PaymentPayload, ExactPaymentPayload, EIP3009Authorization
            auto_payload = PaymentPayload(
                x402_version=1,
                scheme="exact",
                network="base",
                payload=ExactPaymentPayload(
                    signature="0x" + "e" * 130,
                    authorization=EIP3009Authorization(
                        from_=buyer_account.address,
                        to="0xmanualserver789",
                        value="1800000",
                        valid_after="1640995200",
                        valid_before="1640998800",
                        nonce="0x" + "6" * 64
                    )
                )
            )
            
            auto_settle_request = x402SettleRequest(
                payment_requirements=requirements,
                payment_payload=auto_payload
            )
            mock_auto_payment.return_value = auto_settle_request
            
            # Execute auto client
            client_context = Mock()
            client_context.headers = {"X-A2A-Extensions": X402_EXTENSION_URI}
            client_context.current_task = task
            client_event_queue = Mock()
            client_event_queue.enqueue_event = AsyncMock()
            
            await auto_client.execute(client_context, client_event_queue)
            
            # Get the payment submission from auto client
            payment_task = client_event_queue.enqueue_event.call_args[0][0]
            assert auto_client.utils.get_payment_status(payment_task) == PaymentStatus.PAYMENT_SUBMITTED
        
        # 2. Manual Server Side (using core functions)
        utils = X402Utils()
        
        # Extract payment from client's submission
        client_settle_request = utils.get_settle_request(payment_task)
        assert client_settle_request is not None
        
        # Manual server verification
        mock_facilitator = Mock()
        mock_facilitator.verify = AsyncMock(return_value=VerifyResponse(
            is_valid=True,
            payer=buyer_account.address
        ))
        mock_facilitator.settle = AsyncMock(return_value=SettleResponse(
            success=True,
            transaction="0xmanual_server_tx",
            network="base",
            payer=buyer_account.address
        ))
        
        # Manual verification
        verify_result = await verify_payment(client_settle_request, mock_facilitator)
        assert verify_result.is_valid is True
        
        # Manual business logic execution (simulated)
        business_result = "manual_server_provided_service"
        
        # Manual settlement
        settle_result = await settle_payment(client_settle_request, mock_facilitator)
        assert settle_result.success is True
        
        # Manual state management
        final_task = utils.record_payment_success(payment_task, settle_result)
        
        # Verify composition works
        # Auto client payment + manual server processing = success
        final_status = utils.get_payment_status(final_task)
        assert final_status == PaymentStatus.PAYMENT_COMPLETED
        assert final_task.metadata[utils.RECEIPT_KEY]["transaction"] == "0xmanual_server_tx"
    
    def test_composability_assessment(self):
        """Assess overall composability of the a2a_x402 package."""
        # Test that all approaches use the same foundation
        utils = X402Utils()
        config = X402ExtensionConfig()
        account = Account.from_key("0x" + "7" * 64)
        
        # 1. Pure core functions approach
        requirements = create_payment_requirements("1000", "/test", "0x123")
        assert requirements is not None
        
        # 2. Server executor approach
        server = X402ServerExecutor(Mock(), config)
        assert server.utils.STATUS_KEY == utils.STATUS_KEY  # Same utilities
        
        # 3. Client executor approach  
        client = X402ClientExecutor(Mock(), config, account)
        assert client.utils.STATUS_KEY == utils.STATUS_KEY  # Same utilities
        
        # 4. All approaches use same data structures
        from a2a_x402.types import x402SettleRequest, x402SettleResponse
        # These types work across all approaches - good composability
        
        # 5. State management is consistent
        # All approaches can read/write the same task metadata
        assert server.utils.STATUS_KEY == client.utils.STATUS_KEY == utils.STATUS_KEY
        
    @pytest.mark.asyncio
    async def test_mixed_approach_flexibility(self):
        """Test that developers can mix and match approaches flexibly."""
        utils = X402Utils()
        
        # Scenario: Developer starts with manual approach, adds automation later
        
        # 1. Start with manual payment requirements (core functions)
        requirements = create_payment_requirements(
            price="2000000",
            resource="/flexible-service",
            merchant_address="0xflexible123"
        )
        
        # 2. Later wrap with server executor for automation
        config = X402ExtensionConfig()
        mock_delegate = Mock()
        server_executor = X402ServerExecutor(mock_delegate, config)
        
        # 3. Manual client can still work with automated server
        manual_payment_required = x402PaymentRequiredResponse(
            x402_version=1,
            accepts=[requirements],
            error=""
        )
        
        # The data structures are the same regardless of approach
        task = Task(
            id="flexible-task",
            contextId="flexible-context", 
            status=TaskStatus(state=TaskState.input_required),
            metadata={}
        )
        
        # Manual approach can create same task state as executor would
        task = utils.create_payment_required_task(task, manual_payment_required)
        
        # Executor can process task created by manual approach
        extracted = server_executor.utils.get_payment_requirements(task)
        assert extracted is not None
        assert extracted.x402_version == manual_payment_required.x402_version
        
        # This demonstrates good composability - same data, different processing
        assert utils.STATUS_KEY == server_executor.utils.STATUS_KEY
