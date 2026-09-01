# Deployment — NL-to-SQL microservice → Hugging Face Space

Target: a **public Hugging Face Docker Space**, kept awake by UptimeRobot, calling
**Supabase Postgres** through a dedicated read-only role, driven by **OpenRouter**
(free model, gpt-4o-mini as manual fallback). Consumer is `sts-backend` (NestJS on
Render). Rationale: `docs/adr/0005-*`.

```
React ─▶ sts-backend (Render) ─── POST /api/query, X-API-Key ──▶ HF Space (this service)
                    │                                                   │  SELECT only
                    └───────────── read-write ──▶ Supabase ◀── read-only (nl2sql_ro) ┘
```

---

## 1. Prerequisites — the read-only Supabase role (done by the Supabase project owner)

The microservice needs its **own** database login that can only read (ADR 0001) —
never the connection string `sts-backend` uses. Hand these steps to whoever owns
the Supabase project.

### 1a. Create the role + grant SELECT

Supabase dashboard → **SQL Editor** → new query → run:

```sql
-- 1. the login itself
CREATE ROLE nl2sql_ro WITH LOGIN PASSWORD 'PUT_A_LONG_RANDOM_PASSWORD_HERE';

-- 2. let it reach the DB and read the app schema (usually just "public")
GRANT CONNECT ON DATABASE postgres TO nl2sql_ro;
GRANT USAGE  ON SCHEMA public       TO nl2sql_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO nl2sql_ro;

-- 3. also cover tables created by future migrations
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  GRANT SELECT ON TABLES TO nl2sql_ro;
```

If STS keeps tables in more schemas than `public`, repeat lines 2–3 for each.
This role has **no** `INSERT/UPDATE/DELETE` and **no** DDL — a hard backstop under
`core/domain/sql_safety.py`.

### 1b. Check Row-Level Security (important)

If any STS table has RLS **enabled with policies**, a plain role like `nl2sql_ro`
sees **zero rows** and every analytics answer is silently empty. Check:

```sql
SELECT relname FROM pg_class
WHERE relrowsecurity = true AND relnamespace = 'public'::regnamespace;
```

- **No rows returned** → STS does authz in the app layer (the expected case for
  this stack — see `docs/INTEGRATION.md` §2.2). Nothing to do.
- **Rows returned** → let the role read through the policies:
  ```sql
  ALTER ROLE nl2sql_ro BYPASSRLS;
  ```

### 1c. Verify the role actually works

Still in SQL Editor:

```sql
SET ROLE nl2sql_ro;
SELECT count(*) FROM <some_real_sts_table>;   -- must return the real count, not 0 or an error
RESET ROLE;
```

### 1d. Send back the connection string

The microservice runs on Hugging Face (an external host), so it must use the
**Session pooler** endpoint (IPv4, persistent connections), not the direct
`db.<ref>.supabase.co` one (IPv6-only without the paid add-on).

Dashboard → **Project Settings → Database → Connection string → "Session pooler"**.
It looks like:

```
postgresql://postgres.abcdefghijklmnop:[YOUR-PASSWORD]@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres
```

Swap the **username** and **password** for the new role — the username keeps the
`.<project-ref>` suffix that the pooler needs:

```
postgresql://nl2sql_ro.abcdefghijklmnop:THE_PASSWORD_FROM_1a@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres
```

