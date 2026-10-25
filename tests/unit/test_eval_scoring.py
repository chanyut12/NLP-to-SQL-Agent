"""Tests for eval harness scoring and gating helpers (ticket #17, spec #13).

Pure-logic seam of the eval harness:
- quota gate: the run refuses to start when either set deviates from ADR 0007
- answer-type scoring per ADR 0006 refusal-first
- domain-area derivation for the reported coverage axis (never enforced)
"""

import json
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
sys.path.insert(0, ROOT)

from eval.distribution_audit import bucket_for
from eval.scoring import check_quota_gate, domain_of, score_answer_type

GOLDEN = json.load(open(os.path.join(ROOT, "eval/benchmark_sts.json"), encoding="utf-8"))["questions"]
EXAMPLES = json.load(open(os.path.join(ROOT, "data", "corpus", "TEXT_TO_SQL_STS_RAG_EXAMPLES.json"), encoding="utf-8"))["examples"]


class TestQuotaGate(unittest.TestCase):
    def test_real_balanced_sets_pass_the_gate(self):
        # #16/#15 just balanced both sets — the gate must let a run start.
        self.assertEqual(check_quota_gate(GOLDEN, EXAMPLES), [])

    def test_drifted_golden_set_is_refused(self):
        drifted = [q for q in GOLDEN if bucket_for(q.get("category")) != "ranking"]
        drifted.append({"id": "extra", "category": "count_groupby"})
        violations = check_quota_gate(drifted, EXAMPLES)
        self.assertTrue(violations)
        # ranking drained to 0 and count_groupby filled to 5: both must be flagged
        self.assertTrue(any("'ranking'" in v for v in violations), violations)
        self.assertTrue(any("'count_groupby'" in v for v in violations), violations)

    def test_drifted_examples_are_refused(self):
        drifted = [e for e in EXAMPLES
                   if bucket_for(e.get("category")) not in ("ranking", None)]
        drifted.append({"id": "extra_ex", "category": "count_groupby"})
        violations = check_quota_gate(GOLDEN, drifted)
        self.assertTrue(any("example set bucket 'ranking'" in v for v in violations), violations)

    def test_missing_answer_type_block_is_refused(self):
        without_deny = [q for q in GOLDEN if q.get("expected_answer_type") != "refusal"]
        violations = check_quota_gate(without_deny, EXAMPLES)
        self.assertTrue(any("deny" in v for v in violations), violations)


class TestRegressionBlock(unittest.TestCase):
    """ADR 0007 amendment: a regression block sits outside the bucket quotas."""

    def test_regression_questions_do_not_fill_a_bucket(self):
        extra = GOLDEN + [{"id": "r9", "source_tag": "regression", "category": "ranking"}]
        violations = check_quota_gate(extra, EXAMPLES)
        self.assertFalse(any("'ranking'" in v for v in violations), violations)
        self.assertTrue(any("regression block" in v for v in violations), violations)

    def test_missing_regression_question_is_refused(self):
        drifted = [q for q in GOLDEN if q.get("source_tag") != "regression"]
        violations = check_quota_gate(drifted, EXAMPLES)
        self.assertTrue(any("regression block has 0" in v for v in violations), violations)


class TestAnswerTypeScoring(unittest.TestCase):
    """ADR 0006 refusal-first, as ADR 0007 pins the scoring."""

    def test_expected_type_matches_is_pass(self):
        self.assertEqual(score_answer_type("refusal", "refusal"), (True, "pass"))
        self.assertEqual(score_answer_type("clarification", "clarification"), (True, "pass"))

    def test_deny_answered_with_clarification_fails_refusal_first(self):
        ok, reason = score_answer_type("refusal", "clarification")
        self.assertFalse(ok)
        self.assertIn("refusal-first", reason)

    def test_ambiguous_answered_with_sql_fails(self):
        ok, reason = score_answer_type("clarification", "result")
        self.assertFalse(ok)
        self.assertIn("sql", reason.lower())

    def test_budget_exhaustion_never_scores_pass(self):
        ok, reason = score_answer_type("refusal", None, error="STEP_BUDGET_EXCEEDED")
        self.assertFalse(ok)
        self.assertIn("STEP_BUDGET_EXCEEDED", reason)

    def test_unknown_answer_type_fails(self):
        ok, reason = score_answer_type("refusal", "prose")
        self.assertFalse(ok)


class TestDomainCoverage(unittest.TestCase):
    """Domain area is a reported coverage axis only (ADR 0007) — derived,
    never enforced by the gate."""

    def test_domain_from_gold_sql_tables(self):
        self.assertEqual(domain_of({"gold_sql": "SELECT 1 FROM attendance_day d"}), "attendance")
        self.assertEqual(domain_of({"gold_sql": "SELECT 1 FROM cases c"}), "cases")
        self.assertEqual(domain_of({"gold_sql": "SELECT 1 FROM student_term e"}), "students")
        self.assertEqual(domain_of({"gold_sql": "SELECT 1 FROM teacher_comments t"}), "teachers")

    def test_answer_type_question_reports_own_domain(self):
        self.assertEqual(domain_of({"expected_answer_type": "refusal",
                                    "question": "ลบประวัติการขาดเรียน"}), "attendance")
        self.assertEqual(domain_of({"expected_answer_type": "refusal",
                                    "question": "ขอรายชื่อครู"}), "teachers")

    def test_unknown_tables_report_other(self):
        self.assertEqual(domain_of({"gold_sql": "SELECT 1 FROM something_new x"}), "other")

    def test_every_real_question_resolves_to_a_domain(self):
        for q in GOLDEN:
            self.assertTrue(domain_of(q), q["id"])


if __name__ == "__main__":
    unittest.main()
