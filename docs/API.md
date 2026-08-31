# Thai NLP-to-SQL service — API

One HTTP service. A Consumer (e.g. the NestJS backend) sends a Thai question and
gets back the generated SQL, the result rows, and a chart suggestion.

- **Base URL (local dev):** `http://localhost:8000`
- **Interactive docs / OpenAPI:** `GET /docs`, `GET /openapi.json` — generate a
  typed client from this if you like.
- **Datasource:** fixed at deploy time by the `DATABASE_URL` env var. A Consumer
  never passes database credentials.

## Authentication

Every `/api/*` call needs the shared secret in a header:

```
X-API-Key: <the value of the service's API_KEY env var>
```

Exceptions: `GET /api/health` needs no key. When `API_KEY` is unset (local dev),
auth is off entirely and the bundled demo UI is served at `/`.

## Endpoints

### `POST /api/query`

**Request**

```json
{ "question": "จำนวนนักเรียนปัจจุบันแยกตามโรงเรียน", "preferred_chart_type": null }
```

- `question` (required) — Thai natural-language question.
- `preferred_chart_type` (optional) — `"bar" | "line" | "pie" | "scatter"`; omit for auto.
- `dialect` is accepted but **ignored** — the service uses its own datasource's dialect.

**Response — always HTTP 200 for a business outcome**

```json
{
  "status": "ok",
  "request_id": "b1a1…",
  "question": "จำนวนนักเรียนปัจจุบันแยกตามโรงเรียน",
  "sql": "SELECT school.id AS school_id, … LIMIT 500",
  "columns": [
    { "name": "school_id", "type": "int", "numeric": true, "semantic_type": "id" },
    { "name": "school_name", "type": "str", "numeric": false, "semantic_type": "name" },
    { "name": "student_count", "type": "int", "numeric": true, "semantic_type": "count" }
  ],
  "rows": [{ "school_id": 10010002, "school_name": "…", "student_count": 613 }],
  "row_count": 10,
  "truncated": false,
  "summary": {
    "row_count": 10,
    "truncated": false,
    "numeric_aggregates": { "student_count": { "sum": 5980, "min": 572, "max": 613, "mean": 598 } },
    "single_value": false
  },
  "visualization": {
    "chart_type": "bar", "x_col": "school_id", "y_col": "student_count", "series_col": null,
    "options": ["Bar Chart", "Line Chart", "Area Chart", "Pie Chart", "Table"],
    "title": "จำนวนนักเรียนปัจจุบันแยกตามโรงเรียน",
    "x_label": "school id", "y_label": "student count",
    "top_n": null,
    "reason": "เทียบค่าข้ามหมวดหมู่"
  },
  "retry_count": 0,
  "elapsed_ms": 3400,
  "error": null
}
```

**`columns[]`** — `numeric` and `semantic_type` are advisory, derived
deterministically from the result (no LLM; see `docs/adr/0004-*`).
`semantic_type` ∈ `count | number | percent | gpa | date | id | category | name | text`.
Use it to right-align and format: `count` → thousands separator, `percent` → one
decimal + `%`, `gpa` → two decimals, `date` → trim to `YYYY-MM-DD`, `id` → **no**
thousands separator.

**`summary`** — `numeric_aggregates` skips `id` columns and non-finite values.
`single_value` is `true` when the result is one row × one numeric column — headline
the number instead of drawing a one-cell table.

**`visualization`** — `title` is the user's question; `x_label` / `y_label` are the
humanised column names; `top_n` (when set) means "show the top N categories on the
axis, fold the rest into one *other* slice"; `reason` is a short Thai phrase.
Everything here is advisory.

**On a business failure — still HTTP 200**, with `status: "error"` and `error` set:

```json
{ "status": "error", "request_id": "…", "question": "…", "sql": "SELECT …", "error": { "code": "EXEC_FAILED", "message": "column … does not exist" } }
```

`error.code`: `LLM_FAILED` (no SQL produced) · `EXEC_FAILED` (SQL produced but
rejected by PostgreSQL or the safety validator). An empty result set is
`status: "ok"` with `row_count: 0` and `error: null`.

**Infrastructure failures use real HTTP status:** `401` (missing/wrong key),
`503` (`Datasource unavailable`), `422` (malformed body), `5xx` (unexpected).

### `GET /api/health`

`{ "status": "ok", "datasource": true }` — no key required. `datasource` is
`false` when `DATABASE_URL` is unset or unreachable.

### `GET /api/schema`

`{ "tables": [{ "name": "...", "columns": [{ "name": "...", "type": "..." }] }] }`
— the analytical tables/views the model can use (backup/audit/PII objects are
hidden). `503` without a datasource.

### `POST /api/admin/refresh-schema`

`{ "status": "ok" }` — drop the cached schema; call after a migration on the
datasource.

### History / favorites

`GET /api/history`, `GET /api/favorites`, `POST /api/favorites`,
`DELETE /api/favorites/{id}`, `PATCH /api/history/{log_id}/feedback` — used by the
demo UI, backed by local files. A Consumer that wants its own history should keep
it itself (persist the `request_id` and the fields from the envelope).

## Calling it from NestJS

```ts
// text-to-sql.service.ts
import { Injectable, HttpException } from '@nestjs/common';

type SemanticType =
  | 'count' | 'number' | 'percent' | 'gpa'
  | 'date' | 'id' | 'category' | 'name' | 'text';

type QueryEnvelope = {
  status: 'ok' | 'error';
  request_id: string;
  question: string;
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
    chart_type: string;
    x_col: string | null;
    y_col: string | null;
    series_col: string | null;
    options: string[];
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

  async ask(question: string, preferredChartType?: string): Promise<QueryEnvelope> {
    const res = await fetch(`${this.baseUrl}/api/query`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-API-Key': this.apiKey },
      body: JSON.stringify({ question, preferred_chart_type: preferredChartType ?? null }),
      signal: AbortSignal.timeout(60_000),
    });

    // Infrastructure failure — the service is unreachable / auth failed / no datasource.
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new HttpException(body.detail ?? `text-to-sql ${res.status}`, 502);
    }

    // Business outcome — always 200; branch on the envelope.
    const env: QueryEnvelope = await res.json();
    return env; // caller inspects env.status / env.error.code and forwards to React
  }
}
```

React never calls this service directly — it goes through NestJS, which holds the
API key. The service therefore needs no CORS configuration.

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
category axis and sum the rest into one "อื่น ๆ" entry.