Send that final string back. (If the pooler rejects the custom role, fall back to
the direct connection string with plain username `nl2sql_ro` and tell us — we may
need Supabase's IPv4 add-on or a different host.)

### 1e. Turn it into DATABASE_URL

Before pasting into the Space secret, prefix the driver and append SSL:

```
postgresql+psycopg2://nl2sql_ro.abcdefghijklmnop:THE_PASSWORD@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres?sslmode=require
```

---

## 2. One-time: create the Space

> **Why the Gradio SDK, not Docker:** HF now gates Docker Spaces behind billing
> (a payment method or PRO). Prepaid cards are rejected by their processor. The
> **Gradio SDK is free with no billing**, and HF runs `python app.py` directly —
> so `app.py` (repo root) just launches `api.main:app` on port 7860. The
> `Dockerfile` still works for local `docker compose` and is the path to take if
> you ever get a usable card.

1. huggingface.co → **New Space** → SDK **Gradio** → **Blank** → **Public** →
   hardware **CPU basic (free)**. No billing prompt.
2. Space **Settings → Variables and secrets**, add as **Secrets**:

   | key | value |
   |---|---|
   | `DATABASE_URL` | the `nl2sql_ro` session-pooler URL from §1 |
   | `API_KEY` | a fresh strong random string (`openssl rand -hex 32`) |
   | `MODEL_PROVIDER` | `openrouter` |
   | `OPENROUTER_API_KEY` | your key (the account that already has the $10 credit) |
   | `OPENROUTER_MODEL` | `nvidia/nemotron-3.5-lightning:free` — verify the slug on openrouter.ai/models first; fallback model: `meta-llama/llama-3.3-70b-instruct:free` |
   | `DOMAIN_PROFILE` | `sts` |
   | `SCHEMA_STRATEGY` | `pruned` |
   | `CORS_ORIGINS` | `*` (no browser calls this service directly; harmless) |

   Leave `OPENAI_*` unset until you need the fallback (see §6). `API_KEY` **must**
   be set — `app.py` only takes over `/` (hiding the demo UI) when it is.

3. Give the Space its config header. On a **`deploy/hf-space` branch** (so `main`'s
   README stays clean), prepend this to `README.md`:

   ```
   ---
   title: STS NL-to-SQL
   sdk: gradio
   app_file: app.py
   pinned: false
   ---
   ```

   Leave `sdk_version` out — HF fills in the latest on the first build.

---

## 3. Deploy (push it yourself — no CD)

`app.py` (repo root) is the Space entrypoint; `requirements.txt` already lists
`gradio`. All tracked files are small; no Git LFS needed. HF installs
`requirements.txt` and runs `python app.py`.

```bash
# one time — add the Space as a second remote
git remote add space https://huggingface.co/spaces/<user>/<space-name>
# auth: use an HF access token (Settings → Access Tokens, write) as the password

# one time — create the deploy branch with the README frontmatter from §2.3
git switch -c deploy/hf-space
$EDITOR README.md         # prepend the --- ... --- block
git commit -am "chore(deploy): HF Space frontmatter"

# each release
git switch deploy/hf-space
git merge main            # bring in the latest
git push space deploy/hf-space:main
```

The Space rebuilds on push (~5–10 min — installs `torch`, `chromadb`, `gradio`).
Watch **Logs** in the Space UI. First build done → `https://<user>-<space>.hf.space/api/health`
should return `{"status":"ok","datasource":true}`.

> The Gradio SDK image is not under our control, so the embedding model is **not**
> baked in — it downloads (~470 MB) on the first boot and after any restart. With
> the UptimeRobot ping (§4) the Space stays warm, so this only costs time right
> after a deploy. `schema_rag_db/` likewise rebuilds by introspecting Supabase on
> the **first `/api/query`** after a deploy — that one request takes ~1–2 min.
> Normal after that.

---

## 4. Keep it awake — UptimeRobot

Space sleeps after 48 h with no traffic. Create one **HTTP(s) monitor**:

- URL `https://<user>-<space>.hf.space/api/health` · interval **5 min** · no auth
- turn on the email alert (free) — doubles as your uptime + latency monitor

---

## 5. Point `sts-backend` at it

In the Render service for `sts-backend`, set:

```
TEXT_TO_SQL_URL=https://<user>-<space>.hf.space
TEXT_TO_SQL_API_KEY=<the same API_KEY from §2.2>
TEXT_TO_SQL_TIMEOUT_MS=60000
```

Redeploy `sts-backend`.

---

## 6. Runbook

**Verify end to end**

```bash
# 1. service is up + DB reachable
curl https://<user>-<space>.hf.space/api/health

# 2. a real query (first one after a deploy is slow ~1 min)
curl -X POST https://<user>-<space>.hf.space/api/query \
  -H 'Content-Type: application/json' -H 'X-API-Key: <API_KEY>' \
  -d '{"question":"จำนวนนักเรียนปัจจุบันแยกตามโรงเรียน"}'

# 3. through NestJS (needs a logged-in session cookie) — see docs/INTEGRATION.md §4.5
```

**Build succeeds but the Space shows "runtime error" / nothing on `/api/health`:**
check the Space **Logs** for the `uvicorn running on 0.0.0.0:7860` line. If HF
called `demo.launch()` instead of running `app.py` to `__main__`, move the
`uvicorn.run(...)` in `app.py` out of the `if __name__ == "__main__":` guard to
module level and re-push.

**After a STS migration** (tables added/removed): the service caches schema.
Refresh it without a redeploy:

```bash
curl -X POST https://<user>-<space>.hf.space/api/admin/refresh-schema \
  -H 'X-API-Key: <API_KEY>'
```

**OpenRouter quota hit / model deprecated** (`error.code: LLM_FAILED` across the
board): flip to the paid fallback — set on the Space and restart:

```
MODEL_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

**Expected load:** ≤ 500 queries/day. OpenRouter free allowance with the $10
credit on the account is 1,000/day — enough, but watch it if usage grows.

---

## 7. Known limits of this deployment

- Public URL; `API_KEY` is the only boundary. `/docs` is auto-disabled while
  `API_KEY` is set (`api/main.py`).
- Ephemeral FS: demo-UI history (`query_logs.jsonl`, `favorites.json`) is lost on
  every restart. The real record is `nl_query_log` in `sts-backend` (by design —
  see CONTEXT.md "Log store").
- Prompt + schema go to OpenRouter/OpenAI un-redacted — accepted, tracked for the
  PDPA phase (`docs/INTEGRATION.md` §4, ADR 0002).
- Single instance. No horizontal scaling (local ChromaDB state).
