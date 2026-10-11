"""Function-calling conversational agent loop (ADR 0006, ticket #20).

One Turn = one request. The LLM is the controller: it chooses between tools
until it delivers a final answer. The service holds no memory — the Consumer
replays prior Turns from the request history.

Tools (ADR 0006 decision #6):
- get_schema(table_name)  — table-scoped schema block, unlimited
- run_sql(sql)            — read-only; safety validation runs INSIDE the tool on
                            every candidate, so the loop can wander but the
                            datasource surface stays exactly as before
- final_answer(answer_type, message) — delivers a Result, a Clarification, or a
                            Refusal; ADR 0006 refusal-first: a result claim
                            without an executed query is rejected by the tool
                            itself, so clarify/refuse remain the only exits

Budget: 8 model steps per Turn; exhaustion is a hard STEP_BUDGET_EXCEEDED
failure — never best-effort SQL (ADR 0006 decision #8).
"""

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional

import pandas as pd

from core.config import settings
from core.domain.sql_safety import SQLSafetyError, validate_and_sanitize_sql
from core.services.answer_grounding import (
    drop_ungrounded_sentences,
    fallback_message,
    ungrounded_numbers,
)

logger = logging.getLogger(__name__)

AGENT_STEP_BUDGET = int(os.getenv("AGENT_STEP_BUDGET", "8"))
STEP_BUDGET_EXCEEDED = "STEP_BUDGET_EXCEEDED"

# ADR 0010 / ticket #35: mechanical loop guards.
MAX_PROBES_AFTER_EMPTY = 2  # run_sql calls allowed after a successful 0-row query
_DUPLICATE_PREFIX = "DUPLICATE_SQL"
_EXPLORATION_PREFIX = "EXPLORATION_LIMIT"


def _normalize_sql(sql: str) -> str:
    """Whitespace/case/trailing-semicolon-insensitive key for duplicate detection."""
    return " ".join((sql or "").strip().rstrip(";").split()).lower()

ANSWER_TYPES = ("result", "clarification", "refusal")

_SAFETY_REJECTION_PREFIX = "SAFETY_REJECTED"

