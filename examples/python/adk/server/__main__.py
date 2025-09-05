"""Server entry point for the ADK x402 demo."""

import os
import click
import asyncio
from pathlib import Path

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
import uvicorn
from starlette.applications import Starlette
from starlette.routing import Mount

from .agents.routes import create_router


def load_environment():
    """Load environment variables from .env file if it exists."""
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    if key not in os.environ:
                        os.environ[key] = value


@click.command()
@click.option('--port', default=10000, help='Port to run the server on')
@click.option('--host', default='localhost', help='Host to bind the server to')
def main(port: int, host: str):
    """Start the merchant server with x402 payment capabilities."""
    
    # Load environment variables
    load_environment()
    
    # Validate required environment variables
    required_vars = ['GOOGLE_API_KEY', 'MERCHANT_ADDRESS']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        click.echo(f"Error: Missing required environment variables: {', '.join(missing_vars)}")
        click.echo("Please create a .env file based on .env.example and fill in the required values.")
        return
    
    click.echo(f"🏪 Starting merchant server on {host}:{port}")
    click.echo("📦 Services available:")
    click.echo("  - Free: Service catalog, system status, market summary")
    click.echo("  - Paid: Basic analysis ($1.50), Premium analysis ($5.00), Custom reports ($3.00)")
    merchant_address = os.getenv('MERCHANT_ADDRESS')
    click.echo(f"💰 Merchant address: {merchant_address}")
    click.echo("")
    click.echo("Ready to accept A2A agent connections with x402 payments!")
    
    # Create A2A application routes  
    routes = create_router(merchant_address)
    
    # Create Starlette application with A2A routes
    app = Starlette(routes=[
        Mount("/agents", routes=routes)
    ])
    
    # Start the server using uvicorn
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()