"""Distribution audit for the eval sets (ADR 0007).

Computes how the Golden set and the Example set spread across the 7 shared
Category buckets, compares against the ADR 0007 quotas, prints the per-bucket
delta, and exits non-zero when either set deviates from quota — the hook the
eval harness gate (ticket #17) will call.

Usage:
    python eval/distribution_audit.py
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- ADR 0007 quotas ---------------------------------------------------------
# Golden set: 4 questions x 7 buckets + 4 ambiguous + 4 deny = 36.
# Example set: ~8 per bucket + a 3 clarify + 3 refusal block outside the quotas.
BUCKET_QUOTA = 4
AMBIGUOUS_QUOTA = 4
DENY_QUOTA = 4
ANSWER_TYPE_BLOCK_QUOTA = AMBIGUOUS_QUOTA + DENY_QUOTA
EXAMPLE_BUCKET_QUOTA = 8
CLARIFY_REFUSAL_QUOTA = 3

# --- The 7 shared Category buckets -------------------------------------------
CATEGORY_BUCKETS = (
    "count_groupby",
    "count_filter_groupby",
    "aggregation_groupby",
    "ratio_groupby",
    "having_threshold",
    "time_groupby",
    "ranking",
)

# Legacy category tags folded onto their primary SQL shape (ADR 0007).
# Anything absent here and absent from CATEGORY_BUCKETS is UNMAPPED — surfaced,
# never silently dropped. multi_join_aggregation is deliberately absent: join
# depth is a secondary metric, not a bucket.
_LEGACY_TAG_FOLDS = {
    "count_distinct_groupby": "count_groupby",
    "conditional_count_groupby": "count_groupby",
    "count_filter": "count_filter_groupby",
    "not_exists_groupby": "count_filter_groupby",
    "average_groupby": "aggregation_groupby",
    "summary_groupby": "aggregation_groupby",
    "sum_groupby": "aggregation_groupby",
    "time_ratio_groupby": "ratio_groupby",
    "having": "having_threshold",
    "having_subquery": "having_threshold",
    "having_ratio": "having_threshold",
    "freshness_groupby": "time_groupby",
    "ranking_per_group": "ranking",
    "ranking_global": "ranking",
}

# Golden answer-type questions (ADR 0007/#16): carry an expected Answer type
# instead of a gold SQL. Known vocabulary — counted by count_answer_type_block,
# never UNMAPPED and never bucket members.
AMBIGUOUS_CATEGORY = "ambiguous"
DENY_CATEGORY = "deny"
ANSWER_TYPE_CATEGORIES = (AMBIGUOUS_CATEGORY, DENY_CATEGORY)

# Exemplar-block categories for the Example set (outside the bucket quotas).
# Known vocabulary — counted by count_exemplar_block, never UNMAPPED.
CLARIFY_EXEMPLAR_TAG = "clarification_exemplar"
REFUSAL_EXEMPLAR_TAG = "refusal_exemplar"
EXEMPLAR_TAGS = (CLARIFY_EXEMPLAR_TAG, REFUSAL_EXEMPLAR_TAG)


def bucket_for(category: str):
    """Map a category tag onto its shared bucket, or None if unmapped."""
    if category in CATEGORY_BUCKETS:
        return category
    return _LEGACY_TAG_FOLDS.get(category)


def count_buckets(items):
    """Count items per bucket; returns (counts, unmapped).

    Unmapped categories are returned separately so an audit never silently
    swallows a tag that escaped the taxonomy. The exemplar tags are known
    vocabulary (scored by count_exemplar_block) and are excluded from both.
    """
    counts = dict.fromkeys(CATEGORY_BUCKETS, 0)
    unmapped = {}
    for item in items:
        category = item.get("category")
        if category in EXEMPLAR_TAGS:
            continue
        # ADR 0007/#16: a golden question carrying an expected Answer type is a
        # block member regardless of how its category is spelled.
        if (category in ANSWER_TYPE_CATEGORIES
                or item.get("expected_answer_type") in ("clarification", "refusal")):
            continue
        bucket = bucket_for(category)
        if bucket:
            counts[bucket] += 1
        else:
            tag = category or "<missing>"
            unmapped[tag] = unmapped.get(tag, 0) + 1
    return counts, unmapped


def count_answer_type_block(questions):
    """Count the Golden set's ambiguous / deny block (expected answer types)."""
    ambiguous = sum(1 for q in questions if q.get("expected_answer_type") == "clarification")
    deny = sum(1 for q in questions if q.get("expected_answer_type") == "refusal")
    return {"ambiguous": ambiguous, "deny": deny}


