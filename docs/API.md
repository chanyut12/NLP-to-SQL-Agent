# Thai NLP-to-SQL service — API

One HTTP service. A Consumer (e.g. the NestJS backend) sends a Thai question and
receives a structured **Answer envelope**: the SQL, result rows, column metadata,
a result summary, a chart suggestion, and a user-facing Thai message.

- **Base URL (local dev):** `http://localhost:8000`
- **Interactive docs / OpenAPI:** `GET /docs`, `GET /redoc`, `GET /openapi.json`.
  These are **disabled when the service requires an API key** — a deployed service
  is Consumer-only.
- **Datasource:** fixed at deploy time by `DATABASE_URL`. A Consumer never passes
  database credentials, and there is no `/connect` flow.
- **Deployment mode:** `APP_MODE` selects the surface (see Authentication).

For the full STS integration design — session examples, NestJS wiring, SSE relay
and UI guidance — see [INTEGRATION.md](INTEGRATION.md). This file is the endpoint
reference.

## Authentication

In `service` mode (and in `auto` mode when a key is set), every `/api/*` call
needs the shared secret in a header:

```
X-API-Key: <the value of the service's API_KEY env var>
```

`GET /api/health` is the only endpoint that does not require the key.
`APP_MODE` controls which surface the process exposes:

| `APP_MODE` | `/` demo UI | `/api/*` auth | `/docs` |
|---|---|---|---|
| `auto` (default) | on iff `API_KEY` is empty | on iff `API_KEY` is set | on iff `API_KEY` is empty |
| `demo` | on | **off** — `API_KEY` must be empty | on |
| `service` | off | **required** — startup fails without `API_KEY` | off |

Use `demo` only for the local standalone page (`./start_demo.sh`, port 8001).
Use `service` for a Consumer-only deployment. `auto` keeps the pre-`APP_MODE`
behaviour for existing `.env` files.

## Two modes on `POST /api/query`

The request body and response envelope are the same in both modes; the
**presence of the `history` field** selects the mode.

| `history` | Mode | What it can return |
|---|---|---|
| omitted or `null` | Legacy one-shot chain | `answer_type: "result"` only |
| present, including `[]` | Conversational agent loop | `result`, `clarification`, `refusal` |

Send `history: []` for the first Turn of a Session. The service keeps no session
state — the Consumer owns the Turn list and replays it on every call (ADR 0006).
`POST /api/query/stream` always runs the agent loop; omitting `history` there
means an empty history, not legacy mode.

---

## `POST /api/query`

### Request

```json
{
  "question": "จำนวนนักเรียนปัจจุบันแยกตามโรงเรียน",
  "preferred_chart_type": null,
  "history": []
}
```

| Field | Type | Required | Meaning |
|---|---|---|---|
| `question` | string | yes | Thai natural-language question. |
| `preferred_chart_type` | string \| null | no | A chart-kind key: `"bar"`, `"bar_horizontal"`, `"bar_grouped"`, `"bar_stacked"`, `"bar_stacked_100"`, `"line"`, `"area"`, `"combo"`, `"pie"`, `"scatter"`, `"heatmap"`, `"treemap"`, `"histogram"` or `"boxplot"`; omit/null for auto. Advisory — a kind the result cannot support degrades to the plain bar (or a distribution kind, when the rows are raw) that it can draw. |
| `history` | `PriorTurn[]` | no | Prior Turns of this Session. Presence selects agent mode; `[]` is the first Turn. |
| `dialect` | string | no | Accepted for compatibility but **ignored** — the service uses its Datasource's dialect. |

#### `PriorTurn`

```json
{
  "question": "ห้องไหนมีการขาดเรียนมากที่สุด",
  "answer_type": "result",
  "sql": "SELECT classroom_id, ... LIMIT 500",
  "row_count": 5,
  "digest": { "…": "opaque, returned in the previous envelope as turn_digest" }
}
```

| Field | Type | Rules |
|---|---|---|
| `question` | string | Non-empty. |
| `answer_type` | `"result" \| "clarification" \| "refusal"` | Required. |
| `sql` | string \| null | A `result` Turn must carry non-empty SQL; clarification/refusal Turns must not carry SQL. |
| `row_count` | number | Optional; if present must be `>= 0`. |
| `digest` | object \| null | Optional. Pass the previous result envelope's `turn_digest` unchanged. Only meaningful on result Turns. |

