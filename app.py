"""Hugging Face Space entrypoint (Gradio SDK).

Docker Spaces require billing on the HF account; the Gradio SDK does not. HF runs
this file with `python app.py`, so all we need is to bind the port HF expects
(7860) and serve the real service — `api.main:app` — on it. A one-page Gradio
block is mounted at `/` purely so the Space preview shows something; every real
route (`/api/health`, `/api/query`, ...) is the FastAPI app underneath.

Local dev is unchanged — run `uvicorn api.main:app` as before; this file is only
the Space's launch shim. See docs/DEPLOYMENT.md.
"""

import os

import gradio as gr

from api.main import app  # the FastAPI microservice
from core.config import settings

_landing = (
    "# STS NL-to-SQL microservice\n\n"
    "This Space hosts the API. `sts-backend` calls it server-to-server.\n\n"
    "- `GET /api/health` — liveness + datasource check (no key)\n"
    "- `POST /api/query` — needs the `X-API-Key` header\n"
)
if not settings.API_KEY:
    _landing += (
        "\n> ⚠️ **`API_KEY` is not set** — auth is off and the demo UI is served "
        "at `/`. Set the `API_KEY` secret for a real deployment.\n"
    )

with gr.Blocks(title="STS NL-to-SQL") as demo:
    gr.Markdown(_landing)

# Mount the landing page onto the FastAPI app. When API_KEY is set, api.main does
# not mount anything at "/", so this is free to take it.
if settings.API_KEY:
    app = gr.mount_gradio_app(app, demo, path="/")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 7860)))