AGENT_SYSTEM_PROMPT = """You are a Thai natural-language-to-SQL agent for an \
aggregate analytics database. You answer ONE question per conversation Turn, \
using tools — you do not answer from memory.

### Datasource dialect:
{dialect}

### Conversation so far (prior Turns, oldest first):
{history_block}

### Current question:
{question}

### Retrieved few-shot examples:
{examples_block}

### Database schema (summary):
{schema_summary}

### Tools:
- get_schema(table_name): full column list for one table. Use when unsure \
about columns or join paths.
- run_sql(sql): executes a READ-ONLY SELECT (WITH ... SELECT allowed) against \
the datasource. Safety validation runs inside the tool — write operations and \
forbidden tables are rejected and the reason is returned to you. A LIMIT of at \
most {max_limit} is enforced automatically.
- final_answer(answer_type, message): end the Turn. answer_type is one of:
  * "result" — a query already executed successfully this Turn; message is
a short Thai paragraph (2–3 sentences) that: (1) answers the question in
words, including any "why/why-not" part when the rows support it (e.g. the
top entity and what stands out about it), (2) notes one salient fact from
the result (largest/smallest/total), and (3) stays strictly inside what the
rows show — never invent a reason the data does not contain. The Consumer
displays this message as a chat bubble next to the table/chart.
  * "clarification" — the question is ambiguous (missing measure, population \
snapshot, timeframe, or grouping); message asks ONE concrete follow-up \
question (Thai). When a genuine choice is unresolved, ask — never guess.
  * "refusal" — the request is out of scope (personal data / non-analytical \
or write requests); message explains and suggests an analytical alternative \
(Thai). Personal-data and out-of-scope requests are ALWAYS refusals, never \
clarifications.

### Rules:
1. Before any run_sql, classify the question. If it misses a concrete \
measure, population snapshot, date range, or grouping — things every \
answerable analytical question here states — call final_answer with \
answer_type "clarification", asking for exactly the missing piece. \
Ambiguous shapes from this domain: "จำนวนนักเรียนแยกตามโรงเรียน" (no snapshot), \
"เด็กเสี่ยงมีเท่าไหร่" (no risk tier, no snapshot), "การมาเรียนเป็นอย่างไรบ้าง" \
(no date range), "เคสล่าสุดมีกี่เคส" (undefined what counts as latest). Relative recency words — "ล่าสุด", \
"ช่วงนี้" — without explicit dates MUST clarify which period is meant, even \
if the retrieved examples or the schema offer a way to compute them (those \
examples are traps here); never reinterpret them as "ปัจจุบัน". Only the \
literal word "ปัจจุบัน" means the current snapshot. By \
contrast "จำนวนนักเรียนปัจจุบันแยกตามระดับชั้น" is complete — answer it directly.
2. Personal-data requests (names, contacts, guardians, individual salaries) \
and write operations are refusals — never call get_schema or run_sql to hunt \
for such data. A mixed request (analytics plus personal data, e.g. \
"นักเรียนคนไหนเสี่ยงสูงสุด ชื่ออะไร ขอเบอร์ผู้ปกครองด้วย") — refuse the \
entire request; do not answer its analytical part.
3. Decide yourself which tool to call next; prefer run_sql when the question \
passed rule 1 and the schema above already answers it.
4. Interpret pronouns and ellipsis ("โรงเรียนเดียวกัน", "แล้วตัวไหนล่ะ") from \
the prior Turns above; rewrite them into a self-contained query.
5. If run_sql fails, read the error and fix the SQL — retry with run_sql.
6. Call final_answer(result) only AFTER a successful run_sql this Turn.
7. Entity label rule: a result grouped by or filtered to one entity must \
include that entity's readable label column (its name) next to the \
measures — never the id alone; select the id only when the user asks for \
the code itself. The label column is never a person's name — person \
identifiers stay out of results per rule 2.
8. Follow-up filters ("ช่วยกรองเฉพาะ X", "เฉพาะ X", "แล้วของ X ล่ะ") modify the \
IMMEDIATELY PREVIOUS Turn: re-run that Turn's query with the new filter added \
and keep its output shape (same measure, same breakdown columns). If the \
previous Turn broke a measure down by reason/category (e.g. "สาเหตุ…"), the \
answer must list those reasons with their counts — never collapse it into one \
total, and never switch to the measure of an earlier Turn.
"""


@dataclass
class AgentTurnResult:
    """Everything the caller needs to build the envelope for one Turn."""
    answer_type: str = "result"
    message: Optional[str] = None
    sql: Optional[str] = None
    rows: Optional[List[dict]] = None
    row_count: int = 0
    truncated: bool = False
    columns: list = field(default_factory=list)
    summary: Optional[dict] = None
    viz_config: Optional[dict] = None
    steps_used: int = 0
    rag_examples_count: int = 0
    prep_ms: Optional[int] = None  # context-preparation duration (spec #27 / #31)
    error: Optional[str] = None  # error code, e.g. STEP_BUDGET_EXCEEDED
    error_message: Optional[str] = None


def _history_block(history: Optional[list]) -> str:
    if not history:
        return "(none — this is the first Turn)"
    lines = []
    for i, turn in enumerate(history, 1):
        head = f"Turn {i}: question: {turn.get('question', '')}"
        atype = turn.get("answer_type", "result")
        if atype == "result":
            head += f"\n  SQL used: {turn.get('sql', '')}"
            head += f"\n  result rows returned: {turn.get('row_count', 0)}"
        elif atype == "clarification":
            head += "\n  (the agent asked a clarifying question)"
        else:
            head += "\n  (the agent refused — out of scope)"
        lines.append(head)
    return "\n".join(lines)


AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_schema",
            "description": ("Full column list for one table. Use when unsure "
                            "about columns or join paths."),
            "parameters": {
                "type": "object",
                "properties": {
                    "table_name": {"type": "string", "description": "Exact table name"},
                },
                "required": ["table_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_sql",
            "description": ("Execute a READ-ONLY SELECT against the datasource. "
                            "Safety validation runs inside the tool — writes and "
                            "forbidden tables are rejected with the reason returned "
                            "to you. A LIMIT cap is enforced automatically."),
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {"type": "string", "description": "One SELECT statement"},
                },
                "required": ["sql"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "final_answer",
            "description": ("End the Turn. answer_type: 'result' — a query already "
                            "executed successfully this Turn; 'clarification' — the "
                            "question is ambiguous, ask ONE concrete follow-up, "
                            "never guess; 'refusal' — out of scope or personal "
                            "data."),
            "parameters": {
                "type": "object",
                "properties": {
                    "answer_type": {"type": "string",
                                    "enum": ["result", "clarification", "refusal"]},
                    "message": {"type": "string",
                                "description": "The user-facing message (Thai)"},
                    "executed_question": {"type": "string",
                                          "description": ("For result answers: the "
                                                          "self-contained question the "
                                                          "executed SQL answers")},
                },
                "required": ["answer_type", "message"],
            },
        },
    },
]


