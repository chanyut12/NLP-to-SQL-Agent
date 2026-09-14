"""Envelope-expansion contract tests (ticket #19, parent spec #13).

At the HTTP seam, with the NLP engine faked: the request accepts an optional
history of structured prior Turns; the response carries answer_type / message /
steps_used; STEP_BUDGET_EXCEEDED is a recognised error code. Omitting history
reproduces the legacy one-shot envelope exactly. The agent loop that *consumes*
history is ticket #20 — here the contract is what is pinned.
"""

import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

# Must be set before core.config / api.main are imported. Set (not pop) so a
# stray load_dotenv() from the import chain can't repopulate these from .env.
os.environ["API_KEY"] = "test-secret"
os.environ["DATABASE_URL"] = ""

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from fastapi.testclient import TestClient

from api import dependencies as deps
from api.main import app
from api.schemas import QueryError
from core.services.agent import AgentTurnResult

client = TestClient(app)

RESULT_TURN = {"question": "จำนวนนักเรียนแยกโรงเรียน", "answer_type": "result",
               "sql": "SELECT school_id, COUNT(*) FROM student GROUP BY school_id",
               "row_count": 12}
CLARIFY_TURN = {"question": "ความเสี่ยงคืออะไร", "answer_type": "clarification"}


class _FakeEngine:
    """Stands in for NLPEngine: one legacy one-shot result, one canned Turn."""

    async def query_database(self, **kwargs):
        return ("SELECT 1 AS n", [{"n": 1}], None, 0, None, 0)

    async def agent_query_database(self, **kwargs):
        return AgentTurnResult(answer_type="result", steps_used=1,
                               sql="SELECT 1 AS n", rows=[{"n": 1}],
                               row_count=1)


class EnvelopeTestBase(unittest.TestCase):
    def setUp(self):
        self._orig_db = deps.state_manager.db_engine
        self._orig_nlp = deps.state_manager.nlp_engine
        deps.state_manager.db_engine = SimpleNamespace(
            dialect=SimpleNamespace(name="sqlite"))
        deps.state_manager.nlp_engine = _FakeEngine()
        tmp = tempfile.mkdtemp()
        self._tmp = tmp
        patches = mock.patch.multiple(
            "api.routes", LOG_FILE_JSONL=f"{tmp}/q.jsonl", LOG_FILE_CSV=f"{tmp}/q.csv")
        patches.start()
        self.addCleanup(patches.stop)
        self.addCleanup(self._restore)

    def _restore(self):
        deps.state_manager.db_engine = self._orig_db
        deps.state_manager.nlp_engine = self._orig_nlp


class TestLegacyBehaviour(EnvelopeTestBase):
    def test_no_history_returns_result_envelope_with_legacy_fields(self):
        r = client.post("/api/query", json={"question": "จำนวนนักเรียนทั้งหมด"},
                        headers={"X-API-Key": "test-secret"})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["answer_type"], "result")
        self.assertIsNone(body["message"])
        self.assertEqual(body["steps_used"], 1)
        # legacy fields unchanged
        self.assertEqual(body["sql"], "SELECT 1 AS n")
        self.assertEqual(body["row_count"], 1)
        self.assertEqual(body["rows"], [{"n": 1}])
        self.assertIn("request_id", body)
        self.assertIn("elapsed_ms", body)

    def test_explicit_null_history_is_treated_as_omitted(self):
        r = client.post("/api/query", json={"question": "x", "history": None},
                        headers={"X-API-Key": "test-secret"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["answer_type"], "result")


class TestHistoryValidation(EnvelopeTestBase):
    def test_valid_history_is_accepted(self):
        r = client.post("/api/query",
                        json={"question": "โรงเรียนเดียวกันที่เสี่ยงสูงสุด",
                              "history": [RESULT_TURN, CLARIFY_TURN]},
                        headers={"X-API-Key": "test-secret"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["answer_type"], "result")

    def test_result_turn_without_sql_is_rejected(self):
        bad = {"question": "q", "answer_type": "result", "sql": "   "}
        r = client.post("/api/query", json={"question": "x", "history": [bad]},
                        headers={"X-API-Key": "test-secret"})
        self.assertEqual(r.status_code, 422)

    def test_clarification_turn_with_sql_is_rejected(self):
        bad = {"question": "q", "answer_type": "clarification",
               "sql": "SELECT 1"}
        r = client.post("/api/query", json={"question": "x", "history": [bad]},
                        headers={"X-API-Key": "test-secret"})
        self.assertEqual(r.status_code, 422)

    def test_refusal_turn_is_valid_without_sql(self):
        turn = {"question": "รายชื่อนักเรียนทั้งหมด", "answer_type": "refusal"}
        r = client.post("/api/query", json={"question": "x", "history": [turn]},
                        headers={"X-API-Key": "test-secret"})
        self.assertEqual(r.status_code, 200)

    def test_empty_question_is_rejected(self):
        turn = {"question": "", "answer_type": "result", "sql": "SELECT 1"}
        r = client.post("/api/query", json={"question": "x", "history": [turn]},
                        headers={"X-API-Key": "test-secret"})
        self.assertEqual(r.status_code, 422)

    def test_negative_row_count_is_rejected(self):
        turn = dict(RESULT_TURN, row_count=-1)
        r = client.post("/api/query", json={"question": "x", "history": [turn]},
                        headers={"X-API-Key": "test-secret"})
        self.assertEqual(r.status_code, 422)

    def test_unknown_answer_type_is_rejected(self):
        turn = {"question": "q", "answer_type": "maybe", "sql": "SELECT 1"}
        r = client.post("/api/query", json={"question": "x", "history": [turn]},
                        headers={"X-API-Key": "test-secret"})
        self.assertEqual(r.status_code, 422)


class TestErrorCodes(unittest.TestCase):
    def test_step_budget_exceeded_is_a_recognised_error_code(self):
        err = QueryError(code="STEP_BUDGET_EXCEEDED", message="agent ran out of steps")
        self.assertEqual(err.code, "STEP_BUDGET_EXCEEDED")

    def test_unknown_error_code_is_rejected(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            QueryError(code="SOMETHING_ELSE", message="x")


class TestAuthCoversExtendedContract(unittest.TestCase):
    def test_history_request_without_key_is_401(self):
        r = client.post("/api/query",
                        json={"question": "x", "history": [RESULT_TURN]})
        self.assertEqual(r.status_code, 401)


if __name__ == "__main__":
    unittest.main()
