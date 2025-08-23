"""End-to-end integration tests for a2a_x402 core payment flow."""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from eth_account import Account

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
    x402PaymentRequiredResponse,
    x402SettleResponse,
    PaymentStatus,
    VerifyResponse,
    SettleResponse,
    FacilitatorClient
)


class TestE2EPaymentFlow:
    """End-to-end integration tests for complete payment flow."""
    
    @pytest.mark.integration
    def test_seller_creates_payment_requirements(self):
        """Step 1: Seller creates payment requirements for a service."""
        # Seller wants to charge for image generation service
        requirements = create_payment_requirements(
            price="2500000",  # $2.50 in USDC (6 decimals)
            resource="/generate-image",
            merchant_address="0xseller123456789",
            network="base",
            description="AI image generation service",
            mime_type="image/png",
            max_timeout_seconds=300
        )
        
        # Verify seller created proper requirements
        assert requirements.max_amount_required == "2500000"
        assert requirements.resource == "/generate-image"
        assert requirements.pay_to == "0xseller123456789"
        assert requirements.network == "base"
        assert requirements.scheme == "exact"
        
        # Seller wraps requirements in PaymentRequired response
        payment_required = x402PaymentRequiredResponse(
            x402_version=1,
            accepts=[requirements],
            error=""
        )
        
        # Seller creates task with payment required state
        utils = X402Utils()
        task = Task(
            id="service-task-123",
            contextId="context-456",
            status=TaskStatus(state=TaskState.input_required),
            metadata={}
        )
        
        task = utils.create_payment_required_task(task, payment_required)
        
        # Verify task state
        assert utils.get_payment_status(task) == PaymentStatus.PAYMENT_REQUIRED
        extracted_requirements = utils.get_payment_requirements(task)
        assert extracted_requirements.x402_version == 1
        assert len(extracted_requirements.accepts) == 1
    
    @pytest.mark.integration
    def test_buyer_processes_payment_requirements(self):
        """Step 2: Buyer processes payment requirements and creates settle request."""
        # Setup payment requirements from seller
        requirements = create_payment_requirements(
            price="2500000",
            resource="/generate-image",
            merchant_address="0xseller123456789",
            network="base",
            description="AI image generation service"
        )
        
        payment_required = x402PaymentRequiredResponse(
            x402_version=1,
            accepts=[requirements],
            error=""
        )
        
        # Buyer has an account and processes the payment
        buyer_account = Account.from_key("0x" + "2" * 64)
        
        with patch('a2a_x402.core.wallet.x402Client') as mock_client_class:
            # Mock x402Client selection logic
            mock_client = Mock()
            mock_client.select_payment_requirements.return_value = payment_required.accepts[0]
            mock_client_class.return_value = mock_client
            
            # Mock the signing process to avoid real crypto operations
            with patch('a2a_x402.core.wallet.process_payment') as mock_process_payment:
                # Create a realistic mock payment payload
                from a2a_x402.types import PaymentPayload, ExactPaymentPayload, EIP3009Authorization
                mock_payload = PaymentPayload(
                    x402_version=1,
                    scheme="exact", 
                    network="base",
                    payload=ExactPaymentPayload(
                        signature="0x" + "b" * 130,
                        authorization=EIP3009Authorization(
                            from_=buyer_account.address,
                            to="0xseller123456789",
                            value="2500000",
                            valid_after="1640995200",
                            valid_before="1640995500",
                            nonce="0x" + "3" * 64
                        )
                    )
                )
                mock_process_payment.return_value = mock_payload
                
                # Buyer processes payment requirements
                # Updated for new spec - process_payment_required returns PaymentPayload directly
                payment_payload = process_payment_required(
                    payment_required,
                    buyer_account,
                    max_value=10000000  # $10 max
                )
                
                # Verify buyer created proper payment payload
                assert payment_payload == mock_payload
                assert payment_payload.scheme == "exact"
                
                # Verify x402Client was used for selection
                mock_client_class.assert_called_once_with(account=buyer_account, max_value=10000000)
                mock_client.select_payment_requirements.assert_called_once_with(payment_required.accepts)
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_seller_processes_settlement(self):
        """Step 3: Seller verifies and settles the payment."""
        # Setup settle request from buyer
        from a2a_x402.types import PaymentPayload, ExactPaymentPayload, EIP3009Authorization
        
        requirements = create_payment_requirements(
            price="2500000",
            resource="/generate-image", 
            merchant_address="0xseller123456789",
            network="base"
        )
        
        # Updated for new spec - work with PaymentPayload and PaymentRequirements separately
        payment_payload = PaymentPayload(
            x402_version=1,
            scheme="exact",
            network="base",
            payload=ExactPaymentPayload(
                signature="0x" + "a" * 130,
                authorization=EIP3009Authorization(
                    from_="0xbuyer456",
                    to="0xseller123456789",
                    value="2500000",
                    valid_after="1640995200",
                    valid_before="1640998800",
                    nonce="0x" + "1" * 64
                )
            )
        )
        
        # Mock facilitator responses
        mock_verify_response = VerifyResponse(
            is_valid=True,
            invalid_reason=None,
            payer=payment_payload.payload.authorization.from_
        )
        
        mock_settle_response = SettleResponse(
            success=True,
            transaction="0xabc123def456",
            network="base",
            payer=payment_payload.payload.authorization.from_,
            error_reason=None
        )
        
        # Mock facilitator client
        mock_facilitator = Mock(spec=FacilitatorClient)
        mock_facilitator.verify = AsyncMock(return_value=mock_verify_response)
        mock_facilitator.settle = AsyncMock(return_value=mock_settle_response)
        
        # Seller verifies payment first (new spec - separate parameters)
        verify_result = await verify_payment(payment_payload, requirements, mock_facilitator)
        
        assert verify_result.is_valid is True
        assert verify_result.payer == payment_payload.payload.authorization.from_
        
        # Seller settles payment (new spec - separate parameters)
        settlement_result = await settle_payment(payment_payload, requirements, mock_facilitator)
        
        # Verify settlement response conversion
        assert isinstance(settlement_result, x402SettleResponse)
        assert settlement_result.success is True
        assert settlement_result.transaction == "0xabc123def456"
        assert settlement_result.network == "base"
        assert settlement_result.payer == payment_payload.payload.authorization.from_
        
        # Verify facilitator was called correctly (new spec - separate parameters)
        mock_facilitator.verify.assert_called_once_with(
            payment_payload,
            requirements
        )
        mock_facilitator.settle.assert_called_once_with(
            payment_payload,
            requirements
        )
    
    @pytest.mark.integration
    @pytest.mark.asyncio 
    async def test_complete_payment_flow_success(self):
        """Complete end-to-end payment flow - success case."""
        # Step 1: Seller creates payment requirements
        seller_requirements = create_payment_requirements(
            price="1000000",  # $1.00 USDC
            resource="/premium-api-call",
            merchant_address="0xseller999",
            description="Premium API access",
            network="base"
        )
        
        payment_required = x402PaymentRequiredResponse(
            x402_version=1,
            accepts=[seller_requirements],
            error=""
        )
        
        # Step 2: Buyer processes payment
        buyer_account = Account.from_key("0x" + "4" * 64)
        
        with patch('a2a_x402.core.wallet.x402Client') as mock_client_class, \
             patch('a2a_x402.core.wallet.process_payment') as mock_process_payment:
            
            # Setup mocks
            mock_client = Mock()
            mock_client.select_payment_requirements.return_value = seller_requirements
            mock_client_class.return_value = mock_client
            
            from a2a_x402.types import PaymentPayload, ExactPaymentPayload, EIP3009Authorization
            mock_payload = PaymentPayload(
                x402_version=1,
                scheme="exact",
                network="base",
                payload=ExactPaymentPayload(
                    signature="0x" + "c" * 130,
                    authorization=EIP3009Authorization(
                        from_=buyer_account.address,
                        to="0xseller999",
                        value="1000000",
                        valid_after="1640995200",
                        valid_before="1640995500",
                        nonce="0x" + "5" * 64
                    )
                )
            )
            mock_process_payment.return_value = mock_payload
            
            # New spec - process_payment_required returns PaymentPayload directly
            payment_payload = process_payment_required(payment_required, buyer_account)
            
            # Step 3: Seller verifies and settles
            mock_facilitator = Mock(spec=FacilitatorClient)
            mock_facilitator.verify = AsyncMock(return_value=VerifyResponse(
                is_valid=True,
                payer=buyer_account.address
            ))
            mock_facilitator.settle = AsyncMock(return_value=SettleResponse(
                success=True,
                transaction="0xfinal789",
                network="base",
                payer=buyer_account.address
            ))
            
            # Verify and settle (new spec - separate parameters)
            verify_result = await verify_payment(payment_payload, seller_requirements, mock_facilitator)
            assert verify_result.is_valid is True
            
            settle_result = await settle_payment(payment_payload, seller_requirements, mock_facilitator)
            assert settle_result.success is True
            assert settle_result.transaction == "0xfinal789"
            
            # Step 4: Seller updates task state
            utils = X402Utils()
            task = Task(
                id="final-task-789",
                contextId="context-final",
                status=TaskStatus(state=TaskState.working),
                metadata={}
            )
            
            completed_task = utils.record_payment_success(task, settle_result)
            
            # Verify final state
            assert utils.get_payment_status(completed_task) == PaymentStatus.PAYMENT_COMPLETED
            assert completed_task.metadata[utils.RECEIPTS_KEY][0]["success"] is True
            assert completed_task.metadata[utils.RECEIPTS_KEY][0]["transaction"] == "0xfinal789"
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_complete_payment_flow_verification_failure(self):
        """Complete payment flow - verification failure case."""
        # Setup payment requirements
        requirements = create_payment_requirements(
            price="5000000",
            resource="/expensive-service", 
            merchant_address="0xseller456",
            network="base"
        )
        
        payment_required = x402PaymentRequiredResponse(
            x402_version=1,
            accepts=[requirements],
            error=""
        )
        
        # Buyer processes payment
        buyer_account = Account.from_key("0x" + "6" * 64)
        
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
                    signature="0xinvalidsig",
                    authorization=EIP3009Authorization(
                        from_=buyer_account.address,
                        to="0xseller456",
                        value="5000000",
                        valid_after="1640995200",
                        valid_before="1640995500", 
                        nonce="0x" + "7" * 64
                    )
                )
            )
            mock_process_payment.return_value = mock_payload
            
            # New spec - process_payment_required returns PaymentPayload directly
            payment_payload = process_payment_required(payment_required, buyer_account)

            # Mock facilitator verification failure
            mock_facilitator = Mock(spec=FacilitatorClient)
            mock_facilitator.verify = AsyncMock(return_value=VerifyResponse(
                is_valid=False,
                invalid_reason="Invalid signature format",
                payer=None
            ))

            # Verification should fail (new spec - separate parameters)
            verify_result = await verify_payment(payment_payload, requirements, mock_facilitator)
            assert verify_result.is_valid is False
            assert verify_result.invalid_reason == "Invalid signature format"
            
            # Seller records failure
            utils = X402Utils()
            task = Task(
                id="failed-task-456",
                contextId="context-failed",
                status=TaskStatus(state=TaskState.working),
                metadata={}
            )
            
            failure_response = x402SettleResponse(
                success=False,
                network="base",
                error_reason="Invalid signature format"
            )
            
            failed_task = utils.record_payment_failure(task, "INVALID_SIGNATURE", failure_response)
            
            # Verify failure state
            assert utils.get_payment_status(failed_task) == PaymentStatus.PAYMENT_FAILED
            assert failed_task.metadata[utils.ERROR_KEY] == "INVALID_SIGNATURE"
            assert failed_task.metadata[utils.RECEIPTS_KEY][0]["success"] is False
    
    @pytest.mark.integration
    def test_seller_buyer_interaction_with_task_correlation(self):
        """Test seller-buyer interaction with proper task correlation."""
        utils = X402Utils()
        
        # Seller scenario: Service request comes in
        original_task = Task(
            id="original-service-request-123",
            contextId="buyer-context-789", 
            status=TaskStatus(state=TaskState.submitted),
            metadata={}
        )
        
        # Seller determines payment is needed
        requirements = create_payment_requirements(
            price="3000000",
            resource="/ai-analysis",
            merchant_address="0xanalysismerchant",
            description="AI data analysis service"
        )
        
        payment_required = x402PaymentRequiredResponse(
            x402_version=1,
            accepts=[requirements],
            error=""
        )
        
        # Seller updates task to require payment
        payment_task = utils.create_payment_required_task(original_task, payment_required)
        
        # Buyer scenario: Receives payment required task
        buyer_account = Account.from_key("0x" + "8" * 64)
        extracted_requirements = utils.get_payment_requirements(payment_task)
        
        assert extracted_requirements is not None
        assert len(extracted_requirements.accepts) == 1
        
        # Buyer processes payment
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
                        to="0xanalysismerchant",
                        value="3000000",
                        valid_after="1640995200",
                        valid_before="1640995500",
                        nonce="0x" + "9" * 64
                    )
                )
            )
            mock_process_payment.return_value = mock_payload
            
            # New spec - process_payment_required returns PaymentPayload directly
            payment_payload = process_payment_required(extracted_requirements, buyer_account)

            # Buyer updates task with payment submission
            submitted_task = utils.record_payment_submission(payment_task, payment_payload)

            # Verify task correlation is maintained
            assert submitted_task.id == original_task.id
            assert utils.get_payment_status(submitted_task) == PaymentStatus.PAYMENT_SUBMITTED

            # Verify seller can extract payment payload (new spec method name)
            extracted_payment_payload = utils.get_payment_payload(submitted_task)
            assert extracted_payment_payload is not None
            assert extracted_payment_payload.payload.authorization.value == "3000000"
    
    @pytest.mark.integration
    def test_payment_flow_with_state_transitions(self):
        """Test complete payment flow with proper state transitions."""
        utils = X402Utils()
        
        # Initial task
        task = Task(
            id="state-transition-test",
            contextId="context-state",
            status=TaskStatus(state=TaskState.submitted),
            metadata={}
        )
        
        # State 1: Payment Required
        requirements = create_payment_requirements(
            price="1500000",
            resource="/state-test",
            merchant_address="0xstatemerchant"
        )
        
        payment_required = x402PaymentRequiredResponse(
            x402_version=1,
            accepts=[requirements],
            error=""
        )
        
        task = utils.create_payment_required_task(task, payment_required)
        assert utils.get_payment_status(task) == PaymentStatus.PAYMENT_REQUIRED
        assert utils.REQUIRED_KEY in task.metadata
        assert utils.PAYLOAD_KEY not in task.metadata
        
        # State 2: Payment Submitted (simulate buyer signing - new spec uses PaymentPayload directly)
        from a2a_x402.types import PaymentPayload, ExactPaymentPayload, EIP3009Authorization
        payment_payload = PaymentPayload(
            x402_version=1,
            scheme="exact",
            network="base",
            payload=ExactPaymentPayload(
                signature="0x" + "e" * 130,
                authorization=EIP3009Authorization(
                    from_="0xbuyer999",
                    to="0xstatemerchant",
                    value="1500000",
                    valid_after="1640995200",
                    valid_before="1640995500",
                    nonce="0x" + "f" * 64
                )
            )
        )

        task = utils.record_payment_submission(task, payment_payload)
        assert utils.get_payment_status(task) == PaymentStatus.PAYMENT_SUBMITTED
        assert utils.REQUIRED_KEY in task.metadata  # Kept for verification
        assert utils.PAYLOAD_KEY in task.metadata
        
        # State 3: Payment Completed
        success_response = x402SettleResponse(
            success=True,
            transaction="0xstatesuccess123",
            network="base",
            payer="0xbuyer999"
        )
        
        task = utils.record_payment_success(task, success_response)
        assert utils.get_payment_status(task) == PaymentStatus.PAYMENT_COMPLETED
        assert utils.PAYLOAD_KEY not in task.metadata  # Cleaned up after settlement
        assert utils.REQUIRED_KEY not in task.metadata  # Cleaned up after settlement
        assert utils.RECEIPTS_KEY in task.metadata
        
        # Verify final receipt
        receipt = task.metadata[utils.RECEIPTS_KEY][0]
        assert receipt["success"] is True
        assert receipt["transaction"] == "0xstatesuccess123"
        
        # Test failure path with new task
        failed_task = Task(
            id="failure-test", 
            contextId="context-fail",
            status=TaskStatus(state=TaskState.working),
            metadata={}
        )
        
        failed_task = utils.record_payment_submission(failed_task, payment_payload)
        
        failure_response = x402SettleResponse(
            success=False,
            network="base",
            error_reason="Insufficient funds"
        )
        
        failed_task = utils.record_payment_failure(failed_task, "INSUFFICIENT_FUNDS", failure_response)
        assert utils.get_payment_status(failed_task) == PaymentStatus.PAYMENT_FAILED
        assert failed_task.metadata[utils.ERROR_KEY] == "INSUFFICIENT_FUNDS"
