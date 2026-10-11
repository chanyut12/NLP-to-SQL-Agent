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
os.environ["AGENT_STEP_BUDGET"] = "8"  # tests assert the documented default, not a dev .env override
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
            _ai_final("result", "โรงเรียนเดียวกันเข้าเงื่อนไขเสี่ยงสูง 1 แห่งในภาคเรียนนี้"),
        ])
        r = client.post("/api/query",
                        json={"question": "โรงเรียนเดียวกันแต่เฉพาะเสี่ยงสูง",
                              "history": HISTORY},
                        headers={"X-API-Key": "test-secret"})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["answer_type"], "result")
        # Grilled "every Answer speaks": a result's message now reaches the
        # envelope instead of being dropped.
        self.assertEqual(body["message"],
                         "โรงเรียนเดียวกันเข้าเงื่อนไขเสี่ยงสูง 1 แห่งในภาคเรียนนี้")
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


class TestMechanicalLoopGuards(AgentLoopBase):
    """Ticket #35 / ADR 0010: guards in code, not prompt rules."""

    def _ask(self, script):
        self._wire(script)
        return client.post("/api/query",
                           json={"question": "กรองเฉพาะโรงเรียนที่ไม่มี", "history": HISTORY},
                           headers={"X-API-Key": "test-secret"}).json()

    def _tool_outputs(self):
        return [m["content"] if isinstance(m, dict) else m.content
                for m in self.llm.prompts[-1]
                if (isinstance(m, dict) and m.get("role") == "tool")
                or isinstance(m, ToolMessage)]

    def test_duplicate_sql_does_not_hit_the_datasource_twice(self):
        sql = "SELECT id, name FROM schools"
        with mock.patch("core.services.agent.pd.read_sql",
                        wraps=agent.pd.read_sql) as spy:
            body = self._ask([
                _ai_tool("run_sql", sql=sql),
                _ai_tool("run_sql", sql="  select id, name  from schools ;"),
                _ai_final("result", "มี 1 โรงเรียน"),
            ])
        self.assertEqual(body["answer_type"], "result")
        self.assertEqual(spy.call_count, 1)
        self.assertTrue(any(o.startswith("DUPLICATE_SQL") for o in self._tool_outputs()))

    def test_empty_result_carries_a_steer_to_final_answer(self):
        body = self._ask([
            _ai_tool("run_sql", sql="SELECT id FROM schools WHERE id = 99"),
            _ai_final("result", "ไม่พบข้อมูล"),
        ])
        self.assertEqual(body["answer_type"], "result")
        out = [o for o in self._tool_outputs() if '"row_count": 0' in o][0]
        self.assertIn("final_answer", json.loads(out)["note"])

    def test_probing_after_an_empty_result_is_capped(self):
        body = self._ask([
            _ai_tool("run_sql", sql="SELECT id FROM schools WHERE id = 99"),
            _ai_tool("run_sql", sql="SELECT id FROM schools WHERE id = 98"),
            _ai_tool("run_sql", sql="SELECT id FROM schools WHERE id = 97"),
            _ai_tool("run_sql", sql="SELECT id FROM schools WHERE id = 96"),
            _ai_final("result", "ไม่พบข้อมูล"),
        ])
        self.assertEqual(body["answer_type"], "result")
        self.assertTrue(any(o.startswith("EXPLORATION_LIMIT") for o in self._tool_outputs()))
        self.assertEqual(body["steps_used"], 5)

    def test_warns_when_two_steps_remain(self):
        self._ask([_ai_tool("get_schema", table_name="schools")] * 8)
        warned = [m for m in self.llm.prompts[-1]
                  if isinstance(m, dict) and m.get("role") == "system"
                  and "Only 2 steps remain" in m.get("content", "")]
        self.assertEqual(len(warned), 1)

    def test_prompt_no_longer_carries_the_empty_result_rule(self):
        self._ask([_ai_final("clarification", "ขอช่วงเวลา")])
        system = self.llm.prompts[0][0]["content"]
        self.assertNotIn("Empty results are answers", system)


