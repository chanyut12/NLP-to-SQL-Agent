"""Hugging Face Space entrypoint (Gradio SDK).

Docker Spaces require billing on the HF account; the Gradio SDK does not. The
Gradio SDK runtime **starts the web server on port 7860 itself** and serves the
module-level `app` object (a FastAPI/Starlette app) if it finds one — so this
file must NOT bind a port. A second bind on 7860 is the "address already in use"
crash.

`app` below is the real service (`api.main:app`) with a one-page Gradio block
mounted at `/` so `GET /` returns 200 for HF's readiness probe. Every real route
(`/api/health`, `/api/query`, ...) is the FastAPI app underneath — Gradio 5/6
serves its own endpoints under `/gradio_api/`, so `/api/*` stays ours.

Local dev is unchanged: run `uvicorn api.main:app` as before. This file is only
the Space shim. See docs/DEPLOYMENT.md.
"""

import gradio as gr

from api.main import app as api_app
from core.config import settings

_landing = (
    "# STS NL-to-SQL microservice\n\n"
    "Called server-to-server by `sts-backend`.\n\n"
    "- `GET /api/health` — liveness + datasource check (no key)\n"
    "- `POST /api/query` — needs the `X-API-Key` header\n"
)
if not settings.API_KEY:
    _landing += "\n> ⚠️ **`API_KEY` is not set** — auth is off. Set it for a real deployment.\n"

with gr.Blocks(title="STS NL-to-SQL") as demo:
    gr.Markdown(_landing)

# api.main only mounts something at "/" when API_KEY is unset (the dev demo UI);
# in a real deployment API_KEY is set, so "/" is free for this landing page.
app = gr.mount_gradio_app(api_app, demo, path="/")
