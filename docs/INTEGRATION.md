# NL-to-SQL Integration — Design Spec

Design for wiring the Thai NLP-to-SQL Python service into the STS stack (NestJS
backend + React frontend).

> **This file is self-contained.** An AI working in the `sts-backend` repo (or the
> React repo) can implement everything below from this file alone — the envelope
> contract, every field, every format rule, and reference code are all inline. No
> other file from the service repo is needed. The `API.md` / ADR references that
> appear in the service repo are background only, not required reading.

### What you (the human) must supply before an AI runs this

| thing | where it goes |
|---|---|
| The deployed Python-service URL (e.g. `https://sts-nl2sql.onrender.com`) | `TEXT_TO_SQL_URL` env in `sts-backend` |
| The shared secret (the service's `API_KEY` env value) | `TEXT_TO_SQL_API_KEY` env in `sts-backend` |
| Confirmation the service is deployed with `API_KEY` set | — (if unset the service has no auth and serves a demo page) |

---

## 0. บริบท

**Python service** ที่จะเรียก: FastAPI microservice — generate SQL จากคำถามไทย → รันกับ
STS DB (read-only role) → คืน rows + column metadata + chart config

- **โฮสต์แยก**, เรียกแบบ **server-to-server เท่านั้น** (NestJS ถือ key, React ห้ามเรียกตรง)
- **Sync + timeout** (~60s — self-correction retry ช้าได้), cap ผลลัพธ์ 500 แถวที่ service แล้ว
- Auth: header `X-API-Key: <API_KEY>` (บังคับเมื่อ service ตั้ง `API_KEY`)

### Endpoints ของ Python service

| Method | Path | Body / คืน |
|---|---|---|
| `POST` | `/api/query` | `{ question: string, preferred_chart_type?: "bar"\|"line"\|"pie"\|"scatter" }` → **envelope** (ข้อ 1) |
| `GET` | `/api/health` | `{ status: "ok", datasource: boolean }` — ไม่ต้อง key |
| `GET` | `/api/schema` | `{ tables: [{ name, columns: [{ name, type }] }] }` — ตารางเชิงวิเคราะห์ (ซ่อน backup/audit) |
| `POST` | `/api/admin/refresh-schema` | `{ status: "ok" }` — เรียกหลัง migrate STS |

---

## 1. Contract — Response Envelope

**ทุก business outcome คืน HTTP 200** (รวมกรณี error) — branch ที่ `envelope.status` /
`envelope.error.code`.
**HTTP 4xx/5xx = infra เท่านั้น** (401 key ผิด, 503 datasource ล่ม, 422 body ผิด,
5xx unexpected).

```ts
type SemanticType =
  | 'count' | 'number' | 'percent' | 'gpa'
  | 'date' | 'id' | 'category' | 'name' | 'text';

interface QueryEnvelope {
  status: 'ok' | 'error';
  request_id: string;                 // ใช้ผูก log ข้ามระบบ
  question: string;
  sql: string | null;
  columns: {
    name: string;
    type: string;                     // python type name (int/str/float…)
    numeric: boolean;
    semantic_type: SemanticType;
  }[];
  rows: Record<string, unknown>[] | null;
  row_count: number;
  truncated: boolean;                 // true = โดน cap 500 แถว
  summary: {
    row_count: number;
    truncated: boolean;
    numeric_aggregates: Record<string, { sum?: number; min?: number; max?: number; mean?: number }>;
    single_value: boolean;            // true = 1 แถว × 1 คอลัมน์ numeric → โชว์เป็นตัวเลขใหญ่
  } | null;
  visualization: {
    chart_type: 'bar' | 'line' | 'pie' | 'scatter' | 'table' | 'none';
    x_col: string | null;
    y_col: string | null;
    series_col: string | null;        // multi-series grouping
    options: string[];                // ชนิดกราฟทางเลือก (advisory)
    title: string | null;            // = คำถามผู้ใช้
    x_label: string | null;          // ชื่อคอลัมน์ humanize แล้ว
    y_label: string | null;
    top_n: number | null;            // ถ้า set → fold category เกินนี้เป็น "อื่น ๆ"
    reason: string | null;           // เหตุผลเลือกกราฟ (ไทย)
  } | null;
  retry_count: number;
  elapsed_ms: number;
  error: { code: string; message: string } | null;
}
```

**`error.code`** (closed set): `LLM_FAILED` (สร้าง SQL ไม่ได้) · `EXEC_FAILED` (SQL
รันไม่ผ่าน/ไม่ปลอดภัย) · *(PDPA phase จะเพิ่ม `PII_BLOCKED`)*
**ผลว่าง** = `status:"ok"`, `row_count:0`, `error:null` (ไม่ใช่ error)

### ตัวอย่างจริง

**สำเร็จ (bar chart):**

```json
{
  "status": "ok",
  "request_id": "b1a1c0de-...",
  "question": "จำนวนนักเรียนปัจจุบันแยกตามโรงเรียน",
  "sql": "SELECT s.school_id, s.school_name, COUNT(DISTINCT e.person_uuid) AS student_count FROM ... GROUP BY 1, 2 LIMIT 500",
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
    "chart_type": "bar", "x_col": "school_id", "y_col": "student_count", "series_col": null,
    "options": ["Bar Chart", "Line Chart", "Area Chart", "Pie Chart", "Table"],
    "title": "จำนวนนักเรียนปัจจุบันแยกตามโรงเรียน",
    "x_label": "school id", "y_label": "student count",
    "top_n": null, "reason": "เทียบค่าข้ามหมวดหมู่"
  },
  "retry_count": 0,
  "elapsed_ms": 3412,
  "error": null
}
```

**ผลเป็นตัวเลขเดียว** (`นักเรียนทั้งหมดกี่คน`): `rows: [{ "total_students": 5983 }]`,
`summary.single_value: true`, `visualization.chart_type: "table"` → ฝั่ง UI โชว์เป็น
ตัวเลขใหญ่

**ธุรกิจล้มเหลว (ยัง HTTP 200):**

```json
{
  "status": "error",
  "request_id": "...",
  "question": "...",
  "sql": "SELECT foo FROM bar",
  "columns": [], "rows": null, "row_count": 0, "truncated": false,
  "summary": null, "visualization": null,
  "retry_count": 2, "elapsed_ms": 8100,
  "error": { "code": "EXEC_FAILED", "message": "relation \"bar\" does not exist" }
}
```

**ผลว่าง:** `status: "ok"`, `rows: []`, `row_count: 0`, `error: null`

---

## 2. NestJS Design (`sts-backend`)

> **Adjustments confirmed against the real `sts-backend` codebase** (read-only
> reviews flagged these — the spec below reflects them):
>
> **Entity / DB**
> - `nl_query_log.id` = **bigint auto-increment** (matches `audit_log`).
> - `nl_query_log.user_id` = **integer, nullable**, FK → `users(id)` `ON DELETE SET NULL`
>   (`users.id` is integer; nullable is required for SET NULL).
> - Register `NlQueryLog` in **`DATABASE_ENTITIES`** (the datasource does **not**
>   use `autoLoadEntities`), *in addition to* `TypeOrmModule.forFeature([NlQueryLog])`.
> - Migration follows the latest migration's style in the repo.
>
> **HTTP client**
> - No `@nestjs/axios` / `HttpModule` / axios. Use Node's global `fetch` +
>   `AbortController` (TS target is ES2023 — fine).
>
> **Throttling**
> - `ThrottlerGuard` is **not** global; the project uses a **named throttler +
>   per-route decorator**. Add an `nlQuery` entry to `throttle.config.ts` and a
>   `ThrottleNlQuery()` decorator like the other endpoints — **10 req / นาที / IP**.
>   A literal `@Throttle({...})` will not work. No per-user quota in v1.
>
> **Permissions**
> - `@RequirePermission()` needs a paired **`PermissionsGuard`** — put
>   `@UseGuards(PermissionsGuard)` at the controller.
> - Add `nl_query:use` to **`APP_PAGES` as a top-level page** (the permission
>   catalog is derived from the page registry — a raw role grant alone fails the
>   permission-parity tests). Then a migration grants it to **`ADMIN` and
>   `EXECUTIVE`** only. No `data_scope` enforcement exists yet (→ PDPA phase), so
>   wider grants would be the PDPA problem. Per-account overrides can widen later.
>
> **Types**
> - The current-user type is **`AuthenticatedRequestUser`** (not `SessionUser`).
>
> **Scope of this round**
> - `GET /api/nl-query/schema` **is required** (thin proxy + cache) — not optional.
> - Backend only. Frontend is a separate paste in the React repo.
> - `npm run lint` uses `--fix` (mutates files) — run only as the **final** step
>   after implementation. `typecheck` + `build` are safe anytime.
>
> **Audit-write failure policy** — see §2.3.

### 2.1 Module: `NlQueryModule`

```
src/nl-query/
├── nl-query.module.ts
├── nl-query.controller.ts
├── nl-query.service.ts
├── nl-query-log.service.ts
├── dto/nl-query.dto.ts            // NlQueryDto + QueryEnvelope types (จากข้อ 1)
├── entities/nl-query-log.entity.ts
└── ... migration ใน src/database/migrations/
```

`module.ts`: `imports: [TypeOrmModule.forFeature([NlQueryLog])]`,
`controllers: [NlQueryController]`, `providers: [NlQueryService, NlQueryLogService]`.
Import ใน `AppModule`. (ไม่ต้องมี `HttpModule` — service ใช้ global `fetch`)

### 2.2 Controller — `POST /api/nl-query`

- อยู่หลัง **global `AuthGuard`** อยู่แล้ว (ไม่ใส่ `@Public()`)
- **`@RequirePermission()` อย่างเดียวไม่บังคับสิทธิ์** — ต้องมี `PermissionsGuard`
  ด้วย. ใส่ `@UseGuards(PermissionsGuard)` ที่ระดับ controller (ตามที่ controller
  อื่นในระบบทำ)
- ก่อน grant: (1) ประกาศ `nl_query:use` ใน **`APP_PAGES` / permission registry**
  ตามกลไกเดิม (2) migration grant ให้ role **`ADMIN` และ `EXECUTIVE`**
- rate-limit: **named throttler** (`throttle.config.ts` + `@ThrottleNlQuery()`),
  10 req/นาที/IP
- user type จริงในระบบคือ **`AuthenticatedRequestUser`** (ไม่ใช่ `SessionUser`) —
  map `user.id` / `data_scope` ตาม field จริงของ type นั้น

```ts
@Controller('api/nl-query')
@UseGuards(PermissionsGuard)                  // ← จำเป็น: RequirePermission ต้องมี guard คู่กัน
export class NlQueryController {
  constructor(private readonly svc: NlQueryService) {}

  @Post()
  @RequirePermission('nl_query:use')
  @ThrottleNlQuery()                          // named throttler (throttle.config.ts), 10/min/IP
  ask(
    @CurrentUser() user: AuthenticatedRequestUser,
    @Body() dto: NlQueryDto,
  ): Promise<QueryEnvelope> {
    return this.svc.query(dto, user);
  }

  @Get('schema')
  @RequirePermission('nl_query:use')
  schema(): Promise<SchemaResponse> {
    return this.svc.schema();
  }
}
```

**`NlQueryDto`**: `question: string` (`@IsString @MinLength(1) @MaxLength(500)`),
`preferredChartType?: 'bar'|'line'|'pie'|'scatter'` (`@IsOptional @IsIn`)

### 2.3 Service — `NlQueryService`

**Audit-write failure policy (2-step log):** ในเฟสนี้ `nl_query_log` เป็น audit
trail เดียว (ยังไม่มี scope/PII control) — จะไม่ให้เกิด NL-to-SQL ที่ตรวจย้อนหลัง
ไม่ได้:

1. **INSERT แถว `status='pending'`** (userId, question, dataScope, requestId=null,
   createdAt) **ก่อนเรียก Python**. ถ้า INSERT ล้มเหลว → โยน `503` ทันที ไม่เรียก Python
2. เรียก Python service
3. **UPDATE แถวเดิม** ด้วยผล (requestId, sql, status, errorCode, rowCount,
   retryCount, elapsedMs). ถ้า UPDATE ล้มเหลว → `logger.error(...)` แต่ **คืน
   envelope ตามปกติ** (ข้อเท็จจริง "ใครถามอะไรเมื่อไหร่" ถูกบันทึกไปแล้วในขั้น 1)

แถวที่ค้าง `status='pending'` = Python hang / timeout / process ตาย — ถือเป็น
สัญญาณให้ตรวจ

```ts
// global fetch (Node 18+) — no HttpModule/axios
async query(dto: NlQueryDto, user: AuthenticatedRequestUser): Promise<QueryEnvelope> {
  const started = Date.now();

  // 1. audit anchor — commit ว่าเรากำลังจะประมวลผล ก่อนแตะ Python
  let logId: string;
  try {
    logId = await this.log.begin({
      userId: user.id ?? null,
      dataScope: user.data_scope ?? null,
      question: dto.question,
    });
  } catch (e) {
    this.logger.error('nl_query_log.begin failed', e);
    throw new ServiceUnavailableException('ระบบบันทึกการใช้งานไม่พร้อม กรุณาลองใหม่');
  }

  // 2. call Python
  let envelope: QueryEnvelope;
  try {
    const ac = new AbortController();
    const t = setTimeout(() => ac.abort(), this.cfg.timeoutMs);   // 60000
    let res: Response;
    try {
      res = await fetch(`${this.cfg.url}/api/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-API-Key': this.cfg.apiKey },
        body: JSON.stringify({
          question: dto.question,
          preferred_chart_type: dto.preferredChartType ?? null,
        }),
        signal: ac.signal,
      });
    } finally {
      clearTimeout(t);
    }
    if (!res.ok) throw new Error(`upstream ${res.status}`);   // 401 / 503 / 5xx
    envelope = (await res.json()) as QueryEnvelope;           // HTTP 200 → business outcome
  } catch (e) {
    await this.log.fail(logId, String(e)).catch(() => {});    // best-effort
    throw new BadGatewayException('บริการวิเคราะห์ข้อมูลไม่พร้อมใช้งาน');
  }

  // 3. complete the audit row (best-effort — anchor already exists)
  // TODO(pdpa): enforce user.data_scope on the generated SQL / result rows.
  //   ตอนนี้: ทุกคนที่มี nl_query:use ถามได้ทั้ง DB — known limitation ใน docs/PDPA
  try {
    await this.log.complete(logId, {
      requestId: envelope.request_id,
      sql: envelope.sql,
      status: envelope.status,
      errorCode: envelope.error?.code ?? null,
      rowCount: envelope.row_count,
      retryCount: envelope.retry_count,
      elapsedMs: Date.now() - started,
    });
  } catch (e) {
    this.logger.error(`nl_query_log.complete failed (logId=${logId})`, e);
  }

  return envelope;   // forward ตรง ๆ ไม่ reshape
}
```

`NlQueryLogService`: `begin(x) → logId`, `complete(logId, y)`, `fail(logId, msg)`;
ต่อไปเพิ่ม `pruneOlderThan(days)`.

**Config** (`ConfigService` / env):

```
TEXT_TO_SQL_URL=https://<python-host>
TEXT_TO_SQL_API_KEY=<ตรงกับ API_KEY ของ service>
TEXT_TO_SQL_TIMEOUT_MS=60000
```

### 2.4 Entity — `NlQueryLog` (TypeORM, ตาม pattern `audit_log`)

รองรับ 2-step log (§2.3) — fields ที่เติมทีหลังเป็น nullable:

| column | type | หมายเหตุ |
|---|---|---|
| `id` | **bigint auto-increment** PK | ตาม `audit_log` |
| `user_id` | **integer, nullable**, index, FK → `users(id)` ON DELETE SET NULL | `users.id` = int; nullable จำเป็นสำหรับ SET NULL. เก็บแค่ id |
| `data_scope` | jsonb null | scope ของ user ตอนถาม (บันทึก ไม่ enforce) |
| `question` | text | *(PDPA phase: redact ก่อนเก็บ)* |
| `status` | varchar(12) | `pending` → `ok` / `error` / `failed` |
| `request_id` | varchar null, index | เติมตอน complete (uuid string ของ Python) |
| `sql` | text null | เติมตอน complete |
| `error_code` | varchar(32) null | `LLM_FAILED` / `EXEC_FAILED` (จาก envelope) |
| `error_detail` | text null | ข้อความ error ตอน `fail()` (transport failure) |
| `row_count` | int null | |
| `retry_count` | int null | |
| `elapsed_ms` | int null | round-trip ฝั่ง NestJS |
| `created_at` | timestamptz, default now(), index | *(PDPA phase: retention 90 วัน)* |
| `completed_at` | timestamptz null | เซ็ตตอน complete/fail — แถวที่ค้าง `pending` + created_at เก่า = ต้องตรวจ |

Migration: ตาม style migration ล่าสุดใน repo. index: `user_id`, `request_id`,
`created_at`, `status`.

**`NlQueryLogService`** (wrap `Repository<NlQueryLog>`):
`begin({userId, dataScope, question}) → logId` (INSERT `status='pending'`) ·
`complete(logId, {...})` (UPDATE) · `fail(logId, detail)` (UPDATE `status='failed'`) ·
ต่อไป `pruneOlderThan(days)`

### 2.5 Schema proxy (required)

`NlQueryService.schema()` → `fetch(`${url}/api/schema`, { headers: { 'X-API-Key' }})`
→ cache in-memory ~5 นาที → คืนตรง ๆ. Frontend v1 ยังไม่เรียก แต่สร้างให้ครบ API
surface (thin proxy ~15 บรรทัด)

---

## 3. React Design

### 3.1 โครง

```
src/features/nl-query/
├── types.ts              // QueryEnvelope, SemanticType, ... (จากข้อ 1)
├── api.ts                // askNlQuery(), fetchNlSchema()
├── useNlQuery.ts         // hook
├── format.ts             // formatValue, humanizeHeader, toCSV, toMarkdown
├── QueryResult.tsx       // การ์ดผลลัพธ์: summary + tabs + big-number
├── ResultTable.tsx       // ตารางจัดรูป + sort + copy
├── ResultChart.tsx       // react-chartjs-2
├── NlQueryPage.tsx       // หน้าเต็ม: ช่องพิมพ์คำถาม + ประวัติในหน้า + <QueryResult>
└── result.css
```

**ต้องสร้างหน้าจริง + route:**
- `NlQueryPage.tsx` — หน้าใช้งาน (input + loading + error + `<QueryResult>`)
- ลง **route** (เช่น `/analytics/nl-query` หรือ `/ถามข้อมูล`) ใน router ของ repo
- `nl_query:use` เป็น top-level page ใน backend (`APP_PAGES`) — ถ้า frontend มี
  page-registry / nav ที่ mirror permission ให้ **ลงหน้านี้ในนั้นด้วย** (nav entry +
  route guard) ตามกลไกเดิม ผู้ที่ไม่มีสิทธิ์จะไม่เห็น/เข้าไม่ได้

Dependency ใหม่: `chart.js` + `react-chartjs-2`

### 3.2 `api.ts`

React (5173) ↔ NestJS (3000) เป็น cross-origin → ต้องใช้ absolute URL จาก env
เดิมของ repo (`VITE_API_BASE_URL` + `VITE_API_PREFIX`) ใช้ helper/axios instance
ที่มีอยู่ถ้ามี — โค้ดนี้เป็น fallback:

```ts
const BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:3000';
const PREFIX = import.meta.env.VITE_API_PREFIX ?? '/api';

