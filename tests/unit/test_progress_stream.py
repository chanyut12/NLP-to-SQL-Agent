"""Progress streaming tests — ADR 0006 extension agreed in the grilling session.

Two layers, one policy: the loop emits Progress events through an optional
``on_event`` callback (None = exactly today's behaviour); the API layer turns
them into an SSE stream that terminates with the standard envelope as its final
event. Progress events are never part of the Session (never replayed into
history) and reveal nothing the final envelope does not also contain.
"""
import asyncio
import json
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

# Auth (require_api_key) reads settings at request time; set the env before the
# app imports settings — same pattern as test_api_service.py.
os.environ["API_KEY"] = "test-secret"

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from api import dependencies as deps
from api.main import app
from core.services.agent import run_agent_turn

client = TestClient(app)

# ---------------------------------------------------------------- loop layer


class ScriptedLLM:
    """Replays a fixed script of AIMessages; records every prompt it sees."""

    def __init__(self, script):
        self.script = list(script)
        self.prompts = []
        self.bound_tools = None

    def bind_tools(self, tools):
        self.bound_tools = tools
        return self

    async def ainvoke(self, messages):
        self.prompts.append(list(messages))
        if not self.script:
            raise AssertionError("script exhausted — loop misbehaved")
        return self.script.pop(0)


SCHEMA_BUNDLE = SimpleNamespace(
    sql_examples_text="(few-shot examples)",
    schema_text="CREATE TABLE schools (id INT, name TEXT);",
    all_tables=["schools"],
    raw_tables={"schools": "schools(id, name, school_status)"},
    rag_count=2,
)


def _async_prepared(**kw):
    async def _inner(**kw2):
        return SCHEMA_BUNDLE
    return _inner


def _async_return(value):
    async def _inner(*a, **k):
        return value
    return _inner()


def _sqlite_with_schools():
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool
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


def _make_engine(sqlite_engine, llm):
    class _Viz:
        def recommend(self, df, question, preferred=None):
            return {"chart_type": "table", "x_col": None, "y_col": None,
                    "options": []}

    eng = SimpleNamespace(
        _llm=llm,
        _prepare_context=_async_prepared(),
        _viz_service=_Viz(),
    )

    async def agent_query_database(**kw):
        return await run_agent_turn(
            eng, kw["question"], kw["engine"], dialect=kw["dialect"],
            history=kw.get("history"),
            preferred_chart_type=kw.get("preferred_chart_type"),
            on_event=kw.get("on_event"))

    eng.agent_query_database = agent_query_database
    return eng


class LoopBase(unittest.TestCase):
    def setUp(self):
        self.db = _sqlite_with_schools()
        self.events = []
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


class TestLoopCallback(LoopBase):
    def test_result_turn_emits_expected_milestones(self):
        self._wire([
            _ai_tool("run_sql", sql="SELECT id, name FROM schools WHERE id = 1"),
            _ai_final("result"),
        ])
        result = asyncio.run(run_agent_turn(
            deps.state_manager.nlp_engine, "โรงเรียน id 1", self.db,
            dialect="sqlite", history=[],
            on_event=lambda e: self.events.append(e)))
        self.assertEqual(result.answer_type, "result")
        kinds = [e["event"] for e in self.events]
        self.assertEqual(kinds[0], "turn_started")
        self.assertIn("sql_planned", kinds)
        self.assertIn("sql_ok", kinds)
        self.assertEqual(kinds[-1], "turn_done")
        # every event carries the shared envelope of the protocol
        for e in self.events:
            self.assertIn("seq", e)
            self.assertIn("elapsed_ms", e)
        sql_ok = next(e for e in self.events if e["event"] == "sql_ok")
        self.assertEqual(sql_ok["row_count"], 1)
        # sql_planned carries the SQL the moment it exists — the heart of the
        # perceived-latency win
        planned = next(e for e in self.events if e["event"] == "sql_planned")
        self.assertIn("SELECT", planned["sql"])

    def test_clarify_turn_skips_sql_events(self):
        self._wire([_ai_final("clarification", "เสี่ยงหมายถึงอะไรครับ")])
        result = asyncio.run(run_agent_turn(
            deps.state_manager.nlp_engine, "เด็กเสี่ยงมีเท่าไหร่", self.db,
            dialect="sqlite", history=[],
            on_event=lambda e: self.events.append(e)))
        self.assertEqual(result.answer_type, "clarification")
        kinds = [e["event"] for e in self.events]
        self.assertNotIn("sql_planned", kinds)
        self.assertNotIn("sql_ok", kinds)
        self.assertEqual(kinds[-1], "turn_done")

    def test_no_callback_is_exact_legacy_behaviour(self):
        self._wire([
            _ai_tool("run_sql", sql="SELECT id, name FROM schools WHERE id = 1"),
            _ai_final("result"),
        ])
        result = asyncio.run(run_agent_turn(
            deps.state_manager.nlp_engine, "โรงเรียน id 1", self.db,
            dialect="sqlite", history=[]))
        self.assertEqual(result.answer_type, "result")
        self.assertEqual(result.row_count, 1)

    def test_sql_failure_emits_sql_failed_then_final(self):
        self._wire([
            _ai_tool("run_sql", sql="DELETE FROM schools"),
            _ai_final("refusal", "ระบบไม่รับคำสั่งเขียนฐานข้อมูล"),
        ])
        result = asyncio.run(run_agent_turn(
            deps.state_manager.nlp_engine, "ลบข้อมูล", self.db,
            dialect="sqlite", history=[],
            on_event=lambda e: self.events.append(e)))
        kinds = [e["event"] for e in self.events]
        self.assertIn("sql_failed", kinds)
        self.assertEqual(kinds[-1], "turn_done")

    def test_callback_exception_never_breaks_the_turn(self):
        def boom(e):
            raise RuntimeError("observer bug")
        self._wire([
            _ai_tool("run_sql", sql="SELECT id, name FROM schools WHERE id = 1"),
            _ai_final("result"),
        ])
        result = asyncio.run(run_agent_turn(
            deps.state_manager.nlp_engine, "โรงเรียน id 1", self.db,
            dialect="sqlite", history=[], on_event=boom))
        self.assertEqual(result.answer_type, "result")


