"""Function-calling agent loop tests (ticket #20, ADR 0006).

At the HTTP seam with a scripted LLM (real loop, real safety validation, real
sqlite execution): follow-up resolution from history, Clarification/Refusal
answers, refusal-first ordering, the 8-step budget, safety-inside-run_sql, and
unchanged one-shot behaviour.
"""

import asyncio
import json
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ["API_KEY"] = "test-secret"
os.environ["DATABASE_URL"] = ""

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, ToolMessage
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from api import dependencies as deps
from api.main import app
from core.services import agent
from core.services.agent import (
    STEP_BUDGET_EXCEEDED,
    AgentTurnResult,
    run_agent_turn,
)

client = TestClient(app)

SCHEMA_BUNDLE = SimpleNamespace(
    sql_examples_text="(few-shot examples)",
    schema_text="CREATE TABLE schools (id INT, name TEXT); [FK -> districts.id]",
    all_tables=["schools", "student_term"],
    raw_tables={"schools": "schools(id, name, school_status)"},
    rag_count=2,
)

HISTORY = [{
    "question": "จำนวนนักเรียนแยกโรงเรียน",
    "answer_type": "result",
    "sql": "SELECT school_id, COUNT(*) FROM student_term GROUP BY school_id",
    "row_count": 12,
}]


class ScriptedLLM:
    """Replays a fixed script of AIMessages; records every prompt it sees."""

    def __init__(self, script):
        self.script = list(script)
        self.prompts = []
        self.bound_tools = None

    def bind_tools(self, tools):
        # Record what the loop binds — a real ChatOpenAI needs the tool spec
        # or it can only answer in prose and burns the step budget (ticket #21).
        self.bound_tools = tools
        return self

    async def ainvoke(self, messages):
        self.prompts.append(list(messages))
        if not self.script:
            raise AssertionError("script exhausted — loop misbehaved")
        return self.script.pop(0)


def _make_engine(sqlite_engine, llm):
    """Minimal NLPEngine-like object: exactly what the route and the loop consume."""
    class _Viz:
        def recommend(self, df, question, preferred=None):
            # same shape the real VizService emits (VizConfig-compatible)
            return {"chart_type": "table", "x_col": None, "y_col": None,
                    "options": []}

    eng = SimpleNamespace(
        _llm=llm,
        _prepare_context=lambda **kw: _async_return(SCHEMA_BUNDLE),
        _viz_service=_Viz(),
    )

    async def agent_query_database(**kw):
        return await run_agent_turn(
            eng, kw["question"], kw["engine"], dialect=kw["dialect"],
            history=kw.get("history"),
            preferred_chart_type=kw.get("preferred_chart_type"))

    eng.agent_query_database = agent_query_database
    return eng


async def _async_prepared(**kw):
    return SCHEMA_BUNDLE


def _async_return(value):
    async def _inner(*a, **k):
        return value
    return _inner()


def _sqlite_with_schools():
    eng = create_engine(
        "sqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    with eng.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE schools (id INTEGER, name TEXT)")
        conn.exec_driver_sql("INSERT INTO schools VALUES (1, 'บ้านห้วยทราย')")
    return eng


def _ai_tool(name, **args):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": "c"}])


def _ai_final(answer_type, message=""):
    return _ai_tool("final_answer", answer_type=answer_type, message=message)


class AgentLoopBase(unittest.TestCase):
    def setUp(self):
        self.db = _sqlite_with_schools()
        self._orig_db = deps.state_manager.db_engine
        self._orig_nlp = deps.state_manager.nlp_engine
        deps.state_manager.db_engine = self.db

    def tearDown(self):
        deps.state_manager.db_engine = self._orig_db
        deps.state_manager.nlp_engine = self._orig_nlp

    def _wire(self, script):
        llm = ScriptedLLM(script)
        deps.state_manager.nlp_engine = _make_engine(self.db, llm)
        tmp = tempfile.mkdtemp()
        patches = mock.patch.multiple(
            "api.routes", LOG_FILE_JSONL=f"{tmp}/q.jsonl", LOG_FILE_CSV=f"{tmp}/q.csv")
        patches.start()
        self.addCleanup(patches.stop)
        self.addCleanup(self._restore)
        self.llm = llm
        return llm

    def _restore(self):
        deps.state_manager.nlp_engine = self._orig_nlp


