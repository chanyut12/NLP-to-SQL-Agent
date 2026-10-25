"""Tests for the eval-set distribution audit (ticket #14, parent spec #13).

The audit's external behaviour, at the seam of the eval harness:
- counts both sets across the 7 shared Category buckets per ADR 0007
- folds legacy category tags onto their bucket, flags unknown tags as UNMAPPED
- reports the answer-type blocks (ambiguous/deny golden; clarify/refusal exemplars)
- computes delta vs the ADR 0007 quotas and exits non-zero on deviation
"""

import json
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
sys.path.insert(0, ROOT)

from eval.distribution_audit import (
    AMBIGUOUS_QUOTA,
    ANSWER_TYPE_BLOCK_QUOTA,
    ANSWER_TYPE_CATEGORIES,
    BUCKET_QUOTA,
    CATEGORY_BUCKETS,
    CLARIFY_REFUSAL_QUOTA,
    DENY_QUOTA,
    bucket_for,
    count_answer_type_block,
    count_buckets,
    REGRESSION_QUOTA,
    count_exemplar_block,
    count_regression_block,
    delta_report,
)

EX = json.load(open(os.path.join(ROOT, "data", "corpus", "TEXT_TO_SQL_STS_RAG_EXAMPLES.json"),
                    encoding="utf-8"))["examples"]
GOLDEN = json.load(open(os.path.join(ROOT, "eval/benchmark_sts.json"),
                        encoding="utf-8"))["questions"]


class TestQuotas(unittest.TestCase):
    def test_bucket_quota_is_per_bucket(self):
        self.assertEqual(BUCKET_QUOTA, 4)

    def test_answer_type_block_quotas(self):
        self.assertEqual(AMBIGUOUS_QUOTA, 4)
        self.assertEqual(DENY_QUOTA, 4)
        self.assertEqual(ANSWER_TYPE_BLOCK_QUOTA, AMBIGUOUS_QUOTA + DENY_QUOTA)

    def test_clarify_refusal_exemplar_quota_is_symmetric(self):
        self.assertEqual(CLARIFY_REFUSAL_QUOTA, 3)


