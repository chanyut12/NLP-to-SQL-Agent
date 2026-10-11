from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from api.schemas import (
    QueryRequest, QueryResponse, QueryError, ResultSummary,
    SchemaResponse, TableInfo, ColumnInfo,
    HistoryResponse, HistoryItem,
    FavoritesResponse, FavoriteItem, CreateFavoriteRequest,
    FeedbackRequest
)
from api.dependencies import get_state_manager, get_nlp_engine, GlobalStateManager
from core.services.engine import NLPEngine
from core.services.agent import AgentTurnResult
from core.domain.schema_utils import get_database_schema
from core.viz.column_meta import describe_result
from core.utils.sql_metrics import parse_sql_metrics
from core.config import settings
import uuid
import json
import csv
import time
from datetime import datetime
import os
import asyncio
import threading

router = APIRouter()

# --- Helper: Logging ---
LOG_FILE_JSONL = "query_logs.jsonl"
LOG_FILE_CSV = "query_logs.csv"
_LOG_WRITE_LOCK = threading.Lock()

def log_query_to_file(
    question, sql, status, error_msg="", duration=0, dialect="sqlite", retry_count=0,
    tables_used=None, join_count=0, has_aggregation=False, has_subquery=False,
    has_group_by=False, result_row_count=-1, rag_examples_count=0, model_name=""
):
    log_id = str(uuid.uuid4())
    timestamp = datetime.now().isoformat()
    if tables_used is None:
        tables_used = []

    # Keep the two-file write serialized in-process to reduce interleaving risk.
    with _LOG_WRITE_LOCK:
        # 1. JSONL Logging (Rich Data)
        entry = {
            "log_id": log_id,
            "timestamp": timestamp,
            "question": question,
            "sql": sql,
            "status": status,
            "error_msg": error_msg,
            "duration_sec": duration,
            "dialect": dialect,
            "retry_count": retry_count,
            "feedback": "",
            "tables_used": tables_used,
            "join_count": join_count,
            "has_aggregation": has_aggregation,
            "has_subquery": has_subquery,
            "has_group_by": has_group_by,
            "result_row_count": result_row_count,
            "rag_examples_count": rag_examples_count,
            "model_name": model_name,
        }
        try:
            with open(LOG_FILE_JSONL, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"JSONL Logging error: {e}")

        # 2. CSV Logging (Excel/Human Readable)
        try:
            file_exists = os.path.isfile(LOG_FILE_CSV)
            with open(LOG_FILE_CSV, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow([
                        'LogID', 'Timestamp', 'Question', 'SQL', 'Status', 'Error',
                        'Duration_Sec', 'Dialect', 'Retry_Count',
                        'Tables_Used', 'Join_Count', 'Has_Aggregation', 'Has_Subquery',
                        'Has_Group_By', 'Result_Row_Count', 'RAG_Examples_Count', 'Model_Name'
                    ])
                writer.writerow([
                    log_id,
                    timestamp,
                    question,
                    sql,
                    status,
                    error_msg,
                    f"{duration:.2f}",
                    dialect,
                    retry_count,
                    "|".join(tables_used),
                    join_count,
                    has_aggregation,
                    has_subquery,
                    has_group_by,
                    result_row_count,
                    rag_examples_count,
                    model_name,
                ])
        except Exception as e:
            print(f"CSV Logging error: {e}")

    return log_id

@router.post("/query", response_model=QueryResponse)
async def query_data(
    request: QueryRequest,
    state: GlobalStateManager = Depends(get_state_manager),
    engine: NLPEngine = Depends(get_nlp_engine)
):
    if not state.db_engine:
        raise HTTPException(status_code=503, detail="Datasource unavailable")

    request_id = str(uuid.uuid4())
    # The datasource is fixed at deploy time; its own dialect is authoritative,
    # not whatever the client sent.
    dialect = {"postgresql": "postgres"}.get(
        state.db_engine.dialect.name, state.db_engine.dialect.name
    )
    start_time = time.time()

    # ADR 0006 (dispatch refined in #21): the PRESENCE of the history field —
    # even an empty list, which is how a session's first Turn arrives — selects
    # the function-calling agent loop. Omitting the field (or null) keeps the
    # legacy one-shot behaviour, so existing Consumers don't break.
    if request.history is not None:
        return await _agent_query(
            request, state, engine, dialect, request_id, start_time)

    try:
        sql, data, error, retry_count, viz_config, rag_examples_count = await engine.query_database(
            question=request.question,
            engine=state.db_engine,
            dialect=dialect,
            preferred_chart_type=request.preferred_chart_type
        )
    except Exception as e:
        duration = time.time() - start_time
        await asyncio.to_thread(
            log_query_to_file, request.question, "", "Error", str(e), duration, dialect
        )
        return QueryResponse(
            status="error", request_id=request_id, question=request.question,
            elapsed_ms=int(duration * 1000),
            error=QueryError(code="EXEC_FAILED", message=str(e)),
        )

    duration = time.time() - start_time
    elapsed_ms = int(duration * 1000)

    # --- File logging (demo UI history; NestJS keeps its own record) ---
    status_str = "Success" if not error else "Error"
    if retry_count > 0 and not error:
        status_str += f" (Retry {retry_count})"
    provider = settings.MODEL_PROVIDER
    model_name = {
        "openai": settings.OPENAI_MODEL, "google": settings.GOOGLE_MODEL,
        "openrouter": settings.OPENROUTER_MODEL, "zhipu": settings.ZHIPU_MODEL,
    }.get(provider, settings.OLLAMA_MODEL)
    metrics = parse_sql_metrics(sql or "", dialect=dialect)
    await asyncio.to_thread(
        log_query_to_file,
        question=request.question, sql=sql or "", status=status_str,
        error_msg=error or "", duration=duration, dialect=dialect,
        retry_count=retry_count, tables_used=metrics.tables_used,
        join_count=metrics.join_count, has_aggregation=metrics.has_aggregation,
        has_subquery=metrics.has_subquery, has_group_by=metrics.has_group_by,
        result_row_count=len(data) if data is not None else -1,
        rag_examples_count=rag_examples_count, model_name=model_name,
    )

    # --- Envelope ---
    if error:
        code = "EXEC_FAILED" if sql else "LLM_FAILED"
        return QueryResponse(
            status="error", request_id=request_id, question=request.question,
            sql=sql or None, retry_count=retry_count, elapsed_ms=elapsed_ms,
            error=QueryError(code=code, message=error),
        )

    rows = data or []
    truncated = len(rows) >= settings.MAX_SQL_LIMIT
    col_dicts, summary_dict = await asyncio.to_thread(describe_result, rows, truncated)
    return QueryResponse(
        status="ok", request_id=request_id, question=request.question,
        sql=sql,
        columns=[ColumnInfo(**c) for c in col_dicts],
        rows=rows, row_count=len(rows), truncated=truncated,
        summary=ResultSummary(**summary_dict),
        visualization=viz_config, retry_count=retry_count, elapsed_ms=elapsed_ms,
    )


async def _agent_query(
    request: QueryRequest,
    state: GlobalStateManager,
    engine: NLPEngine,
    dialect: str,
    request_id: str,
    start_time: float,
) -> QueryResponse:
    """One conversational Turn (ADR 0006): the LLM-driven agent loop with
    history supplied by the Consumer. Builds the extended envelope."""
    result: AgentTurnResult = await engine.agent_query_database(
        question=request.question,
        engine=state.db_engine,
        dialect=dialect,
        history=[t.model_dump() for t in request.history],
        preferred_chart_type=request.preferred_chart_type,
    )
    return await _agent_envelope(request, request_id, start_time, result, dialect)


async def _agent_envelope(
    request: QueryRequest,
    request_id: str,
    start_time: float,
    result: AgentTurnResult,
    dialect: str,
) -> QueryResponse:
    """Shared envelope builder for /query and /query/stream: elapsed timing,
    the same file-logging trail, and the answer-type dispatch. The stream's
    final SSE event is exactly this envelope."""
    duration = time.time() - start_time
    elapsed_ms = int(duration * 1000)

    # --- File logging (same trail as the one-shot path) ---
    provider = settings.MODEL_PROVIDER
    model_name = {
        "openai": settings.OPENAI_MODEL, "google": settings.GOOGLE_MODEL,
        "openrouter": settings.OPENROUTER_MODEL, "zhipu": settings.ZHIPU_MODEL,
    }.get(provider, settings.OLLAMA_MODEL)
    if result.error:
        status_str = "Error"
    elif result.answer_type == "result":
        status_str = "Success"
    else:
        status_str = f"Success ({result.answer_type.title()})"
    await asyncio.to_thread(
        log_query_to_file,
        question=request.question, sql=result.sql or "", status=status_str,
        error_msg=result.error_message or result.error or "",
        duration=duration, dialect=dialect,
        # steps beyond the first are the loop's self-corrections
        retry_count=max(0, result.steps_used - 1),
        tables_used=[], join_count=0, has_aggregation=False,
        has_subquery=False, has_group_by=False,
        result_row_count=(result.row_count if result.answer_type == "result" else -1),
        rag_examples_count=result.rag_examples_count, model_name=model_name,
    )

    if result.error:
        code = result.error if result.error in (
            "STEP_BUDGET_EXCEEDED", "LLM_FAILED") else "LLM_FAILED"
        return QueryResponse(
            status="error", request_id=request_id, question=request.question,
            answer_type="result", steps_used=result.steps_used,
            prep_ms=result.prep_ms, elapsed_ms=elapsed_ms,
            error=QueryError(code=code, message=result.error_message or code),
        )

    if result.answer_type == "result":
        rows = result.rows or []
        # Grilled decision (Oct 2026): every Answer carries a readable Thai
        # message — the agent's final_answer already produces it for "result"
        # (the prompt requires it), so stop dropping it at the envelope.
        return QueryResponse(
            status="ok", request_id=request_id, question=request.question,
            answer_type="result", message=result.message, steps_used=result.steps_used,
            prep_ms=result.prep_ms, sql=result.sql,
            columns=[ColumnInfo(**c) for c in (result.columns or [])],
            rows=rows, row_count=result.row_count, truncated=result.truncated,
            summary=ResultSummary(**(result.summary or {"row_count": result.row_count})),
            visualization=result.viz_config, elapsed_ms=elapsed_ms,
        )

    # Clarification / Refusal: an Answer without a query behind it.
    return QueryResponse(
        status="ok", request_id=request_id, question=request.question,
        answer_type=result.answer_type, message=result.message,
        steps_used=result.steps_used, prep_ms=result.prep_ms,
        sql=None, rows=[], row_count=0,
        elapsed_ms=elapsed_ms,
    )

@router.post("/query/stream")
async def query_data_stream(
    request: QueryRequest,
    state: GlobalStateManager = Depends(get_state_manager),
    engine: NLPEngine = Depends(get_nlp_engine),
):
    """SSE variant of /query (grilling agreement on perceived latency): same
    request contract, same auth, but Progress events stream to the Consumer
    while the agent works, and the final SSE event is the standard envelope —
    the same object the legacy endpoint returns. Opt-in; /api/query untouched.
    The stream always runs the agent loop; omitting ``history`` means a first
    Turn (empty history), not legacy one-shot mode."""
    if not state.db_engine:
        raise HTTPException(status_code=503, detail="Datasource unavailable")

    request_id = str(uuid.uuid4())
    dialect = {"postgresql": "postgres"}.get(
        state.db_engine.dialect.name, state.db_engine.dialect.name
    )
    start_time = time.time()
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def on_event(payload: dict) -> None:
        # The turn and this queue share one event loop; put_nowait is the
        # ordering-correct hand-off (a loop.call_soon_threadsafe schedule would
        # race the turn_done sentinel and drop trailing events).
        queue.put_nowait(payload)

    history = [t.model_dump() for t in (request.history or [])]

    async def _run_turn():
        try:
            return await engine.agent_query_database(
                question=request.question,
                engine=state.db_engine,
                dialect=dialect,
                history=history,
                preferred_chart_type=request.preferred_chart_type,
                on_event=on_event,
            )
        finally:
            await queue.put(None)  # sentinel: no more progress events

    async def _generate():
        task = asyncio.create_task(_run_turn())
        try:
            while True:
                payload = await queue.get()
                if payload is None:
                    break
                yield (f"event: progress\n"
                       f"data: {json.dumps(payload, ensure_ascii=False)}\n\n")
            try:
                result = await task
            except Exception as e:
                yield (f"event: error\n"
                       f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n")
                return
            envelope = await _agent_envelope(request, request_id, start_time, result, dialect)
            yield f"event: envelope\ndata: {envelope.model_dump_json()}\n\n"
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        _generate(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@router.get("/schema", response_model=SchemaResponse)
async def get_schema(state: GlobalStateManager = Depends(get_state_manager)):
    if not state.db_engine:
        raise HTTPException(status_code=503, detail="Datasource unavailable")
    try:
        # Same view: denylisted junk/PII objects hidden, views included.
        raw = await asyncio.to_thread(get_database_schema, state.db_engine)
        tables = [
            TableInfo(name=name, columns=[
                ColumnInfo(name=c["name"], type=str(c["type"])) for c in cols
            ])
            for name, cols in raw["tables"].items()
        ]
        return SchemaResponse(tables=tables)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/history", response_model=HistoryResponse)
async def get_history(
    limit: int = 50, 
    dialect: str = None, 
    status: str = None,
    state: GlobalStateManager = Depends(get_state_manager)
):
    entries = await asyncio.to_thread(
        state.history_manager.load_history,
        limit=limit, status_filter=status, dialect_filter=dialect)
    # Convert dataclass to Pydantic model
    history_items = [
        HistoryItem(
            log_id=e.log_id,
            timestamp=e.timestamp,
            question=e.question,
            sql=e.sql,
            status=e.status,
            dialect=e.dialect,
            feedback=e.feedback,
            feedback_text=e.feedback_text
        ) for e in entries
    ]
    return HistoryResponse(history=history_items)

@router.patch("/history/{log_id}/feedback")
async def update_feedback(
    log_id: str,
    req: FeedbackRequest,
    state: GlobalStateManager = Depends(get_state_manager)
):
    success = await asyncio.to_thread(
        state.history_manager.update_feedback,
        log_id, 
        req.feedback, 
        feedback_text=req.feedback_text
    )
    if not success:
        raise HTTPException(status_code=404, detail="Log entry not found")
    return {"status": "success", "feedback": req.feedback, "feedback_text": req.feedback_text} 

@router.get("/favorites", response_model=FavoritesResponse)
async def get_favorites(state: GlobalStateManager = Depends(get_state_manager)):
    favs = await asyncio.to_thread(state.history_manager.load_favorites)
    items = [
        FavoriteItem(
            favorite_id=f.favorite_id,
            question=f.question,
            sql=f.sql,
            dialect=f.dialect,
            name=f.name,
            use_count=f.use_count
        ) for f in favs
    ]
    return FavoritesResponse(favorites=items)

@router.post("/favorites", response_model=FavoriteItem)
async def create_favorite(
    req: CreateFavoriteRequest,
    state: GlobalStateManager = Depends(get_state_manager)
):
    fav = await asyncio.to_thread(
        state.history_manager.save_favorite,
        question=req.question,
        sql=req.sql,
        dialect=req.dialect,
        name=req.name,
        log_id=req.log_id
    )
    return FavoriteItem(
        favorite_id=fav.favorite_id,
        question=fav.question,
        sql=fav.sql,
        dialect=fav.dialect,
        name=fav.name,
        use_count=fav.use_count
    )

@router.delete("/favorites/{favorite_id}")
async def delete_favorite(
    favorite_id: str,
    state: GlobalStateManager = Depends(get_state_manager)
):
    success = await asyncio.to_thread(
        state.history_manager.delete_favorite, favorite_id)
    if not success:
        raise HTTPException(status_code=404, detail="Favorite not found")
    return {"status": "success"}


@router.post("/admin/refresh-schema")
async def refresh_schema(engine: NLPEngine = Depends(get_nlp_engine)):
    """Drop the cached datasource schema. Call after a migration on the datasource."""
    engine.refresh_schema()
    return {"status": "ok"}