class TestFollowUpResolution(AgentLoopBase):
    def test_followup_with_history_resolves_prior_turn(self):
        self._wire([
            _ai_tool("run_sql", sql="SELECT id, name FROM schools WHERE id = 1"),
            _ai_final("result"),
        ])
        r = client.post("/api/query",
                        json={"question": "โรงเรียนเดียวกันแต่เฉพาะเสี่ยงสูง",
                              "history": HISTORY},
                        headers={"X-API-Key": "test-secret"})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["answer_type"], "result")
        self.assertIsNone(body["message"])
        self.assertEqual(body["steps_used"], 2)
        self.assertIn("SELECT", body["sql"])
        # history reached the model: the prior question and SQL are in the prompt
        first_prompt = self.llm.prompts[0]
        flat = " ".join(
            (m["content"] if isinstance(m, dict) else str(m.content))
            for m in first_prompt)
        self.assertIn("จำนวนนักเรียนแยกโรงเรียน", flat)
        self.assertIn("GROUP BY school_id", flat)


class TestAnswerTypes(AgentLoopBase):
    def test_ambiguous_question_yields_clarification(self):
        self._wire([_ai_final("clarification", "ต้องการดูความเสี่ยงตามตัวชี้วัดใดครับ")])
        r = client.post("/api/query",
                        json={"question": "โรงเรียนที่เสี่ยงสุดคือไหน",
                              "history": HISTORY},
                        headers={"X-API-Key": "test-secret"})
        body = r.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["answer_type"], "clarification")
        self.assertIn("ตัวชี้วัด", body["message"])
        self.assertIsNone(body["sql"])
        self.assertEqual(body["rows"], [])
        self.assertEqual(body["steps_used"], 1)

    def test_pii_question_yields_refusal(self):
        self._wire([_ai_final("refusal", "ไม่สามารถแสดงรายชื่อนักเรียนรายบุคคลได้ครับ")])
        r = client.post("/api/query",
                        json={"question": "ขอรายชื่อนักเรียนทั้งหมด",
                              "history": HISTORY},
                        headers={"X-API-Key": "test-secret"})
        body = r.json()
        self.assertEqual(body["answer_type"], "refusal")
        self.assertIn("รายบุคคล", body["message"])
        self.assertIsNone(body["sql"])

    def test_refusal_wins_when_question_is_both_ambiguous_and_pii(self):
        # ADR 0006: refusal is always checked before clarification. The model's
        # first ordered decision here is the refusal — no clarification path.
        self._wire([_ai_final("refusal", "ข้อมูลรายบุคคลอยู่นอกขอบเขตครับ")])
        r = client.post("/api/query",
                        json={"question": "ขอดูข้อมูลนักเรียนชื่อด.ต. สมศรี",
                              "history": HISTORY},
                        headers={"X-API-Key": "test-secret"})
        body = r.json()
        self.assertEqual(body["answer_type"], "refusal")
        self.assertNotEqual(body["answer_type"], "clarification")


class TestStepBudget(AgentLoopBase):
    def test_budget_exhaustion_is_a_hard_failure_with_no_sql(self):
        self._wire([_ai_tool("get_schema", table_name="schools")] * 8)
        r = client.post("/api/query",
                        json={"question": "สรุปข้อมูลหน่อย", "history": HISTORY},
                        headers={"X-API-Key": "test-secret"})
        body = r.json()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["code"], "STEP_BUDGET_EXCEEDED")
        self.assertEqual(body["steps_used"], 8)
        self.assertIsNone(body["sql"])
        self.assertEqual(len(self.llm.prompts), 8)