def count_exemplar_block(examples):
    """Count the Example set's clarify / refusal exemplar block."""
    clarify = sum(1 for e in examples if e.get("category") == CLARIFY_EXEMPLAR_TAG)
    refusal = sum(1 for e in examples if e.get("category") == REFUSAL_EXEMPLAR_TAG)
    return {"clarify": clarify, "refusal": refusal}


def _block_status(delta: int) -> str:
    if delta == 0:
        return "ok"
    return "surplus" if delta > 0 else "deficit"


def _bucket_infos(counts, quota: int):
    """Per-bucket {count, delta, status} against one quota."""
    return {
        b: {"count": counts[b],
            "delta": counts[b] - quota,
            "status": _block_status(counts[b] - quota)}
        for b in CATEGORY_BUCKETS
    }


def _block_info(count: int, quota: int):
    """{count, delta, status} for one answer-type block against its quota."""
    return {"count": count, "delta": count - quota, "status": _block_status(count - quota)}


def delta_report(golden_counts, example_counts):
    """Build the audit report: per-bucket counts, delta vs quota, and status.

    golden_counts:  {set_label: (bucket_counts, unmapped, ambiguous, deny)}
    example_counts: (bucket_counts, unmapped, clarify, refusal)
    """
    report = {}
    for set_label, (buckets, unmapped, ambiguous, deny) in golden_counts.items():
        report[set_label] = {
            "quota": BUCKET_QUOTA,
            "buckets": _bucket_infos(buckets, BUCKET_QUOTA),
            "unmapped": unmapped,
            "answer_type_blocks": {
                "ambiguous": _block_info(ambiguous, AMBIGUOUS_QUOTA),
                "deny": _block_info(deny, DENY_QUOTA),
            },
        }
    ex_buckets, ex_unmapped, clarify, refusal = example_counts
    report["examples"] = {
        "quota": EXAMPLE_BUCKET_QUOTA,
        "buckets": _bucket_infos(ex_buckets, EXAMPLE_BUCKET_QUOTA),
        "unmapped": ex_unmapped,
        "answer_type_blocks": {
            "clarify": _block_info(clarify, CLARIFY_REFUSAL_QUOTA),
            "refusal": _block_info(refusal, CLARIFY_REFUSAL_QUOTA),
        },
    }
    return report


def _load_golden():
    path = os.path.join(ROOT, "eval", "benchmark_sts.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)["questions"]


def _load_examples():
    path = os.path.join(ROOT, "TEXT_TO_SQL_STS_RAG_EXAMPLES.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)["examples"]


def _print_report(report):
    print("Eval-set distribution audit (ADR 0007)")
    print("=" * 64)
    for set_label in ("golden", "examples"):
        s = report[set_label]
        print(f"\n{set_label.upper()} set (quota {s['quota']}/bucket)")
        print(f"  {'bucket':24}{'count':>6}{'delta':>7}  status")
        for b, info in s["buckets"].items():
            print(f"  {b:24}{info['count']:>6}{info['delta']:>+7}  {info['status']}")
        blocks = s["answer_type_blocks"]
        print("  answer-type blocks:")
        for name, info in blocks.items():
            print(f"    {name:22}{info['count']:>6}{info['delta']:>+7}  {info['status']}")
        if s["unmapped"]:
            print("  UNMAPPED categories (outside the taxonomy — fix these):")
            for tag, n in sorted(s["unmapped"].items()):
                print(f"    {tag}: {n}")
    print()


def audit() -> int:
    """Run the audit against the real set files. Returns process exit code."""
    golden = _load_golden()
    examples = _load_examples()
    g_buckets, g_unmapped = count_buckets(golden)
    g_blocks = count_answer_type_block(golden)
    e_buckets, e_unmapped = count_buckets(examples)
    e_block = count_exemplar_block(examples)

    report = delta_report(
        {"golden": (g_buckets, g_unmapped, g_blocks["ambiguous"], g_blocks["deny"])},
        (e_buckets, e_unmapped, e_block["clarify"], e_block["refusal"]),
    )
    _print_report(report)

    deviations = 0
    for set_label in ("golden", "examples"):
        s = report[set_label]
        deviations += sum(1 for info in s["buckets"].values() if info["delta"] != 0)
        deviations += sum(1 for info in s["answer_type_blocks"].values() if info["delta"] != 0)
        deviations += len(s["unmapped"])
    if deviations:
        print(f"RESULT: {deviations} deviation(s) from ADR 0007 quotas.")
        return 1
    print("RESULT: both sets match ADR 0007 quotas.")
    return 0


if __name__ == "__main__":
    sys.exit(audit())
