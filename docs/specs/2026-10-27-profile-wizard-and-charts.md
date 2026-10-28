# Spec: First-run profile authoring and a modern chart catalog

Status: published to the issue tracker as #48; tickets #49–#56.
Decisions recorded in [ADR 0014](../adr/0014-demo-wizard-authors-profiles.md) and
[ADR 0015](../adr/0015-echarts-and-expanded-chart-catalog.md); vocabulary lives in
`CONTEXT.md`.

## Problem Statement

The service only answers well against a database it holds a Domain profile for, and
the only way to obtain one today is to hand-author the five-file contract and run an
evaluation. That is possible for the maintainer and impossible for the visitor who
just pointed the demo at their own database — so the demo's very first ask is the one
thing the visitor cannot produce, and every Datasource other than `sts` is effectively
unusable. The knowledge a profile does carry barely helps either: profile hints reach
the one-shot prompt only, and the conversational agent — the mode the demo and the
Consumer actually use — never sees them, so the rules a user carefully states have no
effect where it counts.

Results also read poorly. Charts are drawn in a single flat color, the demo can render
only four chart shapes, and one of the alternatives the service already offers ("Area
Chart") is not implemented by the renderer and silently degrades to a bar — an offered
option that lies.

## Solution

A first-run path in the demo that turns a connected database into a working Domain
profile: the visitor answers a short minimum set of questions, the service drafts SQL
for their example questions, executes it read-only and shows the rows, and the
confirmed result is written into the repository as an ordinary profile that can be
switched into immediately. Profile knowledge then reaches both prompts, so what the
visitor states actually changes how the system answers.

Charts become modern and broader: a new renderer with a value-ramp palette and
readable defaults, and a service-side catalog of roughly ten chart kinds it can
justify from the result grid.

## User Stories

1. As a visitor with my own database, I want to create a Domain profile without
   writing a single file by hand, so that I can get useful answers in one sitting.
2. As a visitor, I want the wizard to ask a minimum set of questions first, so that I
   am not blocked by parts of the profile I cannot fill yet.
3. As a visitor, I want optional follow-up screens after the minimum pass, so that I
   can deepen the profile whenever I have time.
4. As a visitor, I want the service to draft the SQL for my example questions, so that
   I do not need to know SQL.
5. As a visitor, I want to see the rows a drafted example returns before it is saved,
   so that I can confirm it means what I think it means.
6. As a visitor, I want to correct a drafted example when it is wrong, so that a bad
   draft does not block me.
7. As a visitor, I want an example whose SQL cannot execute to be refused rather than
   saved, so that my profile never teaches the system broken SQL.
8. As a visitor, I want to teach the system which Thai words map to which tables and
   columns, so that schema retrieval finds the right tables for my vocabulary.
9. As a visitor, I want to state business rules and known ambiguities in my own words,
   so that the agent asks a clarifying question instead of guessing.
10. As a visitor, I want to record what each table means and which population it
    covers, so that `describe_table` and the Turn digest describe my data, not generic
    columns.
11. As a visitor, I want to add clarification and refusal exemplars, so that non-SQL
    answers keep one consistent format.
12. As a visitor, I want to name my profile and be protected from silently
    overwriting an existing one, so that I cannot lose work.
13. As a visitor, I want to see what my profile covers and what I skipped, so that I
    know where answers will be weaker.
14. As a visitor, I want to start using my new profile immediately after saving it,
    without restarting the server.
15. As a visitor, I want the profile to be an ordinary file in the repository, so that
    I can review, edit and commit it like any other change.
16. As a visitor, I want the rules I wrote to affect the conversational agent, so that
    answering the wizard visibly changes the answers I get.
17. As a maintainer, I want the STS assumptions that live in agent code to move into
    the STS profile, so that domain knowledge stops being code.
18. As a maintainer, I want the agent measured before and after profile hints reach
    it, so that the behaviour change is evidence-backed rather than assumed.
19. As a maintainer, I want the wizard endpoints to exist only in demo mode, so that a
    service deployment cannot write files through its API.
20. As a maintainer, I want wizard-created profiles to obey the same file contract as
    hand-authored ones, so that one loader serves both and no second format appears.
21. As an end user reading an answer, I want a single-measure bar chart to use a value
    ramp with its maximum highlighted, so that I can read the ranking at a glance
    instead of squinting at one flat color.
22. As an end user, I want value labels, sensible ordering and quiet gridlines, so
    that I do not have to hover to understand a chart.
23. As an end user, I want more chart kinds — horizontal, grouped and stacked bars,
    area, combo bar-with-line, doughnut, scatter and bubble, heatmap, treemap, and
    distribution views when the result is raw rows — so that a result is drawn the way
    it should be read.
24. As an end user, I want the chart switcher to offer only kinds the current result
    can actually support, so that switching never produces a broken chart.
25. As an end user, I want charts legible in both light and dark themes, with Thai
    labels truncated gracefully and the full text available on hover.
26. As a Consumer integrator, I want the alternative chart kinds to be
    machine-readable, so that I can dispatch on them instead of parsing display
    strings.
27. As a Consumer integrator, I want the config to state the intended form
    (grouped / stacked / stacked-100%) and the sort order when they matter, so that my
    own rendering matches the recommendation.
28. As a Consumer integrator, I want colors, fonts and layout to stay out of the
    envelope, so that presentation remains mine.
29. As a maintainer, I want the recommender's catalog decisions covered by
    deterministic tests, so that a rule change is checkable without a screenshot.
30. As a maintainer, I want every chart kind the service offers to be one the renderer
    can draw, so that the demo never presents an option that lies.

## Implementation Decisions

**Profile authoring**

- The Profile wizard is a demo-mode-only flow, mounted under the same rule as the
  existing demo connect routes (demo mode, or `auto` without an API key; never in
  `service` mode, where the endpoints return 404). ADR 0014 records the decision and
  its alternatives.
- A profile-writer module owns persistence: it validates the slug (lowercase letters,
  digits, dash/underscore only; no path traversal), refuses to overwrite an existing
  profile without an explicit confirmation flag, and always writes the full file set —
  in particular `examples.json` must exist even when empty, because that file is what
  makes a profile selectable.
- Example records follow the existing Example set contract. The service supplies the
  fields the user should not have to know: `dialect` is derived from the connected
  Datasource and `category` is assigned from the drafted SQL's shape; `id` is
  generated to be stable and unique. The user supplies question, optional synonyms
  (`retrieval_tags`) and an optional one-line grain. Shape:

  ```json
  { "id": "wiz-001", "question": "…", "sql": "SELECT …", "category": "count_groupby",
    "dialect": "sqlite", "retrieval_tags": "…", "grain": "…" }
  ```

  Clarification/refusal exemplars keep the established shape: empty `sql` plus
  `expected_answer_type` and `expected_message`.
- Drafting reuses the service's own generation path; each drafted SQL is executed
  read-only against the connected Datasource, and only a confirmed example whose SQL
  executed successfully is written. A failure is shown to the user with the option to
  correct the SQL.
- There is no draft/supported tier. Saving requires the file contract and an executed
  SQL per result example; everything else is reported as coverage (which sections are
  filled, with counts) and the profile is used as-is.
- After saving in the running demo, switching to the new profile reuses the existing
  runtime switch (ADR 0013), so no restart is required. In any other deployment the
  profile is still selected at startup by `DOMAIN_PROFILE`.
- The wizard's screens: (1) datasource and profile name, (2) Thai terms and table
  meanings, (3) example questions with drafted SQL and live rows, (4) business rules
  and ambiguities, (5) table notes, (6) confirm and coverage. Screens 1–4 form the
  minimum pass; 5–6 and the clarification/refusal exemplars are the follow-up pass.
- Entry point: the Connect tab, plus a first-run nudge when the connected Datasource
  has no matching profile.

**Profile knowledge reaching the agent**

- Both prompts are built from the active profile: the one-shot prompt keeps its current
  injection, and the conversational agent's system prompt gains the profile's hints.
  This closes the known gap documented for `hints.md`.
- The STS-specific ambiguity examples currently owned by agent code move into the STS
  profile, discharging the ADR 0011 known debt for the agent prompt.
- The change is gated by an evaluation run in agent mode on both sides of it.

**Charts**

- The demo UI renders with Apache ECharts, pinned from a CDN like the existing
  Chart.js / highlight.js pins (no build step is added). The chart module becomes an
  adapter from the service's visualization config to a renderer option, and its theme
  is derived from the page's CSS variables so light/dark keeps working. The chart host
  becomes a sized element the renderer can fill.
- Catalog (service-side, rule-based over the result grid): vertical bar, horizontal
  bar, grouped bar, stacked bar, stacked-100% bar, line, area, combo (bar + line, dual
  axis), doughnut, scatter, bubble, heatmap (two category dimensions × one measure),
  treemap; histogram and boxplot only when the result carries raw numeric rows rather
  than an already-aggregated measure. `table` remains the honest fallback and ADR
  0008's axis policy is unchanged and still enforced as an exit guard.
- Single-series charts use a sequential value ramp with the maximum highlighted;
  category-distinct colors remain where color carries identity (multi-series,
  doughnut). Both themes are supported.
- Readability defaults: value labels on bars, ordering taken from the recommendation,
  quiet gridlines and axis lines, preserved top-N + "other" folding, Thai label
  truncation with full text in the tooltip.
- The contract grows semantics only: chart kinds become machine-readable keys; the
  config may state the intended form (grouped / stacked / stacked-100%) and the sort
  order it assumes; colors, fonts and layout never travel in the envelope.
- The alternatives offered for a result are derived from what that result can actually
  support — the static per-type list (and its unimplementable "Area Chart" entry) goes
  away.

## Testing Decisions

Seams, highest first; all three already exist in the codebase, and no new test
infrastructure is introduced.

1. **Engine / agent prompt assembly.** The active profile's knowledge must appear in
   the system prompt the agent runs with, asserted the same way the existing prompt
   rules are asserted (prompt-content tests in the agent-loop and entity-label tests).
   This is the external contract at this seam: the prompt is the product surface for
   the model. Behavioural evidence comes from the STS evaluation runner in agent mode,
   run before and after.
2. **Demo-mode API surface.** The wizard endpoints are exercised through the existing
   demo test client (as the demo connect, demo profile and app-mode tests do), covering
   the happy path, slug validation, overwrite refusal, an example whose SQL fails to
   execute, and 404 in `service` mode. A round-trip test writes a wizard profile and
   loads it with the existing loader + profile conformance test, so "one contract, one
   loader" stays true.
3. **Visualization recommender.** Deterministic DataFrame-in / config-out tests (as the
   axis-policy and column-metadata tests do): each catalog kind's trigger, the agreed
   keys in the alternatives list, the not-chartable refusal, and the invariant that
   every offered kind is renderable.

A good test here asserts external behaviour at a seam — the prompt carries the
profile's knowledge; the API returns the promised shape and refusals; the recommender
returns a renderable plan; written files satisfy the contract. No tests of private
helpers, no assertions on internal call order.

The demo UI's chart adapter has no automated seam (the repository's test suite is
Python; no JS runner exists). It is verified by hand in the demo UI in both themes,
while the contract-shaped decisions it depends on are covered at seam 3.