class TestSafetyInsideRunSql(AgentLoopBase):
    def test_unsafe_sql_never_executes_and_loop_recovers(self):
        self._wire([
            _ai_tool("run_sql", sql="DELETE FROM schools"),
            _ai_tool("run_sql", sql="SELECT id, name FROM schools"),
            _ai_final("result"),
        ])
        r = client.post("/api/query",
                        json={"question": "ลบข้อมูลโรงเรียนแล้วดูใหม่",
                              "history": HISTORY},
                        headers={"X-API-Key": "test-secret"})
        body = r.json()
        self.assertEqual(body["answer_type"], "result")
        self.assertEqual(body["steps_used"], 3)
        # the DELETE never touched the data
        with self.db.connect() as conn:
            n = conn.exec_driver_sql("SELECT COUNT(*) FROM schools").scalar()
        self.assertEqual(n, 1)
        # the model saw the safety rejection as tool output
        tool_contents = [
            m["content"] if isinstance(m, dict) else m.content
            for p in self.llm.prompts for m in p
            if (isinstance(m, dict) and m.get("role") == "tool")
            or isinstance(m, ToolMessage)
        ]
        self.assertTrue(any("read-only" in c or "Disallowed" in c
                            for c in tool_contents),
                        f"no safety rejection in tool output: {tool_contents}")

    def test_execution_error_is_returned_to_model_for_correction(self):
        self._wire([
            _ai_tool("run_sql", sql="SELECT nopes FROM schools"),
            _ai_tool("run_sql", sql="SELECT id, name FROM schools"),
            _ai_final("result"),
        ])
        r = client.post("/api/query",
                        json={"question": "q", "history": HISTORY},
                        headers={"X-API-Key": "test-secret"})
        body = r.json()
        self.assertEqual(body["answer_type"], "result")
        self.assertEqual(body["steps_used"], 3)

    def test_result_claim_without_executed_sql_is_rejected_by_tool(self):
        # final_answer(result) before any successful run_sql must not emit SQL
        self._wire([
            _ai_final("result"),
            _ai_tool("run_sql", sql="SELECT id, name FROM schools"),
            _ai_final("result"),
        ])
        r = client.post("/api/query",
                        json={"question": "q", "history": HISTORY},
                        headers={"X-API-Key": "test-secret"})
        body = r.json()
        self.assertEqual(body["answer_type"], "result")
        self.assertEqual(body["steps_used"], 3)


class TestOneShotUnchanged(AgentLoopBase):
    def test_no_history_skips_agent_and_keeps_legacy_envelope(self):
        class _Legacy:
            async def query_database(self, **kw):
                return ("SELECT 1 AS n", [{"n": 1}], None, 0, None, 0)

        self._wire([])  # empty script: any agent call would crash the test
        deps.state_manager.nlp_engine = _Legacy()
        r = client.post("/api/query", json={"question": "จำนวนนักเรียน"},
                        headers={"X-API-Key": "test-secret"})
        body = r.json()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(body["answer_type"], "result")
        self.assertEqual(body["steps_used"], 1)
        self.assertEqual(body["rows"], [{"n": 1}])
        self.assertEqual(len(self.llm.prompts), 0)  # agent loop never ran


class TestDirectLoopUnit(unittest.TestCase):
    """The loop itself, without the HTTP layer — deterministic edge cases."""

    def test_unknown_tool_is_reported_not_fatal(self):
        llm = ScriptedLLM([
            _ai_tool("peek_table", table_name="schools"),
            _ai_final("clarification", "ต้องการช่วงเวลาใดครับ"),
        ])
        eng = _make_engine(None, llm)
        res = run_agent_turn_sync(eng, "q", _sqlite_with_schools(), HISTORY)
        self.assertEqual(res.answer_type, "clarification")
        self.assertEqual(res.steps_used, 2)

    def test_prose_without_tool_call_counts_toward_budget(self):
        llm = ScriptedLLM([AIMessage(content="ผมคิดว่า...")] * 8)
        eng = _make_engine(None, llm)
        res = run_agent_turn_sync(eng, "q", _sqlite_with_schools(), HISTORY)
        self.assertEqual(res.error, STEP_BUDGET_EXCEEDED)
        self.assertEqual(res.steps_used, 8)


