# Conversational agent with Consumer-owned sessions

The professor's critique — "this is a pipeline, not an agent" — is structurally correct:
the engine is a one-shot chain with an execute-retry loop. We decided to become a true
conversational agent (multi-turn Session/Turn, Clarification and Refusal as first-class
Answers) while keeping the service **stateless**: the Consumer owns the Session and
supplies structured prior-Turn history with every request to `POST /api/query`. The
agent decides within a Turn via a function-calling loop over three tools
(`get_schema`, `run_sql` with safety validation inside, `final_answer`), capped at
8 steps; exhausting the budget is a hard failure (`STEP_BUDGET_EXCEEDED`), never a
best-effort SQL.

Why stateless even though the service is now an agent: ADR 0001 gives the service no
write credentials to any database, and ADR 0005 runs it on-demand behind a tunnel where
restarts are routine — server-side session memory would be both a policy violation and
unreliable. The Consumer (NestJS) already persists query logs, so history round-trips
through data it owns anyway. Refusal is always checked before Clarification so the
clarify path cannot negotiate disallowed (PII) content.

Consequences: the envelope gains `answer_type` / `message` / `steps_used` and a new
error code; the Golden set gains `ambiguous` and `deny` categories and must be
re-baselined once; "always emits SQL" no longer holds. Backward compatible: omitting
`history` reproduces the old one-shot behaviour.
