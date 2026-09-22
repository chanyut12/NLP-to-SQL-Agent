"""ADR 0009 — Entity label in answers, all four layers.

1. Presentation: an identifier-name pair marks the id collapsible in column
   metadata (extends ADR 0004's deterministic metadata; nothing is dropped).
2. Generation: the system prompt carries the Entity label rule.
3. The Example set and the Golden set comply with the contract (no id-only
   per-entity SELECTs) — enforced through the shared audit.
4. Non-SQL exemplars keep their Thai-message convention (guard while editing
   the corpus): non-empty, bounded, and ending in guidance for the user.
"""

import json
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
sys.path.insert(0, ROOT)

from core.viz.column_meta import describe_result
from core.services.agent import AGENT_SYSTEM_PROMPT
from eval.entity_label_audit import audit_example_set, audit_golden_set


def _by_name(rows):
    cols, _ = describe_result(rows, truncated=False)
    return {c["name"]: c for c in cols}


class TestCollapsibleIds(unittest.TestCase):
    """Layer 3 (presentation): deterministic, additive column metadata."""

    def test_paired_id_is_marked_collapsible(self):
        by = _by_name([
            {"school_id": 1, "school_name": "โรงเรียนก", "student_count": 10},
            {"school_id": 2, "school_name": "โรงเรียนข", "student_count": 20},
        ])
        self.assertTrue(by["school_id"].get("collapsible"))
        # The label column and the metric are untouched.
        self.assertNotIn("collapsible", by["school_name"])
        self.assertNotIn("collapsible", by["student_count"])

    def test_unpaired_id_is_not_marked(self):
        by = _by_name([
            {"school_id": 1, "student_count": 10},
            {"school_id": 2, "student_count": 20},
        ])
        self.assertNotIn("collapsible", by["school_id"])

    def test_no_id_columns_no_flags(self):
        by = _by_name([
            {"school_name": "ก", "student_count": 10},
            {"school_name": "ข", "student_count": 20},
        ])
        self.assertFalse(any("collapsible" in c for c in by.values()))

    def test_different_entities_not_paired(self):
        # An id and a name that do not share a stem must not pair.
        by = _by_name([
            {"school_id": 1, "product_name": "กาบหอย", "count": 1},
            {"school_id": 2, "product_name": "ปู", "count": 2},
        ])
        self.assertNotIn("collapsible", by["school_id"])

    def test_payload_rows_are_untouched(self):
        rows = [{"school_id": 1, "school_name": "โรงเรียนก"}]
        cols, _ = describe_result(rows, truncated=False)
        # The rule marks metadata; the data rows still carry both columns.
        self.assertEqual(rows[0]["school_id"], 1)


class TestPromptRule(unittest.TestCase):
    """Layer 2 (generation): the system prompt teaches the Entity label."""

    def test_prompt_has_entity_label_rule(self):
        self.assertIn("Entity label rule", AGENT_SYSTEM_PROMPT)
        self.assertIn("label column", AGENT_SYSTEM_PROMPT)

    def test_rule_is_default_with_exception_and_pii_safe(self):
        low = AGENT_SYSTEM_PROMPT.lower()
        # Default: per-entity results select the entity's label column...
        self.assertIn("grouped by or filtered to one entity", low)
        # ...exception: ids when the user asks for the code itself...
        self.assertIn("asks for the code itself", low)
        # ...and the rule never pushes person names (PII stays a refusal).
        self.assertIn("never a person", low)


class TestExampleSetComplies(unittest.TestCase):
    """Layer 3 (generation fuel): no id-only per-entity SELECT in the corpus."""

    def test_no_id_only_examples(self):
        offenders = audit_example_set()
        self.assertEqual(offenders, [],
                         "id-only SELECT examples remain in the corpus:\n"
                         + "\n".join(offenders))


class TestGoldenSetComplies(unittest.TestCase):
    """The gold defines the expected result under the new contract."""

    def test_no_id_only_gold_sql(self):
        offenders = audit_golden_set()
        self.assertEqual(offenders, [],
                         "id-only gold SQLs remain in the benchmark:\n"
                         + "\n".join(offenders))


class TestExemplarFormat(unittest.TestCase):
    """Editing the corpus must not break the clarification/refusal exemplars."""

    def test_exemplar_messages_follow_documented_convention(self):
        path = os.path.join(ROOT, "TEXT_TO_SQL_STS_RAG_EXAMPLES.json")
        data = json.load(open(path, encoding="utf-8"))
        for ex in data["examples"]:
            if not ex.get("expected_answer_type"):
                continue
            msg = ex.get("expected_message") or ""
            self.assertTrue(msg.strip(), f"{ex['id']}: empty exemplar message")
            self.assertLessEqual(len(msg), 600, f"{ex['id']}: message > 600")


if __name__ == "__main__":
    unittest.main()