export async function askNlQuery(question: string, preferredChartType?: ChartType): Promise<QueryEnvelope> {
  const res = await fetch(`${BASE}${PREFIX}/nl-query`, {
    method: 'POST',
    credentials: 'include',                    // ส่ง sts_session cookie ข้าม origin
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, preferredChartType }),
  });
  if (res.status === 401) throw new Error('เซสชันหมดอายุ');
  if (res.status === 403) throw new Error('ไม่มีสิทธิ์ใช้งานฟีเจอร์นี้');
  if (!res.ok) throw new Error('บริการไม่พร้อมใช้งาน');   // 502 จาก NestJS
  return res.json();                            // 200 envelope
}
```

### 3.3 `useNlQuery.ts`

```ts
function useNlQuery() {
  const [data, setData] = useState<QueryEnvelope | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const ask = useCallback(async (question: string, chart?: ChartType) => {
    setLoading(true); setError(null);
    try { setData(await askNlQuery(question, chart)); }
    catch (e) { setError((e as Error).message); setData(null); }
    finally { setLoading(false); }
  }, []);

  return { ask, data, loading, error, reset: () => setData(null) };
}
```

### 3.4 `format.ts` — reference implementation (คัดลอกได้เลย)

```ts
import type { SemanticType } from './types';

const NF0 = new Intl.NumberFormat('th-TH');
const NF2 = new Intl.NumberFormat('th-TH', { maximumFractionDigits: 2 });

