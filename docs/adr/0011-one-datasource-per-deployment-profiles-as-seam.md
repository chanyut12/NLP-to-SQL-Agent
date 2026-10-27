---
status: accepted
---

# One Datasource per deployment; Domain profiles are the portability seam

## Context

The README advertised a multi-database application with a UI connection flow,
but the deployed service has had a single fixed Datasource since ADR 0001:
`DATABASE_URL` is read once at startup, there is no `/connect` endpoint, and the
`dialect` field in a request is ignored. At the same time, the long-term goal is
to answer questions against other databases.

Two concerns are easy to conflate:

- **Database-engine portability** — PostgreSQL now, perhaps MySQL or SQLite later.
- **Domain portability** — a different schema, vocabulary and business rules.

A runtime connection switcher would address neither cleanly, and would undermine
the read-only role, schema cache and retrieval indexes that the current safety
and accuracy claims depend on.

## Decision

1. **One service instance answers against exactly one Datasource**, fixed at
   deploy time by `DATABASE_URL`. Multiple datasources mean multiple deployments,
   each with its own connection and `DOMAIN_PROFILE` — not runtime switching and
   not a `/connect` endpoint.
2. **Datasource portability goes through Domain profiles** (`profiles/<name>/`).
   The Example set, prompt hints, Thai schema mappings and `describe_table`
   notes are the only domain-specific inputs. A new database is a new profile
   plus a dialect/evaluation pass, not a code branch.
3. **Today `sts` (PostgreSQL) is the only supported profile.**
   `receipt_sample` is a legacy development sample, not a supported datasource.
4. **Runtime multi-tenancy is out of scope.** One instance serving several
   databases, or several permission scopes, needs its own authentication and
   scope design and a separate ADR.

## Considered options

- **Runtime `/connect` with per-request credentials.** Rejected: it would make
  the service a database proxy, multiply the credential-handling and PII surface,
  and invalidate the single read-only role, schema cache and per-profile vector
  stores. The Consumer already owns the datasource; it should deploy a service
  instance for it.
- **A generic schema introspector with no profile.** Rejected: it removes the
  domain knowledge (grain, join paths, status dictionaries) that produces most of
  the accuracy, and would still need per-domain examples and evaluation.
- **One deployment per datasource with a profile seam.** Chosen: it keeps the
  current safety model intact, makes each datasource independently testable, and
  gives new databases a concrete, reviewable unit of work.

## Consequences

- `README.md` must state the one-datasource constraint and list supported
  profiles; it must not advertise `/connect` or multi-database switching.
- A new datasource is complete only when its profile passes the profile
  conformance tests and an evaluation run. Copying the loader files is not
  enough; see `docs/guides/PROFILES.md`.
- The read-only role, schema cache and RAG stores stay keyed to one datasource,
  which is what makes the safety and accuracy claims checkable.
- **Known debt:** STS assumptions still live in core code — the denylist table
  names in `core/domain/schema_utils.py` and the Thai domain examples in
  `core/services/agent.py`. They must move into the profile (or a generic hook)
  when the second real datasource lands. They are recorded here rather than
  refactored speculatively.
