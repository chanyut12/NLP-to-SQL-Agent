"""Deterministic column typing + result summary (see ADR 0004)."""

import os
import sys
import unittest
from decimal import Decimal
from datetime import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from core.viz.column_meta import describe_result


def _types(rows):
    cols, _ = describe_result(rows, truncated=False)
    return {c["name"]: c["semantic_type"] for c in cols}


class TestSemanticType(unittest.TestCase):
    def test_name_fragments_drive_type(self):
        rows = [
            {"school_id": 1, "school_name": "ก", "student_count": 120,
             "attendance_rate": 83.5, "term_gpa": 3.21, "created_at": datetime(2026, 8, 1)},
            {"school_id": 2, "school_name": "ข", "student_count": 98,
             "attendance_rate": 79.0, "term_gpa": 2.98, "created_at": datetime(2026, 8, 2)},
        ]
        t = _types(rows)
        self.assertEqual(t["school_id"], "id")
        self.assertEqual(t["school_name"], "name")
        self.assertEqual(t["student_count"], "count")
        self.assertEqual(t["attendance_rate"], "percent")
        self.assertEqual(t["term_gpa"], "gpa")
        self.assertEqual(t["created_at"], "date")

    def test_unlabelled_numeric_int_is_count_float_is_number(self):
        rows = [{"a": 3, "b": 3.5}, {"a": 4, "b": 4.5}]
        t = _types(rows)
        self.assertEqual(t["a"], "count")
        self.assertEqual(t["b"], "number")

    def test_low_cardinality_text_is_category_high_is_text(self):
        rows = [{"status": "OPEN", "note": f"free text {i}"} for i in range(60)]
        rows.append({"status": "CLOSED", "note": "free text 60"})
        t = _types(rows)
        self.assertEqual(t["status"], "category")
        self.assertEqual(t["note"], "text")

    def test_postgres_decimal_is_numeric(self):
        rows = [{"ratio": Decimal("0.83")}, {"ratio": Decimal("0.79")}]
        cols, summary = describe_result(rows, truncated=False)
        self.assertTrue(cols[0]["numeric"])
        self.assertIn("ratio", summary["numeric_aggregates"])

    def test_unhashable_cells_do_not_crash(self):
        # PostgreSQL JSONB / array columns arrive as dicts / lists.
        rows = [{"meta": {"a": 1}, "tags": [1, 2]}, {"meta": {"b": 2}, "tags": [3]}]
        t = _types(rows)
        self.assertEqual(t["meta"], "text")
        self.assertEqual(t["tags"], "text")

    def test_ratio_is_not_forced_to_percent(self):
        t = _types([{"pass_ratio": 0.83}, {"pass_ratio": 0.5}])
        self.assertEqual(t["pass_ratio"], "number")

    def test_iso_date_strings_not_coerced_to_numeric(self):
        rows = [{"report_date": "2026-08-17"}, {"report_date": "2026-08-18"}]
        cols, _ = describe_result(rows, truncated=False)
        self.assertFalse(cols[0]["numeric"])
        self.assertEqual(cols[0]["semantic_type"], "date")  # from the name fragment


class TestSummary(unittest.TestCase):
    def test_aggregates_skip_id_columns(self):
        rows = [{"school_id": 10, "n": 5}, {"school_id": 20, "n": 15}]
        _, summary = describe_result(rows, truncated=False)
        self.assertNotIn("school_id", summary["numeric_aggregates"])
        self.assertEqual(summary["numeric_aggregates"]["n"],
                         {"sum": 20.0, "min": 5.0, "max": 15.0, "mean": 10.0})

    def test_single_value_flag(self):
        _, summary = describe_result([{"total": 5983}], truncated=False)
        self.assertTrue(summary["single_value"])
        self.assertEqual(summary["row_count"], 1)

    def test_single_value_false_for_multi_column(self):
        _, summary = describe_result([{"a": 1, "b": 2}], truncated=False)
        self.assertFalse(summary["single_value"])

    def test_single_value_false_for_text_scalar(self):
        _, summary = describe_result([{"name": "ก"}], truncated=False)
        self.assertFalse(summary["single_value"])

    def test_empty_result(self):
        cols, summary = describe_result([], truncated=False)
        self.assertEqual(cols, [])
        self.assertEqual(summary["row_count"], 0)
        self.assertFalse(summary["single_value"])

    def test_all_null_numeric_column_dropped_from_aggregates(self):
        rows = [{"x": None}, {"x": None}]
        _, summary = describe_result(rows, truncated=False)
        self.assertEqual(summary["numeric_aggregates"], {})

    def test_truncated_flag_passthrough(self):
        _, summary = describe_result([{"a": 1}], truncated=True)
        self.assertTrue(summary["truncated"])


if __name__ == "__main__":
    unittest.main()