class _AgentSession:
    """Mutable per-Turn state threaded through the tool implementations."""

    def __init__(self, engine_obj, db_engine, dialect, bundle, max_limit, question):
        self.engine_obj = engine_obj
        self.db_engine = db_engine
        self.dialect = dialect
        self.bundle = bundle
        self.max_limit = max_limit
        self.question = question
        self.executed_sql: Optional[str] = None
        self.executed_rows: Optional[List[dict]] = None
        self.executed_df: Optional[pd.DataFrame] = None
        self.executed_truncated: bool = False
        self.schema_queries: list = []
        self.seen_sql: dict = {}          # normalized SQL -> tool output (ticket #35)
        self.empty_seen: bool = False     # a query executed OK with 0 rows
        self.probes_after_empty: int = 0
        self.turn_rows: list = []         # rows of every successful run_sql (grounding, ticket #36)
        self.grounding_repaired: bool = False

    # --- tool: get_schema -----------------------------------------------------
    async def tool_get_schema(self, table_name: str) -> str:
        self.schema_queries.append(table_name)
        wanted = (table_name or "").strip().lower()
        tables = self.bundle.raw_tables or {}
        for name, cols in tables.items():
            if name.lower() == wanted:
                return f"Table {name}:\n{cols}"
        # fuzzy help: list what does exist (capped)
        sample = ", ".join(sorted(tables.keys())[:40])
        return (f"Table '{table_name}' not found. Available tables "
                f"(first 40): {sample}")

    # --- tool: run_sql --------------------------------------------------------
    async def tool_run_sql(self, sql: str) -> str:
        key = _normalize_sql(sql)
        if key in self.seen_sql:
            # Same statement already ran this Turn: never hit the datasource twice.
            return (f"{_DUPLICATE_PREFIX}: this exact query already ran this Turn; "
                    f"its result was: {self.seen_sql[key]} — do not repeat it. "
                    f"Answer with final_answer, or change the approach.")
        if self.empty_seen and self.probes_after_empty >= MAX_PROBES_AFTER_EMPTY:
            return (f"{_EXPLORATION_PREFIX}: an earlier query returned 0 rows and "
                    f"you have already used {MAX_PROBES_AFTER_EMPTY} follow-up "
                    f"queries. Stop probing: call final_answer(result) now and "
                    f"state plainly what the data shows (including that no matching "
                    f"rows exist).")
        if self.empty_seen:
            self.probes_after_empty += 1
        try:
            safe = validate_and_sanitize_sql(
                sql, dialect=self.dialect, max_limit=self.max_limit,
                allowed_tables=self.bundle.all_tables)
        except SQLSafetyError as e:
            # ADR 0006: the gate lives inside the tool; the model reads the
            # rejection and can correct itself, but nothing ever executes.
            return f"{_SAFETY_REJECTION_PREFIX}: {e}"
        try:
            df = await asyncio.to_thread(pd.read_sql, safe.sql, self.db_engine)
        except Exception as e:
            err = f"EXECUTION_ERROR: {str(e)}"
            self.seen_sql[key] = err
            return err
        self.executed_sql = safe.sql
        self.executed_df = df
        self.executed_rows = df.to_dict(orient="records")
        self.turn_rows.append(self.executed_rows)
        self.executed_truncated = len(df) >= self.max_limit
        preview = df.head(20).to_dict(orient="records")
        payload = {"row_count": len(df), "truncated": self.executed_truncated,
                   "rows_preview": preview}
        if len(df) == 0:
            self.empty_seen = True
            payload["note"] = (
                "0 rows. An empty result is a valid answer when the join and "
                "filter are correct — call final_answer(result) and say that no "
                f"matching data exists. At most {MAX_PROBES_AFTER_EMPTY} more "
                "exploratory queries are allowed.")
        out = json.dumps(payload, ensure_ascii=False, default=str)
        self.seen_sql[key] = out
        return out

    # --- grounding (ADR 0010 / ticket #36) ------------------------------------
    def _user_text(self, history) -> str:
        parts = [self.question] + [t.get("question", "") for t in (history or [])]
        return " ".join(parts)

    def ground_message(self, message: str, history) -> Optional[str]:
        """None when the message is grounded. Otherwise the repair instruction
        (first time) — the caller turns a second failure into a deterministic
        message via `grounded_fallback`."""
        bad = ungrounded_numbers(message, self.turn_rows, self._user_text(history))
        if not bad:
            return None
        shown = ", ".join(f"{b:g}" for b in sorted(set(bad))[:6])
        return (f"ERROR: the message states numbers that are not in this Turn's "
                f"result rows: {shown}. State only figures shown by the rows you "
                f"retrieved (or run another query to get them); do not quote or "
                f"compare with figures from earlier Turns. Call final_answer "
                f"again.")

    def grounded_fallback(self, message: str, history) -> str:
        kept = drop_ungrounded_sentences(message, self.turn_rows, self._user_text(history))
        return kept or fallback_message(len(self.executed_rows or []))

    # --- tool: final_answer ---------------------------------------------------
    async def tool_final_answer(self, answer_type: str, message: str = "") -> str:
        if answer_type not in ANSWER_TYPES:
            return (f"ERROR: answer_type must be one of {ANSWER_TYPES}; "
                    f"call final_answer again.")
        if answer_type == "result":
            if not self.executed_sql:
                # refusal-first discipline, enforced mechanically: a Result
                # cannot be claimed for a query that never ran this Turn.
                return ("ERROR: no successful run_sql this Turn yet. Run the "
                        "query with run_sql first, or answer with "
                        "clarification/refusal instead.")
            return "OK"
        if answer_type in ("clarification", "refusal") and not (message or "").strip():
            return (f"ERROR: a {answer_type} needs a message for the user; "
                    f"call final_answer again.")
        return "OK"


def _schema_summary(bundle) -> str:
    tables = bundle.raw_tables or {}
    lines = [f"- {name}: {cols}" for name, cols in list(tables.items())[:60]]
    return "\n".join(lines)


