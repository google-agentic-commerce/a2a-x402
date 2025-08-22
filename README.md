# A2A x402 Extension Monorepo

The **A2A x402 Extension** brings cryptocurrency payments to the Agent-to-Agent (A2A) protocol, enabling agents to monetize their services through on-chain payments. This extension revives the spirit of HTTP 402 "Payment Required" for the decentralized agent ecosystem.

## 🎯 **Goal**

Enable **agent commerce** by providing a standardized way for:
- **Merchant agents** to require payment for services
- **Client agents** to authorize and submit payments  
- **Facilitators** to verify and settle transactions on-chain
- **Developers** to build monetized agent ecosystems

The x402 extension transforms any A2A agent into a **commercial service** that can charge for API calls, data processing, AI inference, or any other valuable capability.

## 🗂️ **Repository Structure**

```
a2a-x402/
├── v0.1/                    # Protocol specification
│   └── spec.md             # Complete x402 extension spec v0.1
│
├── python/                  # Python implementation
│   └── a2a_x402/          # Python SDK package
│       ├── types/          # Data structures & A2A/x402 re-exports
│       ├── core/           # Protocol functions (functional core)
│       ├── executors/      # Middleware for automation (imperative shell)
│       ├── tests/          # Comprehensive test suite
│       └── README.md       # Python package documentation
│
└── examples/               # Examples and demonstrations
    └── python/
        └── adk/            # ADK-based example
            ├── client/     # Wallet/buyer agent
            └── server/     # Merchant agent
```

## 📖 **Key Documents**

### **Protocol Specification**
- [`v0.1/spec.md`](v0.1/spec.md) - Complete A2A x402 extension specification

### **Python Implementation**
- [`python/a2a_x402/README.md`](python/a2a_x402/README.md) - Python SDK documentation
- [`python/a2a_x402/pyproject.toml`](python/a2a_x402/pyproject.toml) - Package configuration

### **Examples**
- [`examples/python/adk/`](examples/python/adk/) - ADK-based merchant/client example

## 🚀 **Quick Start**

### **Python SDK**

```bash
# Install the package
cd python/a2a_x402
uv sync

# Run tests
uv run test

# View coverage
open htmlcov/index.html
```

### **Example Usage**

```python
from a2a_x402 import (
    create_payment_requirements,
    process_payment_required,
    verify_payment,
    settle_payment
)

# Merchant creates payment requirements
requirements = create_payment_requirements(
    price="1000000",  # $1.00 in USDC
    resource="/api/generate-image",
    merchant_address="0xmerchant123",
    network="base"
)

# Client processes payment (with signing)
settle_request = process_payment_required(requirements, account)

# Merchant verifies and settles
await verify_payment(settle_request, facilitator)
await settle_payment(settle_request, facilitator)
```

## 🏗️ **Architecture**

The x402 extension follows a **functional core, imperative shell** architecture:

### **Core Protocol**
- **Data structures** - A2A-specific payment types
- **Protocol functions** - Payment creation, processing, verification
- **State management** - Payment status tracking in A2A metadata

### **Executors**
- **Client executor** - Auto-processes payment requirements (like HTTP interceptor)
- **Server executor** - Auto-handles payment verification & settlement (like middleware)

### **Integration Points**
- **A2A SDK** - Task/Message objects, agent execution
- **x402 Protocol** - Payment requirements, signature verification
- **Facilitator** - On-chain verification and settlement

## 🎯 **Value Proposition**

### **For Agent Developers**
- 💰 **Monetize any agent capability** - Turn functions into paid APIs
- 🔧 **Simple integration** - Add payments with minimal code changes  
- 🛡️ **Security by default** - Cryptographic verification built-in
- ⚡ **Flexible deployment** - Use core functions or automated middleware

### **For Agent Users**  
- 🤖 **Agent commerce** - Agents can buy services from other agents
- 💳 **Crypto payments** - Native on-chain settlement (Base, Ethereum, etc.)
- 🔐 **Non-custodial** - Users control their own signing keys
- 🌐 **Decentralized** - No central payment processor

## 🛠️ **Development**

### **Adding Language Support**

1. Create `/{language}/` directory (e.g., `typescript/`, `rust/`)
2. Implement the [specification](v0.1/spec.md) 
3. Follow the functional core/imperative shell pattern
4. Add comprehensive tests
5. Create examples in `examples/{language}/`

### **Adding Examples**

1. Create `examples/{language}/{example_name}/`
2. Demonstrate real-world usage patterns
3. Include both merchant and client implementations
4. Document setup and usage

## 📚 **Learn More**

- **[A2A Protocol](https://github.com/a2aproject/a2a-python)** - Core agent-to-agent protocol
- **[x402 Protocol](https://x402.gitbook.io/x402)** - Underlying payment protocol
- **[Specification](v0.1/spec.md)** - Complete technical specification

## 🤝 **Contributing**

Contributions welcome! Please:

1. Read the [specification](v0.1/spec.md) first
2. Follow existing patterns in language implementations
3. Add comprehensive tests
4. Update documentation
5. Submit pull requests with clear descriptions

---

**Transform any A2A agent into a commercial service with cryptocurrency payments** 🚀