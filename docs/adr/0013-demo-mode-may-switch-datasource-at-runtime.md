---
status: accepted
---

# Demo mode may switch Datasource at runtime; service mode still cannot

## Context

ADR 0001 removed the mutable connection state, `.last_connection.json` and the
`/connect` endpoint; ADR 0011 restated the rule as one Datasource per deployment.
That is right for the service: the schema cache, the schema-RAG index and the
read-only role are all bound to one datasource, and the Consumer owns that
datasource.

The bundled demo UI is a different animal. `./start_demo.sh` serves the page and
its `/api` from the same local process, has no authentication, and exists so
someone can try the agent against *their* data. Before the microservice
conversion the page had a Connection tab (database type + host/user/password)
wired to `POST /connect`; that conversion dropped both, leaving "edit
`DATABASE_URL` and restart" as the only way to point the demo at another
database.

## Decision

1. **`APP_MODE=demo` (and `auto` without `API_KEY`) may switch Datasource at
   runtime** through `POST /api/demo/connect`. The routes are mounted only where
   the bundled UI is served; `APP_MODE=service` keeps ADR 0011 unchanged and
   returns 404 for them.
2. `GET /api/demo/state` reports the active (redacted) DSN, the active Domain
   profile and the profiles that can be selected, so the panel can show what it
   would switch away from.
3. A switch parses the DSN first, opens the connection once in a worker thread,
   and **only then** replaces the process datasource. A failed attempt leaves the
   previous Datasource answering requests.
4. The engine forgets everything bound to the old Datasource
   (`NLPEngine.reset_for_datasource`), and schema-RAG collections are namespaced
   by Datasource key, so two databases can never share one index.
5. **Selecting another Domain profile rebuilds the NLPEngine**, because the
   Example set, prompt hints and Thai mappings are bound at construction.
6. The demo is unauthenticated by design and binds loopback by default. This
   endpoint can make the process open *any* DSN, so a published demo is out of
   the question; the warning lives in `start_demo.sh`, the endpoint module and
   the docs.

## Considered options

- **Keep the demo restart-only.** Rejected: it is the friction the pre-conversion
  demo did not have, and it makes trying the agent against real data a deployment
  chore.
- **Reintroduce `/connect` for all modes.** Rejected: a service deployment must
  not accept connection details over its API (ADR 0011), and the demo's needs are
  contained by being local, single-user and unauthenticated.
- **Switch only the datasource, never the profile.** Rejected: a database whose
  domain the profile does not describe produces confidently wrong SQL, which is
  worse than the extra engine rebuild.

## Consequences

- `docs/API.md`, `README.md` and `docs/guides/QUICK_START.md` document the demo
  routes as demo-only and unauthenticated.
- A runtime switch is in-memory: restarting the demo returns to `DATABASE_URL`
  from the environment. Nothing is persisted, and the demo never writes to the
  datasource it connects to.
- The first question after a switch can pay the cold-cache cost unless the
  background re-warm wins the race; a profile switch always rebuilds the engine.
- `schema_metadata_<profile>_<datasource_key>` collections accumulate in
  `schema_rag_db` as datasources are tried; they are cheap and get reused when
  the same datasource is selected again.
- A service deployment that repoints the same profile at another database now
  re-indexes into a new collection instead of mixing tables into the old one.
