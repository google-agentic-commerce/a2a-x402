# x402 Payment Protocol Extension for A2A

## Branch Context
This specification combines learnings from two development branches:
- `demo-v3-with-spec`: Contributed package structure, ADK/A2A separation, and functional exports
- `demo`: Provided executor patterns and state management approaches

The resulting spec synthesizes these approaches into a cohesive design that leverages the strengths of both implementations.

## Overview
This PR introduces the specification for the `a2a_x402` package, a payment protocol extension for Agent-to-Agent (A2A) communications. The extension provides a comprehensive framework for handling cryptocurrency payments within A2A applications.

## Key Features
- **Functional Core Architecture**: Separates pure payment logic (core/) from side effects (executors/) using the functional core, imperative shell pattern
- **Complete Payment Flow**: Handles the entire payment lifecycle from requirement creation to settlement
- **Flexible Integration**: Provides both low-level utilities and high-level middleware executors
- **Type-Safe**: Comprehensive type system for payment operations
- **Error Handling**: Structured error hierarchy with domain-specific error types

## Technical Details

### Architectural Pattern
The package follows the "functional core, imperative shell" pattern:

1. **Functional Core** (`core/`)
   - Pure business logic with no side effects
   - Payment validation, signing, and verification
   - Given same inputs, always returns same outputs
   - No external dependencies or state mutations

2. **Imperative Shell** (`executors/`)
   - Handles all side effects (blockchain, network, state)
   - Coordinates message flow and state updates
   - Manages external integrations
   - Wraps core functions in practical workflows

This separation makes the code more testable, maintainable, and allows the core payment logic to be reused in different contexts.

### Package Structure
```
a2a_x402/
├── core/                  # Functional Core
│   ├── merchant.py       # Merchant utilities
│   ├── wallet.py         # Wallet utilities
│   ├── protocol.py       # Protocol definitions
│   └── utils.py          # Core utilities and state management
├── executors/            # Imperative Shell
│   ├── base.py          # Base executor types
│   ├── client.py        # Client-side executor
│   └── server.py        # Server-side executor
├── types/               # Shared Types
│   ├── config.py        # Configuration types
│   ├── messages.py      # Message types
│   ├── errors.py        # Error types
│   └── state.py         # State types
└── extension.py         # Extension declaration
```
