import logging

import click
import uvicorn
from dotenv import load_dotenv
from starlette.applications import Starlette

# Local imports
from server.agents.routes import create_agent_routes

load_dotenv()

logging.basicConfig()


@click.command()
@click.option("--host", "host", default="localhost")
@click.option("--port", "port", default=10000)
def main(host: str, port: int):
    base_url = f"http://{host}:{port}"
    base_path = "/agents"
    routes = create_agent_routes(base_url=base_url, base_path=base_path)

    app = Starlette(routes=routes)
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
