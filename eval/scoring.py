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
    REGRESSION_QUOTA,
    count_answer_type_block,
    count_buckets,
    count_exemplar_block,
    count_regression_block,
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
    g_regression = count_regression_block(questions)
    if g_regression != REGRESSION_QUOTA:
        violations.append(
            f"golden set regression block has {g_regression}, quota {REGRESSION_QUOTA}")
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


# --- result-set scoring (extracted from the runner, ticket #21) ---------------
# The runner and the agent-mode path must score SQL answers identically, so the
# comparators live here where both can import and tests can reach them.

def _col_vectors(df):
    """Each column as an order-normalised tuple of its (rounded/lowercased) values."""
    s = df.sort_values(list(df.columns), kind="stable").reset_index(drop=True)
    out = set()
    for col in s.columns:
        vec = []
        for v in s[col]:
            if isinstance(v, float):
                vec.append(round(v, 2))
            elif isinstance(v, str):
                vec.append(v.strip().lower())
            else:
                vec.append(v)
        out.add(tuple(vec))
    return out


def relaxed_match(gold_df, pred_df):
    """Same answer up to one added or dropped descriptive column (a name/label
    that is functionally dependent on the grouping key). Row counts must match.
    Looser than strict EX; a wrong metric can slip through only if >=2 other
    columns still line up."""
    if gold_df.empty or pred_df.empty:
        return gold_df.empty and pred_df.empty
    if len(gold_df) != len(pred_df):
        return False
    gv, pv = _col_vectors(gold_df), _col_vectors(pred_df)
    shared = len(gv & pv)
    return shared >= len(gv) - 1 and shared >= len(pv) - 1


def result_sets_match(gold_df, pred_df):
    """Strict execution accuracy: order-free equality of full result sets.
    Verbatim semantics from eval/run_eval.py (row-tuple comparison, column
    names dropped, floats rounded, strings lowercased) — the after-run must
    be scored under exactly the same comparator as the baseline."""
    if gold_df.shape[1] != pred_df.shape[1]:
        return False
    return _to_comparable(gold_df) == _to_comparable(pred_df)


def _to_comparable(df):
    """Verbatim from eval/run_eval.py: rows as normalised tuples in a frozenset."""
    rows = []
    for row in df.itertuples(index=False):
        normalized = []
        for v in row:
            if isinstance(v, float):
                normalized.append(round(v, 2))
            elif isinstance(v, str):
                normalized.append(v.strip().lower())
            elif v is None:
                normalized.append(None)
            else:
                normalized.append(v)
        rows.append(tuple(normalized))
    return frozenset(rows)


def score_sql_row(rec, gold_df, pred_df, retry=0):
    """Fill one question record's result-set fields in place and return it.
    Used by BOTH engines (pipeline and agent) so the after-numbers are scored
    under exactly the same rules as the baseline."""
    rec["ex_pass"] = result_sets_match(gold_df, pred_df)
    rec["ex_pass_relaxed"] = rec["ex_pass"] or relaxed_match(gold_df, pred_df)
    rec["grain_ok"] = rec["ex_pass"] or (pred_df.shape[0] == gold_df.shape[0])
    rec["first_try"] = rec["ex_pass"] and retry == 0
    if not rec["ex_pass"]:
        rec["error_class"] = "wrong_grain" if not rec["grain_ok"] else (
            "cols_only" if rec["ex_pass_relaxed"] else "wrong_result")
    return rec


def turn_result_fields(turn):
    """Map an agent Turn answering a SQL question onto the record fields the
    pipeline path produces (pred_sql / validity / executability), so both
    engines land in the same report shape."""
    sql = getattr(turn, "sql", None)
    rows = getattr(turn, "rows", None)
    error = getattr(turn, "error", None)
    ok = bool(sql) and not error
    return {
        "pred_sql": sql if ok else None,
        "sql_valid": ok,
        "executable": ok and rows is not None,
        "error_class": error if not ok else None,
    }