Validation is enforced: a malformed Turn returns **HTTP 422**. Do **not** send
result rows back — the service does not use them. Progress events are never part
of history.

### Response — always HTTP 200 for a business outcome

```json
{
  "status": "ok",
  "request_id": "b1a1c0de-...",
  "question": "จำนวนนักเรียนปัจจุบันแยกตามโรงเรียน",
  "answer_type": "result",
  "message": "โรงเรียนบ้านห้วยทรายมีนักเรียนปัจจุบันมากที่สุด 613 คน จากทั้งหมด 10 โรงเรียนครับ",
  "steps_used": 2,
  "prep_ms": 420,
  "turn_digest": { "…": "opaque result description" },
  "sql": "SELECT school.id AS school_id, school.name AS school_name, COUNT(DISTINCT enrollment.person_uuid)::int AS student_count FROM ... LIMIT 500",
  "columns": [
    { "name": "school_id", "type": "int", "numeric": true, "semantic_type": "id" },
    { "name": "school_name", "type": "str", "numeric": false, "semantic_type": "name" },
    { "name": "student_count", "type": "int", "numeric": true, "semantic_type": "count" }
  ],
  "rows": [
    { "school_id": 10010002, "school_name": "โรงเรียนบ้านห้วยทราย", "student_count": 613 },
    { "school_id": 10010003, "school_name": "โรงเรียนวัดสระ", "student_count": 572 }
  ],
  "row_count": 10,
  "truncated": false,
  "summary": {
    "row_count": 10,
    "truncated": false,
    "numeric_aggregates": { "student_count": { "sum": 5980, "min": 572, "max": 613, "mean": 598 } },
    "single_value": false
  },
  "visualization": {
    "chart_type": "bar",
    "x_col": "school_name",
    "y_col": "student_count",
    "series_col": null,
    "y2_col": null,
    "chart_form": null,
    "sort": "value_desc",
    "options": ["bar", "bar_horizontal", "line", "area", "pie", "table"],
    "title": "จำนวนนักเรียนปัจจุบันแยกตามโรงเรียน",
    "x_label": "school name",
    "y_label": "student count",
    "top_n": null,
    "reason": "เทียบค่าข้ามหมวดหมู่"
  },
  "retry_count": 0,
  "elapsed_ms": 3412,
  "error": null
}
```

### Response fields

| Field | Type | Notes |
|---|---|---|
| `status` | `"ok" \| "error"` | Branch on this first. `clarification` and `refusal` are still `"ok"`. |
| `request_id` | string | Use it to correlate logs across services. |
| `question` | string | Echo of the request question. |
| `answer_type` | `"result" \| "clarification" \| "refusal"` | What this Turn is. |
| `message` | string \| null | User-facing Thai text. On agent `result` Turns: a 2–3 sentence paragraph answering the question and noting one salient fact. On `clarification`: one follow-up question. On `refusal`: the reason plus an alternative. Legacy one-shot results have `null`. |
| `steps_used` | number | Agent loop steps used in this Turn; `1` on the legacy one-shot path. |
| `prep_ms` | number \| null | Context-preparation time (retrieval + schema filtering) on agent Turns; `null` on the legacy path. Additive and advisory. |
| `turn_digest` | object \| null | Deterministic description of a result Turn (tables, population, filters, grouping, columns, top rows). Populated on agent result Turns when available; `null` otherwise. Treat as **opaque** and pass it back as `history[].digest`. |
| `sql` | string \| null | Generated SQL; `null` for clarification/refusal and errors without SQL. |
| `columns` | array | Per-column `name`, `type`, `numeric`, `semantic_type`. |
| `rows` | array \| null | Result rows; `null` on error, `[]` for clarification/refusal. |
| `row_count` | number | Number of returned rows. |
| `truncated` | boolean | `true` when the row cap (`MAX_SQL_LIMIT`, default 500) was reached. |
| `summary` | object \| null | Row count, truncation, numeric aggregates, and `single_value`. |
| `visualization` | object \| null | Chart recommendation (advisory). |
| `retry_count` | number | Self-correction retries on the legacy one-shot path; agent Turns report `0` here — use `steps_used` for loop effort. |
| `elapsed_ms` | number | Total Turn time. |
| `error` | object \| null | `{ code, message }` on a business failure. |

