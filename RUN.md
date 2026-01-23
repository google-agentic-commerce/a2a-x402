# How to run

First, make sure you have installed the dependencies:

```bash
uv sync --directory=python/examples/adk-demo
```

Second, run the Merchant agent:

```bash 
uv --directory=python/examples/adk-demo run server
```

Then, in a separate terminal, run the client agent:

```bash
uv --directory=python/examples/adk-demo run adk web --port=8000
```

Finally, open your browser and navigate to `http://localhost:8000` to interact with the client agent's web interface.