class TestGroundingInLoop(AgentLoopBase):
    """Ticket #36: numbers in the final message must come from this Turn's rows."""

    def _ask(self, script):
        self._wire(script)
        return client.post("/api/query",
                           json={"question": "มีโรงเรียนกี่แห่ง", "history": HISTORY},
                           headers={"X-API-Key": "test-secret"}).json()

    def test_grounded_message_passes_untouched(self):
        body = self._ask([_ai_tool("run_sql", sql="SELECT id, name FROM schools"),
                          _ai_final("result", "มี 1 โรงเรียน")])
        self.assertEqual(body["message"], "มี 1 โรงเรียน")
        self.assertEqual(body["steps_used"], 2)

    def test_foreign_number_triggers_one_repair_step(self):
        body = self._ask([_ai_tool("run_sql", sql="SELECT id, name FROM schools"),
                          _ai_final("result", "มี 1 โรงเรียน แต่กรุงเทพฯ สูงสุด 76 คน"),
                          _ai_final("result", "มี 1 โรงเรียน")])
        self.assertEqual(body["message"], "มี 1 โรงเรียน")
        self.assertEqual(body["steps_used"], 3)
        errs = [m["content"] for m in self.llm.prompts[-1]
                if isinstance(m, dict) and m.get("role") == "tool"
                and "not in this Turn" in m["content"]]
        self.assertEqual(len(errs), 1)
        self.assertIn("76", errs[0])

    def test_second_violation_is_replaced_by_a_deterministic_message(self):
        body = self._ask([_ai_tool("run_sql", sql="SELECT id, name FROM schools"),
                          _ai_final("result", "กรุงเทพฯ สูงสุด 76 คน"),
                          _ai_final("result", "กรุงเทพฯ สูงสุด 76 คน")])
        self.assertEqual(body["answer_type"], "result")
        self.assertNotIn("76", body["message"])
        self.assertIn("1", body["message"])

    def test_clarification_and_refusal_are_not_grounded_against_rows(self):
        body = self._ask([_ai_final("clarification", "ต้องการข้อมูลปี 2569 หรือ 2570")])
        self.assertEqual(body["answer_type"], "clarification")


class TestDataKnowledgeTools(AgentLoopBase):
    """Ticket #37: describe_table / sample_values."""

    def _ask(self, script):
        self._wire(script)
        return client.post("/api/query",
                           json={"question": "โรงเรียนมีกี่แห่ง", "history": HISTORY},
                           headers={"X-API-Key": "test-secret"}).json()

    def _tool_outputs(self):
        return [m["content"] for m in self.llm.prompts[-1]
                if isinstance(m, dict) and m.get("role") == "tool"]

    def test_tools_are_bound_and_in_the_prompt(self):
        self._ask([_ai_final("clarification", "ขอรายละเอียด")])
        names = [t["function"]["name"] for t in self.llm.bound_tools]
        self.assertIn("describe_table", names)
        self.assertIn("sample_values", names)
        self.assertIn("describe_table(table_name)", self.llm.prompts[0][0]["content"])

    def test_describe_table_returns_population_notes(self):
        self._ask([_ai_tool("describe_table", table_name="schools"),
                   _ai_final("clarification", "ขอรายละเอียด")])
        out = self._tool_outputs()[0]
        self.assertIn("Population", out)
        self.assertIn("deleted_at", out)  # schools has no deleted_at — the Oct 2026 lesson

    def test_describe_unknown_table_lists_available(self):
        self._ask([_ai_tool("describe_table", table_name="nope"),
                   _ai_final("clarification", "ขอรายละเอียด")])
        self.assertIn("not found", self._tool_outputs()[0])

    def test_sample_values_returns_real_values(self):
        self._ask([_ai_tool("sample_values", table_name="schools", column_name="name"),
                   _ai_final("clarification", "ขอรายละเอียด")])
        out = json.loads(self._tool_outputs()[0])
        self.assertEqual(out["values"], ["บ้านห้วยทราย"])
        self.assertFalse(out["more_values_exist"])

    def test_sample_values_refuses_personal_columns_and_bad_identifiers(self):
        self._ask([_ai_tool("sample_values", table_name="schools", column_name="citizen_id"),
                   _ai_tool("sample_values", table_name="schools", column_name='name"; --'),
                   _ai_final("clarification", "ขอรายละเอียด")])
        outs = self._tool_outputs()
        self.assertTrue(outs[0].startswith("REFUSED"))
        self.assertTrue(outs[1].startswith("REFUSED"))

    def test_sampling_never_satisfies_the_result_gate(self):
        body = self._ask([_ai_tool("sample_values", table_name="schools", column_name="name"),
                          _ai_final("result", "มีโรงเรียน"),
                          _ai_final("clarification", "ขอรายละเอียด")])
        self.assertEqual(body["answer_type"], "clarification")
        self.assertTrue(any("no successful run_sql" in o for o in self._tool_outputs()))


