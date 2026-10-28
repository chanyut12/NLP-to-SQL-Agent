# Domain Profiles

A **Domain profile** is the bundle of Datasource-specific knowledge the service
needs to answer questions well against one database: the prompt hints, the
few-shot Example set, the Thai-term schema mappings and the curated table notes.
It is selected once per process by `DOMAIN_PROFILE` and lives under
`profiles/<name>/`.

One service instance answers against **one Datasource** (ADR 0011). Supporting a
new database means adding a profile and passing evaluation; the service selects it
at startup by `DOMAIN_PROFILE`, and only the bundled demo may switch datasource at
runtime (ADR 0013) or author a profile with its Profile wizard (ADR 0014).

---

## 1. Directory layout

```
profiles/<name>/
├── hints.md               # prompt hints: dialect rules + domain semantics
├── examples.json          # few-shot Example set (retrieval corpus)
├── schema_mappings.json   # Thai term -> table/column name fragments
├── table_notes.json       # curated meaning/population for describe_table
└── heldout_ids.json       # ids removed from retrieval for evaluation (optional)
```

| File | Runtime use | Required? |
|---|---|---|
| `hints.md` | Injected into the one-shot prompt as `{hints}` (`core/services/engine.py`) | Required for a supported profile |
| `examples.json` | Embedded into Chroma collection `thai_sql_examples_<profile>` and retrieved per Question | Required |
| `schema_mappings.json` | Thai keyword → table boost in `SchemaRAG`; collection `schema_metadata_<profile>` | Optional (empty mapping falls back to pure semantic search) |
| `table_notes.json` | `describe_table` tool, PII column guard, Turn digest | Optional (`describe_table` degrades to raw columns) |
| `heldout_ids.json` | Evaluation corpus-balance checks; lists examples removed from the retrieval corpus, **not** read by retrieval | Optional |

`profiles/demo/` is the standalone SQLite demo profile used by `./start_demo.sh`.
It follows the current contract and is scoped to `local_database.db`; it is a
demo, not a production datasource.

`profiles/receipt_sample/` is a legacy sample kept for development. It predates
this contract (no `id` on examples, many missing `dialect`) and is not a template
to copy for a new datasource.

---

## 2. Example set contract

`examples.json` is a JSON object with an `examples` array. A **supported**
profile follows the full schema below; the legacy sample does not.

| Field | Required | Meaning |
|---|---|---|
| `id` | yes | Stable, unique identifier used by evaluation and `heldout_ids.json`. It is **not** the vector-store id. |
| `question` | yes | Thai question, phrased the way a user would ask it. |
| `sql` | yes for result examples | Read-only SQL that answers the question. Leave empty for clarification/refusal exemplars. |
| `category` | yes | SQL-shape bucket shared with the Golden set (e.g. `count_groupby`, `ranking_per_group`). |
| `dialect` | yes | `postgresql`, `mysql` or `sqlite`. If omitted, the loader defaults to `sqlite` — always set it. |
| `retrieval_tags` | recommended | Thai synonyms appended to the embedded passage. Also part of the vector id, so editing tags re-embeds the example. |
| `grain` | recommended | One-line description of what one result row means. Advisory metadata; not read by the loader. |
| `schema_packs` | recommended | Logical table groups this example belongs to. Advisory metadata; not read by the loader. |
| `expected_answer_type` | for clarification/refusal exemplars | `clarification` or `refusal`. |
| `expected_message` | for clarification/refusal exemplars | The Thai message the agent should produce. Required with `expected_answer_type`. |

For clarification/refusal exemplars, `sql` must be empty and
`expected_message` must be non-empty; the evaluation scores these as answer
types, not as SQL failures.

### How retrieval identifies an example

The vector id is a stable hash of `question + sql + retrieval_tags` — not the
`id` field. Consequences:

- Editing the question, SQL or tags creates a new vector id; the old entry is
  removed on the next startup because the Example set is the only source.
- Editing only `id` or metadata does **not** re-embed anything.
- Removing an example from the file deletes its stale vector entry at startup.

The embedded passage is `question | retrieval_tags` (tags improve paraphrase
recall); the stored document is the SQL, and the metadata carries `question`,
`category`, `dialect` and `difficulty` (default `medium`).

---

## 3. `hints.md`

Write the rules the model cannot infer from the schema: dialect functions,
academic-year conventions, status dictionaries, canonical join paths, and the
definition of ambiguous business terms.

**Both prompts read the profile:** the one-shot prompt
(`NLPEngine.query_database`) and the conversational agent's system prompt
(`core/services/agent.py`) both inject `hints.md`, so one profile governs both
answering paths — including the ambiguous shapes that must clarify instead of
being guessed (ADR 0014). A profile with no `hints.md` still yields a valid
prompt (the block reads `(none)`).

The one-shot prompt is built when the engine initialises, so a change to
`hints.md` reaches it after a **service restart** (or a datasource switch in demo
mode, which rebuilds the engine). The agent reads `hints.md` per Turn, so it sees
a hints change on the next question.

