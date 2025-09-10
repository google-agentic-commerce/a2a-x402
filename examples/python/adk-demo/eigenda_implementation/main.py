#!/usr/bin/env python3
"""
EigenDA Proxy Docker Script - Using docker-py
"""

import asyncio
import docker
import time
import requests
import sys


class EigenDAServer:
    def __init__(self, port: int):
        self.port = port
        self.base_url = f"http://127.0.0.1:{port}"
        self.container_name = "eigenda-proxy"
        self.client = docker.from_env()
        self.container = None

    async def start(self) -> None:
        print(f"Starting EigenDA Proxy on port {self.port}...")
        self.container = self.client.containers.run(
            "ghcr.io/layr-labs/eigenda-proxy:latest",
            command=["--memstore.enabled", "--port", str(self.port)],
            name=self.container_name,
            ports={f"{self.port}/tcp": self.port},
            detach=True,
            remove=False,
        )
        print(f"Container started: {self.container.short_id}")

        # Wait for Docker to report the container as running
        print("Waiting for container to be ready...")
        self.container.reload()
        while self.container.status != "running":
            await asyncio.sleep(1)
            self.container.reload()

        # Wait for the service inside the container to be ready
        print("Waiting for service to be ready...")
        start_time = time.time()
        timeout = 30  # seconds
        while True:
            try:
                test_response = requests.get(f"{self.base_url}/health", timeout=1)
                if test_response.status_code == 200:
                    print("Service is ready!")
                    break
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
                if time.time() - start_time > timeout:
                    raise Exception(
                        f"Service failed to become ready within {timeout} seconds"
                    )
                await asyncio.sleep(1)
                continue

    def submit(self, payload: str) -> str:
        print(f"Submitting payload: '{payload}'")
        response = requests.post(
            f"{self.base_url}/put",
            params={"commitment_mode": "standard"},
            data=payload.encode("utf-8"),
        )
        cert_hex = response.content.hex()
        return cert_hex

    def retrieve(self, certificate_hex: str) -> str:
        print("Retrieving payload...")
        response = requests.get(
            f"{self.base_url}/get/{certificate_hex}",
            params={"commitment_mode": "standard"},
        )
        return response.text


async def run() -> None:
    # Configuration
    port = 3100
    payload = "my-eigenda-payload"

    server = EigenDAServer(port)
    await server.start()

    cert_hex = server.submit(payload)
    print(f"Certificate (hex): {cert_hex[:64]}...")

    retrieved = server.retrieve(cert_hex)
    print(f"Retrieved: '{retrieved}'")

    # Cleanup (keep behavior consistent without extending class API)
    print("\nCleaning up...")
    try:
        client = docker.from_env()
        container = client.containers.get("eigenda-proxy")
        container.stop()
        container.remove()
    except Exception:
        pass
    print("Done!")


def main():
    asyncio.run(run())


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted")
        try:
            client = docker.from_env()
            container = client.containers.get("eigenda-proxy")
            container.stop()
            container.remove()
        except:
            pass
    except Exception as e:
        print(f"Error: {e}")
        try:
            client = docker.from_env()
            container = client.containers.get("eigenda-proxy")
            container.stop()
            container.remove()
        except:
            pass
        sys.exit(1)
