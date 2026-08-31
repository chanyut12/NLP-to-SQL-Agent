---
status: accepted
---

# Column metadata and the result summary are derived deterministically, never by an LLM

## Context

The query envelope (see `0003-query-response-contract.md`) is being widened so a
Consumer can format and headline a result without re-deriving structure from the raw
rows. Three new advisory blocks are added:

- **`columns[].semantic_type`** — a coarse label per column: `count`, `number`,
  `percent`, `gpa`, `date`, `id`, `category`, `name`, `text`. Plus
  `columns[].numeric: bool`. (`count` = integer quantity; `number` = a non-integer
  numeric with no clearer label, e.g. an average.)
- **`summary`** — `row_count`, `truncated`, per-numeric-column `{sum, min, max, mean}`,
  and a `single_value` flag when the result is one row × one numeric column.
- **`visualization`** gains `title`, `x_label`, `y_label`, `reason`, and `top_n`.

There were three ways to produce the semantic labels and the chart title/labels:

1. **Deterministic post-processing** of the result DataFrame — pandas dtypes for
   numeric/temporal/text, regex on column names for the finer label; title is the
   user's question, axis labels are the humanised column names.
2. **A second LLM pass** (or a widened generation prompt) that annotates each column
   and writes a natural-language chart title.
3. A hybrid: deterministic labels, LLM only for the chart title.

We chose **(1), fully deterministic**.

## Why

- **No added latency or cost.** The engine already holds the result as a DataFrame
  and already runs the rule-based viz recommender on it. Column typing and the
  summary are a few milliseconds of pandas on data that is in memory. An LLM pass
  adds 1–3 s and ~300 output tokens to every single query.
- **Deterministic, so it is testable and stable.** `tests/unit/test_column_meta.py`
  can assert exact `semantic_type` values for fixed inputs. The evaluation harness
  (`0003`, the golden-set runner) stays reproducible — an LLM writing titles and
  labels would make each run drift.
- **The labels are advisory.** A Consumer uses `semantic_type` to right-align a
  column and add a `%` suffix. A wrong guess (a `late_count` column mislabelled
  `category`) degrades formatting, it does not corrupt the answer. That risk does
  not justify an LLM call.
- **The chart title the LLM would write is not worth the round trip.** "อัตราการมา
  เรียนรายวัน" as a title carries no information the question and the axis labels do
  not already carry.

## Consequences

- `semantic_type` is a closed vocabulary that Consumers will branch on. Adding or
  renaming a value is a contract change and belongs in a revision of this ADR.
- Typing is heuristic: it keys off column-name fragments (`rate`/`pct` → `percent`,
  `gpa`/`gpax` → `gpa`, `_id`/`uuid` → `id`, `count`/`total`/`จำนวน` → `count`) and
  pandas dtype. A query that aliases columns oddly gets `text`/`category` fallback
  labels. The SQL-generation prompt already tends to produce descriptive aliases,
  which is what makes the heuristic workable.
- If a Consumer ever needs precise SQL types, that is a separate feature: thread the
  DB-API cursor `description` (or SQLAlchemy result column types) through instead of
  the DataFrame. Not done now because no Consumer needs it and the DataFrame is the
  natural hand-off point.
- The `ENABLE_INTELLIGENT_VIZ` LLM path in `viz_recommender.py` is unaffected and
  stays off by default; this ADR only governs the always-on metadata.