# ------------------------------------------------------------------ SSE layer


class _FakeEngine:
    """Canned Turn + canned progress events for the API-seam tests."""

    async def query_database(self, **kwargs):
        return ("SELECT 1 AS n", [{"n": 1}], None, 0, None, 0)

    async def agent_query_database(self, **kwargs):
        on_event = kwargs.get("on_event")
        if on_event:
            on_event({"event": "sql_planned", "seq": 1, "elapsed_ms": 10,
                      "sql": "SELECT 1 AS n"})
            on_event({"event": "sql_ok", "seq": 2, "elapsed_ms": 20,
                      "row_count": 1})
        from core.services.agent import AgentTurnResult
        return AgentTurnResult(answer_type="result", steps_used=1,
                               sql="SELECT 1 AS n", rows=[{"n": 1}], row_count=1)


class SseBase(unittest.TestCase):
    def setUp(self):
        self._orig_db = deps.state_manager.db_engine
        self._orig_nlp = deps.state_manager.nlp_engine
        deps.state_manager.db_engine = SimpleNamespace(
            dialect=SimpleNamespace(name="sqlite"))
        deps.state_manager.nlp_engine = _FakeEngine()
        tmp = tempfile.mkdtemp()
        patches = mock.patch.multiple(
            "api.routes", LOG_FILE_JSONL=f"{tmp}/q.jsonl", LOG_FILE_CSV=f"{tmp}/q.csv")
        patches.start()
        self.addCleanup(patches.stop)
        self.addCleanup(self._restore)

    def tearDown(self):
        self._restore()

    def _restore(self):
        deps.state_manager.db_engine = self._orig_db
        deps.state_manager.nlp_engine = self._orig_nlp


def _parse_sse(text: str):
    """Parse the SSE text body into (list of data payloads, event-name list)."""
    payloads, names, buf, name = [], [], [], None
    for line in text.splitlines():
        if line.startswith("event:"):
            name = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            buf.append(line.split(":", 1)[1].strip())
        elif not line.strip() and buf:
            payloads.append("\n".join(buf))
            names.append(name or "message")
            buf, name = [], None
    return payloads, names


class TestSseStream(SseBase):
    def test_stream_emits_progress_then_terminal_envelope(self):
        r = client.post("/api/query/stream",
                        json={"question": "จำนวนนักเรียนทั้งหมด", "history": []},
                        headers={"X-API-Key": "test-secret"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/event-stream", r.headers["content-type"])
        payloads, names = _parse_sse(r.text)
        self.assertGreaterEqual(len(payloads), 3)  # start + 2 progress + envelope
        # every event is valid JSON with a type
        events = [json.loads(p) for p in payloads]
        # terminal event IS the standard envelope — same fields as /api/query
        final = events[-1]
        self.assertEqual(final["status"], "ok")
        self.assertEqual(final["answer_type"], "result")
        self.assertEqual(final["sql"], "SELECT 1 AS n")
        self.assertEqual(final["row_count"], 1)
        self.assertIn("request_id", final)
        self.assertIn("elapsed_ms", final)
        # progress events carry the agreed disclosure: tool + sql + row count
        kinds = [e.get("event") for e in events[:-1]]
        self.assertIn("sql_planned", kinds)
        self.assertIn("sql_ok", kinds)
        planned = next(e for e in events if e.get("event") == "sql_planned")
        self.assertEqual(planned["sql"], "SELECT 1 AS n")

    def test_stream_requires_api_key_like_legacy(self):
        r = client.post("/api/query/stream",
                        json={"question": "x", "history": []})
        self.assertIn(r.status_code, (401, 403))

    def test_stream_without_datasource_is_503(self):
        deps.state_manager.db_engine = None
        r = client.post("/api/query/stream",
                        json={"question": "x", "history": []},
                        headers={"X-API-Key": "test-secret"})
        self.assertEqual(r.status_code, 503)

    def test_legacy_endpoint_untouched(self):
        r = client.post("/api/query", json={"question": "จำนวนนักเรียนทั้งหมด"},
                        headers={"X-API-Key": "test-secret"})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["answer_type"], "result")


if __name__ == "__main__":
    unittest.main()