export function formatValue(value: unknown, t: SemanticType): string {
  if (value === null || value === undefined || value === '') return '—';
  const n = Number(value);
  switch (t) {
    case 'count':   return Number.isFinite(n) ? NF0.format(n) : String(value);
    case 'number':  return Number.isFinite(n) ? NF2.format(n) : String(value);
    case 'percent': return Number.isFinite(n) ? `${n.toFixed(1)}%` : String(value);
    case 'gpa':     return Number.isFinite(n) ? n.toFixed(2) : String(value);
    case 'date':    return String(value).slice(0, 10);           // YYYY-MM-DD
    case 'id':      return String(value);                        // ห้ามคั่นหลักพัน
    default:        return String(value);
  }
}

/** numeric column ที่ไม่ใช่ identifier → ชิดขวา */
export const isRightAligned = (c: { numeric: boolean; semantic_type: SemanticType }) =>
  c.numeric && c.semantic_type !== 'id';

export const humanizeHeader = (name: string) => name.replace(/_/g, ' ');

/** ตัวเลขบนแกน/tooltip ของกราฟ — เติม % ให้ percent */
export function formatAxisValue(value: unknown, t: SemanticType): string {
  const n = Number(value);
  if (!Number.isFinite(n)) return String(value);
  return t === 'percent' ? `${NF2.format(n)}%` : NF2.format(n);
}

