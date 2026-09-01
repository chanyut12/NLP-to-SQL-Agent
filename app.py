"""Hugging Face Space entrypoint (Gradio SDK, no billing needed).

HF runs `python app.py` and expects a long-lived server on port 7860 that also
answers Gradio's readiness endpoints (`/config`). So:

  * mount a one-page Gradio block at "/" — gives HF the `/config` route it probes
  * `ssr_mode=False` — Gradio 6's SSR would otherwise spawn a Node server that
    races uvicorn for the port (the earlier "address already in use")
  * run uvicorn ourselves on 7860 — the only server in the process

Every real route (`/api/health`, `/api/query`, ...) is `api.main:app` underneath;
Gradio 6 serves its own endpoints under `/gradio_api/`, so `/api/*` stays ours.

Local dev is unchanged: `uvicorn api.main:app`. This file is only the Space shim.
See docs/DEPLOYMENT.md.
"""

import os

import gradio as gr

from api.main import app as api_app

with gr.Blocks(title="STS NL-to-SQL") as demo:
    gr.Markdown(
        "# STS NL-to-SQL microservice\n"
        "Called server-to-server by `sts-backend`.\n\n"
        "- `GET /api/health`\n- `POST /api/query` (needs `X-API-Key`)\n"
    )

app = gr.mount_gradio_app(api_app, demo, path="/", ssr_mode=False)

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT") or os.environ.get("GRADIO_SERVER_PORT") or 7860)
    print(f"[app.py] starting uvicorn on 0.0.0.0:{port}", flush=True)
    uvicorn.run(app, host="0.0.0.0", port=port)
