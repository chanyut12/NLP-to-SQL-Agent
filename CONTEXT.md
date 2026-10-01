# Context: Thai NLP-to-SQL Agent

A service that turns a natural-language question (Thai) into SQL, runs it against a
relational database, and returns the result together with a suggested chart.

## Glossary

### Consumer
An external application that calls this service's API. Distinct from the Demo UI. A
Consumer renders results in its own pages using its own components.

### Demo UI
The chat page bundled in `web/`, served by the service itself. A local development
aid for eyeballing what the service returns — not a Consumer and not shipped to
production. It is served only when the API key is unset; once a key is required, the
page is not mounted and a Consumer is the only way in.

### Export
Delivering the result of one question to a Consumer as a structured JSON payload:
the generated **SQL**, the **result rows**, the **column metadata**, a **result
summary**, and a **visualization config**. The service does not render anything
visual for a Consumer; the Consumer draws the table and chart itself, using the
metadata and summary to format and headline the result.

### Column metadata
Per-column descriptors the service attaches to a result: the column name, a coarse
**semantic type** (`count`, `number`, `percent`, `gpa`, `date`, `id`, `category`,
`name`, `text`), and whether the column is numeric. Derived deterministically from the
result's data types and column names — never from a language model. Advisory: a
Consumer uses it to right-align and format values (thousands separators, a `%`
suffix, date trimming) but may ignore it.

### Result summary
A small digest of one result the service computes from the returned rows: the total
row count, whether the row cap truncated the set, and for each numeric column its
sum / min / max / mean. When a result is a single row with a single numeric column,
it is also flagged as a **single-value answer** so a Consumer can headline the number
instead of drawing a one-cell table.### Question
A single natural-language request from an end user, expressed in Thai, asked within one
Turn of a Session. A Question may rely on earlier Turns of the same Session — follow-ups
and references such as "โรงเรียนเดียวกัน" — and is interpreted with that context.

### Answer
What the service returns for one Question: either a **Result** (SQL with its result rows,
column metadata, summary and visualization config — see Export), a **Clarification**, or
a **Refusal**.

### Entity label
The human-readable name of a non-person entity the result is grouped by (a school, a
classroom, a product) — as opposed to its identifier. The service treats the Entity
label as part of the Answer itself, not decoration: whenever a Question asks for a
count or measure per entity, the result carries the entity's label column alongside
(or instead of) its id, because a result the reader cannot parse is not a good answer
even when the numbers are right. Person names stay outside this guarantee — they are
personal data and belong to the Refusal rules. When both the id and the label of the
same entity appear in one result, the id is bookkeeping: the Consumer may collapse it
and show the label alone.

### Clarification
An Answer that asks the end user to narrow or restate the Question instead of producing
SQL.

### Refusal
An Answer that declines the Question — outside the Datasource's scope or disallowed
content — stating the reason instead of producing SQL. A Question that is both ambiguous
and refusal-eligible always gets a Refusal: the refusal check precedes the ambiguity
check, so Clarification can never be used to negotiate disallowed content.

### Session
An ordered conversation between an end user and the service, made of one or more Turns.
The service keeps no memory of a Session between requests: the Consumer owns the Session
and supplies its history with every call. Distinct from the Log store, which is the
record of answered Questions, not live conversation state.

### Turn
One exchange inside a Session: the end user's Question and the service's answer to it.
The service answers the current Turn; earlier Turns are context it may use to interpret
that Question.

### Progress event
A mid-Turn announcement, streamed to the Consumer while the service is still working on
the current Turn, telling the end user what the agent is doing right now (which tool it
is running, what it has produced so far). A Progress event is not part of the Session —
it is never replayed into history — and it says nothing the final answer does not also
say; it only moves what the final answer will contain into the waiting time. The final
answer remains the single source of truth for the Turn.

### Visualization config
The service's recommendation for how to chart a result: a chart type, which columns
map to which axis / series role, a chart title and axis labels, the list of
alternative chart types the Consumer may offer, a plain-language reason for the
choice, and — for a high-cardinality category axis — a `top_n` cut beyond which the
remaining categories should be folded into one "other" slice. Advisory only — the
Consumer may ignore any of it.

