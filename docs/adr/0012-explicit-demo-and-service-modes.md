---
status: accepted
---

# Explicit demo and service modes; the UI no longer keys off API_KEY

## Context

The bundled UI in `web/` was mounted only when `API_KEY` was empty. That made
`API_KEY` carry two unrelated jobs: authenticate `/api/*` and decide whether the
process was a local demo or a Consumer-only microservice. It also made the
desired combination — a standalone demo page and a secured service — look
impossible without exposing the key to the browser.

The service still has exactly one Datasource per process (ADR 0011). A demo
database is therefore another deployment with its own `DATABASE_URL` and
`DOMAIN_PROFILE`, not a runtime connection switch. (A later decision lets the
standalone demo page point its own process at another Datasource — ADR 0013 — but
the service path still cannot.)

## Decision

1. **Add `APP_MODE` with three values:**
   - `demo` — mount the UI at `/`, leave `/api` unauthenticated, and require
     `API_KEY` to be empty. The demo script binds `127.0.0.1` by default.
   - `service` — do not mount the UI; require a non-empty `API_KEY` and refuse
     to start without it.
   - `auto` — the default and the compatibility path: UI on iff `API_KEY` is
     empty, auth on iff `API_KEY` is set.
2. **Treat an invalid or contradictory mode as a startup error.** In particular,
   `demo` + `API_KEY` and `service` without `API_KEY` fail fast rather than
   serving a surprising surface.
3. **Keep the demo datasource separate.** `./start_demo.sh` exports
   `APP_MODE=demo`, `DATABASE_URL=sqlite:///./local_database.db`,
   `DOMAIN_PROFILE=demo` and an empty `API_KEY`; exported values win over `.env`
   so the demo cannot accidentally point at the production STS database.
4. **Serve the UI same-origin.** `web/js/modules/config.js` uses `/api` instead
   of a hard-coded `localhost:8000`, so the same page works on the demo port.

## Considered options

- **Keep overloading `API_KEY`.** Rejected: it cannot express a secured service
  with an additional demo page, and it hides the demo/service distinction inside
  an auth value.
- **Inject `API_KEY` into the browser or add a key prompt.** Rejected: a shared
  secret in client code or browser storage is a leak. A same-origin backend for
  the UI would be a larger security-sensitive component than this project needs.
- **Restore `/connect` for a database picker.** Rejected for the same reasons as
  ADR 0011: runtime credentials and datasource switching invalidate the
  read-only role, schema cache and per-profile retrieval stores. Reconsidered for
  `APP_MODE=demo` only in ADR 0013, where the switch is confined to the local,
  unauthenticated demo process and the schema-RAG index is namespaced by
  Datasource; service mode still rejects it.
- **Two deployments sharing one codebase.** Chosen: the mode is explicit, each
  deployment has one datasource and one profile, and `auto` keeps existing
  `.env` files working.

## Consequences

- Production `.env` should set `APP_MODE=service`; the process will not start
  without `API_KEY`.
- Demo mode is local-only by default and must never be exposed publicly or
  pointed at real data.
- `README.md`, `docs/API.md`, `docs/guides/QUICK_START.md` and
  `docs/DEPLOYMENT.md` document the mode matrix instead of equating “no API key”
  with “demo”.
- Tests cover the mode matrix (`tests/unit/test_app_modes.py`) and the demo
  profile's SQL against the demo schema (`tests/unit/test_demo_profile.py`).
