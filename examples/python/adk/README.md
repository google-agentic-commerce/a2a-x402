# Agents Server

This folder contains the Python code for the server that hosts our agents.

## Requirements

- Python 3.13 or higher
- uv (Python package installer)

## Setup

Perform these initial setup steps:

1. Install `uv` (if not already installed).

2. Create a `.env` file and provide the secrets needed to access [Gemini](https://google.github.io/adk-docs/get-started/quickstart/#set-up-the-model)

   This file is ignored by git, so it's safe to store "secrets" (e.g., API keys) in it.

   If you want to use a different model, follow the instructions [from ADK docs](https://google.github.io/adk-docs/agents/models/#using-different-models-with-adk) and update the agents to use the new model.

## Development

The project uses the following Python tooling:

- `pyproject.toml` for project configuration and dependencies
- `uv` for dependency management
- `ruff` for linting, formatting, and type checking

### Run the server

```bash
uv run server
```

This will start the server listening on port 10000 and serve the agents in this repo as A2A agents.

### Run the ADK dev UI

```bash
uv --directory=client run adk web
```

This will start the ADK dev UI listening on port 8000. The host agent acts as an
A2A client and connects to the A2A agents running on the server on port 10000.

### Formatting and linting

To run Ruff:

```bash
# Check code
uvx ruff check .

# Format code
uvx ruff format .

# Fix code automatically
uvx ruff check --fix .
```

## Tips

### Fix imports in VSCode

VSCode will default to using the default Python path on your machine, which means your editor might not be able to resolve imports. To fix this, you'll need to set the correct Python path in VSCode.

You can follow [this workaround](https://github.com/astral-sh/uv/issues/9637#issue-2717716303) to fix this.

Also, it looks like [this will be fixed soon](https://github.com/microsoft/vscode-python/issues/25068#issuecomment-2967309800) in a future version of the Python extension.
