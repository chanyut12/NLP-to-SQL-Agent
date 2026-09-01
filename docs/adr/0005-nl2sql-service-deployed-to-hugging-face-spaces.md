---
status: accepted
---

# The NL-to-SQL microservice is deployed to a Hugging Face Space

## Context

The STS stack runs `sts-backend` (NestJS) on Render and its database on Supabase
Postgres. This microservice is the odd one out: it is deployed to a **public
Hugging Face Space (Gradio SDK)**, kept awake 24/7 by an external cron ping
(UptimeRobot hitting `/api/health` every 5 minutes).

## Why

The service loads `torch` + `sentence-transformers` + `chromadb` for local
embedding, so it needs ~1–1.5 GB RAM — more than the free tier of Render or any
other PaaS provides, and Fly.io no longer has a free tier. A Hugging Face Space
gives 16 GB RAM for free and is purpose-built for this stack. The project has no
hosting budget (research prototype / thesis), and $0 was a hard constraint.

HF gates the **Docker** SDK behind billing (a payment method or PRO), and the
available card is a prepaid one, which their payment processor rejects. The
**Gradio** SDK has no billing gate and runs `python app.py` directly, so
`app.py` (repo root) is a thin shim that launches the FastAPI app (`api.main:app`)
on HF's expected port. `Dockerfile` is kept for local `docker compose` and as the
path to take if a usable card ever appears.

## Considered options

- **Render, next to `sts-backend`** — best operationally (one dashboard,
  private service-to-service networking, no public exposure) but the RAM this
  service needs forces the Standard plan at ~$25/mo.
- **Fly.io** — ~$6–12/mo, good volumes, Singapore region near Supabase, but a
  second platform to operate and no free tier.
- **HF Space, Gradio SDK (chosen)** — free, no billing, enough RAM. Accepted
  downsides: the Space is reachable on the public internet (so `API_KEY` is the
  only boundary — it is always set in this deployment, and `/docs` is disabled
  when it is); the filesystem is ephemeral, so the embedding model re-downloads
  and the ChromaDB indexes (`rag_db/`, `schema_rag_db/`) rebuild on every
  restart, making the first query after a deploy slow (~1–2 min); the Space
  sleeps after 48 h idle, which the cron ping prevents.

## Consequences

- `sts-backend` calls the service over the public internet at its
  `*.hf.space` URL with `X-API-Key`, exactly the server-to-server contract in
  `docs/INTEGRATION.md`. There is no private network path between the two.
- `app.py` at the repo root exists solely as the Space entrypoint; `gradio` is in
  `requirements.txt` only for that. Local dev still runs `uvicorn api.main:app`.
- If usage or reliability outgrows the free tier, the move is to Render Standard
  next to `sts-backend` (build from `Dockerfile`); only `TEXT_TO_SQL_URL`, the
  secrets, and the cron ping change.
- Does not affect ADR 0001: the service still holds its own **read-only**
  Supabase role (`nl2sql_ro`) and executes SQL itself.
