"""Spec #27 latency work — TDD at the single API seam.

Three work items, one seam:
- #28 warm engine at startup: schema introspection + schema-RAG indexing run in
  the background at boot (no request carries the cold-cache cost); /api/health
  reports warm/cold state.
- #30 event-loop hygiene: auxiliary endpoints (history, feedback, favorites)
  do their file I/O off the event loop. TestClient gives each request its own
  loop, so cross-request blocking cannot be observed through it — the offload
  is asserted directly: every store call must run off the main thread.
- #31 visible timing: the envelope carries ``prep_ms`` (context preparation
  duration) on both the query and streamed paths — additive field.
"""
import asyncio
import json
import os
import sqlite3
import sys
import threading
import unittest
from types import SimpleNamespace
from unittest import mock

# Auth reads settings at request time; set env before app import (project pattern).
os.environ["API_KEY"] = "test-secret"

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from api import dependencies as deps
from api.main import app
from core.services.agent import STEP_BUDGET_EXCEEDED, run_agent_turn

client = TestClient(app)

AUTH = {"X-API-Key": "test-secret"}
MAIN_THREAD = threading.main_thread()


def _ai_tool(name, **args):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": "call_0"}])


class ScriptedLLM:
    def __init__(self, script):
        self.script = list(script)

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        return self.script.pop(0)


class SlowContextEngine:
    """Test double: _prepare_context sleeps, LLM script ends the Turn."""

    def __init__(self, delay, script):
        self.delay = delay
        self._script = script
        self._llm = ScriptedLLM(script)
        self._viz_service = SimpleNamespace(recommend=lambda *a, **k: None)

    async def _prepare_context(self, **kwargs):
        await asyncio.sleep(self.delay)
        return SimpleNamespace(
            sql_examples_text="(examples)", schema_text="schema",
            all_tables=["t"], raw_tables={"t": "t(a,b)"}, raw_schema={"t": {}},
            rag_count=1, pruned=False)

    async def agent_query_database(self, **kwargs):
        from core.services.agent import run_agent_turn
        return await run_agent_turn(
            self, kwargs.get("question", ""), kwargs.get("engine"),
            dialect=kwargs.get("dialect", "sqlite"),
            history=kwargs.get("history"),
            preferred_chart_type=kwargs.get("preferred_chart_type"),
            on_event=kwargs.get("on_event"))


class _SqliteDb(sqlite3.Connection):
    """In-memory sqlite usable by pd.read_sql AND carrying .dialect like the
    SQLAlchemy engine the routes inspect."""

    dialect = SimpleNamespace(name="sqlite")


def _make_sqlite_db():
    # check_same_thread=False: pd.read_sql runs in a worker thread
    # (asyncio.to_thread inside the agent loop), not the creating thread.
    db = sqlite3.connect(":memory:", factory=_SqliteDb, check_same_thread=False)
    db.execute("CREATE TABLE t (n INTEGER)")
    db.execute("INSERT INTO t VALUES (1)")
    return db


class _SetupBase(unittest.TestCase):
    """Common stubbing: no real LLM/DB needed at this seam."""

    def _install_engine(self, engine):
        self._orig_nlp = deps.state_manager.nlp_engine
        deps.state_manager.nlp_engine = engine
        self.addCleanup(self._restore_nlp)

    def _restore_nlp(self):
        deps.state_manager.nlp_engine = self._orig_nlp

    def _stub_db(self):
        self._orig_db = deps.state_manager.db_engine
        deps.state_manager.db_engine = _make_sqlite_db()
        self.addCleanup(self._restore_db)

    def _restore_db(self):
        deps.state_manager.db_engine = self._orig_db


# ---------------------------------------------------------------- #28 warmup


class WarmableFakeEngine:
    """Records warm() calls; simulates the question-independent warm state."""

    def __init__(self):
        self.warm_calls = []
        self.warm_error = None

    async def warm(self, db_engine):
        if self.warm_error:
            raise self.warm_error
        self.warm_calls.append(db_engine)


