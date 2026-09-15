"""Scoring and gating helpers for the STS eval harness (ADR 0006 / ADR 0007).

Ticket #17:
- check_quota_gate: the run refuses to start when either eval set deviates
  from its ADR 0007 distribution (balance cannot silently decay)
- score_answer_type: expected-answer-type questions score pass/fail per the
  ADR 0006 refusal-first rule
- domain_of: derives the reported domain-area coverage axis (reported, never
  enforced — ADR 0007 decision #1)
"""

import sys
from collections import Counter

from eval.distribution_audit import (
    AMBIGUOUS_QUOTA,
    BUCKET_QUOTA,
    CATEGORY_BUCKETS,
    CLARIFY_REFUSAL_QUOTA,
    DENY_QUOTA,
    EXAMPLE_BUCKET_QUOTA,
    count_answer_type_block,
    count_buckets,
    count_exemplar_block,
)

# --- domain coverage vocabulary (reported axis only) --------------------------
# Ordered prefix table over table names appearing in gold SQL.
_DOMAIN_PREFIXES = (
    ("attendance", "attendance"),
    ("cases", "cases"),
    ("case_", "cases"),
    ("teacher", "teachers"),
    ("student", "students"),
    ("school", "schools"),
    ("school_classrooms", "classrooms"),
    ("risk", "students"),
)

# Thai keyword fallback for answer-type questions (no gold SQL to inspect).
_THAI_DOMAIN_HINTS = (
    ("ขาดเรียน", "attendance"),
    ("มาเรียน", "attendance"),
    ("เช็กชื่อ", "attendance"),
    ("เคส", "cases"),
    ("ครู", "teachers"),
    ("นักเรียน", "students"),
    ("เด็ก", "students"),
    ("โรงเรียน", "schools"),
)


def check_quota_gate(questions, examples):
    """Return a list of human-readable violations; empty = the run may start."""
    violations = []
    g_buckets, g_unmapped = count_buckets(questions)
    for b in CATEGORY_BUCKETS:
        if g_buckets[b] != BUCKET_QUOTA:
            violations.append(
                f"golden set bucket '{b}' has {g_buckets[b]} questions, quota {BUCKET_QUOTA}")
    g_blocks = count_answer_type_block(questions)
    if g_blocks["ambiguous"] != AMBIGUOUS_QUOTA:
        violations.append(
            f"golden set ambiguous block has {g_blocks['ambiguous']}, quota {AMBIGUOUS_QUOTA}")
    if g_blocks["deny"] != DENY_QUOTA:
        violations.append(
            f"golden set deny block has {g_blocks['deny']}, quota {DENY_QUOTA}")
    violations.extend(f"golden set unmapped category '{t}' x{n}"
                      for t, n in sorted(g_unmapped.items()))

    e_buckets, e_unmapped = count_buckets(examples)
    for b in CATEGORY_BUCKETS:
        if e_buckets[b] != EXAMPLE_BUCKET_QUOTA:
            violations.append(
                f"example set bucket '{b}' has {e_buckets[b]} examples, quota {EXAMPLE_BUCKET_QUOTA}")
    e_block = count_exemplar_block(examples)
    if e_block["clarify"] != CLARIFY_REFUSAL_QUOTA:
        violations.append(
            f"example set clarify exemplars: {e_block['clarify']}, quota {CLARIFY_REFUSAL_QUOTA}")
    if e_block["refusal"] != CLARIFY_REFUSAL_QUOTA:
        violations.append(
            f"example set refusal exemplars: {e_block['refusal']}, quota {CLARIFY_REFUSAL_QUOTA}")
    violations.extend(f"example set unmapped category '{t}' x{n}"
                      for t, n in sorted(e_unmapped.items()))
    return violations


def score_answer_type(expected, observed, error=None):
    """Score one expected-answer-type question. Returns (passed, reason).

    Refusal-first (ADR 0006): a deny question answered with a Clarification
    fails. An ambiguous question answered with SQL (result) fails.
    """
    if error == "STEP_BUDGET_EXCEEDED":
        return False, "STEP_BUDGET_EXCEEDED: agent exhausted its step budget"
    if observed == expected:
        return True, "pass"
    if expected == "refusal" and observed == "clarification":
        return False, "refusal-first violation: deny question answered with a clarification"
    if expected == "clarification" and observed == "result":
        return False, "ambiguous question answered with SQL instead of a clarification"
    return False, f"expected {expected}, got {observed or 'no answer'}"


def domain_of(q):
    """Derive the domain-area coverage label for one golden question.

    Reported axis only (ADR 0007): the gate never checks this. Gold SQL table
    prefixes first; Thai question keywords as fallback for answer-type
    questions; anything unknown reports as 'other'.
    """
    sql = q.get("gold_sql") or ""
    low = sql.lower()
    for prefix, domain in _DOMAIN_PREFIXES:
        if prefix in low:
            return domain
    question = q.get("question") or ""
    for keyword, domain in _THAI_DOMAIN_HINTS:
        if keyword in question:
            return domain
    return "other"
