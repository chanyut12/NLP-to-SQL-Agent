# Context: Thai NLP-to-SQL Agent

A service that turns a natural-language question (Thai) into SQL, runs it against a
relational database, and returns the result together with a suggested chart.

## Glossary

### Consumer
An external application that calls this service's API. Distinct from the built-in
web UI in `web/`, which is one specific client. A Consumer renders results in its
own pages using its own components.

### Export
Delivering the result of one question to a Consumer as a structured JSON payload:
the generated **SQL**, the **result rows**, and a **visualization config** (chart
type + column roles). The service does not render anything visual for a Consumer;
the Consumer draws the table and chart itself.

### Question
A single natural-language request from an end user, expressed in Thai, that the
service answers with one SQL statement and one result set.

### Visualization config
The service's recommendation for how to chart a result: a chart type plus which
columns map to which axis / series role. Advisory only — the Consumer may ignore it.

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
`TEXT_TO_SQL_STS_GUIDE.md`. The bundled `classicmodels` / receipts schema is only
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
to one Domain profile. Swapping the profile means swapping the Example set and
rebuilding the retrieval stores.

### Retrieval store
A local vector index the service builds from the Example set (`rag_db/`) and from the
Datasource schema (`schema_rag_db/`). Derived data, not source of truth — it is wiped
and rebuilt whenever the Example set or the Datasource schema changes.

### Golden set
A fixed list of Thai questions paired with a gold SQL and a category, held per Domain
profile, that an Evaluation run replays to score the service. The gold SQL defines the
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
amplification), the latency distribution, and a breakdown of failure kinds. Separate
from the Log store, which records live traffic. Clarify / deny / adversarial cases
are not scored while the service always emits SQL — that is Tier-2 work.
