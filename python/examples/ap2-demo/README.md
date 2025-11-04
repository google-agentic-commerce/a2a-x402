# AP2 & x402 Agent-to-Agent Demo

This directory contains a demonstration of the Agent Payments Protocol (AP2) integrated with the x402 payments extension. It showcases the "Embedded Flow," where a client agent orchestrates a purchase from a merchant agent using a sequence of digitally signed mandates.

The demo consists of three main components:
1.  **Client Agent**: An orchestrator built with the Google Agent Development Kit (ADK) that manages the user interaction and the overall purchase flow.
2.  **Merchant Agent**: A seller agent that can create product carts and process payments using the x402 protocol.
3.  **Mock Wallet**: A simple Flask service that simulates a user's wallet, responsible for signing all mandates and transactions.

## How to Run

### 1. Prerequisites

- Python 3.13+
- [uv](https://github.com/astral-sh/uv) (for environment and package management)

### 2. Installation

From this directory (`a2a-x402/python/examples/ap2-demo`), install the required dependencies:
```bash
uv pip install -e .
```

### 3. Setup Environment

Copy the example environment file and populate it with your details. This file will be used by the Mock Wallet and Merchant Agent.

```bash
cp .env.example .env
```

Now, edit the `.env` file:
- `CLIENT_PRIVATE_KEY`: Your Ethereum private key. This account will be used for signing and must have Base Sepolia USDC test tokens.
- `MERCHANT_WALLET_ADDRESS`: The public Ethereum address of the merchant who will receive the payment.
- `GOOGLE_API_KEY`: Your Google API key for the ADK agent. Get one from [Google AI Studio](https://aistudio.google.com/apikey).

### 4. Run the Demo

You need to run the three services in separate terminals.

**Terminal 1: Mock Wallet**

From the `python/examples/ap2-demo` directory, run:
```bash
uv run python local_wallet.py
```

**Terminal 2: Client Agent (ADK Web UI)**

From the `python/examples/ap2-demo` directory, run:
```bash
uv run adk web
```

**Terminal 3: Server Agent**

From the `python/examples/ap2-demo` directory, run:
```bash
uv run server
```

Once the client agent is running, you can connect to it from the ADK Web UI to begin the purchase flow.

## Understanding the Flow

This demo illustrates a complete, secure, and verifiable agent-to-agent transaction using AP2 mandates.

**Step 1: Intent to Purchase**
1.  The user tells the **Client Agent** their purchase intent (e.g., "I want to buy two bananas").
2.  The Client Agent creates an `IntentMandate` and asks the user for approval.
3.  The user approves, and the Client Agent sends the `IntentMandate` to the **Mock Wallet** to be signed.
4.  The Client Agent forwards the signed `IntentMandate` to the **Merchant Agent**.

**Step 2: Cart Creation & Payment Requirements**
1.  The Merchant Agent receives the `IntentMandate` and uses its `get_product_details_and_create_cart` tool.
2.  This tool constructs a `CartMandate`, which includes the price and, crucially, the x402 payment requirements (specifying the token, network, and amount).
3.  The Merchant Agent signs the `CartMandate` and returns it to the Client Agent as a structured A2A Artifact.

**Step 3: Transaction Signing (EIP-712)**
1.  The Client Agent receives the `CartMandate` and informs the user that the order is ready for payment.
2.  When the user agrees to pay, the Client Agent's `pay_for_cart` tool is triggered.
3.  It inspects the `CartMandate` to get the payment details and fetches the correct `nonce` from the USDC smart contract.
4.  It constructs a secure **EIP-712 typed data** structure for the `transferWithAuthorization` function call.
5.  This typed data is sent to the **Mock Wallet**, which uses the correct `sign_typed_data` method to produce a valid EIP-712 signature.

**Step 4: Payment Authorization**
1.  The Client Agent receives the signature and uses it to create a `PaymentMandate`.
2.  The user is asked to approve this final mandate.
3.  The Client Agent sends the `PaymentMandate` to the **Mock Wallet** for a final signature (authorizing the payment).
4.  The Client Agent sends the fully signed `PaymentMandate` back to the **Merchant Agent**.

**Step 5: Settlement**
1.  The Merchant Agent receives the `PaymentMandate` and triggers its `process_payment` tool.
2.  It reconstructs the `PaymentPayload` and `PaymentRequirements`.
3.  It calls the `verify()` and then `settle()` methods on the **Mock Facilitator**.
4.  The Mock Facilitator performs an off-chain signature check and then submits the transaction to the Base Sepolia testnet, completing the payment.
5.  The Merchant Agent receives the successful settlement response and confirms the purchase is complete.