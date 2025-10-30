# ADK x402 Payment Protocol Demo - Architecture Documentation

## Table of Contents

1. [Overview](#overview)
2. [System Architecture](#system-architecture)
3. [Component Overview](#component-overview)
4. [Complete Payment Flow](#complete-payment-flow)
5. [x402_a2a Library Methods Reference](#x402_a2a-library-methods-reference)
6. [Detailed Flow Diagrams](#detailed-flow-diagrams)
7. [Key Design Patterns](#key-design-patterns)
8. [Pluggable Components](#pluggable-components)

---

## Overview

This demo implements a complete end-to-end payment flow between two AI agents using the **A2A x402 Payment Protocol Extension**. The system demonstrates how agents can autonomously negotiate and execute payments for services.

### Core Concept

The x402 protocol enables payment-gated services through a standardized exception-based pattern:

1. **Merchant Agent** requests payment by raising `x402PaymentRequiredException`
2. **x402ServerExecutor** intercepts the exception and creates a payment request
3. **Client Agent** receives payment requirements and prompts user for approval
4. **Wallet** signs the payment authorization using EIP-3009
5. **Server** verifies and settles the payment through a **Facilitator**
6. **Service** is executed and results are returned to the client

---

## System Architecture

```mermaid
graph TB
    subgraph "Client Side"
        User[User/Browser]
        ADKWeb[ADK Web UI]
        ClientAgent[ClientAgent]
        Wallet[MockLocalWallet]
    end

    subgraph "x402 Client Library"
        x402Utils1[x402Utils]
        ProcessPayment[process_payment_required]
    end

    subgraph "Network"
        HTTP[HTTP/JSON-RPC]
    end

    subgraph "Server Side"
        Routes[Starlette Routes]
        A2AApp[A2AStarletteApplication]

        subgraph "Executor Chain"
            x402Executor[x402MerchantExecutor]
            ADKExecutor[ADKAgentExecutor]
        end

        MerchantAgent[AdkMerchantAgent]
        Facilitator[MockFacilitator / FacilitatorClient]
    end

    subgraph "x402 Server Library"
        x402Utils2[x402Utils]
        ServerExec[x402ServerExecutor Base]
    end

    User -->|Interacts| ADKWeb
    ADKWeb -->|Runs| ClientAgent
    ClientAgent -->|Uses| x402Utils1
    ClientAgent -->|Signs with| Wallet
    Wallet -->|Uses| ProcessPayment

    ClientAgent <-->|Messages| HTTP
    HTTP <-->|Routes| A2AApp
    A2AApp -->|Delegates| x402Executor
    x402Executor -->|Wraps| ADKExecutor
    ADKExecutor -->|Executes| MerchantAgent

    x402Executor -->|Uses| x402Utils2
    x402Executor -->|Verify/Settle| Facilitator
    x402Executor -.Inherits.-> ServerExec

    style x402Executor fill:#e1f5ff
    style ClientAgent fill:#e1f5ff
    style x402Utils1 fill:#fff4e1
    style x402Utils2 fill:#fff4e1
    style Wallet fill:#f0f0f0
    style Facilitator fill:#f0f0f0
```

---

## Component Overview

### Client-Side Components

#### 1. **ClientAgent** (`client_agent/client_agent.py`)

The orchestrator agent that manages user interaction and delegates tasks to remote agents.

**Key Responsibilities:**

- Discover available remote agents
- Send messages to merchant agents
- Handle payment-required responses
- Prompt user for payment approval
- Coordinate wallet signing
- Report final outcomes

**Key Methods:**

- `list_remote_agents()` - Lists available agents
- `send_message(agent_name, message, tool_context)` - Sends messages and handles payment flows

#### 2. **Wallet Interface** (`client_agent/wallet.py`)

Abstract interface for payment signing, allowing different wallet implementations.

**Key Implementations:**

- `MockLocalWallet` - Demo wallet with hardcoded private key (NOT for production)
- Future: MetaMask integration, MPC services, hardware wallets

#### 3. **RemoteAgentConnections** (`client_agent/_remote_agent_connection.py`)

Manages HTTP connections to remote A2A agents.

### Server-Side Components

#### 4. **AdkMerchantAgent** (`server/agents/adk_merchant_agent.py`)

The merchant's business logic agent, responsible for product information and payment requests.

**Key Responsibilities:**

- Provide product details and pricing
- Raise `x402PaymentRequiredException` when payment is needed
- Process verified payments
- Return service results

**Key Methods:**

- `get_product_details_and_request_payment(product_name)` - Tool that requests payment
- `before_agent_callback(callback_context)` - Injects payment verification status

#### 5. **x402MerchantExecutor** (`server/agents/x402_merchant_executor.py`)

Concrete implementation of the x402 server-side protocol handler.

**Key Responsibilities:**

- Intercept `x402PaymentRequiredException`
- Create payment-required responses
- Verify payments with facilitator
- Settle payments
- Record payment status

**Key Methods:**

- `verify_payment(payload, requirements)` - Verify payment with facilitator
- `settle_payment(payload, requirements)` - Settle payment with facilitator

#### 6. **ADKAgentExecutor** (`server/agents/_adk_agent_executor.py`)

Bridges the ADK (Google Agent Development Kit) with the A2A protocol.

**Key Responsibilities:**

- Execute ADK agent tools
- Convert between A2A and GenAI types
- Handle multi-turn agent conversations
- Propagate `x402PaymentRequiredException` to wrapper

#### 7. **MockFacilitator** (`server/agents/mock_facilitator.py`)

Testing facilitator that approves all valid transactions without blockchain interaction.

**Production Alternative:**

- `FacilitatorClient` - Real facilitator for on-chain settlement

---

## Complete Payment Flow

```mermaid
sequenceDiagram
    participant User
    participant ClientAgent
    participant Wallet
    participant x402Utils as x402Utils (Client)
    participant HTTP
    participant Server as x402MerchantExecutor
    participant ADKExec as ADKAgentExecutor
    participant Merchant as AdkMerchantAgent
    participant Facilitator

    User->>ClientAgent: "I want to buy a banana"
    ClientAgent->>HTTP: send_message("merchant_agent", "buy banana")
    HTTP->>Server: MessageSendParams

    Note over Server: Phase 1: Payment Request
    Server->>ADKExec: execute(context, event_queue)
    ADKExec->>Merchant: Call tool: get_product_details_and_request_payment("banana")
    Merchant->>Merchant: Calculate price
    Merchant-->>ADKExec: Raise x402PaymentRequiredException(requirements)
    ADKExec-->>Server: Propagate exception

    Server->>Server: Store payment requirements in _payment_requirements_store[task_id]
    Server->>Server: x402Utils.create_payment_required_task(task, requirements)
    Server->>HTTP: Task (state=input_required, metadata with x402.payment.required)
    HTTP->>ClientAgent: Task with payment requirements

    ClientAgent->>ClientAgent: Extract payment requirements using x402Utils
    ClientAgent->>User: "Merchant requesting payment for 'banana' for 12345 USDC. Approve?"
    User->>ClientAgent: "yes"

    Note over ClientAgent,Wallet: Phase 2: Payment Signing
    ClientAgent->>Wallet: sign_payment(requirements)
    Wallet->>x402Utils: process_payment_required(requirements, account)
    x402Utils->>x402Utils: prepare_payment_header()
    x402Utils->>x402Utils: sign_payment_header() [EIP-3009]
    x402Utils->>Wallet: PaymentPayload with signature
    Wallet->>ClientAgent: Signed PaymentPayload

    ClientAgent->>ClientAgent: Create message with metadata[x402.payment.object]
    ClientAgent->>HTTP: send_message with PaymentPayload in metadata
    HTTP->>Server: MessageSendParams with payment

    Note over Server,Facilitator: Phase 3: Payment Verification
    Server->>Server: Detect PaymentStatus.PAYMENT_SUBMITTED
    Server->>Server: Extract PaymentPayload from message
    Server->>Server: Retrieve requirements from _payment_requirements_store[task_id]
    Server->>Facilitator: verify(payload, requirements)
    Facilitator->>Facilitator: Validate signature, amounts, addresses
    Facilitator->>Server: VerifyResponse(is_valid=true, payer=address)

    Server->>Server: x402Utils.record_payment_verified(task)
    Server->>Server: Set task.metadata["x402_payment_verified"] = True

    Note over Server,Merchant: Phase 4: Service Execution
    Server->>ADKExec: execute(context, event_queue)
    ADKExec->>ADKExec: Detect x402_payment_verified=True
    ADKExec->>ADKExec: Set session.state["payment_verified_data"]
    ADKExec->>Merchant: Run agent with payment verification
    Merchant->>Merchant: before_agent_callback() injects payment status
    Merchant->>Merchant: LLM processes "payment verified"
    Merchant->>ADKExec: "Your order is being prepared!"
    ADKExec->>Server: Agent response

    Note over Server,Facilitator: Phase 5: Payment Settlement
    Server->>Facilitator: settle(payload, requirements)
    Facilitator->>Facilitator: Execute on-chain transaction (or mock)
    Facilitator->>Server: SettleResponse(success=true, network="base-sepolia")

    Server->>Server: x402Utils.record_payment_success(task, settle_response)
    Server->>Server: Set task status to PAYMENT_COMPLETED
    Server->>HTTP: Task (completed, with artifacts)
    HTTP->>ClientAgent: Final task result
    ClientAgent->>User: "Payment successful! Your purchase is complete."
```

---

## x402_a2a Library Methods Reference

### Core Utility Class: `x402Utils`

Located in: `x402_a2a/core/utils.py`

The `x402Utils` class provides state management for the x402 protocol across A2A tasks and messages.

#### Metadata Keys

```python
STATUS_KEY = "x402.payment.status"
REQUIRED_KEY = "x402.payment.required"
PAYLOAD_KEY = "x402.payment.object"
RECEIPTS_KEY = "x402.payment.receipts"
ERROR_KEY = "x402.payment.error"
```

#### Payment Status Methods

##### `get_payment_status(task: Task) -> Optional[PaymentStatus]`

Extracts the current payment status from a task's metadata.

**Returns:**

- `PaymentStatus.PAYMENT_REQUIRED` - Payment is needed
- `PaymentStatus.PAYMENT_SUBMITTED` - Client sent payment
- `PaymentStatus.PAYMENT_VERIFIED` - Payment verified
- `PaymentStatus.PAYMENT_COMPLETED` - Payment settled successfully
- `PaymentStatus.PAYMENT_FAILED` - Payment failed
- `None` - No payment status found

**Usage Example:**

```python
utils = x402Utils()
status = utils.get_payment_status(task)
if status == PaymentStatus.PAYMENT_SUBMITTED:
    # Process payment
```

##### `get_payment_status_from_message(message: Message) -> Optional[PaymentStatus]`

Extracts payment status directly from a message.

##### `get_payment_status_from_task(task: Task) -> Optional[PaymentStatus]`

Extracts payment status from task's status message metadata.

#### Payment Requirements Methods

##### `get_payment_requirements(task: Task) -> Optional[x402PaymentRequiredResponse]`

Extracts payment requirements from a task. These requirements contain the `accepts` array with payment options.

**Returns:** `x402PaymentRequiredResponse` object containing:

- `x402_version`: Protocol version
- `accepts`: List of `PaymentRequirements` objects
- `error`: Error message (optional)

**Usage Example:**

```python
requirements = utils.get_payment_requirements(task)
if requirements:
    for option in requirements.accepts:
        print(f"Network: {option.network}, Amount: {option.max_amount_required}")
```

##### `get_payment_requirements_from_message(message: Message) -> Optional[x402PaymentRequiredResponse]`

Extracts payment requirements directly from a message.

#### Payment Payload Methods

##### `get_payment_payload(task: Task) -> Optional[PaymentPayload]`

Extracts the signed payment payload from a task.

**Returns:** `PaymentPayload` object containing:

- `x402_version`: Protocol version
- `scheme`: Payment scheme (e.g., "exact")
- `network`: Blockchain network
- `payload`: Scheme-specific payload (e.g., `ExactPaymentPayload` with EIP-3009 authorization)

**Usage Example:**

```python
payload = utils.get_payment_payload(task)
if payload and isinstance(payload.payload, ExactPaymentPayload):
    auth = payload.payload.authorization
    print(f"From: {auth.from_}, Amount: {auth.value}")
```

##### `get_payment_payload_from_message(message: Message) -> Optional[PaymentPayload]`

Extracts payment payload directly from a message.

#### Task State Management Methods

##### `create_payment_required_task(task: Task, payment_required: x402PaymentRequiredResponse) -> Task`

Updates a task to indicate payment is required.

**Actions:**

- Sets task state to `TaskState.input_required`
- Adds payment requirements to metadata
- Sets payment status to `PAYMENT_REQUIRED`

**Usage Example:**

```python
payment_required = x402PaymentRequiredResponse(
    x402_version=1,
    accepts=[requirements],
    error="Payment required for banana"
)
task = utils.create_payment_required_task(task, payment_required)
# Task is now ready to be sent to client
```

##### `record_payment_verified(task: Task) -> Task`

Records that payment has been verified.

**Actions:**

- Sets payment status to `PAYMENT_VERIFIED`
- Maintains task state

##### `record_payment_success(task: Task, settle_response: SettleResponse) -> Task`

Records successful payment settlement.

**Actions:**

- Sets payment status to `PAYMENT_COMPLETED`
- Appends settlement receipt to `x402.payment.receipts` array
- Cleans up intermediate payment data

**Usage Example:**

```python
settle_response = SettleResponse(
    success=True,
    network="base-sepolia",
    transaction_hash="0x123..."
)
task = utils.record_payment_success(task, settle_response)
```

##### `record_payment_failure(task: Task, error_code: str, settle_response: SettleResponse) -> Task`

Records payment failure.

**Actions:**

- Sets payment status to `PAYMENT_FAILED`
- Records error code in metadata
- Appends failure receipt

#### Receipt Methods

##### `get_payment_receipts(task: Task) -> list[SettleResponse]`

Gets all payment receipts from a task.

##### `get_latest_receipt(task: Task) -> Optional[SettleResponse]`

Gets the most recent payment receipt.

### Wallet Functions

Located in: `x402_a2a/core/wallet.py`

##### `process_payment_required(payment_required: x402PaymentRequiredResponse, account: Account, max_value: Optional[int] = None) -> PaymentPayload`

Processes a complete payment-required response and creates a signed payment payload.

**Parameters:**

- `payment_required`: The complete response from merchant with `accepts[]` array
- `account`: Ethereum account (from `eth_account`) for signing
- `max_value`: Maximum payment value willing to pay (optional)

**Returns:** `PaymentPayload` - Fully signed payment ready to send

**Process:**

1. Uses `x402Client` to select best payment requirement from `accepts` array
2. Calls `process_payment()` to sign the selected requirement
3. Returns signed payload

**Usage Example:**

```python
from eth_account import Account
from x402_a2a import process_payment_required

account = Account.from_key(private_key)
signed_payload = process_payment_required(payment_required, account)
# signed_payload is ready to send to merchant
```

##### `process_payment(requirements: PaymentRequirements, account: Account, max_value: Optional[int] = None) -> PaymentPayload`

Creates a signed `PaymentPayload` for a single payment requirement using EIP-3009 signing.

**Parameters:**

- `requirements`: Single `PaymentRequirements` object to sign
- `account`: Ethereum account for signing
- `max_value`: Maximum payment value (optional)

**Returns:** `PaymentPayload` with signature

**Process:**

1. Prepares unsigned payment header with authorization details
2. Signs using EIP-712 typed data signing (EIP-3009)
3. Constructs `PaymentPayload` with `ExactPaymentPayload` containing:
   - `signature`: EIP-712 signature
   - `authorization`: EIP-3009 authorization with from, to, value, nonce, validity window

### Extension Functions

Located in: `x402_a2a/types/` and `x402_a2a/extension.py`

##### `get_extension_declaration(description: str, required: bool) -> dict`

Creates an extension declaration for an agent card.

**Usage Example:**

```python
from x402_a2a import get_extension_declaration

capabilities = AgentCapabilities(
    streaming=False,
    extensions=[
        get_extension_declaration(
            description="Supports payments using the x402 protocol.",
            required=True
        )
    ]
)
```

### Exception Classes

##### `x402PaymentRequiredException`

Located in: `x402_a2a/types/errors.py`

Exception raised by merchant agents to signal payment is required.

**Constructor:**

```python
x402PaymentRequiredException(
    resource_name: str,
    requirements: PaymentRequirements | List[PaymentRequirements]
)
```

**Methods:**

- `get_accepts_array() -> List[PaymentRequirements]` - Returns payment requirements as list

**Usage Example:**

```python
from x402_a2a import x402PaymentRequiredException, PaymentRequirements

requirements = PaymentRequirements(
    scheme="exact",
    network="base-sepolia",
    asset="0x036CbD53842c5426634e7929541eC2318f3dCF7e",
    pay_to="0xAb5801a7D398351b8bE11C439e05C5B3259aeC9B",
    max_amount_required="100000",
    description="Payment for: banana",
)

raise x402PaymentRequiredException("banana", requirements)
```

### Server Executor

##### `x402ServerExecutor` (Abstract Base Class)

Located in: `x402_a2a/executors/server.py`

Server-side middleware that wraps an `AgentExecutor` to handle the x402 payment protocol.

**Abstract Methods to Implement:**

```python
async def verify_payment(
    self,
    payload: PaymentPayload,
    requirements: PaymentRequirements
) -> VerifyResponse:
    """Verify payment with facilitator"""

async def settle_payment(
    self,
    payload: PaymentPayload,
    requirements: PaymentRequirements
) -> SettleResponse:
    """Settle payment with facilitator"""
```

**Key Features:**

- Automatically intercepts `x402PaymentRequiredException`
- Manages payment state across request cycles
- Stores payment requirements for verification
- Coordinates verify → execute → settle flow

**Usage Example:**

```python
from x402_a2a.executors import x402ServerExecutor
from x402_a2a import FacilitatorClient, x402ExtensionConfig

class MyMerchantExecutor(x402ServerExecutor):
    def __init__(self, delegate: AgentExecutor):
        super().__init__(delegate, x402ExtensionConfig())
        self._facilitator = FacilitatorClient(facilitator_config)

    async def verify_payment(self, payload, requirements):
        return await self._facilitator.verify(payload, requirements)

    async def settle_payment(self, payload, requirements):
        return await self._facilitator.settle(payload, requirements)
```

### Facilitator Client

##### `FacilitatorClient`

Located in: `x402/facilitator/` (from x402 base library)

Handles on-chain payment verification and settlement.

**Methods:**

- `verify(payload: PaymentPayload, requirements: PaymentRequirements) -> VerifyResponse`
- `settle(payload: PaymentPayload, requirements: PaymentRequirements) -> SettleResponse`

---

## Detailed Flow Diagrams

### Phase 1: Payment Request Flow

```mermaid
graph TD
    Start[User: Buy banana] --> ClientSend[ClientAgent sends message]
    ClientSend --> ServerRecv[x402MerchantExecutor.execute]
    ServerRecv --> CheckStatus{Check payment status}
    CheckStatus -->|No payment| DelegateExec[Delegate to ADKAgentExecutor]

    DelegateExec --> RunAgent[Run ADK agent]
    RunAgent --> ToolCall[Agent calls tool: get_product_details_and_request_payment]
    ToolCall --> CalcPrice[Calculate price for banana]
    CalcPrice --> RaiseException[Raise x402PaymentRequiredException]

    RaiseException --> CatchException[Executor catches exception]
    CatchException --> StoreReqs[Store requirements in _payment_requirements_store]
    StoreReqs --> CreateTask[x402Utils.create_payment_required_task]
    CreateTask --> SetMetadata[Set task metadata with x402.payment.required]
    SetMetadata --> SetState[Set task.state = input_required]
    SetState --> SendToClient[Send Task to client]
    SendToClient --> ClientRecv[ClientAgent receives Task]
    ClientRecv --> ExtractReqs[Extract payment requirements]
    ExtractReqs --> PromptUser[Prompt user for approval]

    style RaiseException fill:#ffcccc
    style CatchException fill:#ccffcc
    style StoreReqs fill:#ffffcc
    style SetMetadata fill:#ccccff
```

### Phase 2: Payment Signing Flow

```mermaid
graph TD
    UserApprove[User approves payment] --> GetReqs[Get payment requirements from state]
    GetReqs --> CallWallet[Call wallet.sign_payment]

    CallWallet --> ProcessReq[process_payment_required]
    ProcessReq --> SelectReq[x402Client.select_payment_requirements]
    SelectReq --> PrepHeader[prepare_payment_header]
    PrepHeader --> CreateAuth[Create EIP-3009 authorization]

    CreateAuth --> SignHeader[sign_payment_header]
    SignHeader --> EIP712Sign[EIP-712 typed data signing]
    EIP712Sign --> DecodePayment[Decode signed payload]
    DecodePayment --> CreatePayload[Create PaymentPayload object]

    CreatePayload --> ReturnSig[Return signed PaymentPayload]
    ReturnSig --> AddMetadata[Add to message metadata]
    AddMetadata --> SetStatus[Set x402.payment.status = PAYMENT_SUBMITTED]
    SetStatus --> AddPayload[Set x402.payment.object = signed payload]
    AddPayload --> SendToServer[Send message to server]

    style SignHeader fill:#ccffcc
    style EIP712Sign fill:#ffffcc
    style AddPayload fill:#ccccff
```

### Phase 3: Payment Verification & Settlement Flow

```mermaid
graph TD
    ServerRecv[x402MerchantExecutor receives message] --> DetectPayment{Detect PAYMENT_SUBMITTED?}
    DetectPayment -->|Yes| ExtractPayload[Extract PaymentPayload from metadata]

    ExtractPayload --> GetReqs[Get requirements from store using task.id]
    GetReqs --> MatchReqs[Match requirement to payload]
    MatchReqs --> CallVerify[Call verify_payment]

    CallVerify --> FacilitatorVerify[Facilitator.verify]
    FacilitatorVerify --> CheckSig[Verify EIP-712 signature]
    CheckSig --> CheckAmounts[Verify amounts match]
    CheckAmounts --> CheckAddresses[Verify addresses match]
    CheckAddresses --> ReturnValid{Is valid?}

    ReturnValid -->|Yes| RecordVerified[x402Utils.record_payment_verified]
    ReturnValid -->|No| FailPayment[Fail payment]

    RecordVerified --> SetMetadata[Set task.metadata.x402_payment_verified = True]
    SetMetadata --> ExecuteDelegate[Execute delegate agent]
    ExecuteDelegate --> ServiceLogic[Run merchant's service logic]
    ServiceLogic --> ServiceComplete[Service completed]

    ServiceComplete --> CallSettle[Call settle_payment]
    CallSettle --> FacilitatorSettle[Facilitator.settle]
    FacilitatorSettle --> OnChain[Execute on-chain transaction]
    OnChain --> SettleSuccess{Settled?}

    SettleSuccess -->|Yes| RecordSuccess[x402Utils.record_payment_success]
    SettleSuccess -->|No| RecordFailure[x402Utils.record_payment_failure]

    RecordSuccess --> AddReceipt[Add receipt to x402.payment.receipts]
    RecordFailure --> AddError[Add error to x402.payment.error]
    AddReceipt --> SetCompleted[Set status = PAYMENT_COMPLETED]
    AddError --> SetFailed[Set status = PAYMENT_FAILED]

    SetCompleted --> SendResult[Send final Task to client]
    SetFailed --> SendResult
    FailPayment --> SendResult

    style FacilitatorVerify fill:#ccffcc
    style CheckSig fill:#ffffcc
    style OnChain fill:#ffcccc
    style RecordSuccess fill:#ccccff
```

### Executor Chain Flow

```mermaid
graph LR
    Request[A2A Request] --> Handler[DefaultRequestHandler]
    Handler --> x402Exec[x402MerchantExecutor]

    x402Exec --> CheckPayment{Has PaymentPayload?}
    CheckPayment -->|Yes| VerifyFlow[Verify & Settle Flow]
    CheckPayment -->|No| Delegate1[Delegate to ADKAgentExecutor]

    Delegate1 --> RunAgent[Run ADK Agent]
    RunAgent --> ToolExec[Execute Agent Tool]
    ToolExec --> Exception{x402PaymentRequiredException?}

    Exception -->|Yes| PropUp[Propagate to x402Executor]
    Exception -->|No| Return1[Return normal response]

    PropUp --> CatchExec[x402Executor catches]
    CatchExec --> CreateReq[Create payment-required response]
    CreateReq --> Return2[Return to client]

    VerifyFlow --> Verify[Facilitator.verify]
    Verify --> Delegate2[Delegate to ADKAgentExecutor]
    Delegate2 --> RunService[Run service with verified flag]
    RunService --> Settle[Facilitator.settle]
    Settle --> Return3[Return completed task]

    style x402Exec fill:#e1f5ff
    style Exception fill:#ffcccc
    style CatchExec fill:#ccffcc
    style Verify fill:#ffffcc
```

---

## Key Design Patterns

### 1. Exception-Based Payment Request Pattern

Instead of returning payment requirements directly from tools, agents raise an exception:

```python
# ❌ Old approach - requires mixing business logic with protocol
def get_product(product_name: str) -> dict:
    price = calculate_price(product_name)
    return {
        "x402_payment_required": {
            "accepts": [...]
        }
    }

# ✅ New approach - clean separation
def get_product(product_name: str) -> dict:
    price = calculate_price(product_name)
    requirements = PaymentRequirements(...)
    raise x402PaymentRequiredException(product_name, requirements)
```

**Benefits:**

- Business logic stays pure
- Protocol handling is delegated to middleware
- Easy to add payment gates to existing functions

### 2. Executor Wrapper Pattern

The x402 protocol is implemented as executor wrappers that intercept requests:

```python
# Layer 1: Base agent executor (business logic)
agent_executor = ADKAgentExecutor(runner, agent_card)

# Layer 2: x402 protocol wrapper (payment handling)
agent_executor = x402MerchantExecutor(agent_executor)

# Layer 3: Request handler (A2A protocol)
request_handler = DefaultRequestHandler(
    agent_executor=agent_executor,
    task_store=InMemoryTaskStore()
)
```

**Benefits:**

- Separation of concerns
- Protocol logic is reusable
- Easy to add/remove features
- Business logic doesn't know about payments

### 3. State Injection Pattern

Payment verification status is injected into the agent's callback:

```python
# In ADKAgentExecutor
if context.current_task.metadata.get("x402_payment_verified"):
    session.state["payment_verified_data"] = {
        "product": product_name,
        "status": "SUCCESS"
    }

# In AdkMerchantAgent
def before_agent_callback(self, callback_context):
    payment_data = callback_context.state.get("payment_verified_data")
    if payment_data:
        # Inject virtual tool response
        tool_response = types.Part(
            function_response=types.FunctionResponse(
                name="check_payment_status",
                response=payment_data
            )
        )
        callback_context.new_user_message = types.Content(parts=[tool_response])
```

**Benefits:**

- Agent doesn't need payment-specific tools
- Natural LLM integration
- Maintains agent's conversation flow

### 4. Pluggable Component Pattern

Both wallet and facilitator are interfaces with swappable implementations:

```python
# Demo mode
wallet = MockLocalWallet()
facilitator = MockFacilitator()

# Production mode
wallet = MetaMaskWallet()
facilitator = FacilitatorClient(config)

# The agent code doesn't change
```

---

## Pluggable Components

### Wallet Implementations

The `Wallet` interface (`client_agent/wallet.py`) allows different signing backends:

#### Current: MockLocalWallet

```python
class MockLocalWallet(Wallet):
    def sign_payment(self, requirements):
        # Uses hardcoded private key
        account = Account.from_key("0x00...01")
        return process_payment_required(requirements, account)
```

#### Future: MetaMask Integration

```python
class MetaMaskWallet(Wallet):
    async def sign_payment(self, requirements):
        # Request signature from browser extension
        signature = await self.metamask.request({
            "method": "eth_signTypedData_v4",
            "params": [account, typed_data]
        })
        return PaymentPayload(...)
```

#### Future: MPC Wallet

```python
class MPCWallet(Wallet):
    async def sign_payment(self, requirements):
        # Distributed signing via MPC service
        signature = await self.mpc_service.sign(
            message=message,
            keyshare_id=self.keyshare_id
        )
        return PaymentPayload(...)
```

### Facilitator Implementations

The `FacilitatorClient` base class allows different payment processors:

#### Current: MockFacilitator

```python
class MockFacilitator(FacilitatorClient):
    async def verify(self, payload, requirements):
        # Always returns valid for testing
        return VerifyResponse(is_valid=True, payer=address)

    async def settle(self, payload, requirements):
        # No actual blockchain interaction
        return SettleResponse(success=True, network="mock")
```

#### Production: Real Facilitator

```python
facilitator = FacilitatorClient(FacilitatorConfig(
    api_url="https://facilitator.example.com",
    api_key="your-api-key",
    network="base-sepolia"
))

# Handles real on-chain verification and settlement
```

To switch between implementations, set environment variable:

```bash
# Use mock (default)
export USE_MOCK_FACILITATOR=true

# Use real facilitator
export USE_MOCK_FACILITATOR=false
```

---

## Summary

This architecture demonstrates a clean, modular approach to implementing payment-gated AI services:

1. **Business logic** remains pure and focused (AdkMerchantAgent)
2. **Protocol handling** is delegated to middleware (x402ServerExecutor)
3. **Payment processing** is abstracted behind interfaces (Wallet, Facilitator)
4. **State management** is handled by utility classes (x402Utils)
5. **Agent frameworks** are bridged through executors (ADKAgentExecutor)

The x402_a2a library provides all the core primitives needed to implement payment protocols while keeping your agent code clean and maintainable.