class TestDigestInEnvelope(AgentLoopBase):
    def test_result_envelope_carries_turn_digest_and_clarification_does_not(self):
        self._wire([_ai_tool("run_sql", sql="SELECT id, name FROM schools WHERE id = 1"),
                    _ai_final("result", "มี 1 โรงเรียน")])
        body = client.post("/api/query", json={"question": "โรงเรียนมีกี่แห่ง", "history": HISTORY},
                           headers={"X-API-Key": "test-secret"}).json()
        d = body["turn_digest"]
        self.assertEqual(d["tables"], ["schools"])
        self.assertEqual(d["filters"], ["id = 1"])
        self.assertEqual(d["row_count"], 1)

    def test_clarification_has_no_digest(self):
        self._wire([_ai_final("clarification", "ขอรายละเอียด")])
        body = client.post("/api/query", json={"question": "ขอข้อมูล", "history": HISTORY},
                           headers={"X-API-Key": "test-secret"}).json()
        self.assertIsNone(body.get("turn_digest"))

    def test_prior_turn_digest_reaches_the_prompt_and_is_optional(self):
        digest = {"tables": ["schools"], "populations": {"schools": "All schools."},
                  "filters": [], "group_by": [], "columns": [], "top_rows": [], "row_count": 12}
        hist = [dict(HISTORY[0], digest=digest)]
        self._wire([_ai_final("clarification", "ขอรายละเอียด")])
        r = client.post("/api/query", json={"question": "ขอข้อมูล", "history": hist},
                        headers={"X-API-Key": "test-secret"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("population of schools: All schools.", self.llm.prompts[0][0]["content"])


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
        self.assertEqual(names, {"get_schema", "describe_table", "sample_values",
                                 "run_sql", "final_answer"})

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


class TestAgentModeContext(unittest.TestCase):
    """The agent loop must request agent_mode=True so _prepare_context skips
    smart_filter's Tier-3 LLM table-guessing — that fallback is a recovery path
    for the one-shot chain, which cannot recover; the loop recovers via the
    get_schema tool instead, so in agent mode the extra call is a duplicate,
    unbudgeted LLM call per Turn (latency-grilling decision).
    """

    def test_agent_turn_requests_agent_mode_from_prepare_context(self):
        captured = {}

        async def prep(**kw):
            captured.update(kw)
            return SimpleNamespace(
                sql_examples_text="(few-shot examples)",
                all_tables=["schools"],
                raw_tables={"schools": "schools(id, name)"},
                rag_count=0,
            )

        llm = ScriptedLLM([_ai_final("clarification", "ต้องการช่วงเวลาใดครับ")])
        eng = SimpleNamespace(_llm=llm, _prepare_context=prep)
        turn = asyncio.run(run_agent_turn(eng, "q", None, "postgres"))
        self.assertIsNone(turn.error)
        self.assertTrue(captured.get("agent_mode"))


class TestProviderPortableMessages(unittest.TestCase):
    """Regression (found live, Oct 2026): the loop opened with a system-only
    messages array. OpenAI accepts that shape; Zhipu rejects it with HTTP 400
    code 1214 ("The messages parameter is illegal"), so the moment
    MODEL_PROVIDER became GLM-5.3-Flash every Turn failed at step 1 with
    LLM_FAILED. The question now also travels as a user turn, so the array is
    valid for every OpenAI-compatible provider.
    """

    def test_every_call_carries_a_non_system_turn_with_the_question(self):
        question = "จำนวนนักเรียนแยกโรงเรียน"
        llm = ScriptedLLM([_ai_final("refusal", "คำขอนี้อยู่นอกขอบเขต")])
        eng = _make_engine(None, llm)

        turn = asyncio.run(run_agent_turn(eng, question, None, "postgres"))

        self.assertIsNone(turn.error)
        self.assertTrue(llm.prompts, "the loop must have called the LLM")
        for i, prompt in enumerate(llm.prompts):
            roles = [m["role"] for m in prompt]
            self.assertIn("system", roles)
            self.assertTrue(
                any(m["role"] == "user" for m in prompt),
                f"call {i} sent a system-only array — rejected by Zhipu (1214)",
            )
        first = llm.prompts[0]
        self.assertTrue(
            any(m["role"] == "user" and question in m["content"] for m in first),
            "the user turn must carry the question",
        )


if __name__ == "__main__":
    unittest.main()
