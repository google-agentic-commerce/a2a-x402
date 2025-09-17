Never update the .env file.

# EigenDA Demo Example Rules

## Package Structure
- **Dependency path**: `../../../python/x402_a2a` in all pyproject.toml and uv.lock files
- **Main directories**: `server/`, `client_agent/`, `cli_agent/` - each has its own uv workspace

## Agent Architecture
- **Server agents**: Located in `server/agents/` - inherit from BaseAgent
- **Client agents**: Use ADK framework with payment wallet integration
- **Payment flow**: MockFacilitator for testing, RealFacilitator for production
- **Agent cards**: Must include x402 extension declaration

## Development Workflow
- **Start server**: `uv run server` (auto-starts EigenDA docker)
- **Start client**: `uv run adk web` or `uv run cli_agent/agent.py`
- **Environment**: Copy `.env.example` to `.env` with your keys
- **Testing**: Use `USE_MOCK_FACILITATOR=true` to bypass real payments

## Key Files
- `server/agents/eigenda_agent.py` - Main storage agent
- `server/agents/x402_merchant_executor.py` - Payment processing
- `client_agent/wallet.py` - Auto-approval wallet (DEMO ONLY)
- `pyproject.toml` - Project config with x402_a2a dependency

## Modification Guidelines
- **Agents**: Extend BaseAgent, use x402Utils for payments
- **Payments**: $0.01 per storage operation, free retrieval
- **Docker**: EigenDA container managed automatically
- **Imports**: Always use x402_a2a package imports
- **Wallets**: MockLocalWallet for demo, implement secure wallet for production

# important-instruction-reminders
Do what has been asked; nothing more, nothing less.
NEVER create files unless they're absolutely necessary for achieving your goal.
ALWAYS prefer editing an existing file to creating a new one.
NEVER proactively create documentation files (*.md) or README files. Only create documentation files if explicitly requested by the User.