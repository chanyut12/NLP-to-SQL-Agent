---
status: accepted
---

# The service holds its own read-only connection to the Datasource and executes SQL itself

## Context

The NLP-to-SQL engine is being turned into a microservice that a separate stack
(React + NestJS + PostgreSQL) calls. The NestJS backend already owns the database,
so the obvious split is: this service generates SQL from a Thai question and hands
the string back for NestJS to run. That would keep database credentials in one
place and make this service a pure, stateless text transformer.

We chose the opposite: the service is given its own PostgreSQL connection — a
dedicated **read-only** role — and runs the query itself before responding.

## Why

The value of the engine is not the raw SQL string; it is the answer. Three
behaviours depend on executing the query inside the service:

1. **Self-correction.** `core/services/engine.py` runs the generated SQL, and when
   PostgreSQL rejects it (unknown column, bad join), it feeds the error back to the
   LLM and retries. A generate-only service cannot see that error without a second
   round-trip per attempt, and NestJS would have to re-implement the retry loop.
2. **Visualization recommendation.** `core/viz/viz_recommender.py` inspects the
   actual result DataFrame (column types, cardinality, row count) to pick a chart.
   Column names alone are not enough.
3. **A single, testable contract.** One request in, one answered result out — SQL,
   rows, and a chart suggestion together — is far simpler for NestJS to consume and
   for us to evaluate offline against a golden set.

## Consequences

- The service needs network reach to the `sts` database and a PostgreSQL role that
  can only `SELECT` and read catalog metadata. Provisioning that role is a
  deployment prerequisite, not application code.
- The service is **not** a security boundary. It has no row-level scope
  enforcement, no PII gating, and its read-only role can see the OLTP tables. That
  is acceptable only because this is a research prototype answering aggregate
  questions; see `0002-sts-guide-tier-1-adoption.md`.
- The mutable global connection state and `.last_connection.json` are removed. The
  connection is fixed at deploy time from `DATABASE_URL`, which makes the service
  effectively stateless per request. `/connect` survives only as a no-op shim so the
  bundled demo UI's button keeps working; it changes nothing.
- If STS ever needs real multi-tenant scope or PII controls, this decision is
  revisited: execution would move behind the NestJS-owned gateway described in
  `TEXT_TO_SQL_STS_GUIDE.md` and this service would become generate-only.