class TestWarmEngine(_SetupBase):
    """#28: warm at startup, health reports it, failures are non-fatal."""

    def test_health_reports_warm_state_fields(self):
        r = client.get("/api/health")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "ok")
        self.assertIn("schema_cached", body)
        self.assertIn("warming", body)
        self.assertIsInstance(body["schema_cached"], bool)
        self.assertIsInstance(body["warming"], bool)

    def test_warm_engine_runs_schema_work_without_question(self):
        engine = WarmableFakeEngine()
        from api.main import _warm_engine
        asyncio.run(_warm_engine(deps.state_manager.db_engine, engine))
        self.assertEqual(len(engine.warm_calls), 1)

    def test_warm_engine_survives_failure(self):
        """_run_startup_warmup logs and continues when the engine's warm fails."""
        engine = WarmableFakeEngine()
        engine.warm_error = RuntimeError("db hiccup")
        deps.state_manager.nlp_engine = engine
        self._stub_db()
        from api.main import _run_startup_warmup
        asyncio.run(_run_startup_warmup())  # must not raise

    def test_startup_warmup_uses_engine_and_db(self):
        """The lifespan task calls engine.warm with the state manager's db."""
        engine = WarmableFakeEngine()
        deps.state_manager.nlp_engine = engine
        self._stub_db()
        from api.main import _run_startup_warmup
        asyncio.run(_run_startup_warmup())
        self.assertEqual(len(engine.warm_calls), 1)
        self.assertEqual(engine.warm_calls[0], deps.state_manager.db_engine)

    def test_startup_warmup_skipped_when_db_missing(self):
        engine = WarmableFakeEngine()
        deps.state_manager.nlp_engine = engine
        self._stub_db()
        deps.state_manager.db_engine = None
        from api.main import _run_startup_warmup
        asyncio.run(_run_startup_warmup())
        self.assertEqual(engine.warm_calls, [])

    def test_real_engine_warm_builds_schema_state(self):
        """NLPEngine.warm fills the schema cache + RAG + text cache off any
        question — verified with stubbed heavy pieces."""
        engine = deps.state_manager.nlp_engine or object()
        # Build a minimal real NLPEngine-like target: patch the module-level
        # heavy functions the warm routine uses.
        from core.services import engine as engine_mod
        raw = {"tables": {"schools": {"id": "int", "name": "text"}}}
        with mock.patch.object(engine_mod, "get_database_schema", return_value=raw), \
             mock.patch.object(engine_mod, "create_schema_rag") as mk_rag, \
             mock.patch.object(engine_mod, "format_schema_for_prompt",
                               return_value="SCHEMA_TEXT"), \
             mock.patch.object(engine_mod, "get_join_hints", return_value=""):
            rag = mock.Mock()
            mk_rag.return_value = rag
            from core.services.engine import NLPEngine
            eng = NLPEngine.__new__(NLPEngine)  # skip heavy __init__
            eng._schema_cache = None
            eng._schema_cache_ts = 0.0
            eng._current_engine = None
            eng._schema_rag = None
            eng._schema_reindex = False
            eng._schema_warmed = False
            eng._schema_lock = __import__("asyncio").Lock()
            async def _examples(*a, **k):
                return "(examples)", 0
            eng._example_store = SimpleNamespace(
                embedder=object(),
                _embedding_cache={},
                _embedding_cache_lock=threading.Lock(),
                async_format_examples_for_prompt_with_count=_examples)
            asyncio.run(eng.warm(self._stub_db_engine()))
            self.assertEqual(eng._schema_cache, raw)
            self.assertEqual(eng._all_tables_cache, ["schools"])
            self.assertEqual(eng._schema_text_cache, "SCHEMA_TEXT")
            self.assertTrue(eng._schema_warmed)
            rag.index_schema_from_db.assert_called_once()

    @staticmethod
    def _stub_db_engine():
        return SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))


# ------------------------------------------------------- #30 event-loop hygiene


class SpyStore:
    """Records which thread each store call ran on; supports 404 semantics."""

    def __init__(self):
        self.threads = []

    def load_history(self, **kw):
        self.threads.append(threading.current_thread())
        return []

    def load_favorites(self):
        self.threads.append(threading.current_thread())
        return []

    def update_feedback(self, log_id, *a, **kw):
        self.threads.append(threading.current_thread())
        return log_id != "nope"

    def save_favorite(self, **kw):
        self.threads.append(threading.current_thread())
        return SimpleNamespace(favorite_id="f1", question="q", sql="s",
                               dialect="sqlite", name="n", use_count=0)

    def delete_favorite(self, favorite_id):
        self.threads.append(threading.current_thread())
        return favorite_id != "nope"


class TestEventLoopHygiene(_SetupBase):
    """#30: every auxiliary-endpoint store call runs off the event loop.

    Called through the endpoint functions directly inside one coroutine, so
    the loop thread is known exactly — a sync store call would run ON it and
    fail the assertion; the thread-offload convention passes.
    """

    def setUp(self):
        self.store = SpyStore()
        self.state = SimpleNamespace(
            history_manager=self.store,
            db_engine=SimpleNamespace(dialect=SimpleNamespace(name="sqlite")))
        self._loop_thread = None

    def _assert_off_loop(self):
        self.assertTrue(self.store.threads, "store was never called")
        loop_thread = self._loop_thread
        for t in self.store.threads:
            self.assertIsNot(t, loop_thread,
                             "store I/O ran on the event loop thread")

    def _run_scenario(self, coro_factory):
        from api import routes

        async def scenario():
            self._loop_thread = threading.current_thread()
            return await coro_factory(routes)

        return asyncio.run(scenario())

    def test_history_io_off_loop(self):
        from api.schemas import HistoryResponse
        resp = self._run_scenario(
            lambda routes: routes.get_history(
                limit=50, dialect=None, status=None, state=self.state))
        self.assertIsInstance(resp, HistoryResponse)
        self._assert_off_loop()

    def test_feedback_io_off_loop(self):
        from api.schemas import FeedbackRequest
        req = FeedbackRequest(feedback="positive")
        resp = self._run_scenario(
            lambda routes: routes.update_feedback("log-1", req, self.state))
        self.assertEqual(resp["status"], "success")
        self._assert_off_loop()

    def test_feedback_404_semantics_kept(self):
        from api.schemas import FeedbackRequest
        from fastapi import HTTPException
        req = FeedbackRequest(feedback="positive")

        def scenario(routes):
            return routes.update_feedback("nope", req, self.state)

        with self.assertRaises(HTTPException) as ctx:
            self._run_scenario(scenario)
        self.assertEqual(ctx.exception.status_code, 404)
        self._assert_off_loop()

    def test_favorites_io_off_loop(self):
        from api.schemas import CreateFavoriteRequest, FavoritesResponse
        resp = self._run_scenario(
            lambda routes: routes.get_favorites(self.state))
        self.assertIsInstance(resp, FavoritesResponse)
        req = CreateFavoriteRequest(question="q", sql="s", dialect="sqlite")
        resp = self._run_scenario(
            lambda routes: routes.create_favorite(req, self.state))
        self.assertEqual(resp.favorite_id, "f1")
        self._assert_off_loop()

    def test_favorites_delete_404_semantics_kept(self):
        from fastapi import HTTPException

        def scenario(routes):
            return routes.delete_favorite("nope", self.state)

        with self.assertRaises(HTTPException) as ctx:
            self._run_scenario(scenario)
        self.assertEqual(ctx.exception.status_code, 404)
        self._assert_off_loop()


