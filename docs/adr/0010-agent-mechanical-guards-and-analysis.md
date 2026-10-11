# Agent behaviour moves from prompt rules to mechanical guards, and gains analysis

A live conversation (Oct 2026) exposed four failures in the agent loop that no single
prompt rule fixes: a follow-up ("ช่วยกรองเฉพาะ X") resolved against the wrong earlier
Turn; a successful query returning 0 rows sent the model probing 20+ run_sql calls
until it timed out; a final message quoted a figure from a different table and
population than its own rows; and "สาเหตุของความเสี่ยง" was answered from
`case_risk_signals` (11 signals, 7 cases) although the risk the user meant lives in
`student_risk_profiles` (610 at-risk students, drivers are attendance columns).
We patched the first two with prompt rules 8–10, which is whack-a-mole: the prompt
already carries ten rules, each born from one bug.

Decision — enforce in code what a prompt can only request, and give the agent the
knowledge and the shape it lacks:

1. **History carries meaning, not only SQL.** Each Turn's envelope exposes a
   deterministic `turn_digest` (population, measure, filters, top rows; never an LLM
   call, in the spirit of ADR 0004). The Consumer replays it in `history`; absent →
   fall back to today's SQL-only block. The service stays stateless (ADR 0006).
2. **Loop guards are mechanical.** Duplicate SQL is answered from the previous result;
   an executed query with 0 rows is steered to `final_answer`; the model is told when
   two steps remain. These replace prompt rules 8 and the "stay on the previous Turn"
   rule 9.
3. **Grounding check.** After `final_answer(result)`, numbers in the message must
   appear in (or be trivially derived from) this Turn's rows; otherwise one repair
   step, then a deterministic fallback sentence. Replaces prompt rule 10.
4. **Data knowledge as tools.** `describe_table` (meaning, **population**, join path,
   from `profiles/<profile>/table_notes.json`) and `sample_values` (real distinct
   values, denylist-checked) so the model stops guessing which table means what.
5. **Analysis shape.** A `plan` tool and an optional envelope `analysis`
   (`headline`, `findings[]`, `caveats[]`) let one Turn run several queries and
   synthesise, stating the limits of the data. Backward compatible: legacy fields
   unchanged.

## Considered options

- *More prompt rules* — rejected: unbounded, order-sensitive, model-specific (the
  prompt was tuned on gpt-4o-mini and breaks differently on other providers).
- *LLM-written history summaries* — rejected: an unverified model output feeding the
  next Turn's prompt compounds the grounding problem.
- *Server-side sessions* — rejected by ADR 0001/0006.

## Consequences

- Envelope and `PriorTurn` gain optional fields; the NestJS Consumer must pass
  `digest` back (`docs/INTEGRATION.md` updated with ticket 1).
- Regression fixtures are real multi-turn conversations from the query log
  (`eval/`), starting with the Oct 2026 Bangkok/Nakhon Pathom case.
- `AGENT_STEP_BUDGET` stays 8 by default; the guards, not a larger budget, bound
  the loop.
