"""Hugging Face Space entrypoint (Gradio SDK, no billing needed).

HF's Gradio runtime requires `demo.launch()` to be called — it does a handshake
with HF infra, and without it HF decides the Space isn't a Gradio app and kills
it in a restart loop. So: launch a one-page Gradio block (non-blocking), then
bolt the real FastAPI service (`api.main:app`) onto the server Gradio just
started, and keep the process alive.

Gradio 6 serves its own endpoints under `/gradio_api/`, so `/api/*` stays ours.
Local dev is unchanged: `uvicorn api.main:app`. See docs/DEPLOYMENT.md.
"""

import os
import time

# Defer engine warm-up to the first request (loading the embedding model at
# startup would stall Gradio's launch handshake).
os.environ.setdefault("SKIP_ENGINE_PRELOAD", "1")

import gradio as gr

from api.main import app as api_app

with gr.Blocks(title="STS NL-to-SQL") as demo:
    gr.Markdown(
        "# STS NL-to-SQL microservice\n"
        "Called server-to-server by `sts-backend`.\n\n"
        "- `GET /api/health`\n- `POST /api/query` (needs `X-API-Key`)\n"
    )

if __name__ == "__main__":
    port = int(os.environ.get("GRADIO_SERVER_PORT") or os.environ.get("PORT") or 7860)
    print(f"[app.py] gradio launch on 0.0.0.0:{port}, then mounting api.main at /", flush=True)

    # Non-blocking launch so we can attach our routes to the server Gradio starts.
    demo.launch(server_name="0.0.0.0", server_port=port, prevent_thread_lock=True, ssr_mode=False)
    demo.app.mount("/", api_app)
    print("[app.py] api.main mounted; service is up", flush=True)

    while True:
        time.sleep(3600)