# ---------------------------------------------------------- #31 visible timing


class TestPrepTiming(_SetupBase):
    """#31: prep_ms in the envelope — query endpoint, stream, all answers."""

    def _engine_with_prep(self, delay, script):
        return SlowContextEngine(delay, script)

    def test_agent_result_carries_prep_ms(self):
        engine = self._engine_with_prep(0.01, [
            _ai_tool("run_sql", sql="SELECT n FROM t"),
            _ai_tool("final_answer", answer_type="result"),
        ])
        result = asyncio.run(run_agent_turn(
            engine, "คำถาม", None, dialect="sqlite", history=[]))
        self.assertEqual(result.answer_type, "result")
        self.assertIsNotNone(result.prep_ms)
        self.assertGreaterEqual(result.prep_ms, 5)

    def test_agent_clarification_carries_prep_ms(self):
        engine = self._engine_with_prep(0.01, [
            _ai_tool("final_answer", answer_type="clarification",
                     message="ขอรายละเอียดเพิ่ม"),
        ])
        result = asyncio.run(run_agent_turn(
            engine, "คำถามกำกวม", None, dialect="sqlite", history=[]))
        self.assertEqual(result.answer_type, "clarification")
        self.assertIsNotNone(result.prep_ms)

    def test_agent_error_result_still_carries_prep_ms(self):
        engine = self._engine_with_prep(0.01, [
            _ai_tool("run_sql", sql="SELECT * FROM missing_table"),
            _ai_tool("run_sql", sql="SELECT * FROM missing_table"),
            _ai_tool("run_sql", sql="SELECT * FROM missing_table"),
            _ai_tool("run_sql", sql="SELECT * FROM missing_table"),
            _ai_tool("run_sql", sql="SELECT * FROM missing_table"),
            _ai_tool("run_sql", sql="SELECT * FROM missing_table"),
            _ai_tool("run_sql", sql="SELECT * FROM missing_table"),
            _ai_tool("run_sql", sql="SELECT * FROM missing_table"),
            _ai_tool("run_sql", sql="SELECT * FROM missing_table"),
        ])
        result = asyncio.run(run_agent_turn(
            engine, "คำถาม", None, dialect="sqlite", history=[]))
        self.assertEqual(result.error, STEP_BUDGET_EXCEEDED)
        self.assertIsNotNone(result.prep_ms)

    def test_envelope_query_endpoint_has_prep_ms(self):
        engine = self._engine_with_prep(0.01, [
            _ai_tool("run_sql", sql="SELECT n FROM t"),
            _ai_tool("final_answer", answer_type="result"),
        ])
        self._install_engine(engine)
        self._stub_db()
        r = client.post("/api/query",
                        json={"question": "จำนวนนักเรียน", "history": []},
                        headers=AUTH)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "ok")
        self.assertIsInstance(body["prep_ms"], int)
        self.assertGreaterEqual(body["prep_ms"], 0)

    def test_envelope_stream_terminal_has_prep_ms(self):
        engine = self._engine_with_prep(0.01, [
            _ai_tool("run_sql", sql="SELECT n FROM t"),
            _ai_tool("final_answer", answer_type="result"),
        ])
        self._install_engine(engine)
        self._stub_db()
        r = client.post("/api/query/stream",
                        json={"question": "จำนวนนักเรียน", "history": []},
                        headers=AUTH)
        self.assertEqual(r.status_code, 200)
        payloads = [ln.split("data:", 1)[1].strip()
                    for ln in r.text.splitlines() if ln.startswith("data:")]
        final = json.loads(payloads[-1])
        self.assertIsInstance(final["prep_ms"], int)
        # the safety layer appends LIMIT; the sanitized SQL is what ships
        self.assertEqual(final["sql"], "SELECT n FROM t LIMIT 500")


if __name__ == "__main__":
    unittest.main()