def run_agent_turn_sync(engine, question, db, history):
    import asyncio
    return asyncio.get_event_loop().run_until_complete(
        run_agent_turn(engine, question, db, dialect="sqlite", history=history))


class TestToolBinding(unittest.TestCase):
    def test_loop_binds_the_tool_spec_to_the_llm(self):
        # Regression: without bind_tools a real ChatOpenAI never sees the tool
        # definitions, emits prose for all 8 steps, and dies with
        # STEP_BUDGET_EXCEEDED (found live during the #21 after-run smoke).
        import asyncio
        eng = _make_engine(None, ScriptedLLM([
            AIMessage(content="", tool_calls=[{
                "name": "final_answer", "args": {
                    "answer_type": "refusal",
                    "message": "คำขอนี้อยู่นอกขอบเขต"},
                "id": "c1"}]),
        ]))
        turn = asyncio.run(run_agent_turn(
            eng, "จำนวนนักเรียนแยกโรงเรียน", None, "postgres"))
        self.assertIsNone(turn.error)
        tools = eng._llm.bound_tools
        self.assertIsNotNone(tools, "loop must bind the tool spec to the LLM")
        names = {t["function"]["name"] for t in tools}
        self.assertEqual(names, {"get_schema", "run_sql", "final_answer"})

    def test_system_prompt_classifies_before_writing_sql(self):
        """Regression (post-#21 eval): clarify 0/4 and one PII denial hunted to
        STEP_BUDGET_EXCEEDED, because the prompt ordered 'prefer run_sql
        directly'. Classification must come FIRST, with the concrete ambiguous
        shapes from the golden set, and refusals must forbid tool-hunting."""
        self.assertIn("Before any run_sql", agent.AGENT_SYSTEM_PROMPT)
        # the exact ambiguous shapes the golden set scores
        for frag in (
            "จำนวนนักเรียนแยกตามโรงเรียน",   # no population snapshot
            "เด็กเสี่ยงมีเท่าไหร่",           # no tier, no snapshot
            "การมาเรียนเป็นอย่างไรบ้าง",      # no date range
        ):
            self.assertIn(frag, agent.AGENT_SYSTEM_PROMPT,
                          "prompt must teach the ambiguous shapes explicitly")
        # a matched SQL shape, so the rule is learnable by contrast
        self.assertIn("จำนวนนักเรียนปัจจุบันแยกตามระดับชั้น",
                      agent.AGENT_SYSTEM_PROMPT)
        # vague recency without dates clarifies; the current snapshot does not
        # (regression: answer_type_04 'เคสล่าสุดมีกี่เคส' answered as SQL)
        self.assertIn("ล่าสุด", agent.AGENT_SYSTEM_PROMPT)
        self.assertIn("never reinterpret them as", agent.AGENT_SYSTEM_PROMPT)
        # refusal priority: never hunt for personal data with tools
        self.assertIn("never call get_schema or run_sql",
                      agent.AGENT_SYSTEM_PROMPT)
        # mixed requests (analytics + personal data) refuse as a whole
        self.assertIn("refuse the entire request",
                      agent.AGENT_SYSTEM_PROMPT)
        # the final_answer tool spec carries the same priority
        spec = json.dumps(agent.AGENT_TOOLS, ensure_ascii=False)
        self.assertIn("never guess", spec)

    def test_system_prompt_keeps_stateless_history_rule(self):
        """The clarify fix must not break the ADR 0006 follow-up contract."""
        self.assertIn("prior Turns", agent.AGENT_SYSTEM_PROMPT)
        self.assertIn("self-contained", agent.AGENT_SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()
