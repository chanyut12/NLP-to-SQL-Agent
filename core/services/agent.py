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
from dataclasses import dataclass, field
from typing import Any, List, Optional

import pandas as pd

from core.config import settings
from core.domain.sql_safety import SQLSafetyError, validate_and_sanitize_sql

logger = logging.getLogger(__name__)

AGENT_STEP_BUDGET = 8
STEP_BUDGET_EXCEEDED = "STEP_BUDGET_EXCEEDED"

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
  * "result" — a query already executed successfully this Turn; message \
briefly summarises the result (Thai).
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
            return f"EXECUTION_ERROR: {str(e)}"
        self.executed_sql = safe.sql
        self.executed_df = df
        self.executed_rows = df.to_dict(orient="records")
        self.executed_truncated = len(df) >= self.max_limit
        preview = df.head(20).to_dict(orient="records")
        return json.dumps(
            {"row_count": len(df), "truncated": self.executed_truncated,
             "rows_preview": preview},
            ensure_ascii=False, default=str)

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
) -> AgentTurnResult:
    """Run one conversational Turn with the LLM as the controller.

    engine_obj is the NLPEngine (or a test double) providing ``_llm``,
    ``_prepare_context(**kw)`` and ``_viz_service``.
    """
    if max_limit is None:
        max_limit = settings.MAX_SQL_LIMIT

    bundle = await engine_obj._prepare_context(
        question=question, engine=db_engine, dialect=dialect)
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
    messages: List[dict] = [{"role": "system", "content": system}]

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
                error="LLM_FAILED", error_message=str(e), steps_used=steps)

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
                    out = await session.tool_get_schema(args.get("table_name", ""))
                elif name == "run_sql":
                    out = await session.tool_run_sql(args.get("sql", ""))
                elif name == "final_answer":
                    out = await session.tool_final_answer(
                        args.get("answer_type", ""), args.get("message", ""))
                    if out == "OK":
                        done = _build_final(session, args, bundle,
                                            preferred_chart_type, steps)
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
        if done is not None:
            return done

    return AgentTurnResult(
        error=STEP_BUDGET_EXCEEDED,
        error_message=(f"Agent exceeded its {AGENT_STEP_BUDGET}-step budget "
                       f"without a final answer."),
        steps_used=steps,
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
