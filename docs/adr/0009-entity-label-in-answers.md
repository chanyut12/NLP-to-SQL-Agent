# Entity label in answers: id-only results are not good answers

Live query logs (554 successful questions) showed two recurring presentation
failures, both caused by the generated SQL, not by the presentation layer:

- **76 questions (14%)** selected an entity id *alongside* a readable name
  (`school_id` next to `school_name`) — readable, but the id is noise in every
  table a human reads.
- **5 questions** selected *only* the id (`cases.school_id, COUNT(...)`) — the
  result is unreadable: "which school is 3?" The same question asked again with
  "โดยอยากให้แสดงชื่อโรง" returned `school.name` — proving the model can comply
  but does not by default.

Root causes, verified in code: the Example set teaches the pattern (13 of the
first 20 examples SELECT `_id`), and the system prompt carries no rule about
result columns (its only column rule is the PII refusal). Meanwhile 14 of 28
gold SQLs already select id + name together, so a blanket "never select ids"
would tank strict EX against our own benchmark.

Decision — one contract, applied at three layers at once:

1. **The contract (glossary: Entity label).** A result grouped by a non-person
   entity must carry that entity's readable label column, not its id alone.
   When id and label both appear, the id is bookkeeping the Consumer may
   collapse. Person names stay out of scope (PII refusal rules).
2. **Generation.** System prompt gains a default-with-exception rule ("per-entity
   results select the entity's label column; select ids only when the user asks
   for the code itself") and the Example set's id-only SELECT patterns are
   rewritten to include the label — prompt and corpus changed in the same pass
   because they point the same direction and RAG is the strongest lever
   (ADR 0007 sweep: 3% → 47%).
3. **Presentation.** Deterministic display rule extending ADR 0008: when a
   result carries an identifier–name pair, the Consumer-facing column metadata
   marks the id as collapsible so Consumers (and the demo UI) can show the
   label alone. Nothing is dropped from the payload.

And one correction the contract forces: the 5 gold SQLs that select ids only
are updated to carry the entity label (old versions archived), because under
the new contract a *compliant* model answer would otherwise lose strict EX
against a worse-than-contract gold. The other 23 gold SQLs are untouched.

Corrections found while implementing (recorded so the drift is visible):

- An initial approximate count said 6 id-only golds; exact output-column
  analysis showed 5 (the sixth already carried `grade_label`).
- Two corpus examples referenced `tasks.school_id`, a column the live schema
  does not have (`tasks.target_school_id`) — they were not executable before
  this change. They were corrected as part of the label rewrite and verified
  against the live database; all rewrites were verified to preserve the
  original result rows (one exception: the pre-broken examples, verified for
  executability only).

Consequences:

- Eval must be re-run once to confirm strict EX holds within noise and that
  the 5 id-only live patterns now return labels.
- The 76-noise class disappears at the presentation layer immediately and
  deterministically, regardless of what the model does.
- Any future Consumer that *wants* the ids (exports, joins) still gets them —
  the contract is about display and generation defaults, not data removal.
- This does not weaken ADR 0008; it supplies it with an upstream guarantee:
  axis selection now usually finds a name because generation usually provides
  one.