#### `columns[]`

`numeric` and `semantic_type` are derived deterministically from the result (no
LLM; see [ADR 0004](adr/0004-deterministic-column-metadata.md)).
`semantic_type` ∈ `count | number | percent | gpa | date | id | category | name | text`.

Use it to align and format values:

- `count` → thousands separator
- `number` → locale number, up to 2 decimals
- `percent` → one decimal + `%`
- `gpa` → two decimals
- `date` → trim to `YYYY-MM-DD`
- `id` → **no** thousands separator
- `name` / `category` / `text` → plain string

Right-align a column when `numeric === true && semantic_type !== "id"`.

> **Known gap (Oct 2026):** `describe_result` computes a `collapsible` flag for
> an identifier–name pair (ADR 0009) and the demo UI reads it, but
> `api.schemas.ColumnInfo` does not expose the field yet — the HTTP response
> currently omits it. Until that is fixed, do not rely on `collapsible` from the
> envelope.

#### `summary`

`numeric_aggregates` skips `id` columns and non-finite values. `single_value` is
`true` for one row × one numeric column — headline the number instead of drawing
a one-cell table.

#### `visualization`

`title` is the user's question; `x_label` / `y_label` are humanised column names;
`top_n` (when set) means "show the top N categories on the axis and fold the rest
into one *other* slice"; `reason` is a short Thai phrase. Everything here is
advisory.

`chart_type` is a **kind key**, not a display label — supply your own label. The
catalog is `bar`, `bar_horizontal`, `bar_grouped`, `bar_stacked`,
`bar_stacked_100`, `line`, `area`, `combo`, `pie` (drawn as a doughnut),
`scatter`, `heatmap`, `treemap`, `histogram`, `boxplot`, `table` and `none`.
`table` and `none` are terminal: they carry no axis.

A `heatmap` uses `x_col` and `series_col` as its two category dimensions and
`y_col` as the colour scale; a two-dimension grid of 12 cells or more recommends
it, while a smaller one keeps the grouped-bar family (and still offers the
heatmap). A `treemap` carries one high-cardinality category in `x_col` and a
single additive, strictly positive measure in `y_col` — the service never offers
it for a percent/rate/GPA measure or a result with a negative value, because the
rectangle areas would then misstate the whole.

A `histogram` and a `boxplot` describe **raw rows**, not an aggregate: one
measurement column whose values are observations, not per-group summaries. The
measurement travels in `y_col`. A histogram bins it into equal-width intervals —
the Consumer owns the bin width, but each bin must be labelled with its range and
carry the number of rows it holds — so `x_col` is `null` unless the rows also
carry a category a boxplot could group by, in which case it names that category
(carried so switching to the boxplot needs no new request). A `boxplot` uses
`x_col` as the category and `y_col` as the measurement, one box per category with
its five-number summary. Neither kind is offered for an aggregate (a count, sum,
average, rate or share, or one row per group), a constant measurement, or a
result too short to have a spread: those are a `table` with a plain-language
`reason`.

| Field | Meaning |
|---|---|
| `chart_type` | The recommended kind key. |
| `x_col` / `y_col` | Axis columns; never an `id` column (ADR 0008). |
| `series_col` | Column that splits the result into multiple series, or `null`. |
| `y2_col` | The second measure a `combo` carries on its own axis (the rate/percent), or `null`. |
| `chart_form` | `"grouped"`, `"stacked"` or `"stacked_100"` when a series role exists; `null` otherwise. For a bar-family kind the key already encodes it. |
| `sort` | The order the recommendation assumes: `"value_desc"`, `"x_asc"` or `"row_order"`; `null` when order is irrelevant. Honour it or sort your own way. |
| `options` | The alternative kind keys **this result can actually be drawn as**, derived from the grid. Always includes `chart_type` and `table`. |

`series_col` + `chart_form` are how a Consumer knows to group, stack, or stack
to 100%; a `stacked_100` result needs no normalization from the Consumer — draw
the `y_col` values as shares of each `x_col` (the service does not rewrite the
rows). Colors, fonts and layout never travel in this block (ADR 0015).

#### Clarification and refusal

Both are successful business outcomes (`status: "ok"`, HTTP 200) with no query
behind them:

```json
{
  "status": "ok",
  "request_id": "...",
  "question": "เด็กเสี่ยงมีเท่าไหร่",
  "answer_type": "clarification",
  "message": "อยากทราบจำนวนนักเรียนเสี่ยงในช่วงเวลาใดครับ (ภาคเรียนนี้ หรือ 30 วันล่าสุด)",
  "steps_used": 2,
  "prep_ms": 380,
  "turn_digest": null,
  "sql": null,
  "columns": [],
  "rows": [],
  "row_count": 0,
  "truncated": false,
  "summary": null,
  "visualization": null,
  "retry_count": 0,
  "elapsed_ms": 6210,
  "error": null
}
```

A refusal has the same shape with `answer_type: "refusal"` and a Thai explanation
in `message`. Append both kinds to the Session like any other Turn — they do not
reset the conversation.

### Business failure — still HTTP 200

```json
{
  "status": "error",
  "request_id": "...",
  "question": "...",
  "answer_type": "result",
  "message": null,
  "steps_used": 2,
  "prep_ms": 410,
  "turn_digest": null,
  "sql": "SELECT foo FROM bar",
  "columns": [],
  "rows": null,
  "row_count": 0,
  "truncated": false,
  "summary": null,
  "visualization": null,
  "retry_count": 0,
  "elapsed_ms": 8100,
  "error": { "code": "EXEC_FAILED", "message": "relation \"bar\" does not exist" }
}
```

`error.code` is a closed set:

| Code | Meaning |
|---|---|
| `LLM_FAILED` | The model produced no usable SQL / the LLM call failed. |
| `EXEC_FAILED` | SQL was produced but rejected by the datasource or the safety validator. |
| `SQL_INVALID` | Reserved for deterministic SQL-validation failures. |
| `STEP_BUDGET_EXCEEDED` | The agent loop used all 8 steps without a final answer; no SQL to best-effort. |

An empty result is **not** an error: `status: "ok"`, `rows: []`, `row_count: 0`,
`error: null`.

Infrastructure failures use real HTTP status: `401` (missing/wrong key), `503`
(`Datasource unavailable`), `422` (malformed body / invalid history), `5xx`
(unexpected).

---

## `POST /api/query/stream`

Same request and auth as `POST /api/query`, but the response is
`text/event-stream` (SSE). The stream always runs the agent loop; `history` is
optional and omitted means a first Turn.

```bash
curl -N -X POST http://localhost:8000/api/query/stream \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -H "Accept: text/event-stream" \
  -d '{"question":"จำนวนนักเรียนปัจจุบันแยกตามโรงเรียน","history":[]}'
```

The response has `Cache-Control: no-cache` and `X-Accel-Buffering: no`; a proxy
must not buffer it.

### Events

```
event: progress
data: {"event":"turn_started","seq":1,"elapsed_ms":0,"question":"..."}

event: progress
data: {"event":"tool","seq":2,"elapsed_ms":2500,"tool":"get_schema"}

event: progress
data: {"event":"sql_planned","seq":3,"elapsed_ms":5200,"sql":"SELECT ..."}

event: progress
data: {"event":"sql_ok","seq":4,"elapsed_ms":6100,"row_count":42}

event: progress
data: {"event":"turn_done","seq":5,"elapsed_ms":9000,"answer_type":"result","row_count":42}

event: envelope
data: { …the same envelope as POST /api/query… }
```

| SSE `event` | Payload |
|---|---|
| `progress` | A mid-Turn update. The JSON `event` field is `turn_started`, `tool`, `sql_planned`, `sql_ok`, `sql_failed` or `turn_done`; every payload has `seq` and `elapsed_ms`. `tool` and `sql_ok` may omit their optional field. |
| `envelope` | Always the final event. It is the complete Answer envelope (result / clarification / refusal / business error). |
| `error` | Only when the stream itself fails before an envelope can be produced; payload is `{ "error": "..." }`. |

Progress events are **not** part of the Session — never append them to history,
and never use them as the answer. They only move information the final envelope
will contain into the waiting time. The existing `/api/query` endpoint is
unchanged; streaming is opt-in.

---

## `GET /api/health`

No API key required.

```json
{ "status": "ok", "datasource": true, "schema_cached": true, "warming": false }
```

