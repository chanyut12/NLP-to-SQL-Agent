"""Aggregate eval/sts/results_*.json into one Markdown comparison table.

    python eval/compare.py [results_dir]     # default: eval/sts
"""

import glob
import json
import os
import re
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---------------------------------------------------------------------------
# Cost model — rough. The eval does not log real token counts, so this is a
# per-question budget (±50%). Measured: full schema ~17.5k tok, hints ~1.85k tok.
#   base input  = pruned schema (~6.5k, ~35 tables after FK expansion)
#               + hints/template/CoT (~2.6k) + RAG examples (3 -> ~0.7k, 0 -> 0)
#   base output = the SQL, ~0.2k
#   a retry call re-sends the FULL schema: ~18.5k in / ~0.2k out
#   RETRY_CALLS: avg extra LLM calls per question, by --max-retries setting
# USD per 1M tokens (in, out).
# ---------------------------------------------------------------------------
TOK_IN_BASE = {"0": 9_100, "3": 9_800}
TOK_OUT_BASE = 200
TOK_IN_RETRY = 18_500
TOK_OUT_RETRY = 200
RETRY_CALLS = {"0": 0.0, "2": 0.7}
PRICE_PER_MTOK = {
    "openai/gpt-4o-mini": (0.15, 0.60),
    "openrouter/deepseek/deepseek-v4-flash-0731": (0.05, 0.16),
}


def load(d):
    rows = []
    for p in sorted(glob.glob(os.path.join(d, "results_*.json"))):
        r = json.load(open(p, encoding="utf-8"))
        m = re.search(r"_rag(\d+)_re(\d+)_run(\d+)", os.path.basename(p))
        rag, retry, run = (m.group(1), m.group(2), m.group(3)) if m else ("?", "?", "1")
        o = r["overall"]
        rows.append({
            "model": r["model"], "rag": rag, "retry": retry, "run": run, "n": o["n"],
            "ex": o["execution_accuracy"], "exr": o.get("execution_accuracy_relaxed", o["execution_accuracy"]),
            "first": o["first_try_success"],
            "grain": o["grain_correct"], "p50": o["p50_latency"], "p95": o["p95_latency"],
            "held_out": r["by_source_tag"]["held_out"]["execution_accuracy"],
            "paraphrase": r["by_source_tag"]["paraphrase"]["execution_accuracy"],
            "novel": r["by_source_tag"]["novel"]["execution_accuracy"],
        })
    return rows


def estimate_cost_usd(rows):
    """Rough USD by model, summed over every result file we have."""
    by_model = {}
    for r in rows:
        n = r["n"]
        tin = n * TOK_IN_BASE.get(r["rag"], TOK_IN_BASE["3"])
        tout = n * TOK_OUT_BASE
        rc = n * RETRY_CALLS.get(r["retry"], 0.0)
        tin += rc * TOK_IN_RETRY
        tout += rc * TOK_OUT_RETRY
        pin, pout = PRICE_PER_MTOK.get(r["model"], (0.0, 0.0))
        usd = tin / 1e6 * pin + tout / 1e6 * pout
        m = by_model.setdefault(r["model"], {"files": 0, "questions": 0, "usd": 0.0})
        m["files"] += 1
        m["questions"] += n
        m["usd"] += usd
    return by_model


def agg(rows, keys):
    """mean +/- sd over repeat runs, grouped by keys."""
    groups = {}
    for r in rows:
        groups.setdefault(tuple(r[k] for k in keys), []).append(r)
    out = []
    for gk, g in sorted(groups.items()):
        rec = dict(zip(keys, gk))
        rec["runs"] = len(g)
        for metric in ("ex", "exr", "first", "grain", "held_out", "paraphrase", "novel", "p50", "p95"):
            vals = [x[metric] for x in g]
            rec[metric] = statistics.mean(vals)
            rec[metric + "_sd"] = statistics.pstdev(vals) if len(vals) > 1 else 0.0
        out.append(rec)
    return out


