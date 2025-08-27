"""End-to-end integration tests for x402 executor middleware."""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from eth_account import Account

from a2a_x402.executors import X402ServerExecutor, X402ClientExecutor
from a2a_x402.core import create_payment_requirements
from a2a_x402.types import (
    Task,
    TaskState,
    TaskStatus,
    PaymentStatus,
    X402ExtensionConfig,
    X402ServerConfig,
    X402_EXTENSION_URI,
    x402PaymentRequiredResponse,
    SettleResponse,
    VerifyResponse
)


class TestExecutorE2E:
    """End-to-end tests for executor middleware in agent commerce scenarios."""
    
    @pytest.mark.asyncio
    async def test_selling_agent_with_server_executor(self, sample_server_config):
        """Test selling agent using X402ServerExecutor middleware."""
        # Selling agent provides image generation service
        mock_business_agent = Mock()
        mock_business_agent.execute = AsyncMock(return_value="generated_image.png")
        
        config = X402ExtensionConfig()
        selling_agent = X402ServerExecutor(mock_business_agent, config, sample_server_config)
        
        # Create a payment submission task (buyer has already paid)
        requirements = create_payment_requirements(
            price="$2.50",  # $2.50 USD
            resource="/generate-image",
            pay_to_address="0xseller123",
            description="AI image generation"
        )
        
        # Simulate buyer's payment submission
        from a2a_x402.types import PaymentPayload, ExactEvmPaymentPayload, EIP3009Authorization
        payment_payload = PaymentPayload(
            x402_version=1,
            scheme="exact",
            network="base",
            payload=ExactEvmPaymentPayload(
                signature="0x" + "a" * 130,
                authorization=EIP3009Authorization(
                    from_="0xbuyer456",
                    to="0xseller123",
                    value="2500000",
                    valid_after="1640995200",
                    valid_before="1640998800",
                    nonce="0x" + "1" * 64
                )
            )
        )
        
        # Create task with payment requirements first (simulating the full flow)
        task = Task(
            id="image-generation-task",
            contextId="buyer-context",
            status=TaskStatus(state=TaskState.working)
        )
        
        # Setup payment requirements before payment submission
        payment_required = x402PaymentRequiredResponse(
            x402_version=1,
            accepts=[requirements],
            error=""
        )
        task_with_requirements = selling_agent.utils.create_payment_required_task(task, payment_required)
        # Store the payment requirements in the server's store
        selling_agent._payment_requirements_store[task_with_requirements.id] = [requirements]
        task = selling_agent.utils.record_payment_submission(task_with_requirements, payment_payload)
        
        # Mock facilitator success
        mock_verify_response = VerifyResponse(is_valid=True, payer="0xbuyer456")
        mock_settle_response = SettleResponse(
            success=True,
            transaction="0xpayment123",
            network="base",
            payer="0xbuyer456"
        )
        
        selling_agent.facilitator_client.verify = AsyncMock(return_value=mock_verify_response)
        selling_agent.facilitator_client.settle = AsyncMock(return_value=mock_settle_response)
        
        # Execute selling agent
        mock_context = Mock()
        mock_context.headers = {"X-A2A-Extensions": X402_EXTENSION_URI}
        mock_context.current_task = task
        mock_event_queue = Mock()
        mock_event_queue.enqueue_event = AsyncMock()
        
        await selling_agent.execute(mock_context, mock_event_queue)
        
        # Verify complete flow
        # 1. Payment was verified
        selling_agent.facilitator_client.verify.assert_called_once()
        
        # 2. Business logic was executed
        mock_business_agent.execute.assert_called_once()
        
        # 3. Payment was settled
        selling_agent.facilitator_client.settle.assert_called_once()
        
        # 4. Task was completed successfully
        final_task = mock_event_queue.enqueue_event.call_args[0][0]
        final_status = selling_agent.utils.get_payment_status(final_task)
        assert final_status == PaymentStatus.PAYMENT_COMPLETED
        
        # 5. Payment receipt is available
        receipt = final_task.status.message.metadata[selling_agent.utils.RECEIPTS_KEY][0]
        assert receipt["success"] is True
        assert receipt["transaction"] == "0xpayment123"
    
    @pytest.mark.asyncio
    async def test_buying_agent_with_client_executor(self):
        """Test buying agent using X402ClientExecutor middleware."""
        # Buying agent wants to use a paid service
        mock_service_client = Mock()
        mock_service_client.execute = AsyncMock()
        
        config = X402ExtensionConfig()
        buyer_account = Account.from_key("0x" + "2" * 64)
        buying_agent = X402ClientExecutor(mock_service_client, config, buyer_account, max_value=10000000)
        
        # Create initial task (service request)
        task = Task(
            id="service-request-task",
            contextId="buyer-context",
            status=TaskStatus(state=TaskState.submitted)
        )
        
        # Service responds with payment required
        requirements = create_payment_requirements(
            price="$1.50",  # $1.50 USD
            resource="/premium-analysis",
            pay_to_address="0xanalysisservice",
            description="Premium data analysis"
        )
        
        payment_required = x402PaymentRequiredResponse(
            x402_version=1,
            accepts=[requirements],
            error=""
        )
        
        # Simulate service returning payment required
        task = buying_agent.utils.create_payment_required_task(task, payment_required)
        
        # Mock successful payment processing
        with patch('a2a_x402.executors.client.process_payment_required') as mock_process_payment:
            from a2a_x402.types import PaymentPayload, ExactEvmPaymentPayload, EIP3009Authorization
            mock_payload = PaymentPayload(
                x402_version=1,
                scheme="exact",
                network="base",
                payload=ExactEvmPaymentPayload(
                    signature="0x" + "b" * 130,
                    authorization=EIP3009Authorization(
                        from_=buyer_account.address,
                        to="0xanalysisservice",
                        value="1500000",
                        valid_after="1640995200",
                        valid_before="1640998800",
                        nonce="0x" + "2" * 64
                    )
                )
            )
            
            # Updated for new spec - process_payment returns PaymentPayload directly
            mock_process_payment.return_value = mock_payload
            
            # Execute buying agent
            mock_context = Mock()
            mock_context.headers = {"X-A2A-Extensions": X402_EXTENSION_URI}
            mock_context.current_task = task
            mock_event_queue = Mock()
            mock_event_queue.enqueue_event = AsyncMock()
            
            await buying_agent.execute(mock_context, mock_event_queue)
            
            # Verify automatic payment processing
            # 1. Original service was called
            mock_service_client.execute.assert_called_once()
            
            # 2. Payment was processed automatically
            mock_process_payment.assert_called_once_with(
                payment_required,
                buyer_account,
                buying_agent.max_value
            )
            
            # 3. Payment submission was enqueued
            mock_event_queue.enqueue_event.assert_called_once()
            
            # 4. Task now has payment submission
            final_task = mock_event_queue.enqueue_event.call_args[0][0]
            final_status = buying_agent.utils.get_payment_status(final_task)
            assert final_status == PaymentStatus.PAYMENT_SUBMITTED
    
    @pytest.mark.asyncio
    async def test_agent_commerce_full_flow_with_executors(self, sample_server_config):
        """Test complete agent commerce flow using both server and client executors."""
        # Setup: Two agents - image generator (seller) and content creator (buyer)
        
        # 1. Seller Agent Setup
        mock_image_generator = Mock()
        mock_image_generator.execute = AsyncMock(return_value="beautiful_image.png")
        
        seller_config = X402ExtensionConfig()
        # Create custom server config for this test
        image_service_config = X402ServerConfig(
            price="$2.50",
            pay_to_address="0xmerchant456",
            network="base",
            description="AI image generation service",
            resource="/generate"
        )
        image_service = X402ServerExecutor(mock_image_generator, seller_config, image_service_config)
        
        # 2. Buyer Agent Setup  
        mock_content_creator = Mock()
        mock_content_creator.execute = AsyncMock()
        
        buyer_config = X402ExtensionConfig()
        buyer_account = Account.from_key("0x" + "3" * 64)
        content_creator = X402ClientExecutor(mock_content_creator, buyer_config, buyer_account)
        
        # 3. Service Definition
        image_requirements = create_payment_requirements(
            price="$5.00",  # $5.00 USD for premium image
            resource="/generate-premium-image",
            pay_to_address="0ximageservice999",
            description="Premium AI image generation",
            network="base"
        )
        
        # 4. Buyer requests service (gets payment required)
        initial_task = Task(
            id="content-creation-project",
            contextId="creator-context",
            status=TaskStatus(state=TaskState.submitted)
        )
        
        payment_required = x402PaymentRequiredResponse(
            x402_version=1,
            accepts=[image_requirements],
            error=""
        )
        
        # Simulate service responding with payment required
        payment_task = content_creator.utils.create_payment_required_task(initial_task, payment_required)
        
        # 5. Buyer processes payment automatically
        with patch('a2a_x402.executors.client.process_payment_required') as mock_buyer_payment:
            from a2a_x402.types import PaymentPayload, ExactEvmPaymentPayload, EIP3009Authorization
            mock_buyer_payload = PaymentPayload(
                x402_version=1,
                scheme="exact",
                network="base",
                payload=ExactEvmPaymentPayload(
                    signature="0x" + "c" * 130,
                    authorization=EIP3009Authorization(
                        from_=buyer_account.address,
                        to="0ximageservice999",
                        value="5000000",
                        valid_after="1640995200",
                        valid_before="1640998800",
                        nonce="0x" + "3" * 64
                    )
                )
            )
            # Updated for new spec - process_payment returns PaymentPayload directly
            mock_buyer_payment.return_value = mock_buyer_payload
            
            buyer_context = Mock()
            buyer_context.headers = {"X-A2A-Extensions": X402_EXTENSION_URI}
            buyer_context.current_task = payment_task
            buyer_event_queue = Mock()
            buyer_event_queue.enqueue_event = AsyncMock()
            
            # Buyer executes (auto-pays)
            await content_creator.execute(buyer_context, buyer_event_queue)
            
            # Verify buyer processed payment
            mock_buyer_payment.assert_called_once()
            buyer_final_task = buyer_event_queue.enqueue_event.call_args[0][0]
            assert content_creator.utils.get_payment_status(buyer_final_task) == PaymentStatus.PAYMENT_SUBMITTED
        
        # 6. Seller processes the paid request
        # Extract the payment submission from buyer
        paid_task = buyer_final_task
        
        # Store the payment requirements in the seller's executor store
        # (In a real scenario, this would have been stored when the seller first issued the payment request)
        image_service._payment_requirements_store[paid_task.id] = [image_requirements]
        
        # Mock successful verification and settlement
        mock_verify_response = VerifyResponse(is_valid=True, payer=buyer_account.address)
        mock_settle_response = SettleResponse(
            success=True,
            transaction="0xcommerce_success",
            network="base",
            payer=buyer_account.address
        )
        
        image_service.facilitator_client.verify = AsyncMock(return_value=mock_verify_response)
        image_service.facilitator_client.settle = AsyncMock(return_value=mock_settle_response)
        
        seller_context = Mock()
        seller_context.headers = {"X-A2A-Extensions": X402_EXTENSION_URI}
        seller_context.current_task = paid_task
        seller_event_queue = Mock()
        seller_event_queue.enqueue_event = AsyncMock()
        
        # Seller executes (verifies, provides service, settles)
        await image_service.execute(seller_context, seller_event_queue)
        
        # 7. Verify complete commerce flow
        # Payment verified
        image_service.facilitator_client.verify.assert_called_once()
        
        # Service provided
        mock_image_generator.execute.assert_called_once()
        
        # Payment settled
        image_service.facilitator_client.settle.assert_called_once()
        
        # Final state is completed
        seller_final_task = seller_event_queue.enqueue_event.call_args[0][0]
        final_status = image_service.utils.get_payment_status(seller_final_task)
        assert final_status == PaymentStatus.PAYMENT_COMPLETED
        
        # Commerce transaction complete!
        receipt = seller_final_task.status.message.metadata[image_service.utils.RECEIPTS_KEY][0]
        assert receipt["success"] is True
        assert receipt["transaction"] == "0xcommerce_success"
        assert receipt["payer"] == buyer_account.address
    
    def test_executor_value_proposition(self, sample_server_config):
        """Test that executors provide clear developer value."""
        config = X402ExtensionConfig()
        account = Account.from_key("0x" + "4" * 64)
        
        # Server executor for selling agents
        server = X402ServerExecutor(Mock(), config, sample_server_config)
        
        # Value: Automatic payment wall for any business logic
        assert server is not None
        assert hasattr(server, 'execute')
        assert server.facilitator_client is not None
        
        # Client executor for buying agents  
        client = X402ClientExecutor(Mock(), config, account)
        
        # Value: Automatic payment processing for any service requests
        assert client is not None
        assert hasattr(client, 'execute')
        assert client.account == account
        assert client.auto_pay is True  # Default to automatic payments
        
        # Both executors are middleware - they wrap existing functionality
        assert hasattr(server, '_delegate')
        assert hasattr(client, '_delegate')
        
        # Both use core protocol functions under the hood
        assert server.utils is not None
        assert client.utils is not None
