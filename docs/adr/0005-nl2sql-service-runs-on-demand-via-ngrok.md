---
status: accepted
---

# The NL-to-SQL microservice runs on-demand on a developer machine, exposed via ngrok

## Context

`sts-backend` (NestJS) and the frontend run on Render; the STS database is
Supabase. This microservice is **not** hosted anywhere permanent: it runs on a
developer's machine when the NL-query feature is needed and is stopped
afterwards, reached by the Render backend through a stable `*.ngrok-free.app`
URL. See `docs/DEPLOYMENT.md`.

## Why

The project has no hosting budget (research prototype / thesis) and $0 was a hard
constraint. The service needs ~1–1.5 GB RAM for `torch` + `sentence-transformers`
+ `chromadb`, which rules out the free tier of Render / Fly / most PaaS. The
free routes that were tried and rejected:

- **Hugging Face Docker Space** — HF gates the Docker SDK behind billing, and the
  available card is prepaid, which their payment processor rejects.
- **Hugging Face Gradio Space** (free, no billing) — its runtime requires a
  Gradio app launched its own way; every attempt to host the FastAPI service
  inside it (own uvicorn, `mount_gradio_app`, `demo.launch()` + mounting) ended
  in a restart loop. Not worth more time for a prototype.
- **Oracle Cloud Always Free / Azure for Students** — a card or an academic email
  that were not available / not worth the setup.

On-demand local + ngrok costs nothing, needs no card, and matches how the feature
is actually used (occasional, during demos).

## Consequences

- The NL-query feature works only while the developer's machine is running the
  service. `sts-backend`'s NL-query route returns 502 otherwise; the rest of STS
  is unaffected (`docs/INTEGRATION.md` §2.3).
- `sts-backend` calls the ngrok URL with `X-API-Key` — the server-to-server
  contract in `docs/INTEGRATION.md` is unchanged.
- The engine warm-up is deferred to the first request (`SKIP_ENGINE_PRELOAD`), so
  the first `/api/query` after each start takes ~1–2 min.
- ADR 0001 still holds: the service keeps its own **read-only** Supabase role
  (`nl2sql_ro`) and executes SQL itself.
- `Dockerfile` is kept and stays working — the path to a paid always-on host
  (Render Standard, Fly.io) if the prototype outgrows on-demand.