`datasource` is `false` when `DATABASE_URL` is unset or unreachable.
`schema_cached` / `warming` are additive warm-state signals; older Consumers may
ignore them.

## `GET /api/schema`

```json
{
  "tables": [
    {
      "name": "schools",
      "columns": [
        { "name": "id", "type": "int", "numeric": false, "semantic_type": "text" }
      ]
    }
  ]
}
```

The analytical tables/views the model can use; backup/audit/token/PII objects are
hidden by the denylist. `503` without a datasource. Column metadata here comes
from the schema, not from a result, so `numeric` / `semantic_type` are defaults.

## `POST /api/admin/refresh-schema`

`{ "status": "ok" }` — marks the cached schema stale. The next query
re-introspects the datasource and re-indexes the schema RAG. Call it after a
migration on the datasource.

## Demo-mode Datasource switching (demo only)

Mounted only while the bundled UI is served (`APP_MODE=demo`, or `auto` without
an API key); a service deployment returns `404`. See ADR 0013.

| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/demo/state` | `{ datasource, profile, profiles }` — the active DSN with the password redacted (or `null`), plus the selectable `profiles/<name>` directories. |
| `POST` | `/api/demo/connect` | Body `{ database_url?, profile? }`. Opens the DSN once, then points the process at it. Omit `database_url` to switch profile on the Datasource already connected (the state DSN has its password redacted, so the wizard cannot resend it). `400` (with a Thai message) when the DSN is malformed, unreachable, or the profile is unknown — the previous Datasource keeps serving. Response `{ datasource, profile, tables }`. |
| `POST` | `/api/demo/profile/draft` | Body `{ question, sql? }`. Drafts one example for the Profile wizard: the generated SQL and the rows it produced, or the failure. Writes nothing. Response `{ status, dialect, sql, rows, row_count, category, error }`. |
| `POST` | `/api/demo/profile/save` | Body `{ name, hints, schema_mappings, table_notes, examples, overwrite }`. Writes an ordinary `profiles/<name>/` profile after executing every result example's SQL read-only; an example with `expected_answer_type` (`clarification`/`refusal`) and `expected_message` is written as a non-SQL exemplar instead. `400` for a bad slug, a half-filled `table_notes` entry, or an example that fails, `409` for an existing profile without `overwrite`. Response `{ profile, coverage }` where coverage is `{ hints, examples, exemplars, schema_mappings, table_notes }`. See `docs/guides/PROFILES.md` section 7. |

A switch is an in-memory state change: it lasts until the process restarts, and
it exists because the demo page is served by the process it talks to. These
routes open *any* DSN the caller names, so the demo — unauthenticated by design
and loopback-bound by default — must never be published.

## History / favorites (demo UI only)

These endpoints are used by the bundled demo UI and are backed by local files.
A real Consumer keeps its own Log store (persist the `request_id` and envelope
fields); the service does not own that record.

| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/history?limit=50&dialect=&status=` | Local demo log. |
| `PATCH` | `/api/history/{log_id}/feedback` | Body `{ "feedback": "positive" \| "negative", "feedback_text": "..." }`. |
| `GET` | `/api/favorites` | Local favorites. |
| `POST` | `/api/favorites` | Body `{ question, sql, dialect, log_id?, name? }`. |
| `DELETE` | `/api/favorites/{favorite_id}` | Remove one favorite. |

---

## Calling it from NestJS

The service is server-to-server only: NestJS holds the API key; React must not
call the service directly. The service therefore needs no CORS configuration.

