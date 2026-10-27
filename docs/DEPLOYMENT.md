# Deployment — NL-to-SQL microservice (on-demand, local + Tailscale Funnel)

`sts-backend` (NestJS) and the frontend run on Render; the STS database is
Supabase. This microservice runs **on one developer machine, on demand** — you
start it when the NL-query feature is needed and stop it afterwards — and is
exposed to the Render backend through a stable **Tailscale Funnel** URL.
Rationale: `docs/adr/0005-*`.

```
React ─▶ sts-backend (Render) ── POST /api/query, X-API-Key ──▶ Funnel ──▶ your machine:8000
                    │                                                          │ SELECT only
                    └───────────── read-write ──▶ Supabase ◀── read-only (nl2sql_ro) ┘
```

When your machine is off, `sts-backend` gets a 502 from the NL-query route and
the rest of STS is unaffected (`docs/INTEGRATION.md` §2.3).

---

## 1. One-time — the read-only Supabase role (Supabase project owner)

The microservice needs its **own** read-only login (ADR 0001) — never the
connection string `sts-backend` uses. Hand these steps to whoever owns the
Supabase project.

### 1a. Create the role + grant SELECT

Supabase dashboard → **SQL Editor** → run:

```sql
CREATE ROLE nl2sql_ro WITH LOGIN PASSWORD 'PUT_A_LONG_RANDOM_PASSWORD_HERE';
GRANT CONNECT ON DATABASE postgres TO nl2sql_ro;
GRANT USAGE  ON SCHEMA public       TO nl2sql_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO nl2sql_ro;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  GRANT SELECT ON TABLES TO nl2sql_ro;
```

Repeat lines 2–3 for any schema other than `public` that holds STS tables. This
role has no `INSERT/UPDATE/DELETE` and no DDL — a hard backstop under
`core/domain/sql_safety.py`.

### 1b. Check Row-Level Security

```sql
SELECT relname FROM pg_class
WHERE relrowsecurity = true AND relnamespace = 'public'::regnamespace;
```

- **No rows** → nothing to do (STS does authz in the app layer — the expected case).
- **Rows returned** → `ALTER ROLE nl2sql_ro BYPASSRLS;` or the role sees zero rows.

### 1c. Verify

```sql
SET ROLE nl2sql_ro;
SELECT count(*) FROM <some_real_sts_table>;   -- real count, not 0 or an error
RESET ROLE;
```

### What the delivered role enforces (STS, as of first setup)

- `BYPASSRLS` — 28 tables had RLS on with no policies; set so the role sees all rows.
- Column-level grants hide `password` / PIN hashes on `users` and `araid_profiles`
  → `SELECT *` on those errors. `araid_profiles` is also denylisted in
  `core/domain/schema_utils.py`; `users` stays visible (name columns explicitly).
- Fully blocked (token/hash only): `task_links`, `classroom_attendance_links`,
  `teacher_line_group_invitations`, `pii_export_requests` — added to the denylist.
- `statement_timeout = 30s`, `idle_in_transaction_session_timeout = 1min`,
  `default_transaction_read_only = on`. If a legitimate heavy aggregate needs more
  than 30 s, ask the Supabase owner to raise it for the role.

### 1d. Send back the connection string

Dashboard → **Project Settings → Database → Connection string → "Session pooler"**
(not Transaction, not Direct — the machine connects over the public internet).
Swap the username/password for the new role, keeping the `.<project-ref>` suffix:

```
postgresql://nl2sql_ro.abcdefghijklmnop:THE_PASSWORD@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres
```

---

## 2. One-time — your machine

### 2a. `.env`

In the repo root, create `.env`:

```
APP_MODE=service
DATABASE_URL=postgresql+psycopg2://nl2sql_ro.abcdefghijklmnop:THE_PASSWORD@aws-0-ap-northeast-1.pooler.supabase.com:5432/postgres?sslmode=require
API_KEY=1df6af602a3f783d86c7bce648f785dc0e7095efccaf12969057368bdb1e631f
MODEL_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
DOMAIN_PROFILE=sts
SCHEMA_STRATEGY=pruned
```

`APP_MODE=service` requires a non-empty `API_KEY`; the process refuses to start
without it. With the key set, the demo UI and `/docs` are off and the service is
Consumer-only. For a local UI demo, use `./start_demo.sh` instead — never point
demo mode at the STS datasource.

**LLM: gpt-4o-mini** — OpenRouter's free models were ~58 s per call (unusable
with the 90 s HTTP timeout once self-correction retries stack). gpt-4o-mini is
~2–8 s and costs roughly $0.5–2/month at ≤ 500 queries/day. To try a free model
again, swap `MODEL_PROVIDER` / add `OPENROUTER_*` and expect slower responses.

