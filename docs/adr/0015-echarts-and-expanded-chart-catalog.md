---
status: accepted
---

# ECharts renderer, an expanded chart catalog, and no presentation in the contract

## Context

The demo UI is judged on how a result reads, and today it reads badly: the renderer
is Chart.js 4.5.1 drawing four shapes (bar, line, scatter, doughnut), a
single-series chart uses one flat color (`--chart-series-1`), the service's catalog
is `bar/line/scatter/pie/table/none`, and `get_chart_options()` already offers an
"Area Chart" the renderer cannot draw — choosing it silently renders a bar. The ask
is a modern, legible look and a wider catalog of chart kinds.

## Decision

1. **Render with Apache ECharts**, loaded from a pinned CDN script like the existing
   Chart.js / highlight.js pins (no build step added). The chart module becomes an
   adapter from the service's visualization config to an ECharts option, and its
   theme is derived from the page's CSS variables so light/dark keeps working.
2. **The catalog grows to the kinds a result grid can justify** — vertical and
   horizontal bar, grouped bar, stacked bar (including the 100% form), line, area,
   combo (bar + line, dual axis), doughnut, scatter, bubble, heatmap (two category
   dimensions × one measure), treemap — plus histogram and boxplot only when the
   result carries raw numeric rows rather than an already-aggregated measure. `table`
   remains the honest fallback, unchanged by ADR 0008's axis policy.
3. **`alternatives` becomes machine-readable keys** — a Consumer switches on them and
   supplies its own labels; the current human strings ("Area Chart") cannot be
   dispatched on and one of them does not exist in the renderer.
4. **The contract grows semantics only.** It may state the intended form when a
   series role exists (grouped / stacked / stacked-100%) and the sort order the
   recommendation assumes. Colors, gradients, fonts and layout stay in the rendering
   UI: the config is advisory, and a Consumer that draws its own charts must not
   receive a palette from the service.
5. **A single-series chart uses a value ramp with its maximum highlighted.**
   Category-distinct colors stay where color carries identity (multi-series,
   doughnut); a lone measure gets intensity, not decoration.

## Considered options

- **Chart.js plus plugins** (`treemap`, `matrix`, `boxplot`, `funnel`). Rejected:
  several more pinned scripts, and the modern look would still be hand-built.
- **Keep Chart.js core and restyle only.** Rejected: answers the look, not the
  catalog, which is half the request.
- **Send a palette or theme in the envelope** so every Consumer draws identically.
  Rejected: presentation is the Consumer's; an advisory config that dictates colors
  stops being advisory.
- **The library's full catalog, including funnel, gauge, waterfall and sankey.**
  Deferred, not rejected: funnel needs ordered stages and gauge needs a target, and
  a result grid cannot show either — they become candidates once a profile can
  declare that semantics.

## Consequences

- `web/js/modules/chart.js` and the result card's chart container are rewritten
  (ECharts renders into a sized host element); the "Area" alternative stops
  degrading to a bar.
- `docs/API.md` and `CONTEXT.md` list the new kinds; consumers that rendered the old
  `options` strings verbatim must switch to keys — the demo UI is the only known
  consumer.
- Chart type stays advisory, so no evaluation scoring changes; the demo screenshots
  in the docs do.
- ECharts adds roughly a megabyte of CDN JavaScript to the demo page; the page
  already depends on CDN assets and has no bundler, so nothing else moves.