```ts
// text-to-sql.service.ts
import { Injectable, HttpException } from '@nestjs/common';

type SemanticType =
  | 'count' | 'number' | 'percent' | 'gpa'
  | 'date' | 'id' | 'category' | 'name' | 'text';

type AnswerType = 'result' | 'clarification' | 'refusal';

type ChartKind =
  | 'bar' | 'bar_horizontal' | 'bar_grouped' | 'bar_stacked' | 'bar_stacked_100'
  | 'line' | 'area' | 'combo' | 'pie' | 'scatter'
  | 'heatmap' | 'treemap' | 'histogram' | 'boxplot'
  | 'table' | 'none';

export type PriorTurn = {
  question: string;
  answer_type: AnswerType;
  sql: string | null;
  row_count?: number;
  digest?: Record<string, unknown> | null;
};

export type QueryEnvelope = {
  status: 'ok' | 'error';
  request_id: string;
  question: string;
  answer_type: AnswerType;
  message: string | null;
  steps_used: number;
  prep_ms?: number | null;
  turn_digest?: Record<string, unknown> | null;
  sql: string | null;
  columns: { name: string; type: string; numeric: boolean; semantic_type: SemanticType }[];
  rows: Record<string, unknown>[] | null;
  row_count: number;
  truncated: boolean;
  summary: {
    row_count: number;
    truncated: boolean;
    numeric_aggregates: Record<string, { sum?: number; min?: number; max?: number; mean?: number }>;
    single_value: boolean;
  } | null;
  visualization: {
    chart_type: ChartKind;
    x_col: string | null;
    y_col: string | null;
    series_col: string | null;
    y2_col: string | null;
    chart_form: 'grouped' | 'stacked' | 'stacked_100' | null;
    sort: 'value_desc' | 'x_asc' | 'row_order' | null;
    options: ChartKind[];
    title: string | null;
    x_label: string | null;
    y_label: string | null;
    top_n: number | null;
    reason: string | null;
  } | null;
  retry_count: number;
  elapsed_ms: number;
  error: { code: string; message: string } | null;
};

@Injectable()
export class TextToSqlService {
  private readonly baseUrl = process.env.TEXT_TO_SQL_URL ?? 'http://localhost:8000';
  private readonly apiKey = process.env.TEXT_TO_SQL_API_KEY ?? '';

  async ask(
    question: string,
    history: PriorTurn[] = [],          // [] = first Turn; this helper always uses agent mode
    preferredChartType?: string,
  ): Promise<QueryEnvelope> {
    const res = await fetch(`${this.baseUrl}/api/query`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-API-Key': this.apiKey },
      body: JSON.stringify({
        question,
        history,                        // always sent by this helper; omit it only in a raw fetch
        preferred_chart_type: preferredChartType ?? null,
      }),
      signal: AbortSignal.timeout(90_000),
    });

    // Infrastructure failure — unreachable / auth failed / no datasource.
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new HttpException(body.detail ?? `text-to-sql ${res.status}`, 502);
    }

    // Business outcome — always 200; branch on the envelope.
    const env: QueryEnvelope = await res.json();
    return env;
  }
}
```

### Session bookkeeping in the Consumer

The service is stateless. For every answered Turn, append one `PriorTurn`:

```ts
function appendTurn(history: PriorTurn[], question: string, env: QueryEnvelope): void {
  history.push({
    question,
    answer_type: env.answer_type,
    sql: env.answer_type === 'result' ? env.sql : null,
    row_count: env.row_count,
    digest: env.turn_digest ?? null,   // opaque; send back unchanged on result Turns
  });
}

// after receiving an envelope
appendTurn(history, question, env);
```

- Render `env.message` as a chat bubble for **every** answer type.
- Render the table/chart only when `answer_type === 'result'`.
- For a `clarification`, show the message and let the user answer; keep the Turn
  in history so the agent can interpret the answer.
- For a `refusal`, show the explanation and an alternative; it also stays in
  history.
- For `status === 'error'`, branch on `error.code`; do not show a table.
- Never append progress events to history.

---

## Formatting a cell in React (from `semantic_type`)

```ts
const fmt = new Intl.NumberFormat('th-TH');

export function formatCell(value: unknown, type: SemanticType): string {
  if (value == null) return '—';
  switch (type) {
    case 'count':   return fmt.format(Number(value));
    case 'number':  return Number(value).toLocaleString('th-TH', { maximumFractionDigits: 2 });
    case 'percent': return `${Number(value).toFixed(1)}%`;
    case 'gpa':     return Number(value).toFixed(2);
    case 'date':    return String(value).slice(0, 10);       // YYYY-MM-DD
    case 'id':      return String(value);                     // never a thousands separator
    default:        return String(value);
  }
}
// right-align a column when col.numeric && col.semantic_type !== 'id'
```

For a chart, feed `visualization.title` / `x_label` / `y_label` straight into the
chart library, and when `visualization.top_n` is set, keep the first N rows of the
category axis and sum the rest into one "อื่น ๆ" entry. Read `env.message` first:
it often states the headline the chart is meant to support.