### 2b. Tailscale Funnel — a stable public URL, no interstitial, no request cap

Chosen over ngrok: the NestJS client (`docs/API.md`) sends only `X-API-Key` /
`Content-Type`, and ngrok's free plan puts a browser-warning interstitial in
front of the tunnel plus a ~20k-request/month cap. Funnel has neither.

1. Install Tailscale on **this one machine** and sign in:
   ```
   brew install --cask tailscale      # macOS
   tailscale up
   ```
2. In the [admin console](https://login.tailscale.com/admin) enable, for your
   tailnet: **HTTPS certificates** (DNS → enable MagicDNS + HTTPS) and **Funnel**
   (Access controls → add `"nodeAttrs": [{"target": ["*"], "attr": ["funnel"]}]`,
   or use the Funnel toggle in the machine's ⋯ menu).
3. The public URL is `https://<hostname>.<tailnet>.ts.net` — `tailscale status`
   shows the hostname; it is stable for the life of this machine + tailnet.

### 2c. Point `sts-backend` at it (once)

Render → `sts-backend` service → **Environment**:

```
TEXT_TO_SQL_URL=https://<hostname>.<tailnet>.ts.net
TEXT_TO_SQL_API_KEY=1df6af602a3f783d86c7bce648f785dc0e7095efccaf12969057368bdb1e631f
TEXT_TO_SQL_TIMEOUT_MS=90000
```

Redeploy. (Confirm the friend used these exact env names in the NestJS `nl-query`
module — `docs/INTEGRATION.md` §2.3 — otherwise match theirs.) The 90 s timeout
covers a cold first request after a fresh model download or a STS migration; a
warm request is a few seconds.

---

## 3. Each session — start / stop

```bash
# start (two terminals, from the repo root)
uv run uvicorn api.main:app --host 127.0.0.1 --port 8000   # terminal 1
tailscale funnel 8000                                       # terminal 2

# ... use the NL-query feature in the deployed STS app ...

# stop: Ctrl+C both. `tailscale funnel status` to check; `tailscale funnel reset` to force-clear.
```

- Timing (gpt-4o-mini, Supabase session pooler in ap-northeast-1):
  - warm query (schema cached < 1 h): **3–9 s**
  - first query after a normal restart (`schema_rag_db/` persisted): **~15 s**
  - first query after `rm -rf schema_rag_db` or a STS migration: **~60 s**
    (re-embeds 105 table descriptions)
  The model cache (`~/.cache/huggingface`) and ChromaDB indexes persist on this
  machine, so the ~60 s case is rare.
- Confirm it is ready before anyone uses it:
  ```bash
  curl -X POST https://<hostname>.<tailnet>.ts.net/api/query \
    -H 'Content-Type: application/json' -H 'X-API-Key: 1df6af60...' \
    -d '{"question":"จำนวนนักเรียนปัจจุบันแยกตามโรงเรียน"}'
  ```

Docker alternative: `docker compose up` also works, but `docker-compose.yml` only
forwards `MODEL_PROVIDER` / `GOOGLE_*` / `OPENAI_*` today — add `DATABASE_URL`,
`APP_MODE`, `API_KEY`, `OPENROUTER_*`, `DOMAIN_PROFILE` to its `environment:` list first, or
just use `uvicorn` as above.

---

## 4. Runbook

**Verify:**

```bash
curl https://<hostname>.<tailnet>.ts.net/api/health          # {"status":"ok","datasource":true}
# datasource:false → DATABASE_URL wrong / Supabase unreachable / RLS / role
```

**After a STS migration** (tables added/removed):

```bash
curl -X POST https://<hostname>.<tailnet>.ts.net/api/admin/refresh-schema -H 'X-API-Key: 1df6af60...'
```

**OpenRouter quota hit / model deprecated** (`error.code: LLM_FAILED` everywhere):
switch `.env` to the paid fallback and restart uvicorn:

```
MODEL_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

**Expected load:** ≤ 500 queries/day; OpenRouter's free allowance with the $10
credit on the account is 1,000/day.

---

## 5. Known limits

- The service is up only while your machine is on and both processes are running.
  `sts-backend`'s NL-query route returns 502 otherwise; the rest of STS is fine.
- Prompt + schema go to OpenRouter un-redacted — accepted, tracked for the PDPA
  phase (`docs/INTEGRATION.md` §4, ADR 0002).
- Single instance, no scaling (local ChromaDB state in `rag_db/`, `schema_rag_db/`).
- If you later want it always-on without your machine: a paid host (Render
  Standard ~$25/mo next to `sts-backend`, or Fly.io ~$6–12/mo) builds from the
  `Dockerfile` — only `TEXT_TO_SQL_URL` and where the env vars live change.
```
