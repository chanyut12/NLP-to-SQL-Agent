"""describe_table / sample_values helpers and the STS notes file (ADR 0010, #37)."""

import json
import os
import sys
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from core.profiles import load_table_notes
from core.services.data_knowledge import column_blocked, format_table_notes, is_identifier


class TestGuards(unittest.TestCase):
    def test_identifiers_only(self):
        self.assertTrue(is_identifier("school_status"))
        self.assertFalse(is_identifier('x"; DROP TABLE y; --'))
        self.assertFalse(is_identifier(""))

    def test_personal_columns_blocked_with_or_without_notes(self):
        for col in ["first_name", "FirstName_Onec", "citizen_id", "phone", "email",
                    "address_line", "student_name", "password_hash", "line_id",
                    "photo_storage_key", "address_latitude"]:
            self.assertTrue(column_blocked(col, None), col)
            self.assertTrue(column_blocked(col, load_table_notes("sts")), col)

    def test_analytic_columns_not_blocked(self):
        notes = load_table_notes("sts")
        for col in ["risk_tier", "province", "school_status", "AttendanceStatus",
                    "status", "task_type", "signal_reason", "name"]:
            self.assertFalse(column_blocked(col, notes), col)


class TestFormat(unittest.TestCase):
    def test_notes_include_population_and_columns(self):
        notes = load_table_notes("sts")
        out = format_table_notes("case_risk_signals", notes, "id, case_id, signal_reason")
        self.assertIn("Population", out)
        self.assertIn("NOT the cause of risk for all at-risk students", out)
        self.assertIn("All columns: id, case_id, signal_reason", out)

    def test_degrades_without_notes(self):
        out = format_table_notes("x", {}, "a, b")
        self.assertIn("no curated notes", out)
        self.assertIn("a, b", out)


class TestNotesFile(unittest.TestCase):
    def test_every_table_has_meaning_population_and_no_raw_values(self):
        notes = load_table_notes("sts")
        self.assertGreaterEqual(len(notes["tables"]), 15)
        for name, e in notes["tables"].items():
            self.assertTrue(e["meaning"] and e["population"], name)
            self.assertIsInstance(e.get("joins", []), list)

    def test_profile_without_notes_is_empty(self):
        self.assertEqual(load_table_notes("does_not_exist"), {})


if __name__ == "__main__":
    unittest.main()
