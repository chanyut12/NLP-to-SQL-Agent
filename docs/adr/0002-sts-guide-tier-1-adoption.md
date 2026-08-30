---
status: accepted
---

# Adopt only the prompt-and-examples layer of TEXT_TO_SQL_STS_GUIDE.md

## Context

A collaborator supplied `TEXT_TO_SQL_STS_GUIDE.md`, a full implementation contract
for running Text-to-SQL against the real STS (Student Tracking System) PostgreSQL
database. It specifies far more than a prompt: a cheap routing model, a structured
`decision: query | clarify | deny` output, a 23-step deterministic AST validation
pipeline, server-owned scope rewriting on every query branch (school / area /
grade / room / own-only), PII classification with capability gating, a curated
`text_to_sql` schema of views behind a least-privilege role, small-group
suppression, and snapshot-freshness metadata. The guide itself states that the
security pieces are PDPA / data-owner decisions and production blockers, and that
nothing in it is deployable as written.

This project's goal is narrower: expose the existing engine as a microservice, wire
it to the STS schema, integrate it with a deployed app, and measure its accuracy
for a research write-up.

We adopt **Tier 1**: sections 4–7, 10, and 13 of the guide — the PostgreSQL-only
dialect rules, the STS semantic model (table grain, canonical join paths, status
dictionaries, the current-student rule, attendance source-of-truth, academic vs
calendar year), the Thai intent hints, and the nine worked SQL examples. These
become the `sts` Domain profile (`profiles/sts/hints.md` + `profiles/sts/examples.json`).
The MySQL/SQLite hints and the receipts vocabulary listed in the guide's Appendix A
are deleted from the prompt.

Everything else in the guide — routing, structured decision output, the AST
validator, scope rewriting, PII gating, curated views, capability matrix,
suppression — is deliberately **out of scope**.

## Why

- Tier 1 is where almost all the accuracy comes from for a prototype, and it is
  days of work rather than months.
- The scope / PII / gateway machinery only earns its cost against a real
  multi-tenant production deployment with authenticated users. This service has one
  trusted caller (the NestJS backend) hitting a local database, and answers
  aggregate questions.
- Building a half-version of the security model would be worse than none — it would
  look like a boundary without being one.

## Consequences

These limitations are real and must be stated plainly in the README and the thesis:

- No row-level scope enforcement. A question is answered against the whole
  database, not the asker's permitted slice.
- No PII classification or capability gating. STS column names (including
  `citizen_id`, address, contact, token columns) and the user's question text are
  sent to OpenAI as part of the prompt. The prompt instructs the model not to
  *select* PII columns, but nothing enforces it.
- Validation is `sqlglot` parsing plus prompt rules and a read-only role — not the
  guide's deterministic AST pipeline.
- The read-only role sees the OLTP tables directly; there is no curated
  `text_to_sql` view boundary.
- No small-group suppression and no `data_as_of` freshness signal on
  snapshot-derived answers (e.g. `student_risk_profiles`).

Moving toward the full guide later is additive: the profile content stays, and the
gateway is built in NestJS in front of a generate-only version of this service.