def pct(m, sd):
    return f"{m:.0%} ±{sd:.0%}" if sd else f"{m:.0%}"


def main():
    d = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "eval", "sts")
    rows = load(d)
    if not rows:
        print("no results in", d)
        return

    lines = ["# STS Text-to-SQL — model comparison", ""]

    lines += ["## Model comparison (best config: rag=3, retry=2)", "",
              "| Model | runs | EX | EX relaxed | first-try | grain | held-out | paraphrase | novel | p50 s | p95 s |",
              "|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|"]
    best = [r for r in rows if r["rag"] == "3" and r["retry"] == "2"]
    for a in agg(best, ["model"]):
        lines.append("| {model} | {runs} | {ex} | {exr} | {first} | {grain} | {ho} | {pa} | {no} | {p50:.1f} | {p95:.1f} |".format(
            model=a["model"], runs=a["runs"], ex=pct(a["ex"], a["ex_sd"]), exr=pct(a["exr"], a["exr_sd"]),
            first=pct(a["first"], a["first_sd"]), grain=pct(a["grain"], a["grain_sd"]),
            ho=pct(a["held_out"], a["held_out_sd"]), pa=pct(a["paraphrase"], a["paraphrase_sd"]),
            no=pct(a["novel"], a["novel_sd"]), p50=a["p50"], p95=a["p95"]))

    # Ablation — for every model that was run at more than one (rag, retry) config.
    models = sorted({r["model"] for r in rows})
    for model in models:
        mr = [r for r in rows if r["model"] == model]
        if len({(r["rag"], r["retry"]) for r in mr}) < 2:
            continue
        lines += ["", f"## Ablation — {model}", "",
                  "| rag_top_k | retry | runs | EX | EX relaxed | first-try | grain | p50 s |",
                  "|--:|--:|--:|--:|--:|--:|--:|--:|"]
        for a in agg(mr, ["rag", "retry"]):
            lines.append("| {rag} | {retry} | {runs} | {ex} | {exr} | {first} | {grain} | {p50:.1f} |".format(
                rag=a["rag"], retry=a["retry"], runs=a["runs"], ex=pct(a["ex"], a["ex_sd"]),
                exr=pct(a["exr"], a["exr_sd"]), first=pct(a["first"], a["first_sd"]),
                grain=pct(a["grain"], a["grain_sd"]), p50=a["p50"]))

    # Cost — rough estimate (no real token logging; see the note).
    cost = estimate_cost_usd(rows)
    if any(v["usd"] for v in cost.values()):
        lines += ["", "## Cost (rough estimate, ±50%)", "",
                  "| Model | result files | question-runs | est. USD | est. THB* |",
                  "|---|--:|--:|--:|--:|"]
        total = 0.0
        for model in sorted(cost):
            c = cost[model]
            total += c["usd"]
            lines.append(f"| {model} | {c['files']} | {c['questions']} | "
                         f"${c['usd']:.2f} | ~{c['usd'] * 35:.0f} |")
        lines.append(f"| **total** | | | **${total:.2f}** | **~{total * 35:.0f}** |")
        lines += ["",
                  "\\* THB at ~35/USD. Estimate only — the eval does not record real "
                  "token usage. Per-question budget: ~9–10k input + ~0.2k output, plus "
                  "~0.7 extra full-schema retry calls per question at `--max-retries 2` "
                  "(0 at `--max-retries 0`). Excludes development / debugging runs and "
                  "the embedding model (local, free)."]

    # Hand-written addendum (partial runs, caveats) — survives regeneration.
    notes = os.path.join(d, "NOTES.md")
    if os.path.exists(notes):
        lines += ["", open(notes, encoding="utf-8").read().rstrip()]

    out = os.path.join(d, "COMPARISON.md")
    open(out, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print("\nwrote", out)


if __name__ == "__main__":
    main()
