"""Turn digest (ADR 0010, ticket #34): deterministic, replayable, backward compatible."""

import os
import sys
import unittest

os.environ["API_KEY"] = "test-secret"
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from core.profiles import load_table_notes
from core.services.agent import _history_block
from core.services.turn_digest import build_turn_digest, digest_block

NOTES = load_table_notes("sts")
SQL = ("SELECT crs.signal_reason, CAST(COUNT(*) AS INT) AS c FROM case_risk_signals crs "
       "JOIN cases ON cases.id = crs.case_id WHERE cases.status = 'OPEN' AND cases.school_id = 3 "
       "GROUP BY crs.signal_reason ORDER BY c DESC LIMIT 20")
COLS = [{"name": "signal_reason", "semantic_type": "text"}, {"name": "c", "semantic_type": "count"}]
ROWS = [{"signal_reason": "ขาด 8 วัน", "c": 1}]


class TestBuild(unittest.TestCase):
    def test_describes_tables_populations_filters_and_grouping(self):
        d = build_turn_digest(SQL, ROWS, COLS, 1, NOTES)
        self.assertEqual(d["tables"], ["case_risk_signals", "cases"])
        self.assertIn("opened cases only", d["populations"]["case_risk_signals"])
        self.assertEqual(d["filters"], ["cases.status = 'OPEN'", "cases.school_id = 3"])
        self.assertEqual(d["group_by"], ["crs.signal_reason"])
        self.assertEqual(d["top_rows"], ROWS)
        self.assertEqual(d["row_count"], 1)

    def test_deterministic(self):
        self.assertEqual(build_turn_digest(SQL, ROWS, COLS, 1, NOTES),
                         build_turn_digest(SQL, ROWS, COLS, 1, NOTES))

    def test_no_sql_no_digest(self):
        self.assertIsNone(build_turn_digest(None, [], [], 0, NOTES))
        self.assertIsNone(build_turn_digest("  ", [], [], 0, NOTES))

    def test_unparseable_sql_still_yields_a_partial_digest(self):
        d = build_turn_digest("SELEKT ??? FROM", ROWS, COLS, 1, NOTES)
        self.assertEqual(d["tables"], [])
        self.assertEqual(d["row_count"], 1)

    def test_personal_columns_never_enter_top_rows(self):
        cols = [{"name": "student_name", "semantic_type": "name"}, {"name": "c", "semantic_type": "count"}]
        d = build_turn_digest("SELECT 1", [{"student_name": "x", "c": 2}], cols, 1, NOTES)
        self.assertEqual(d["top_rows"], [{"c": 2}])

    def test_bounded_size(self):
        rows = [{"signal_reason": "ก" * 500, "c": i} for i in range(50)]
        d = build_turn_digest(SQL, rows, COLS, 50, NOTES)
        self.assertEqual(len(d["top_rows"]), 3)
        self.assertLessEqual(len(d["top_rows"][0]["signal_reason"]), 60)

    def test_cte_names_are_not_tables(self):
        d = build_turn_digest("WITH x AS (SELECT id FROM schools) SELECT * FROM x", [], [], 0, NOTES)
        self.assertEqual(d["tables"], ["schools"])


class TestHistoryBlock(unittest.TestCase):
    def test_digest_is_rendered_and_followup_instruction_present(self):
        d = build_turn_digest(SQL, ROWS, COLS, 1, NOTES)
        block = _history_block([{"question": "สาเหตุ", "answer_type": "result",
                                 "sql": SQL, "row_count": 1, "digest": d}])
        self.assertIn("MOST RECENT Turn", block)
        self.assertIn("population of case_risk_signals", block)
        self.assertIn("filters: cases.status = 'OPEN' AND cases.school_id = 3", block)
        self.assertIn("SQL used:", block)  # SQL is kept — digest supplements it

    def test_history_without_digest_is_sql_only_as_before(self):
        block = _history_block([{"question": "q", "answer_type": "result",
                                 "sql": "SELECT 1", "row_count": 1}])
        self.assertIn("SQL used: SELECT 1", block)
        self.assertNotIn("population of", block)
        self.assertEqual(digest_block(None), [])


if __name__ == "__main__":
    unittest.main()
