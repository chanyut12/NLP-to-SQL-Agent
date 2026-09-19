# Semantic-type axis selection: ids never label a chart axis

The demo showed bar/pie charts whose axis was a meaningless id column (e.g.
`student_id`) while the entity's human-readable name column sat unused in the same
result. Reproduced deterministically: the rule-based recommender buckets `id` /
`no` / `number` / `code` name fragments into the same "dimension" pile as dates and
bubbles the id to the front of the category-column queue, so every downstream
selection path picks it as the axis. The result is a chart that answers "which row
number is biggest" — the exact presentation failure the demo is judged on.

Decision, as a direct extension of ADR 0004's closed semantic-type vocabulary:

1. **An axis label column must be meaningful to a reader.** A column typed `id`
   never labels an axis, never heads a legend, never feeds a chart title. This holds
   regardless of chart type, user's dropdown choice, or keyword priority.
2. **Identifier–name pairs resolve to the name.** When a result carries an id and
   the readable name of the same entity, the name becomes the axis label column.
   Candidate order: `name` → `category` → non-id/non-date `text`.
3. **No axis label column ⇒ not chartable.** A result of ids plus numbers renders
   as a table with a plain-language reason ("no name column to label an axis"),
   instead of a chart with numeric noise for labels. The agent can then suggest
   asking for the name via a join — refusing to chart beats charting garbage.
4. **The rule is a guard, not a suggestion path.** It applies *after* any
   recommendation, including the (currently disabled) LLM-based recommender — a
   model may propose an id axis and the guard will still correct it. Determinism
   stays with semantic types, not with the recommender that ran.

Why refuse-to-chart instead of id-labelled charts: a chart is a claim about
entities; labelling it with surrogate keys asserts structure the reader cannot use.
Why a name lookup against the Datasource was rejected: the visualization layer
would need to run its own SQL — new latency, a second failure mode, and a boundary
violation (recommenders describe results; they do not query).

Consequences: some numeric results that used to render a chart now render a table
(the id-only case) — a deliberate regression toward honesty. Consumers get the
behaviour for free through the existing envelope (`chart_type: table` + reason);
no contract change, but eval expectations and the demo implicitly tighten: no
screenshot of this system should ever show an id on an axis. `top_n` folding
continues to apply on top of whatever axis label column was chosen.