export function toCSV(rows: Record<string, unknown>[]): string {
  if (!rows.length) return '';
  const headers = Object.keys(rows[0]);
  const esc = (v: unknown) => {
    if (v === null || v === undefined) return '';
    const s = String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  return [headers.join(','), ...rows.map((r) => headers.map((h) => esc(r[h])).join(','))].join('\n');
}

export function toMarkdown(rows: Record<string, unknown>[]): string {
  if (!rows.length) return '';
  const headers = Object.keys(rows[0]);
  const esc = (v: unknown) => (v === null || v === undefined ? '' : String(v).replace(/\|/g, '\\|'));
  const line = (cells: string[]) => `| ${cells.join(' | ')} |`;
  return [
    line(headers),
    line(headers.map(() => '---')),
    ...rows.map((r) => line(headers.map((h) => esc(r[h])))),
  ].join('\n');
}
```

### 3.5 `QueryResult.tsx` (การ์ดหลัก — รับ `envelope`)

```
<div class="nlq-card">
  ถ้า rows ว่าง → <p>ไม่พบข้อมูล</p>
  <SummaryBar>   จำนวนแถว · [Σ / เฉลี่ย ของ 1 คอลัมน์ numeric] · ⚠️ ถ้า truncated
                 [📋 CSV] [📋 MD]
  ถ้า summary.single_value → <BigNumber>  (ตัวเลขใหญ่ + ชื่อคอลัมน์) — จบ
  ถ้า visualization.chart_type ∈ {table, none} → <ResultTable> อย่างเดียว — จบ
  <h4 class="nlq-title">{visualization.title}</h4>
  <Tabs [ตาราง | กราฟ]>  default = กราฟ
     ℹ️ {visualization.reason}
     <select> เปลี่ยนชนิดกราฟ (bar/line/pie/scatter) + [⬇ PNG]
  <ResultChart>  /  <ResultTable>
</div>
```

### 3.6 `ResultTable.tsx`

- header sticky, `max-height: 480px` scroll ในกล่องตัวเอง
- คลิกหัวคอลัมน์ → sort asc/desc (client-side จาก `rows` ที่มี, numeric เทียบตัวเลข,
  text ใช้ `localeCompare('th')`, null ไปท้าย)
- cell format ด้วย `formatValue(row[col.name], col.semantic_type)`, class `num` เมื่อ
  right-align
- Copy CSV / MD ใช้ `navigator.clipboard.writeText`

### 3.7 `ResultChart.tsx` (react-chartjs-2)

รับ `{ viz, rows, columns }`. Map:

| viz.chart_type | Chart.js | รายละเอียด |
|---|---|---|
| `bar` | `Bar` | `borderRadius: 6`, `maxBarThickness: 48`; ถ้า labels > 8 → `indexAxis: 'y'` (แนวนอน — ป้ายไทยยาวอ่านออก) |
| `line` | `Line` | `tension: 0.35`, `pointRadius: 3` (→ 0 ถ้าจุด > 30), `fill: true` พื้นจาง |
| `pie` | `Doughnut` | `cutout: '55%'`, legend point-style |
| `scatter` | `Scatter` | หา 2 คอลัมน์ `numeric && semantic_type !== 'id'` → `{x, y}` points |

- **สี**: single-series bar/line = สีแบรนด์เดียว; pie/multi-series = palette เช่น
  `['#4C72B0','#DD8452','#55A868','#C44E52','#8172B2','#937860','#DA8BC3']`
- **top_n fold**: ถ้า `viz.top_n` set และเป็น single-series bar/pie → sort `rows` desc
  ตาม `y_col`, เก็บ `top_n` แรก, ที่เหลือรวมเป็น 1 จุด label `อื่น ๆ (N)` ค่า = ผลรวม
- **format ตัวเลขแกน/tooltip** ตาม `semantic_type` ของ `y_col` (percent → `"…%"`)
- **title ไม่อยู่ใน canvas** (โชว์เป็น `<h4>` แล้ว); axis label จาก `x_label`/`y_label`
- **PNG**: `chartRef.current.toBase64Image()` → `<a download>`
- destroy instance เก่าก่อน render ใหม่ (`react-chartjs-2` จัดการให้ถ้า key/props
  เปลี่ยน — หรือใช้ `ref` + `.destroy()`)
- resize เมื่อสลับมาแท็บกราฟ (`chartRef.current?.resize()`)

### 3.8 `NlQueryPage.tsx` — หน้าใช้งาน

หน้าเต็ม: ช่องพิมพ์คำถาม + สถานะ loading/error + `<QueryResult>`. โครงขั้นต่ำ:

```tsx
export function NlQueryPage() {
  const { ask, data, loading, error } = useNlQuery();
  const [q, setQ] = useState('');
  return (
    <div className="nlq-page">
      <h1>ถามข้อมูลด้วยภาษาไทย</h1>
      <form onSubmit={(e) => { e.preventDefault(); if (q.trim()) ask(q); }}>
        <input value={q} onChange={(e) => setQ(e.target.value)}
               placeholder="เช่น จำนวนนักเรียนปัจจุบันแยกตามโรงเรียน" />
        <button disabled={loading}>{loading ? 'กำลังค้นหา…' : 'ถาม'}</button>
      </form>
      {error && <Alert kind="error">{error}</Alert>}
      {data?.status === 'error' && <Alert kind="warn">{data.error?.message}</Alert>}
      {data?.status === 'ok' && <QueryResult envelope={data} />}
    </div>
  );
}
```

ใช้ layout / `<Alert>` / `<Spinner>` ของ design system repo. เพิ่ม chip ตัวอย่างคำถาม
(3-4 อัน) ถ้าอยากช่วย onboarding

### 3.9 ฝังในหน้าอื่น (optional)

`<QueryResult envelope={...}>` render standalone — ดรอปในหน้าไหนก็ได้ที่มี envelope
อยู่แล้ว. หน้าที่อยากได้ layout เอง → อ่าน `data.rows` / `data.columns` /
`data.summary` ตรง ๆ ข้าม `QueryResult`

---

## 4. นอก scope เฟสนี้ (→ เฟส PDPA)

- ❌ **ไม่บังคับ `data_scope`** — คำตอบเป็นทั้ง DB ไม่ใช่เฉพาะโรงเรียนของผู้ถาม (บันทึกใน
  `nl_query_log.data_scope` ไว้แล้ว)
- ❌ **ไม่บล็อกคอลัมน์ PII** — ถาม `citizen_id` ยังได้ผลกลับมา
- ❌ **ยังไม่ redact** สิ่งที่ส่ง OpenAI / ที่เก็บใน `nl_query_log.question`
- ❌ **ไม่มี retention** บน `nl_query_log`

ทั้ง 4 ข้อผูกกับ checkpoint PDPA (มี ADR 0005/0006 + `docs/PDPA.md` รออยู่)

---

## 4.5 Local development — รัน 3 ตัวต่อกัน

### Port map

| service | port | หมายเหตุ |
|---|---|---|
| Python NL-to-SQL (repo นี้) | **8000** | `./start_server.sh` — ต่อ local `sts` DB ที่ `localhost:5432` |
| NestJS (`sts-backend`) | **3000** | `PORT=3000` ใน env, prefix `/api` |
| React (Vite) | **5173** | `VITE_API_BASE_URL=http://localhost:3000`, `VITE_API_PREFIX=/api` |
| PostgreSQL `sts` | **5432** | **Python service กับ NestJS ชี้ DB ตัวเดียวกัน** |

### Python service — ไม่ต้องแก้อะไร

รันตามปกติ: `./start_server.sh`

**ไม่ต้องตั้ง `API_KEY` ใน local** — `require_api_key` เป็น no-op เมื่อ `API_KEY` ว่าง
(NestJS ส่ง header `X-API-Key` มาก็ได้ Python จะไม่สนใจ) และหน้า demo UI ที่ `/` ยัง
ใช้ได้ด้วย. `.env` ปัจจุบันมี:

```
DATABASE_URL=postgresql+psycopg2://postgres:<pw>@localhost:5432/sts
DOMAIN_PROFILE=sts
MODEL_PROVIDER=openai
OPENAI_API_KEY=sk-...
# API_KEY เว้นว่างไว้
```

> local ไม่ต้องสร้าง `nl2sql_ro` role — ใช้ `postgres` ธรรมดาไปก่อน (read-only role
> ทำตอน deploy prod). Python engine รัน `SELECT` เท่านั้นอยู่แล้ว (`sql_safety.py`)

### NestJS — env สำหรับ nl-query module

```
TEXT_TO_SQL_URL=http://localhost:8000
TEXT_TO_SQL_API_KEY=local-dev-not-checked      # อะไรก็ได้ Python ไม่เช็คใน local
TEXT_TO_SQL_TIMEOUT_MS=60000
```

รัน migration `nl_query_log` เข้า local `sts` DB, seed permission `nl_query:use`,
grant ให้ user ทดสอบ (role ADMIN/EXECUTIVE)

### React

เรียก `${VITE_API_BASE_URL}${VITE_API_PREFIX}/nl-query` = `http://localhost:3000/api/nl-query`
ด้วย `credentials: 'include'` — cookie `sts_session` (จาก login เดิม) จะไปด้วย.
CORS: `CORS_ORIGINS=http://localhost:5173` ใน NestJS อนุญาตอยู่แล้ว

### Verify chain (ไล่จากล่างขึ้นบน)

```bash
# 1. Python ตรง ๆ — datasource: true
curl http://localhost:8000/api/health

# 2. Python query ตรง (ครั้งแรกช้า ~30s engine warm)
curl -X POST http://localhost:8000/api/query -H 'Content-Type: application/json' \
  -d '{"question":"จำนวนนักเรียนปัจจุบันแยกตามโรงเรียน"}'

# 3. ผ่าน NestJS (ต้อง login ก่อน เอา cookie มา)
curl -X POST http://localhost:3000/api/nl-query \
  -H 'Content-Type: application/json' -b 'sts_session=<cookie>' \
  -d '{"question":"จำนวนนักเรียนปัจจุบันแยกตามโรงเรียน"}'
# → ได้ envelope เดียวกับข้อ 2 + มีแถวใหม่ใน nl_query_log

# 4. React: เปิด localhost:5173 → หน้า NlQueryPage → พิมพ์คำถาม
```

ถ้าข้อ 3 ได้ envelope แต่ `nl_query_log` ไม่มีแถว → เช็ค 2-step log (§2.3)
ถ้าข้อ 3 ได้ 502 → Python service ไม่ขึ้น หรือ `TEXT_TO_SQL_URL` ผิด
ถ้าข้อ 3 ได้ 403 → permission `nl_query:use` ยังไม่ได้ grant ให้ user

---

## 5. Reference implementation — demo UI source (vanilla JS → port เป็น React)

โค้ดจริงจาก demo UI ของ service (`web/js/modules/`). **ไม่ใช่ React** — ใช้ Chart.js
global + DOM API ตรง ๆ. Frontend AI port ตามนี้:

- `renderResult(env)` → `<QueryResult envelope={env} />` (React component)
- `buildTable` → `<ResultTable rows columns />`, `buildTabs` + `renderChart` → `<ResultChart />`
- global `Chart` → `import { Bar, Line, Doughnut, Scatter } from 'react-chartjs-2'`
  (หรือ `Chart` class ผ่าน `chart.js/auto` + `ref`)
- ตัด `appendMessage` / `chat-history` / `escapeHtml` ทิ้ง (React escape ให้เอง);
  tab/pane visibility ใช้ `useState` แทน `.hidden`
- `resolveColor()` (hidden-probe) — เก็บไว้ ถ้า React ใช้ CSS custom properties;
  ถ้า hardcode สีเป็น hex ในไฟล์ก็ตัดทิ้งได้
- `formatValue` / `formatAxisValue` / `toCSV` / `toMarkdown` = §3.4 (มีโค้ด TS แล้ว)

### 5.1 `CATEGORICAL_COLORS` (จาก `config.js`)

```js
export const CATEGORICAL_COLORS = [
  '#4C72B0', '#DD8452', '#55A868', '#C44E52',
  '#8172B2', '#937860', '#DA8BC3',
];
// single-series bar/line: ใช้สีแบรนด์เดียว (ในเว็บคือ CSS var --color-primary /
// --chart-series-1). React: ใช้ token ของ design system คุณ หรือ hardcode เช่น '#2f5c8f'.
```

### 5.2 `result.js` (การ์ดผลลัพธ์ — summary / tabs / table / big-number)

```js
/**
 * Result card: summary bar + formatted table + (optional) chart, switchable by tab.
 * Built from the /api/query envelope.
 */
import { renderChart, resizeChart } from './chart.js';
import { formatValue, isRightAligned, humanizeHeader, toCSV, toMarkdown } from './format.js';

let _seq = 0;

export function renderResult(env) {
    // (demo UI puts the SQL in a chat bubble — React: show it in a <details> or skip)

    const chatHistory = document.getElementById('chat-history');
    const card = document.createElement('div');
    card.className = 'result-card';
    const place = () => {
        chatHistory.appendChild(card);
        chatHistory.scrollTop = chatHistory.scrollHeight;
    };

    const rows = env.rows || [];
    if (rows.length === 0) {
        card.innerHTML = '<p class="empty-state">ไม่พบข้อมูล (ผลลัพธ์ว่าง)</p>';
        return place();
    }

    card.appendChild(buildSummaryBar(env));

    if (env.summary && env.summary.single_value) {
        card.appendChild(buildBigNumber(env));           // 1x1 numeric → ตัวเลขใหญ่
        return place();
    }

    const viz = env.visualization;
    const hasChart = viz && viz.chart_type !== 'none' && viz.chart_type !== 'table';

    const tablePane = document.createElement('div');
    tablePane.className = 'result-pane result-pane-table';
    tablePane.appendChild(buildTable(rows, env.columns));

    if (!hasChart) {
        card.appendChild(tablePane);
        return place();
    }

    const chartId = `chart-${++_seq}`;
    const chartPane = document.createElement('div');
    chartPane.className = 'result-pane result-pane-chart';
    chartPane.innerHTML = `<div class="chart-container"><canvas id="${chartId}"></canvas></div>`;

    if (viz.title) {
        const h4 = document.createElement('h4');
        h4.className = 'result-title';
        h4.textContent = viz.title;
        card.appendChild(h4);
    }
    card.appendChild(buildTabs(card, viz, chartId, rows, env.columns));
    if (viz.reason) {
        const reason = document.createElement('div');
        reason.className = 'result-reason';
        reason.textContent = `ℹ️ ${viz.reason}`;
        card.appendChild(reason);
    }
    card.appendChild(chartPane);
    card.appendChild(tablePane);

    tablePane.hidden = true;   // default view: chart
    place();
    renderChart(chartId, viz, rows, env.columns);
}

function buildSummaryBar(env) {
    const bar = document.createElement('div');
    bar.className = 'result-summary';

    const parts = [`${env.row_count.toLocaleString('th-TH')} แถว`];
    const single = env.summary && env.summary.single_value;
    const aggs = (env.summary && env.summary.numeric_aggregates) || {};
    if (!single) {
        for (const [name, stats] of Object.entries(aggs)) {
            if (stats.sum !== undefined) parts.push(`Σ ${humanizeHeader(name)} ${stats.sum.toLocaleString('th-TH')}`);
            if (stats.mean !== undefined) parts.push(`เฉลี่ย ${stats.mean.toLocaleString('th-TH', { maximumFractionDigits: 2 })}`);
            break;   // one column's worth is enough for the summary line
        }
    }
    if (env.truncated) parts.push('⚠️ แสดง 500 แถวแรก (ปรับคำถามให้แคบลง)');

    const text = document.createElement('span');
    text.className = 'result-summary-text';
    text.textContent = parts.join('  ·  ');
    bar.appendChild(text);

    const actions = document.createElement('div');
    actions.className = 'result-actions';
    actions.appendChild(copyButton('📋 CSV', () => toCSV(env.rows)));
    actions.appendChild(copyButton('📋 MD', () => toMarkdown(env.rows)));
    bar.appendChild(actions);
    return bar;
}

function buildBigNumber(env) {
    const box = document.createElement('div');
    box.className = 'result-bignum';
    const col = env.columns[0];
    const value = env.rows[0][col.name];
    box.innerHTML = `
        <span class="bignum-value">${escapeHtml(formatValue(value, col.semantic_type))}</span>
        <span class="bignum-label">${escapeHtml(humanizeHeader(col.name))}</span>`;
    return box;
}

function buildTabs(card, viz, chartId, rows, columns) {
    const tabs = document.createElement('div');
    tabs.className = 'result-tabs';

    const show = (pane) => {
        card.querySelector('.result-pane-chart').hidden = pane !== 'chart';
        card.querySelector('.result-pane-table').hidden = pane !== 'table';
        tabs.querySelectorAll('.result-tab').forEach((b) => {
            b.classList.toggle('active', b.dataset.pane === pane);
        });
        if (pane === 'chart') resizeChart(chartId);   // re-measure after being hidden
    };

    ['chart', 'table'].forEach((pane) => {
        const btn = document.createElement('button');
        btn.className = `result-tab${pane === 'chart' ? ' active' : ''}`;
        btn.dataset.pane = pane;
        btn.textContent = pane === 'chart' ? 'กราฟ' : 'ตาราง';
        btn.addEventListener('click', () => show(pane));
        tabs.appendChild(btn);
    });

    const select = document.createElement('select');
    select.className = 'result-chart-type';
    const types = { bar: 'Bar', line: 'Line', area: 'Area', pie: 'Pie', scatter: 'Scatter' };
    const offered = new Set(['bar', 'line', 'pie', 'scatter', viz.chart_type]);
    for (const [value, label] of Object.entries(types)) {
        if (!offered.has(value)) continue;
        const opt = document.createElement('option');
        opt.value = value;
        opt.textContent = label;
        if (value === viz.chart_type) opt.selected = true;
        select.appendChild(opt);
    }
    select.addEventListener('change', () => {
        // Show the pane BEFORE rendering — Chart.js measures the container at
        // creation and renders blank (won't self-heal) if it is still display:none.
        show('chart');
        renderChart(chartId, { ...viz, chart_type: select.value }, rows, columns);
    });
    tabs.appendChild(select);
    tabs.appendChild(pngButton(chartId, viz.title));
    return tabs;
}

function buildTable(rows, columns) {
    const cols = columns && columns.length
        ? columns
        : Object.keys(rows[0]).map((name) => ({ name, numeric: false, semantic_type: 'text' }));

    const scroll = document.createElement('div');
    scroll.className = 'result-table-scroll';
    const table = document.createElement('table');
    const thead = document.createElement('thead');
    const headRow = document.createElement('tr');
    let sortState = { name: null, dir: 1 };
    const tbody = document.createElement('tbody');

    const paint = () => {
        tbody.replaceChildren();
        const view = [...rows];
        if (sortState.name) {
            const st = cols.find((c) => c.name === sortState.name);
            const numeric = st && st.numeric;
            view.sort((a, b) => {
                const x = a[sortState.name];
                const y = b[sortState.name];
                if (x === null || x === undefined) return 1;
                if (y === null || y === undefined) return -1;
                const cmp = numeric ? Number(x) - Number(y) : String(x).localeCompare(String(y), 'th');
                return cmp * sortState.dir;
            });
        }
        for (const r of view) {
            const tr = document.createElement('tr');
            for (const c of cols) {
                const td = document.createElement('td');
                td.textContent = formatValue(r[c.name], c.semantic_type);
                if (isRightAligned(c)) td.className = 'num';
                tr.appendChild(td);
            }
            tbody.appendChild(tr);
        }
    };

    for (const c of cols) {
        const th = document.createElement('th');
        th.textContent = humanizeHeader(c.name);
        if (isRightAligned(c)) th.className = 'num';
        th.classList.add('sortable');
        th.addEventListener('click', () => {
            sortState = sortState.name === c.name
                ? { name: c.name, dir: -sortState.dir }
                : { name: c.name, dir: 1 };
            headRow.querySelectorAll('th').forEach((h) => h.removeAttribute('data-sort'));
            th.dataset.sort = sortState.dir === 1 ? 'asc' : 'desc';
            paint();
        });
        headRow.appendChild(th);
    }

    thead.appendChild(headRow);
    table.appendChild(thead);
    table.appendChild(tbody);
    scroll.appendChild(table);
    paint();
    return scroll;
}

function copyButton(label, getText) {
    const btn = document.createElement('button');
    btn.className = 'result-mini-btn';
    btn.textContent = label;
    btn.addEventListener('click', async () => {
        try {
            await navigator.clipboard.writeText(getText());
            const original = btn.textContent;
            btn.textContent = '✓ คัดลอกแล้ว';
            setTimeout(() => { btn.textContent = original; }, 1500);
        } catch { btn.textContent = '✗ คัดลอกไม่ได้'; }
    });
    return btn;
}

function pngButton(chartId, title) {
    const btn = document.createElement('button');
    btn.className = 'result-mini-btn';
    btn.textContent = '⬇ PNG';
    btn.addEventListener('click', () => {
        const canvas = document.getElementById(chartId);      // React: chartRef.current.canvas
        if (!canvas) return;
        const a = document.createElement('a');
        a.href = canvas.toDataURL('image/png');               // React: chartRef.current.toBase64Image()
        a.download = `${(title || 'chart').slice(0, 40)}.png`;
        a.click();
    });
    return btn;
}

function escapeHtml(text) {   // React: not needed
    const div = document.createElement('div');
    div.textContent = text === null || text === undefined ? '' : String(text);
    return div.innerHTML;
}
```

### 5.3 `chart.js` (Chart.js config — bar/line/doughnut/scatter, top-N, horizontal)

```js
import { CATEGORICAL_COLORS } from './config.js';
import { formatAxisValue } from './format.js';

const _charts = new Map();                    // canvasId -> Chart instance
const HORIZONTAL_BAR_THRESHOLD = 8;           // >N bars → horizontal

let _defaultsApplied = false;
function applyChartDefaults() {
    if (_defaultsApplied || typeof Chart === 'undefined' || !Chart.defaults) return;
    Chart.defaults.font.family = "'Anuphan', system-ui, sans-serif";   // React: your app font
    _defaultsApplied = true;
}

/** Resolve var()/color-mix() to concrete rgb() (canvas may not understand color-mix). */
function resolveColor(expr) {
    const probe = document.createElement('span');
    probe.style.cssText = `color:${expr};position:absolute;left:-9999px`;
    document.body.appendChild(probe);
    const value = getComputedStyle(probe).color;
    probe.remove();
    return value;
}

function destroyChart(canvasId) {
    const tracked = _charts.get(canvasId);
    if (tracked) { tracked.destroy(); _charts.delete(canvasId); }
    // Kill any orphan Chart.js still holds on this canvas (a previous new Chart()
    // that threw mid-init) — otherwise "Canvas is already in use".
    const orphan = (typeof Chart !== 'undefined' && Chart.getChart) ? Chart.getChart(canvasId) : null;
    if (orphan) orphan.destroy();
}

export function resizeChart(canvasId) {
    const chart = _charts.get(canvasId);
    if (chart) chart.resize();
}

function semanticTypeOf(columns, name) {
    const col = (columns || []).find((c) => c.name === name);
    return col ? col.semantic_type : 'number';
}

function numericColumns(columns) {
    return (columns || []).filter((c) => c.numeric && c.semantic_type !== 'id').map((c) => c.name);
}

/** Fold a high-cardinality category axis into "top N + other" (single-series bar/pie). */
function applyTopN(config, data) {
    const { top_n: topN, chart_type: type, x_col: x, y_col: y } = config;
    if (!topN || config.series_col) return data;
    if (type !== 'bar' && type !== 'pie') return data;
    if (data.length <= topN) return data;
    const sorted = [...data].sort((a, b) => (Number(b[y]) || 0) - (Number(a[y]) || 0));
    const head = sorted.slice(0, topN);
    const tailSum = sorted.slice(topN).reduce((s, r) => s + (Number(r[y]) || 0), 0);
    return [...head, { [x]: `อื่น ๆ (${sorted.length - topN})`, [y]: tailSum }];
}

export function renderChart(canvasId, config, data, columns) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    applyChartDefaults();
    destroyChart(canvasId);
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const isPie = config.chart_type === 'pie';
    const isScatter = config.chart_type === 'scatter';
    const isLine = config.chart_type === 'line';

    const tick = resolveColor('var(--color-text-muted)');
    const grid = resolveColor('var(--chart-grid)');
    const series1 = resolveColor('var(--chart-series-1)');   // React: your brand color
    const fill1 = resolveColor('var(--chart-fill-1)');       // brand @ ~14% alpha
    const surface = resolveColor('var(--color-surface)');
    const surfaceAlt = resolveColor('var(--color-surface-alt)');
    const textColor = resolveColor('var(--color-text)');

    let datasets = [];
    let labels = [];

    if (isScatter) {
        const nums = numericColumns(columns);
        const xCol = nums.includes(config.x_col) ? config.x_col : (nums[0] || config.x_col);
        const yCol = nums.includes(config.y_col) ? config.y_col : (nums[1] || nums[0] || config.y_col);
        config = { ...config, x_col: xCol, y_col: yCol, x_label: xCol, y_label: yCol };
        datasets.push({
            label: `${xCol} × ${yCol}`,
            data: data.map((row) => ({ x: Number(row[xCol]), y: Number(row[yCol]) })),
            backgroundColor: series1, borderColor: series1, pointRadius: 4, pointHoverRadius: 6,
        });
    } else if (config.series_col) {
        const seriesValues = [...new Set(data.map((r) => r[config.series_col]))].sort();
        const xValues = [...new Set(data.map((r) => r[config.x_col]))].sort((a, b) => a - b);
        labels = xValues;
        seriesValues.forEach((seriesVal, idx) => {
            const rs = data.filter((r) => r[config.series_col] === seriesVal);
            const map = {};
            rs.forEach((r) => { map[r[config.x_col]] = r[config.y_col]; });
            const color = CATEGORICAL_COLORS[idx % CATEGORICAL_COLORS.length];
            datasets.push({
                label: `${config.series_col}: ${seriesVal}`,
                data: xValues.map((x) => (map[x] !== undefined ? map[x] : null)),
                backgroundColor: color, borderColor: color, borderWidth: 2,
                borderRadius: isLine ? 0 : 6, maxBarThickness: 48, tension: 0.35,
                pointRadius: xValues.length <= 30 ? 3 : 0, pointHoverRadius: 6, fill: false,
            });
        });
    } else {
        const rs = applyTopN(config, data);
        labels = rs.map((r) => r[config.x_col]);
        const values = rs.map((r) => r[config.y_col]);
        if (isPie) {
            datasets.push({ data: values, backgroundColor: CATEGORICAL_COLORS, borderColor: surface, borderWidth: 2 });
        } else if (isLine) {
            datasets.push({
                label: config.y_label || config.y_col, data: values,
                borderColor: series1, backgroundColor: fill1, borderWidth: 2.5, tension: 0.35,
                pointRadius: values.length <= 30 ? 3 : 0, pointHoverRadius: 6,
                pointBackgroundColor: series1, fill: true,
            });
        } else {
            datasets.push({
                label: config.y_label || config.y_col, data: values,
                backgroundColor: series1, borderRadius: 6, borderWidth: 0, maxBarThickness: 48,
            });
        }
    }

    const horizontal = config.chart_type === 'bar' && !config.series_col
        && labels.length > HORIZONTAL_BAR_THRESHOLD;
    const chartType = isPie ? 'doughnut' : (isScatter ? 'scatter' : (isLine ? 'line' : 'bar'));
    const yType = semanticTypeOf(columns, config.y_col);
    const fmtVal = (v) => formatAxisValue(v, yType);

    const catAxis = () => {
        const a = { grid: { display: false }, border: { display: false }, ticks: { color: tick } };
        if (config.x_label) a.title = { display: true, text: config.x_label, color: tick };
        return a;
    };
    const valAxis = () => {
        const a = { grid: { color: grid }, border: { display: false }, ticks: { color: tick, callback: (v) => fmtVal(v) } };
        if (config.y_label) a.title = { display: true, text: config.y_label, color: tick };
        return a;
    };

    let scales = {};
    if (isScatter) {
        const axis = (label) => ({
            grid: { color: grid }, border: { display: false }, ticks: { color: tick },
            ...(label ? { title: { display: true, text: label, color: tick } } : {}),
        });
        scales = { x: axis(config.x_label), y: axis(config.y_label) };
    } else if (!isPie) {
        scales = horizontal ? { x: valAxis(), y: catAxis() } : { x: catAxis(), y: valAxis() };
    }

    const spec = {
        type: chartType,
        data: { labels, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: isPie,
            indexAxis: horizontal ? 'y' : 'x',
            ...(isPie ? { cutout: '55%' } : {}),
            layout: { padding: 4 },
            plugins: {
                legend: {
                    display: isPie || !!config.series_col,
                    position: isPie ? 'right' : 'top',
                    labels: { color: textColor, usePointStyle: true, boxWidth: 8, padding: 14 },
                },
                tooltip: {
                    usePointStyle: true, padding: 10, cornerRadius: 8,
                    backgroundColor: surfaceAlt || 'rgba(0,0,0,0.8)',
                    titleColor: textColor, bodyColor: textColor, borderColor: grid, borderWidth: 1,
                    callbacks: {
                        label(context) {
                            const base = context.dataset.label ? `${context.dataset.label}: ` : '';
                            if (isPie) {
                                const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                const pct = ((context.parsed / total) * 100).toFixed(1);
                                return `${base}${fmtVal(context.parsed)} (${pct}%)`;
                            }
                            if (isScatter) return `${base}(${fmtVal(context.parsed.x)}, ${fmtVal(context.parsed.y)})`;
                            return `${base}${fmtVal(horizontal ? context.parsed.x : context.parsed.y)}`;
                        },
                    },
                },
            },
            scales,
        },
    };

    try {
        _charts.set(canvasId, new Chart(ctx, spec));
    } catch (e) {
        destroyChart(canvasId);            // leave canvas clean so the next switch can retry
        console.error('Chart render failed:', e);
    }
}
```

### 5.4 CSS (คัดเฉพาะที่ result card / table / chart ใช้)

```css
:root {
  /* palette — swap for your design tokens; light values shown */
  --color-surface: #fefefe;
  --color-surface-alt: #f2f3f5;
  --color-border: #dfe3e8;
  --color-text: #2b2f36;
  --color-text-muted: #5b626e;
  --color-primary: #2f5c8f;

  --chart-series-1: var(--color-primary);
  --chart-fill-1: color-mix(in oklch, var(--color-primary) 14%, transparent);
  --chart-grid: color-mix(in oklch, var(--color-text) 8%, transparent);

  --text-2xl: 1.5rem; --text-md: 1rem; --text-base: .875rem;
  --text-sm: .8125rem; --text-xs: .75rem;
}

.result-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 12px;
  padding: 16px;
  box-shadow: 0 2px 8px rgba(0,0,0,.06);
}

.result-summary {
  display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between;
  gap: 10px; margin-bottom: 12px;
  font-size: var(--text-sm); color: var(--color-text-muted);
}
.result-actions { display: flex; gap: 6px; }
.result-mini-btn {
  font: inherit; font-size: var(--text-xs); color: var(--color-text-muted);
  background: color-mix(in oklch, var(--color-text) 5%, transparent);
  border: 1px solid var(--color-border); border-radius: 6px;
  padding: 4px 10px; cursor: pointer;
}
.result-mini-btn:hover { color: var(--color-text); background: color-mix(in oklch, var(--color-text) 10%, transparent); }

.result-title { margin: 4px 0 10px; font-size: var(--text-md); font-weight: 600; color: var(--color-text); line-height: 1.4; }

.result-tabs { display: flex; align-items: center; gap: 6px; margin-bottom: 10px; border-bottom: 1px solid var(--color-border); }
.result-tab {
  font: inherit; font-size: var(--text-sm); color: var(--color-text-muted);
  background: transparent; border: none; border-bottom: 2px solid transparent;
  padding: 8px 12px; cursor: pointer;
}
.result-tab.active { color: var(--color-primary); border-bottom-color: var(--color-primary); }
.result-chart-type { margin-left: auto; font-size: var(--text-xs); padding: 4px 8px; }
.result-reason { font-size: var(--text-xs); color: var(--color-text-muted); margin-bottom: 10px; }

.result-bignum { display: flex; flex-direction: column; align-items: center; gap: 4px; padding: 24px 12px; }
.bignum-value { font-size: var(--text-2xl); font-weight: 700; color: var(--color-primary); }
.bignum-label { font-size: var(--text-sm); color: var(--color-text-muted); }

.result-table-scroll { overflow: auto; max-height: 480px; border: 1px solid var(--color-border); border-radius: 8px; }
table { width: 100%; border-collapse: collapse; font-size: var(--text-base); }
th, td { padding: 10px 12px; text-align: left; border-bottom: 1px solid var(--color-border); white-space: nowrap; }
th {
  position: sticky; top: 0; z-index: 1;
  background: var(--color-surface-alt); color: var(--color-text-muted); font-weight: 600;
}
th.sortable { cursor: pointer; user-select: none; }
th.sortable:hover { color: var(--color-text); }
th[data-sort="asc"]::after  { content: " ▲"; }
th[data-sort="desc"]::after { content: " ▼"; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
tr:hover td { background: color-mix(in oklch, var(--color-text) 3%, transparent); }

.chart-container { position: relative; width: 100%; min-height: 300px; max-height: 450px; }
.chart-container canvas { display: block; max-width: 100% !important; max-height: 350px !important; }

.empty-state { text-align: center; color: var(--color-text-muted); padding: 24px; }
```

Dark mode: redefine the `--color-*` tokens under `[data-theme="dark"]` / a media
query. The `--chart-*` tokens are `var()`/`color-mix()` of those, so they flip
automatically.
