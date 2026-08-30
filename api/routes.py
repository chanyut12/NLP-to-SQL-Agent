from fastapi import APIRouter, Depends, HTTPException, Body
from api.schemas import (
    QueryRequest, QueryResponse, QueryError,
    SchemaResponse, TableInfo, ColumnInfo,
    HistoryResponse, HistoryItem,
    FavoritesResponse, FavoriteItem, CreateFavoriteRequest,
    FeedbackRequest
)
from api.dependencies import get_state_manager, get_nlp_engine, GlobalStateManager
from core.services.engine import NLPEngine
from core.utils.sql_metrics import parse_sql_metrics
from core.config import settings
from sqlalchemy import inspect
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

@router.post("/connect")
async def connect_database(_: dict = Body(default={})):
    """Deprecated no-op. The datasource is fixed at deploy time from DATABASE_URL;
    kept only so the bundled demo UI's connect button keeps working."""
    return {"status": "success", "message": "Using server-configured datasource"}


def _derive_columns(rows: list[dict]) -> list[ColumnInfo]:
    """Best-effort column list from the first row (SQL types are lost upstream)."""
    if not rows:
        return []
    first = rows[0]
    cols = []
    for key in first:
        sample = next((r[key] for r in rows if r.get(key) is not None), None)
        cols.append(ColumnInfo(name=key, type=type(sample).__name__ if sample is not None else "unknown"))
    return cols


@router.post("/query", response_model=QueryResponse)
async def query_data(
    request: QueryRequest,
    state: GlobalStateManager = Depends(get_state_manager),
    engine: NLPEngine = Depends(get_nlp_engine)
):
    if not state.db_engine:
        raise HTTPException(status_code=503, detail="Datasource unavailable")

    request_id = str(uuid.uuid4())
    dialect = request.dialect or "postgres"
    start_time = time.time()

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
    model_name = (
        settings.OPENAI_MODEL if provider == "openai"
        else settings.GOOGLE_MODEL if provider == "google"
        else settings.OLLAMA_MODEL
    )
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
    return QueryResponse(
        status="ok", request_id=request_id, question=request.question,
        sql=sql, columns=_derive_columns(rows), rows=rows, row_count=len(rows),
        truncated=len(rows) >= settings.MAX_SQL_LIMIT,
        visualization=viz_config, retry_count=retry_count, elapsed_ms=elapsed_ms,
    )

@router.get("/schema", response_model=SchemaResponse)
async def get_schema(state: GlobalStateManager = Depends(get_state_manager)):
    if not state.db_engine:
        raise HTTPException(status_code=400, detail="Database not connected")
    
    try:
        inspector = inspect(state.db_engine)
        tables = []
        for table_name in inspector.get_table_names():
            columns = []
            for col in inspector.get_columns(table_name):
                columns.append(ColumnInfo(name=col['name'], type=str(col['type'])))
            tables.append(TableInfo(name=table_name, columns=columns))
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
    entries = state.history_manager.load_history(limit=limit, status_filter=status, dialect_filter=dialect)
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
    success = state.history_manager.update_feedback(
        log_id, 
        req.feedback, 
        feedback_text=req.feedback_text
    )
    if not success:
        raise HTTPException(status_code=404, detail="Log entry not found")
    return {"status": "success", "feedback": req.feedback, "feedback_text": req.feedback_text} 

@router.get("/favorites", response_model=FavoritesResponse)
async def get_favorites(state: GlobalStateManager = Depends(get_state_manager)):
    favs = state.history_manager.load_favorites()
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
    fav = state.history_manager.save_favorite(
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
    success = state.history_manager.delete_favorite(favorite_id)
    if not success:
        raise HTTPException(status_code=404, detail="Favorite not found")
    return {"status": "success"}


@router.post("/admin/refresh-schema")
async def refresh_schema(engine: NLPEngine = Depends(get_nlp_engine)):
    """Drop the cached datasource schema. Call after a migration on the datasource."""
    engine.refresh_schema()
    return {"status": "ok"}