---

## 4. `schema_mappings.json`

A JSON object mapping a Thai term to a list of English name fragments:

```json
{
  "นักเรียน": ["student_term", "student_person"],
  "โรงเรียน": ["schools"],
  "ปีการศึกษา": ["academic_year", "school_terms"]
}
```

`SchemaRAG` case-insensitively matches each fragment against table names and
column names, then appends the Thai terms to that table's searchable
description. This is a **recall aid** for pruned schema retrieval, not an
authoritative mapping — it does not validate that a table exists.

Used only when `SCHEMA_STRATEGY=pruned`. Changing this file requires a **restart**
(the mappings are loaded when `SchemaRAG` is constructed) and a forced re-index:
either `rm -rf schema_rag_db` before the restart, or restart and then call
`POST /api/admin/refresh-schema`. Re-indexing without a restart keeps the old
mappings in memory.

---

## 5. `table_notes.json`

Curated table meaning and population for the agent's `describe_table` tool:

```json
{
  "_comment": "Free-form note for maintainers; ignored by code.",
  "_global": {
    "blocked_column_pattern": "(student|teacher)_?name|citizen|phone|email"
  },
  "tables": {
    "schools": {
      "meaning": "One row per school.",
      "population": "All schools, including inactive ones.",
      "key_columns": ["id", "name", "province", "school_status"],
      "joins": ["schools.id = student_term.\"SchoolID_Onec\""],
      "notes": ["No deleted_at column — do not add a deleted_at filter."]
    }
  }
}
```

- `_global.blocked_column_pattern` is merged with the built-in PII pattern. It
  guards `sample_values` and the Turn digest; it is **not** a substitute for
  database permissions.
- `tables.<name>` supports `meaning`, `population`, `key_columns`, `joins` and
  `notes`. Missing entries degrade to the raw column list.
- Never put real data values, names or identifiers in this file — only curated
  metadata.
- `load_table_notes` is cached per process; restart the service after editing.

---

## 6. Adding a new Datasource — checklist

1. **Create the profile** under `profiles/<name>/` with `hints.md` and
   `examples.json`. Start from the real schema, not from `receipt_sample` (the
demo wizard in section 7 can draft the minimum pass for you).
2. **Point the service at the datasource:** set `DATABASE_URL` to a read-only
   connection and `DOMAIN_PROFILE=<name>`. There is no runtime connection flow.
3. **Write the dialect hints** for the engine you are actually using. Do not mix
   MySQL/SQLite functions into a PostgreSQL profile.
4. **Build the Example set** against the live database. Every result SQL must
   execute and return the expected grain; verify with the real datasource.
5. **Add optional knowledge:** Thai mappings for the terms users actually type,
   and `table_notes.json` for the tables the agent is likely to confuse.
6. **Register the profile in the conformance test:** add its name to
   `SUPPORTED_PROFILES` in `tests/unit/test_profiles.py`, then run:
   ```bash
   uv run --extra dev pytest tests/unit/test_profiles.py -q
   ```
   The test checks required files, example ids, dialect values, SQL parseability,
   schema mappings and table-note structure.
7. **Rebuild the retrieval stores** for a clean run:
   ```bash
   rm -rf rag_db schema_rag_db
   ./start_server.sh
   ```
   Example edits alone are synced at startup; this wipe is for a clean rebuild
   after schema-format or mapping changes.
8. **Run evaluation.** Add a Golden set for the new domain and follow
   [`eval/STS_EVAL.md`](../../eval/STS_EVAL.md). A profile is not "supported"
   until it has been measured, not merely loaded.
9. **Update the README** supported-datasource table and, if this becomes the
   active profile, the deployment docs.

### Restart rules

- `DOMAIN_PROFILE` is read at process start; switching profiles requires a
  restart. The exception is demo mode, where the page's **🔌 Connect** tab can
  switch profile at runtime — that rebuilds the NLPEngine (ADR 0013).
- `start_server.sh --reload` watches `api/` and `core/`, **not** `profiles/`.
  Editing a profile file does not hot-reload it.
- Example changes sync automatically at the next startup; the one-shot prompt's
  `hints.md` and `table_notes.json` require a restart because they are
  read/cached at engine construction. The conversational agent reads `hints.md`
  per Turn, so it picks up an edit on the next question.

---

## 7. Creating a profile from the demo (Profile wizard)

