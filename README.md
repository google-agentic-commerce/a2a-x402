# A2A x402 Extension

The **A2A x402 Extension** brings cryptocurrency payments to the Agent-to-Agent (A2A) protocol, enabling agents to monetize their services through on-chain payments. This extension revives the spirit of HTTP 402 "Payment Required" for the decentralized agent ecosystem.

## 🎯 **Goal**

Enable **agent commerce** by providing a standardized way for agents to charge for their services and receive payments on-chain. This transforms any A2A agent into a commercial service that can charge for API calls, data processing, AI inference, or any other valuable capability.

## 🗂️ **Repository Structure**

This repository contains the specification, core libraries, and example implementations for the A2A x402 extension, supporting multiple languages.

```
x402-a2a/
├── spec/
│   └── v0.1/
│       └── spec.md         # The official x402 extension specification
│
├── schemes/                # Directory contains experimental x402 payment schemes drafted by partners and other contributors
│
└── {language}/             # Language-specific implementations (e.g., python/, typescript/)
    ├── x402_a2a/           # The core library for the x402 extension
    │
    └── examples/
        └── {demo}/         # Demonstrations for each language implementation
```

## 🤔 **How It Works**

The x402 extension defines a simple, robust payment flow between agents:

1.  **Payment Required:** A merchant agent, when payment is required for a service, responds with a `payment-required` message.
2.  **Payment Submitted:** The client agent signs the payment details and sends them back to the merchant in a `payment-submitted` message.
3.  **Payment Completed:** The merchant verifies the payment, settles it on-chain, and responds with a `payment-completed` message, delivering the requested service.

This flow is designed to be implemented in any language, allowing developers to focus on their agent's core logic.

## 🚀 **Getting Started**

Each language-specific implementation (e.g., `python/x402_a2a`) contains its own `README.md` with detailed instructions on how to install dependencies, run tests, and use the library.

The `examples/` directory contains various demonstrations of the x402 extension. Each example also has its own `README.md` with instructions on how to run it.

## 🏗️ **Architecture**

The `x402_a2a` libraries follow a **functional core, imperative shell** architecture:

*   **Core Protocol:** The fundamental data structures and functions for creating, signing, and verifying payments.
*   **Executors:** Middleware that automates the payment flow, making it easy to add payment capabilities to any agent.

This design provides both flexibility and ease of use, allowing developers to either build custom payment logic with the core protocol or use the executors for a more hands-off approach.

## 📚 **Learn More**

*   **[Specification](spec/v0.1/spec.md)**: The complete technical specification for the x402 extension.
*   **[Python Library](python/x402_a2a/README.md)**: The documentation for the Python implementation of the x402 extension.
*   **[Python Examples](python/examples/)**: The directory containing demonstration applications for the Python implementation.
*   **[A2A Protocol](https://github.com/a2aproject/a2a-python)**: The core agent-to-agent protocol.
*   **[x402 Protocol](https://x402.gitbook.io/x402)**: The underlying payment protocol.
*   **[AP2 Protocol](https://github.com/google-agentic-commerce/AP2)**: The Agent Payments Protocol.

## 🤝 **Contributing**

Contributions are welcome! Please read the [specification](spec/v0.1/spec.md) and the existing code to understand the project's design and goals. Then, feel free to open a pull request with your changes.