Axis-selection language (part of the config's meaning, not implementation):
- An **axis label column** is a column that tells the reader *what each mark is*.
  A column whose semantic type is `id` can never serve this role — an identifier
  distinguishes rows but carries no meaning to a chart reader.
- When a result carries an **identifier–name pair** (the id and the human-readable
  name of the same entity), the name is the axis label column; the id is bookkeeping.
- If a result offers no axis label column at all, the result is **not chartable**
  regardless of how many numeric columns it has.

### Datasource
The single relational database this service answers questions against. The service
connects to it directly through a read-only account: it may run `SELECT` and read
schema metadata, nothing else. The Datasource is owned and operated by the Consumer;
the service is given connection details, not administrative control.

The target Datasource is **STS** (Student Tracking System) — a PostgreSQL database
of schools, enrollment, attendance, student risk profiles, follow-up cases, and
assistance tasks (100+ tables). Its authoritative semantics — table grain, canonical
join paths, status dictionaries, the "current student" rule, attendance
source-of-truth, academic-year vs calendar-year — are defined in
`docs/guides/TEXT_TO_SQL_STS_GUIDE.md`. The bundled `classicmodels` / receipts schema is only
sample data from earlier development.

STS holds real personal data (names, citizen IDs, contacts, addresses, home-visit
notes, auth tokens). This project answers **aggregate analytical questions** and the
prompt forbids selecting those columns, but the full validation / scope-enforcement /
PII-gating gateway described in the guide is **out of scope** here and recorded as a
known limitation. See `docs/adr/0002-sts-guide-tier-1-adoption.md`.

### Domain profile
The bundle of Datasource-specific knowledge the service needs to answer questions
well against one Datasource: the Thai-term-to-column and semantic hints injected into
the prompt, the Example set, the retrieval-store namespaces, and the query-log
stream. Selected by a single config value; swapping the Datasource means switching
profile, not editing code. The active profile is `sts`; the prior receipts knowledge
is retained as an inactive profile.

### Log store
The record of every answered Question — Thai text, generated SQL, outcome, timing,
retry count, structural metrics. The service does not own it: every response carries
these fields in the envelope and the Consumer persists them. The service itself holds
no write credentials to any database; its Datasource connection is strictly read-only.
The bundled demo UI's local file logs are for development only, not this record.

### Example set
The curated file of Thai-question / SQL pairs used for few-shot retrieval, belonging
to one Domain profile, balanced across the same Category buckets as the Golden set —
surplus examples of an over-represented shape are retired to the Example archive
rather than left to dominate retrieval. It also carries a small fixed block of
Clarification and Refusal exemplars so the agent's non-SQL answers stay in one format.
Swapping the profile means swapping the Example set and rebuilding the retrieval stores.

### Example archive
Retired examples kept on disk but never loaded by retrieval — how an over-represented
shape leaves the corpus without being destroyed.

### Retrieval store
A local vector index the service builds from the Example set (`rag_db/`) and from the
Datasource schema (`schema_rag_db/`). Derived data, not source of truth — it is wiped
and rebuilt whenever the Example set or the Datasource schema changes.### Category bucket
The coarse class of SQL shape — what the query has to do, not which tables it touches —
shared as the single primary distribution axis by both the Golden set and the Example
set, so per-bucket evaluation numbers mean the same thing for questions and for
few-shot fuel.

### Golden set
A fixed list of Thai questions paired with a gold SQL and a Category bucket, held per
Domain profile, that an Evaluation run replays to score the service. The set is
quota-balanced: every Category bucket holds the same number of questions, plus a fixed
block of ambiguity and refusal questions whose expected outcome is an Answer type —
Clarification or Refusal — rather than rows. The gold SQL defines the
expected result, not the expected SQL text — two different queries that return the
same rows both pass. Kept strictly disjoint from the Example set so retrieval cannot
hand the model its own answer. Each question is tagged with how it was sourced:
`held_out` (pulled out of the corpus and removed from retrieval), `paraphrase`
(reworded / typo'd / code-switched variant of a question still in the corpus), or
`novel` (a metric/grain combination the corpus does not contain).

### Evaluation run
An offline batch that answers every Golden-set question and reports, broken down by
source tag and by category: how often SQL was produced, how often it executed, how
often the result matched the gold result, how often that happened on the first try
with no self-correction, whether the row grain was right (no duplicate
amplification), the latency distribution,and a breakdown of failure kinds. Separate from the Log store, which records live traffic.
Clarifications and Refusals are first-class scored outcomes, not failures — ambiguous and
out-of-scope questions expect them.
