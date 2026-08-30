---
status: accepted
---

# A failed query still returns HTTP 200; only infrastructure failures use HTTP error codes

## Context

The NestJS backend calls `POST /api/query` with a Thai question and gets back one
JSON envelope. We had to decide how failures are signalled. The REST-idiomatic
choice is to map failures to status codes — 422 when no SQL could be generated, 400
when the SQL is invalid, 503 when the database or LLM is unavailable.

We chose instead: **business outcomes always return HTTP 200** with a typed
`error` object in the envelope; **only transport / infrastructure failures**
(bad API key, service down, request timeout, LLM or database unreachable) return
HTTP 4xx/5xx.

Envelope shape:

```json
{
  "status": "ok" | "error",
  "request_id": "…",
  "question": "…",
  "sql": "SELECT …",
  "columns": [{ "name": "…", "type": "…" }],
  "rows": [ … ],
  "row_count": 42,
  "truncated": false,
  "visualization": { "chart_type": "bar", "x_col": "…", "y_col": "…", "series_col": null },
  "retry_count": 1,
  "elapsed_ms": 3400,
  "error": null | { "code": "…", "message": "…" }
}
```

`error.code` is a closed set: `LLM_FAILED`, `SQL_INVALID`, `EXEC_FAILED`,
`EMPTY_RESULT`.

## Why

Text-to-SQL produces a spectrum of partial outcomes that map badly onto HTTP
status: SQL generated but rejected by PostgreSQL, SQL that succeeded only after
self-correction, a valid query that returned zero rows. Forcing these into 4xx/5xx
means NestJS parses error strings to tell "rephrase your question" apart from
"the system is down".

With a stable 200 envelope, NestJS branches on `error.code` for business meaning
and reserves its HTTP-error handling for genuine infrastructure problems. The React
app can then show the user a useful message ("ลองปรับคำถามใหม่" vs "ระบบไม่พร้อม")
without the two paths getting confused. `request_id` ties a call together across
NestJS logs, this service, and the query-log record NestJS persists.

## Consequences

- NestJS integration code depends on this shape. Changing it later is a breaking
  change for the consumer, hence recording it here.
- Monitoring that only watches HTTP status will not see a high rate of
  `SQL_INVALID`; dashboards must read `status` / `error.code` from the body.
