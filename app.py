"""Hugging Face Space entrypoint.

The Docker SDK needs billing on the HF account; the Gradio SDK does not. With
`sdk: gradio` HF runs `python app.py` and expects THAT process to start and hold
a web server. So this file just runs the real service (`api.main:app`) with
uvicorn — no Gradio object, nothing for HF to auto-launch, no second bind.

Local dev is unchanged: run `uvicorn api.main:app` as before. This file is only
the Space launch shim. See docs/DEPLOYMENT.md.
"""

import os

from api.main import app

# So the Space's root URL returns 200 instead of 404 (api.main only serves "/"
# when API_KEY is unset, i.e. the dev demo UI).
@app.get("/", include_in_schema=False)
def _root():
    return {"service": "sts-nl2sql", "docs": "server-to-server only", "health": "/api/health"}


if __name__ == "__main__":
    import uvicorn

    # HF may hand us the port via env; fall back to the Spaces default 7860.
    port_env = {k: os.environ.get(k) for k in ("PORT", "GRADIO_SERVER_PORT", "SERVER_PORT")}
    print(f"[app.py] port env: {port_env}", flush=True)
    port = int(os.environ.get("PORT") or os.environ.get("GRADIO_SERVER_PORT") or 7860)
    print(f"[app.py] starting uvicorn on 0.0.0.0:{port}", flush=True)

    uvicorn.run(app, host="0.0.0.0", port=port)