`./start_demo.sh` serves a Profile wizard that writes an **ordinary** profile:
the output is the same five-file artifact described above, under
`profiles/<name>/`, so the same loader, conformance test, diff review and git
commit apply. There is no second format and no draft tier. The endpoints are
mounted only with the demo routes (`APP_MODE=demo`, or `auto` without an API
key); a service deployment returns `404`.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/demo/profile/draft` | Body `{ question, sql? }`. Drafts one example: generates SQL through the service's own path, or executes the supplied corrected SQL. Read-only and LIMIT-clamped. Response `{ status, dialect, sql, rows, row_count, category, error }`. Nothing is written. |
| `POST` | `/api/demo/profile/save` | Body `{ name, hints, schema_mappings, table_notes, examples, overwrite }`. Writes the profile and returns `{ profile, coverage }`. |

A save body looks like:

```json
{
  "name": "my_school",
  "overwrite": false,
  "hints": "ปีการศึกษามีสองภาค …",
  "schema_mappings": { "นักเรียน": ["students"] },
  "table_notes": {
    "students": {
      "meaning": "หนึ่งแถวต่อนักเรียนหนึ่งคน",
      "population": "เฉพาะนักเรียนที่ยังมีสถานะใช้งาน"
    }
  },
  "examples": [
    { "question": "จำนวนนักเรียนทั้งหมด", "sql": "SELECT COUNT(*) FROM students",
      "retrieval_tags": ["นับนักเรียน"], "grain": "หนึ่งแถวต่อจำนวนนักเรียน" },
    { "question": "ขอรายชื่อนักเรียนทุกคน",
      "expected_answer_type": "refusal",
      "expected_message": "ขออภัยครับ ระบบให้เฉพาะข้อมูลเชิงสถิติ" }
  ]
}
```

The wizard collects this in six screens: name, Thai terms, example questions,
business rules, per-table notes and clarification/refusal exemplars. Screens 2,
4, 5 and 6 may be skipped; only a valid name is required, and a result example
counts only once its SQL has run.

The writer enforces the contract:

- **Name**: lowercase `a-z`, `0-9`, `-` and `_`, at most 64 characters; path
  separators and dots are refused, so a name cannot escape `profiles/`.
- **No silent overwrite**: an existing profile is refused (`409`) unless the
  request sets `overwrite: true`.
- **Only SQL that ran is saved**: every result example is executed read-only
  before any file is written. One failure refuses the whole save (`400`) and
  leaves the tree untouched.
- **Always selectable**: `examples.json` is written even when the visitor
  supplied no examples — that file is what makes a profile appear in the demo.
- **The service supplies what the visitor should not know**: `id`
  (`wiz-001`…, stable for the same example order), `dialect` from the
  connection (`sqlite`, `postgresql` or `mysql`, in contract spelling) and
  `category` from the drafted SQL's shape. `retrieval_tags` and `grain` remain
  optional visitor input.
- **Non-SQL exemplars keep the established shape**: an example with
  `expected_answer_type` (`clarification` or `refusal`) and `expected_message`
  is written with an empty `sql`, `category` `<type>_exemplar`, and is never
  executed. Supplying both an answer type and SQL is refused, as is an answer
  type without a message.
- **Table notes are complete or absent**: `table_notes` entries need both
  `meaning` and `population` (the file contract in §5); a half-filled entry is
  refused. The section may be omitted entirely, and an overwrite that omits it
  removes the previous `table_notes.json` rather than keeping stale text.
- **Coverage, not a tier**: the response reports which sections are filled
  (`hints`, `examples`, `exemplars`, `schema_mappings`, `table_notes`) and the
  profile is used as-is.

A saved profile appears in `GET /api/demo/state` immediately and can be switched
to at runtime with `POST /api/demo/connect` (ADR 0013) — no restart. In any other
deployment it is selected at startup by `DOMAIN_PROFILE`, like any profile.
Editing an existing profile through the UI stays out of scope — the files are the
editing surface — and a new run can only replace a profile with an explicit
overwrite. The wizard covers both passes in one sitting: screens 1–4 are the
minimum, screens 5–6 add `table_notes.json` and the non-SQL exemplars.

---

## 8. Known portability gaps

These are the places where STS still leaks into core code. They do not block
using the profile mechanism today, but they must be addressed before a second
real datasource is called supported:

- `core/domain/schema_utils.py` — `_DENYLIST_EXACT` lists STS table names
  (`task_links`, `classroom_attendance_links`, `pii_export_requests`, …). Review
  this list for every new datasource.
- `profiles/receipt_sample/` — legacy corpus, not contract-complete; do not use
  it as the reference implementation.
- `profiles/sts/table_notes.json` covers the analytically important tables, not
  all 100+; a new profile needs its own curation.

See [ADR 0011](../adr/0011-one-datasource-per-deployment-profiles-as-seam.md)
for why one deployment serves one datasource, and
[ADR 0002](../adr/0002-sts-guide-tier-1-adoption.md) for the STS limitations
that remain out of scope.

---

## 9. References

- [ADR 0002 — STS guide Tier 1 adoption](../adr/0002-sts-guide-tier-1-adoption.md)
- [ADR 0006 — stateless conversational sessions](../adr/0006-conversational-agent-stateless-sessions.md)
- [ADR 0010 — agent mechanical guards and analysis](../adr/0010-agent-mechanical-guards-and-analysis.md)
- [ADR 0011 — one datasource per deployment](../adr/0011-one-datasource-per-deployment-profiles-as-seam.md)
- [STS Text-to-SQL Guide](TEXT_TO_SQL_STS_GUIDE.md)
- [STS evaluation](../../eval/STS_EVAL.md)
