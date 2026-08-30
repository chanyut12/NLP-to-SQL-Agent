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


def load(d):
    rows = []
    for p in sorted(glob.glob(os.path.join(d, "results_*.json"))):
        r = json.load(open(p, encoding="utf-8"))
        m = re.search(r"_rag(\d+)_re(\d+)_run(\d+)", os.path.basename(p))
        rag, retry, run = (m.group(1), m.group(2), m.group(3)) if m else ("?", "?", "1")
        o = r["overall"]
        rows.append({
            "model": r["model"], "rag": rag, "retry": retry, "run": run,
            "ex": o["execution_accuracy"], "first": o["first_try_success"],
            "grain": o["grain_correct"], "p50": o["p50_latency"], "p95": o["p95_latency"],
            "held_out": r["by_source_tag"]["held_out"]["execution_accuracy"],
            "paraphrase": r["by_source_tag"]["paraphrase"]["execution_accuracy"],
            "novel": r["by_source_tag"]["novel"]["execution_accuracy"],
        })
    return rows


def agg(rows, keys):
    """mean +/- sd over repeat runs, grouped by keys."""
    groups = {}
    for r in rows:
        groups.setdefault(tuple(r[k] for k in keys), []).append(r)
    out = []
    for gk, g in sorted(groups.items()):
        rec = dict(zip(keys, gk))
        rec["runs"] = len(g)
        for metric in ("ex", "first", "grain", "held_out", "paraphrase", "novel", "p50", "p95"):
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

    lines += ["## Model comparison (best config: rag=5, retry=2)", "",
              "| Model | runs | EX | first-try | grain | held-out | paraphrase | novel | p50 s | p95 s |",
              "|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|"]
    best = [r for r in rows if r["rag"] == "5" and r["retry"] == "2"]
    for a in agg(best, ["model"]):
        lines.append("| {model} | {runs} | {ex} | {first} | {grain} | {ho} | {pa} | {no} | {p50:.1f} | {p95:.1f} |".format(
            model=a["model"], runs=a["runs"], ex=pct(a["ex"], a["ex_sd"]),
            first=pct(a["first"], a["first_sd"]), grain=pct(a["grain"], a["grain_sd"]),
            ho=pct(a["held_out"], a["held_out_sd"]), pa=pct(a["paraphrase"], a["paraphrase_sd"]),
            no=pct(a["novel"], a["novel_sd"]), p50=a["p50"], p95=a["p95"]))

    anchor = "openai/gpt-4o-mini"
    abl = [r for r in rows if r["model"] == anchor]
    if abl:
        lines += ["", f"## Ablation — {anchor}", "",
                  "| rag_top_k | retry | runs | EX | first-try | grain | p50 s |",
                  "|--:|--:|--:|--:|--:|--:|--:|"]
        for a in agg(abl, ["rag", "retry"]):
            lines.append("| {rag} | {retry} | {runs} | {ex} | {first} | {grain} | {p50:.1f} |".format(
                rag=a["rag"], retry=a["retry"], runs=a["runs"], ex=pct(a["ex"], a["ex_sd"]),
                first=pct(a["first"], a["first_sd"]), grain=pct(a["grain"], a["grain_sd"]), p50=a["p50"]))

    out = os.path.join(d, "COMPARISON.md")
    open(out, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print("\nwrote", out)


if __name__ == "__main__":
    main()
