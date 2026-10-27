---
status: accepted
---

# The demo wizard authors Domain profiles, and profile hints reach both prompts

## Context

ADR 0011 made Domain profiles the portability seam and recorded the debt that comes
due when a second datasource arrives: STS assumptions still live in core code, and
creating a profile is a hand-authoring exercise against the five-file contract
(`docs/guides/PROFILES.md`) followed by an evaluation run. That is workable for the
maintainer who wrote the contract and impossible for the person who just pointed
`./start_demo.sh` at their own database — the demo's first ask is a profile they
cannot make.

Two facts in the current code shape the fix:

- `hints.md` is injected into the one-shot prompt only (`NLPEngine.query_database`).
  The conversational agent — the mode the demo UI actually uses — builds its system
  prompt in code and never sees the profile's hints or its ambiguity rules, so the
  knowledge a profile carries is invisible exactly where the demo needs it
  (documented as a known gap in `docs/guides/PROFILES.md`).
- `POST /api/demo/connect` already switches Datasource *and* profile at runtime in
  demo mode (ADR 0013), so a profile written while the demo runs can be selected
  without a restart.

## Decision

1. **Demo mode may author profiles.** A Profile wizard in the bundled UI (mounted
   with the demo routes — `demo`, or `auto` without an API key; never `service`)
   collects the knowledge and writes an ordinary profile to `profiles/<name>/` in
   the project tree. The output is the same artifact the service reads, reviewable
   as a git diff, and usable by any mode that reads the profiles directory.
2. **The wizard asks a minimum pass first** — datasource identity and profile name,
   the Thai terms and table meanings, the first example questions, the business
   rules — and offers follow-up screens (more examples, clarification and refusal
   exemplars, notes) for whoever wants to go further.
3. **The service drafts, the user confirms.** For each example question the system
   generates SQL, executes it read-only and shows the resulting rows; only
   confirmed examples are written, and a result example whose SQL cannot execute is
   never saved. Clarification/refusal exemplars keep their existing shape (no SQL,
   expected answer type).
4. **Validity is enforced, completeness is reported.** A saved profile must satisfy
   the file contract (`examples.json` always present, every saved example parses and
   runs, slug uniqueness, no silent overwrite of an existing profile). What the user
   skipped surfaces as coverage in the UI. There is no second tier of profile:
   "supported" keeps its existing meaning of "ships in this repo and passes
   conformance and evaluation", and nothing the wizard produces claims it.
5. **Profile hints are injected into the conversational agent too**, so both prompts
   are built from the same profile knowledge; this retires the PROFILES.md known
   gap. The STS-specific ambiguity examples that live in `core/services/agent.py`
   move into the profile as part of this work, discharging the ADR 0011 known debt,
   with an evaluation run on both sides of the change.

## Considered options

- **Keep hand-authoring and add a checklist.** Rejected: it leaves the demo's
  first-run experience asking for a file the visitor cannot produce.
- **Write wizard profiles into a separate user directory.** Rejected: a profile is
  a deployment artifact — it should be reviewable, diffable and committable next to
  the datasource it describes, not a hidden local cache.
- **Introduce `draft` vs `supported` tiers.** Rejected: `supported` already means
  "passes this repo's conformance and evaluation"; reusing the word for a
  wizard-state would muddy it, and coverage plus the automatic checks carry the
  same information for the user.
- **Save example questions without executing them.** Rejected: retrieval imitates
  the stored SQL, so an example that cannot run teaches the model the wrong shape.
- **Strengthen the demo's example retrieval only, no prompt hints.** Rejected: it
  spends the user's answers on the secondary channel and leaves the primary one —
  the system prompt — unaware of the business rules they just stated.

## Consequences

- New demo-only routes plus a profile-writer module that validates slugs, refuses
  path traversal and never overwrites silently; the demo's unauthenticated,
  loopback-only warning (ADR 0013) now covers file authoring as well.
- `docs/guides/PROFILES.md` loses its "known gap" section and its
  hand-authoring-only framing; `docs/guides/QUICK_START.md` gains the wizard as the
  documented path to a first profile.
- Injecting hints into the agent changes behaviour for every existing profile
  (`sts`, `demo`): the prompt grows and answers shift, so the change needs an
  evaluation run, not just unit tests.
- A wizard-created profile is usable in the running demo immediately (ADR 0013's
  runtime switch); in any other deployment it is still selected by `DOMAIN_PROFILE`
  at startup.