async def run_agent_turn(
    engine_obj,
    question: str,
    db_engine,
    dialect: str,
    history: Optional[list] = None,
    max_limit: Optional[int] = None,
    preferred_chart_type: Optional[str] = None,
    on_event: Optional[Callable[[dict], None]] = None,
) -> AgentTurnResult:
    """Run one conversational Turn with the LLM as the controller.

    engine_obj is the NLPEngine (or a test double) providing ``_llm``,
    ``_prepare_context(**kw)`` and ``_viz_service``.

    on_event (optional, grilling agreement on perceived latency): receives
    Progress event dicts as the loop hits milestones — turn_started, sql_planned
    (the SQL exists the moment the model wrote it), sql_ok (row count),
    sql_failed, tool (get_schema/final_answer), turn_done. Events say nothing
    the final envelope would not; they are not part of the Session and are
    never replayed into history. Exceptions from the observer are swallowed —
    a broken listener must never break the Turn. None = exact legacy behaviour.
    """
    started = time.monotonic()
    prep_started = time.monotonic()
    seq = 0

    def emit(event: str, **fields) -> None:
        nonlocal seq
        if on_event is None:
            return
        seq += 1
        payload = {"event": event, "seq": seq,
                   "elapsed_ms": int((time.monotonic() - started) * 1000),
                   **fields}
        try:
            on_event(payload)
        except Exception:
            logger.warning("Progress-event observer raised; ignored", exc_info=True)

    if max_limit is None:
        max_limit = settings.MAX_SQL_LIMIT

    bundle = await engine_obj._prepare_context(
        question=question, engine=db_engine, dialect=dialect, agent_mode=True)
    prep_ms = int((time.monotonic() - prep_started) * 1000)
    session = _AgentSession(engine_obj, db_engine, dialect, bundle, max_limit,
                            question)

    system = AGENT_SYSTEM_PROMPT.format(
        dialect=dialect,
        history_block=_history_block(history),
        question=question,
        examples_block=bundle.sql_examples_text or "(none)",
        schema_summary=_schema_summary(bundle),
        max_limit=max_limit,
    )
    # Providers disagree on whether a messages array may hold ONLY a system
    # message: OpenAI accepts it, Zhipu rejects it with HTTP 400 code 1214
    # ("The messages parameter is illegal") — found live (Oct 2026) when
    # MODEL_PROVIDER switched to GLM-5.3-Flash and every Turn died at step 1
    # with LLM_FAILED. The question keeps its system-prompt section (prompt
    # stability for the existing provider) AND travels as the user turn, so
    # the array is valid for every OpenAI-compatible provider.
    messages: List[dict] = [
        {"role": "system", "content": system},
        {"role": "user", "content": question},
    ]
    emit("turn_started", question=question)

    llm = engine_obj._llm
    # The model cannot call tools it never sees: bind the spec once per Turn.
    # (Regression ticket #21: without this a real ChatOpenAI answers in prose
    # until the budget is gone.)
    tool_llm = llm.bind_tools(AGENT_TOOLS)
    steps = 0
    while steps < AGENT_STEP_BUDGET:
        steps += 1
        try:
            ai_msg = await tool_llm.ainvoke(messages)
        except Exception as e:
            return AgentTurnResult(
                error="LLM_FAILED", error_message=str(e), steps_used=steps,
                prep_ms=prep_ms)

        tool_calls = getattr(ai_msg, "tool_calls", None) or []
        if not tool_calls:
            # Prose without a tool call is a wasted step, not an answer —
            # the loop continues (counts toward the budget).
            messages.append({"role": "assistant", "content": str(getattr(ai_msg, "content", ""))})
            messages.append({"role": "system", "content":
                             "Respond with a tool call (get_schema, run_sql, "
                             "or final_answer) — not with prose."})
            continue

        messages.append({
            "role": "assistant",
            "content": str(getattr(ai_msg, "content", "") or ""),
            "tool_calls": [
                {"name": tc.get("name"), "args": tc.get("args", {}),
                 "id": tc.get("id") or f"call_{i}"}
                for i, tc in enumerate(tool_calls)
            ],
        })

        done: Optional[AgentTurnResult] = None
        tool_outputs = []
        for i, tc in enumerate(tool_calls):
            name = tc.get("name")
            args = tc.get("args") or {}
            call_id = tc.get("id") or f"call_{i}"
            try:
                if name == "get_schema":
                    emit("tool", tool="get_schema")
                    out = await session.tool_get_schema(args.get("table_name", ""))
                elif name == "run_sql":
                    emit("sql_planned", sql=args.get("sql", ""))
                    out = await session.tool_run_sql(args.get("sql", ""))
                    if out.startswith(_SAFETY_REJECTION_PREFIX) or out.startswith(
                            "EXECUTION_ERROR:"):
                        emit("sql_failed")
                    elif out.startswith((_DUPLICATE_PREFIX, _EXPLORATION_PREFIX)):
                        pass  # guard reply, nothing ran — no progress event
                    else:
                        try:
                            emit("sql_ok", row_count=json.loads(out).get("row_count"))
                        except Exception:
                            emit("sql_ok")
                elif name == "final_answer":
                    out = await session.tool_final_answer(
                        args.get("answer_type", ""), args.get("message", ""))
                    if out == "OK" and args.get("answer_type") == "result":
                        repair = session.ground_message(args.get("message", ""), history)
                        if repair and not session.grounding_repaired:
                            session.grounding_repaired = True
                            out = repair
                        elif repair:
                            args["message"] = session.grounded_fallback(
                                args.get("message", ""), history)
                    if out == "OK":
                        done = _build_final(session, args, bundle,
                                            preferred_chart_type, steps)
                        done.prep_ms = prep_ms
                else:
                    out = (f"ERROR: unknown tool '{name}'. "
                           f"Available tools: get_schema, run_sql, final_answer.")
            except Exception as e:
                # A tool crash must be readable by the model, never fatal to the
                # Turn — the loop is exactly the mechanism for recovering.
                logger.warning("Agent tool %s raised: %s", name, e)
                out = f"TOOL_ERROR: {e}"
            tool_outputs.append({
                "role": "tool", "tool_call_id": call_id, "name": name,
                "content": out,
            })

        messages.extend(tool_outputs)
        if done is None and AGENT_STEP_BUDGET > 3 and steps == AGENT_STEP_BUDGET - 2:
            messages.append({"role": "system", "content":
                             "Only 2 steps remain in this Turn. Do not explore "
                             "further: call final_answer now with what the data "
                             "shows (or a clarification if the question cannot "
                             "be answered)."})
        if done is not None:
            emit("turn_done", answer_type=done.answer_type,
                 row_count=done.row_count)
            return done

    emit("turn_done", answer_type="error", error=STEP_BUDGET_EXCEEDED)
    return AgentTurnResult(
        error=STEP_BUDGET_EXCEEDED,
        error_message=(f"Agent exceeded its {AGENT_STEP_BUDGET}-step budget "
                       f"without a final answer."),
        steps_used=steps,
        prep_ms=prep_ms,
    )


def _build_final(session, args, bundle, preferred_chart_type, steps) -> AgentTurnResult:
    """Assemble the Turn result from the session state at final_answer time."""
    answer_type = args.get("answer_type")
    message = (args.get("message") or "").strip() or None
    result = AgentTurnResult(answer_type=answer_type, message=message,
                             steps_used=steps,
                             rag_examples_count=bundle.rag_count)
    if answer_type == "result":
        result.sql = session.executed_sql
        result.rows = session.executed_rows
        result.row_count = len(session.executed_rows or [])
        result.truncated = session.executed_truncated
        if session.executed_df is not None:
            from core.viz.column_meta import describe_result
            col_dicts, summary_dict = describe_result(
                session.executed_rows, result.truncated)
            result.columns = col_dicts
            result.summary = summary_dict
            result.viz_config = session.engine_obj._viz_service.recommend(
                session.executed_df, session.question, preferred_chart_type)
    return result