class TestBucketFor(unittest.TestCase):
    def test_all_canonical_buckets_map_to_themselves(self):
        for b in CATEGORY_BUCKETS:
            self.assertEqual(bucket_for(b), b, f"canonical bucket {b} must map to itself")

    def test_legacy_tags_fold_onto_primary_shape(self):
        cases = {
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
        for legacy, bucket in cases.items():
            self.assertEqual(bucket_for(legacy), bucket, f"{legacy} must fold into {bucket}")

    def test_unknown_tag_is_unmapped(self):
        self.assertIsNone(bucket_for("some_new_tag"))

    def test_complexity_dimension_is_deliberately_not_a_bucket(self):
        # ADR 0007: join depth is a secondary metric, not a bucket — the audit
        # surfaces multi_join_aggregation items as UNMAPPED so tickets #15/#16
        # re-tag each to its primary shape.
        self.assertIsNone(bucket_for("multi_join_aggregation"))


class TestAnswerTypeQuestions(unittest.TestCase):
    """ADR 0007/#16: golden ambiguous/deny questions carry an expected Answer
    type instead of a gold SQL; the audit counts them as their own blocks, not
    as bucket members."""

    def test_answer_type_categories_are_known_vocabulary(self):
        self.assertEqual(ANSWER_TYPE_CATEGORIES, ("ambiguous", "deny"))

    def test_count_buckets_skips_answer_type_questions(self):
        items = [
            {"category": "ambiguous", "expected_answer_type": "clarification"},
            {"category": "deny", "expected_answer_type": "refusal"},
            {"category": "count_groupby"},
        ]
        buckets, unmapped = count_buckets(items)
        self.assertEqual(buckets["count_groupby"], 1)
        self.assertEqual(sum(buckets.values()), 1)
        self.assertEqual(unmapped, {})

    def test_count_answer_type_block_counts_expected_types(self):
        questions = [
            {"category": "ambiguous", "expected_answer_type": "clarification"},
            {"category": "ambiguous", "expected_answer_type": "clarification"},
            {"category": "deny", "expected_answer_type": "refusal"},
            {"category": "count_groupby"},
        ]
        block = count_answer_type_block(questions)
        self.assertEqual(block, {"ambiguous": 2, "deny": 1})


class TestCountBuckets(unittest.TestCase):
    def test_counts_fold_legacy_tags_and_flag_unknown(self):
        items = [
            {"category": "count_groupby"},
            {"category": "count_distinct_groupby"},
            {"category": "having_ratio"},
            {"category": "ranking_global"},
            {"category": "brand_new_tag"},
        ]
        buckets, unmapped = count_buckets(items)
        self.assertEqual(buckets["count_groupby"], 2)
        self.assertEqual(buckets["having_threshold"], 1)
        self.assertEqual(buckets["ranking"], 1)
        self.assertEqual(unmapped, {"brand_new_tag": 1})
        self.assertEqual(sum(buckets.values()), 4)

    def test_every_bucket_key_present_even_when_zero(self):
        buckets, unmapped = count_buckets([])
        self.assertEqual(set(buckets), set(CATEGORY_BUCKETS))
        self.assertEqual(unmapped, {})


class TestExemplarBlock(unittest.TestCase):
    def test_counts_only_clarify_and_refusal_examples(self):
        items = [
            {"category": "clarification_exemplar"},
            {"category": "clarification_exemplar"},
            {"category": "refusal_exemplar"},
            {"category": "count_groupby"},
        ]
        block = count_exemplar_block(items)
        self.assertEqual(block, {"clarify": 2, "refusal": 1})

    def test_absent_block_reports_zeroes(self):
        block = count_exemplar_block([{"category": "count_groupby"}])
        self.assertEqual(block, {"clarify": 0, "refusal": 0})


class TestDeltaReport(unittest.TestCase):
    def test_delta_report_shape(self):
        buckets = {b: 4 for b in CATEGORY_BUCKETS}
        golden_counts = {"golden": (buckets, {}, 4, 4)}
        examples = (buckets, {}, 3, 3)
        report = delta_report(golden_counts, examples)
        self.assertIn("golden", report)
        self.assertIn("examples", report)
        for set_name in ("golden", "examples"):
            self.assertEqual(set(report[set_name]["buckets"]), set(CATEGORY_BUCKETS))
        self.assertEqual(set(report["golden"]["answer_type_blocks"]), {"ambiguous", "deny"})
        self.assertEqual(set(report["examples"]["answer_type_blocks"]), {"clarify", "refusal"})

    def test_on_quota_report_is_in_delta_and_zero(self):
        golden_counts = {"golden": ({b: 4 for b in CATEGORY_BUCKETS}, {}, 4, 4)}
        examples = ({b: 8 for b in CATEGORY_BUCKETS}, {}, 3, 3)
        report = delta_report(golden_counts, examples)
        for set_name in ("golden", "examples"):
            for info in report[set_name]["buckets"].values():
                self.assertEqual(info["delta"], 0)
                self.assertEqual(info["status"], "ok")
        amb = report["golden"]["answer_type_blocks"]["ambiguous"]
        den = report["golden"]["answer_type_blocks"]["deny"]
        self.assertEqual(amb["delta"], 0)
        self.assertEqual(den["delta"], 0)
        ex_block = report["examples"]["answer_type_blocks"]
        self.assertEqual(ex_block["clarify"]["delta"], 0)
        self.assertEqual(ex_block["refusal"]["delta"], 0)

    def test_off_quota_report_flags_deficit_and_surplus(self):
        buckets = dict.fromkeys(CATEGORY_BUCKETS, 0)
        buckets["ranking"] = 9  # surplus of 5
        golden_counts = {"golden": (buckets, {}, 0, 0)}
        examples = (buckets, {}, 0, 0)
        report = delta_report(golden_counts, examples)
        self.assertEqual(report["golden"]["buckets"]["ranking"]["status"], "surplus")
        self.assertEqual(report["golden"]["buckets"]["count_groupby"]["status"], "deficit")
        self.assertEqual(report["golden"]["buckets"]["count_groupby"]["delta"], -4)


class TestRealSetsAuditability(unittest.TestCase):
    """The audit runs against the real set files' shape (not their balance —
    balancing is tickets #15/#16)."""

    def test_real_sets_have_category_field(self):
        for q in GOLDEN:
            self.assertIn("category", q, f"golden question {q.get('id')} missing category")
        for e in EX:
            self.assertIn("category", e, f"example {e.get('id')} missing category")

    def test_all_real_categories_resolve_to_a_bucket_or_known_block(self):
        known = (set(CATEGORY_BUCKETS) | {"multi_join_aggregation"}
                 | {"clarification_exemplar", "refusal_exemplar"}
                 | set(ANSWER_TYPE_CATEGORIES))
        for e in EX:
            cat = e["category"]
            self.assertTrue(
                bucket_for(cat) or cat in known,
                f"example {e['id']}: unmapped category {cat}")
        for q in GOLDEN:
            cat = q["category"]
            self.assertTrue(
                bucket_for(cat) or cat in known,
                f"golden question {q['id']}: unmapped category {cat}")


class TestAuditRun(unittest.TestCase):
    def test_audit_prints_report_and_exits_nonzero_on_deviation(self):
        import subprocess
        r = subprocess.run(
            [sys.executable, os.path.join(ROOT, "eval", "distribution_audit.py")],
            capture_output=True, text=True, cwd=ROOT,
        )
        self.assertIn(r.returncode, (0, 1))  # balance state changes as #15/#16/#17 land
        self.assertIn("golden", r.stdout.lower())
        self.assertIn("examples", r.stdout.lower())
        self.assertIn("count_groupby", r.stdout)
        self.assertIn("delta", r.stdout.lower())


class TestRegressionBlock(unittest.TestCase):
    """ADR 0007 amendment: regression questions are a block, not bucket members."""

    def test_regression_items_are_not_counted_in_buckets(self):
        items = [{"category": "count_groupby", "source_tag": "regression"},
                 {"category": "count_groupby", "source_tag": "held_out"}]
        counts, unmapped = count_buckets(items)
        self.assertEqual(counts["count_groupby"], 1)
        self.assertEqual(unmapped, {})

    def test_count_regression_block(self):
        items = [{"source_tag": "regression"}, {"source_tag": "regression"}, {"source_tag": "novel"}]
        self.assertEqual(count_regression_block(items), 2)

    def test_report_includes_the_block_against_its_quota(self):
        zero = dict.fromkeys(CATEGORY_BUCKETS, 0)
        report = delta_report({"golden": (zero, {}, 0, 0)}, (zero, {}, 0, 0), regression_count=REGRESSION_QUOTA - 1)
        self.assertEqual(report["golden"]["answer_type_blocks"]["regression"]["status"], "deficit")

    def test_real_golden_set_matches_the_regression_quota(self):
        self.assertEqual(count_regression_block(GOLDEN), REGRESSION_QUOTA)


if __name__ == "__main__":
    unittest.main()