## Out of Scope

- Funnel, gauge, waterfall and sankey: they need ordered stages or a target that a
  result grid cannot express. They become candidates once a profile can declare that
  semantics.
- Histogram and boxplot over already-aggregated results (only raw-row results qualify).
- Any evaluation gate inside the wizard.
- Moving the STS table denylist out of core (separate, already-recorded debt).
- Committing or publishing the created profile automatically — the user reviews the
  diff and commits.
- Editing an existing profile through the UI; the files stay the editing surface.
- LLM-based chart recommendation (the catalog stays rule-based and deterministic).
- Runtime multi-Datasource support beyond what ADR 0013 already allows.

## Further Notes

- Suggested sequencing: (1) profile hints reach the agent — small, unlocks the
  wizard's value, gated by the evaluation run; (2) the chart work — independent and
  immediately visible; (3) the profile writer + demo API; (4) the wizard UI;
  (5) the documentation pass (PROFILES.md loses its known-gap section, QUICK_START
  gains the wizard path, API.md lists the new chart kinds, screenshots refresh).
- Risk: injecting hints into the agent grows the prompt and can shift answers; the
  moved STS examples must keep today's clarification behaviour for relative recency
  ("ล่าสุด", "ช่วงนี้"). The evaluation run is the gate, not unit tests alone.
- Risk: the wizard writes into the working tree. It must stay demo-only and
  loopback-bound, like the existing demo routes, and never run in a service
  deployment.
- Risk: a partially filled profile is used as-is by design; the coverage report is what
  keeps that honest to the user.
- The wizard's Thai microcopy and the first-run nudge wording are implementation
  details to be written during the build, in the demo UI's existing voice.
