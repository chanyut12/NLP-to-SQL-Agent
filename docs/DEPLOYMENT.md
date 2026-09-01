# Deployment — NL-to-SQL microservice (on-demand, local + ngrok)

`sts-backend` (NestJS) and the frontend run on Render; the STS database is
Supabase. This microservice runs **on your machine, on demand** — you start it
when the NL-query feature is needed and stop it afterwards — and is exposed to
the Render backend through a **stable ngrok URL**. Rationale: `docs/adr/0005-*`.

```
React ─▶ sts-backend (Render) ── POST /api/query, X-API-Key ──▶ ngrok ──▶ your machine:8000
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
DATABASE_URL=postgresql+psycopg2://nl2sql_ro.abcdefghijklmnop:THE_PASSWORD@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres?sslmode=require
API_KEY=1df6af602a3f783d86c7bce648f785dc0e7095efccaf12969057368bdb1e631f
MODEL_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_MODEL=<verified slug from openrouter.ai/models>
DOMAIN_PROFILE=sts
SCHEMA_STRATEGY=pruned
```

`API_KEY` set → the demo UI and `/docs` are off; the service is Consumer-only.
Fallback LLM: comment the `OPENROUTER_*` lines and add `MODEL_PROVIDER=openai` +
`OPENAI_API_KEY` + `OPENAI_MODEL=gpt-4o-mini`.

### 2b. ngrok with a stable domain

1. Sign up at ngrok.com (free) → **Domains** → you get one free static domain,
   e.g. `sts-nl2sql.ngrok-free.app`. Note it.
2. Install ngrok and add your authtoken (dashboard → Your Authtoken):
   ```
   brew install ngrok        # macOS
   ngrok config add-authtoken <token>
   ```

### 2c. Point `sts-backend` at it (once)

Render → `sts-backend` service → **Environment**:

```
TEXT_TO_SQL_URL=https://sts-nl2sql.ngrok-free.app
TEXT_TO_SQL_API_KEY=1df6af602a3f783d86c7bce648f785dc0e7095efccaf12969057368bdb1e631f
TEXT_TO_SQL_TIMEOUT_MS=60000
```

Redeploy. (Confirm the friend used these exact env names in the NestJS `nl-query`
module — `docs/INTEGRATION.md` §2.3 — otherwise match theirs.)

---

## 3. Each session — start / stop

```bash
# start (two terminals, from the repo root)
uv run uvicorn api.main:app --host 0.0.0.0 --port 8000     # terminal 1
ngrok http --url=https://sts-nl2sql.ngrok-free.app 8000    # terminal 2

# ... use the NL-query feature in the deployed STS app ...

# stop: Ctrl+C both
```

- First `/api/query` after each start is slow (~1–2 min): the engine loads the
  embedding model and builds the schema index off Supabase. Fast after that.
- Warm it yourself right after starting:
  ```bash
  curl -X POST https://sts-nl2sql.ngrok-free.app/api/query \
    -H 'Content-Type: application/json' -H 'X-API-Key: 1df6af60...' \
    -d '{"question":"จำนวนนักเรียนปัจจุบันแยกตามโรงเรียน"}'
  ```

Docker alternative: `docker compose up` also works, but `docker-compose.yml` only
forwards `MODEL_PROVIDER` / `GOOGLE_*` / `OPENAI_*` today — add `DATABASE_URL`,
`API_KEY`, `OPENROUTER_*`, `DOMAIN_PROFILE` to its `environment:` list first, or
just use `uvicorn` as above.

---

## 4. Runbook

**Verify:**

```bash
curl https://sts-nl2sql.ngrok-free.app/api/health          # {"status":"ok","datasource":true}
# datasource:false → DATABASE_URL wrong / Supabase unreachable / RLS / role
```

**After a STS migration** (tables added/removed):

```bash
curl -X POST https://sts-nl2sql.ngrok-free.app/api/admin/refresh-schema -H 'X-API-Key: 1df6af60...'
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
