"""Engine-dispatch seam of the eval harness (ticket #21, spec #13).

- SQL-question scoring lives in eval.scoring (pure, testable) instead of
  inline in the runner.
- An agent-Turn answering a SQL question maps onto the same record fields
  the pipeline path produces, so both engines are scored identically.
- --engine picks which engine call answers SQL questions; answer-type
  questions always go through the conversational agent.
"""

import unittest

import pandas as pd

from eval.scoring import score_sql_row, turn_result_fields


class _Turn:
    """Minimal stand-in for AgentTurnResult (duck-typed on purpose)."""

    def __init__(self, sql=None, rows=None, error=None, steps_used=2,
                 answer_type="result"):
        self.sql, self.rows, self.error = sql, rows, error
        self.steps_used = steps_used
        self.answer_type = answer_type


class TestScoreSqlRow(unittest.TestCase):
    def _rec(self):
        return {"pred_sql": "SELECT 1", "sql_valid": True, "executable": True,
                "ex_pass": False, "ex_pass_relaxed": False, "grain_ok": False,
                "first_try": False, "error_class": None}

    def test_exact_match_passes_all_axes(self):
        gold = pd.DataFrame({"n": [2, 1]})
        pred = pd.DataFrame({"n": [2, 1]})
        rec = score_sql_row(self._rec(), gold, pred, retry=0)
        self.assertTrue(rec["ex_pass"])
        self.assertTrue(rec["ex_pass_relaxed"])
        self.assertTrue(rec["grain_ok"])
        self.assertTrue(rec["first_try"])
        self.assertIsNone(rec["error_class"])

    def test_retry_disqualifies_first_try_only(self):
        gold = pd.DataFrame({"n": [1]})
        rec = score_sql_row(self._rec(), gold, gold.copy(), retry=2)
        self.assertTrue(rec["ex_pass"])
        self.assertFalse(rec["first_try"])

    def test_row_count_mismatch_is_wrong_grain(self):
        gold = pd.DataFrame({"n": [1, 2, 3]})
        pred = pd.DataFrame({"n": [1, 2]})
        rec = score_sql_row(self._rec(), gold, pred, retry=0)
        self.assertFalse(rec["ex_pass"])
        self.assertFalse(rec["grain_ok"])
        self.assertEqual(rec["error_class"], "wrong_grain")

    def test_one_extra_descriptive_column_is_cols_only(self):
        gold = pd.DataFrame({"n": [3, 2]})
        pred = pd.DataFrame({"n": [3, 2], "school_name": ["a", "b"]})
        rec = score_sql_row(self._rec(), gold, pred, retry=0)
        self.assertFalse(rec["ex_pass"])
        self.assertTrue(rec["ex_pass_relaxed"])
        self.assertEqual(rec["error_class"], "cols_only")

    def test_both_metrics_wrong_is_wrong_result(self):
        # 3 columns sharing only the key: the canonical comparator (verbatim
        # from eval/run_eval.py) requires >=2 shared columns for relaxed pass,
        # so two wrong metrics must fall through to wrong_result.
        gold = pd.DataFrame({"k": ["a", "b"], "n1": [1, 2], "n2": [10, 20]})
        pred = pd.DataFrame({"k": ["a", "b"], "n1": [5, 6], "n2": [50, 60]})
        rec = score_sql_row(self._rec(), gold, pred, retry=0)
        self.assertEqual(rec["error_class"], "wrong_result")

    def test_row_order_does_not_matter(self):
        gold = pd.DataFrame({"k": ["a", "b"], "n": [1, 2]})
        pred = pd.DataFrame({"k": ["b", "a"], "n": [2, 1]})
        rec = score_sql_row(self._rec(), gold, pred, retry=0)
        self.assertTrue(rec["ex_pass"])


class TestTurnResultFields(unittest.TestCase):
    def test_successful_turn_maps_to_result_record(self):
        fields = turn_result_fields(_Turn(sql="SELECT 1", rows=[{"n": 1}]))
        self.assertEqual(fields["pred_sql"], "SELECT 1")
        self.assertTrue(fields["sql_valid"])
        self.assertTrue(fields["executable"])
        self.assertIsNone(fields["error_class"])

    def test_errored_turn_is_not_executable(self):
        fields = turn_result_fields(_Turn(error="STEP_BUDGET_EXCEEDED"))
        self.assertIsNone(fields["pred_sql"])
        self.assertFalse(fields["executable"])
        self.assertEqual(fields["error_class"], "STEP_BUDGET_EXCEEDED")


class TestEngineCallDispatch(unittest.TestCase):
    def test_pipeline_mode_uses_query_database(self):
        from eval.run_eval_sts import engine_call_for

        class Eng:
            calls = []
            async def query_database(self, q, db, dialect=None):
                self.calls.append(("pipeline", q))
                return ("SELECT 1", [], None, 0, None, None)
            async def agent_query_database(self, q, db, dialect=None):
                self.calls.append(("agent", q))
                raise AssertionError("agent path must not run in pipeline mode")

        eng = Eng()
        call = engine_call_for("pipeline", eng)
        import asyncio
        asyncio.run(call("q1", None, dialect="postgres"))
        self.assertEqual(eng.calls, [("pipeline", "q1")])

    def test_agent_mode_uses_agent_query_database(self):
        from eval.run_eval_sts import engine_call_for

        class Eng:
            calls = []
            async def query_database(self, q, db, dialect=None):
                self.calls.append(("pipeline", q))
                raise AssertionError("pipeline path must not run in agent mode")
            async def agent_query_database(self, q, db, dialect=None):
                self.calls.append(("agent", q))
                return _Turn(sql="SELECT 1", rows=[])

        eng = Eng()
        call = engine_call_for("agent", eng)
        import asyncio
        turn = asyncio.run(call("q1", None, dialect="postgres"))
        self.assertEqual(eng.calls, [("agent", "q1")])
        self.assertEqual(turn.sql, "SELECT 1")


if __name__ == "__main__":
    unittest.main()
