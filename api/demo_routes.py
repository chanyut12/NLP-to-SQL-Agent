"""Demo-mode Datasource switching (ADR 0013).

Mounted only where the bundled UI is served — ``APP_MODE=demo``, or ``auto``
with no API key. Service deployments keep ADR 0011's fixed single Datasource and
never expose these endpoints.

WARNING: the demo UI has no authentication by design, so this endpoint lets
anyone who can reach the server open a database connection. The demo binds
loopback by default (``start_demo.sh``); never publish it.
"""

import asyncio
import logging
import os

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import Engine, make_url

from api.dependencies import GlobalStateManager, get_state_manager
from api.schemas import (
    DemoConnectRequest, DemoConnectResponse, DemoStateResponse,
    DemoProfileCoverage, DemoProfileDraftRequest, DemoProfileDraftResponse,
    DemoProfileSaveRequest, DemoProfileSaveResponse,
)
from core import profile_writer, profiles
from core.config import settings
from core.domain.schema_utils import is_denylisted
from core.domain.sql_safety import SQLSafetyError, validate_and_sanitize_sql
from core.utils.dialect_transpiler import sqlglot_dialect_name

logger = logging.getLogger(__name__)

router = APIRouter()


def available_profiles() -> list:
    """Names under profiles/ that carry an Example set, i.e. a usable profile."""
    if not os.path.isdir(profiles.PROFILES_DIR):
        return []
    return sorted(
        name
        for name in os.listdir(profiles.PROFILES_DIR)
        if os.path.isfile(os.path.join(profiles.PROFILES_DIR, name, "examples.json"))
    )


def redacted_url(dsn) -> str:
    """The DSN as text with any password replaced — for logs and responses."""
    return make_url(dsn).render_as_string(hide_password=True)


def safe_error(exc: Exception, dsn: str) -> str:
    """An error message safe to return to the browser: short, and without the
    password even if the driver echoed the DSN back."""
    message = str(exc)
    password = make_url(dsn).password
    if password:
        message = message.replace(password, "***")
    return message[:300]


def readable_tables(db_engine: Engine) -> list:
    """Table names the demo may show: the denylist applied, sorted."""
    return sorted(
        name
        for name in inspect(db_engine).get_table_names()
        if not is_denylisted(name)
    )


def open_datasource(dsn: str):
    """Connect once and read the readable table list. Returns (engine, tables).

    Runs in a worker thread: creating the engine and touching the connection
    here keeps an unreachable datasource from stalling the event loop. The
    engine is disposed when the connection attempt fails.
    """
    engine = create_engine(dsn, pool_pre_ping=True)
    try:
        with engine.connect():
            pass
        tables = readable_tables(engine)
    except Exception:
        engine.dispose()
        raise
    return engine, tables


def run_readonly(db_engine: Engine, sql: str, dialect: str) -> tuple:
    """Validate and execute one read-only statement. Returns (sql, rows).

    Shared by drafting and saving: a drafted example is only usable once it has
    actually run, and a saved example is only ever one that ran here.
    """
    safe = validate_and_sanitize_sql(
        sql, dialect=dialect, max_limit=settings.MAX_SQL_LIMIT
    )
    dataframe = pd.read_sql(safe.sql, db_engine)
    return safe.sql, dataframe.to_dict(orient="records")


async def rewarm(engine, db_engine: Engine) -> None:
    """Rebuild the new Datasource's warm state in the background, best-effort."""
    try:
        await engine.warm(db_engine, dialect=sqlglot_dialect_name(db_engine.dialect.name))
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.warning("Demo re-warm failed (non-fatal): %s", e)


@router.get("/demo/state", response_model=DemoStateResponse)
async def demo_state(state: GlobalStateManager = Depends(get_state_manager)):
    """What the connection panel needs: active Datasource, profile and choices."""
    return DemoStateResponse(
        datasource=redacted_url(state.db_engine.url) if state.db_engine is not None else None,
        profile=settings.DOMAIN_PROFILE,
        profiles=available_profiles(),
    )


@router.post("/demo/connect", response_model=DemoConnectResponse)
async def demo_connect(
    request: DemoConnectRequest,
    state: GlobalStateManager = Depends(get_state_manager),
):
    """Switch the running demo to another Datasource, or to another profile
    on the Datasource it is already connected to (ADR 0013)."""
    dsn = (request.database_url or "").strip()

    profile = (request.profile or settings.DOMAIN_PROFILE).strip()
    profiles = available_profiles()
    if profile not in profiles:
        raise HTTPException(
            status_code=400,
            detail=f"ไม่พบ profile {profile!r} — ที่มีอยู่: {', '.join(profiles) or '(ไม่มี)'}",
        )

    if not dsn:
        # A profile-only switch: the state's DSN has its password redacted, so
        # the wizard cannot reconnect and must not have to. Only the engine is
        # dropped; the next question rebuilds it from the new profile.
        if state.db_engine is None:
            raise HTTPException(
                status_code=400,
                detail="ยังไม่ได้เชื่อมต่อฐานข้อมูล — ต้องระบุ database_url",
            )
        if profile != settings.DOMAIN_PROFILE:
            settings.DOMAIN_PROFILE = profile
            state.reset_nlp_engine()
            logger.info("Demo profile switched to %r (same Datasource)", profile)
        tables = await asyncio.to_thread(readable_tables, state.db_engine)
        return DemoConnectResponse(
            datasource=redacted_url(state.db_engine.url),
            profile=profile,
            tables=tables,
        )

    try:
        make_url(dsn)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Connection string ไม่ถูกต้อง: {e}")

    try:
        new_engine, tables = await asyncio.to_thread(open_datasource, dsn)
    except Exception as e:
        logger.warning("Demo connect failed for %s: %s", redacted_url(dsn), e)
        raise HTTPException(
            status_code=400,
            detail=f"เชื่อมต่อไม่สำเร็จ: {safe_error(e, dsn)}",
        )

    if profile != settings.DOMAIN_PROFILE:
        settings.DOMAIN_PROFILE = profile
        state.reset_nlp_engine()
        logger.info("Demo profile switched to %r", profile)

    state.replace_datasource(new_engine)

    # Rebuild the warm state for the new Datasource only when the engine has
    # already been built — a cold demo (or a test) pays nothing here.
    engine = state.nlp_engine
    if engine is not None:
        await engine.reset_for_datasource()
        asyncio.create_task(rewarm(engine, new_engine))

    logger.info(
        "Demo Datasource switched to %s (profile=%s, %s tables)",
        redacted_url(dsn), profile, len(tables),
    )
    return DemoConnectResponse(
        datasource=redacted_url(dsn),
        profile=profile,
        tables=tables,
    )


@router.post("/demo/profile/draft", response_model=DemoProfileDraftResponse)
async def demo_profile_draft(
    request: DemoProfileDraftRequest,
    state: GlobalStateManager = Depends(get_state_manager),
):
    """Draft one example: the SQL and the rows it produced, saved nowhere.

    A question goes through the service's own generation path; a supplied SQL
    (the visitor corrected it by hand) is executed as-is. Either way the SQL is
    read-only-validated and LIMIT-clamped first.
    """
    db_engine = state.db_engine
    if db_engine is None:
        raise HTTPException(status_code=503, detail="ยังไม่ได้เชื่อมต่อฐานข้อมูล")

    dialect = sqlglot_dialect_name(db_engine.dialect.name)
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="ต้องมีคำถามของตัวอย่าง")

    if request.sql and request.sql.strip():
        try:
            sql, rows = await asyncio.to_thread(
                run_readonly, db_engine, request.sql, dialect
            )
        except SQLSafetyError as e:
            return DemoProfileDraftResponse(
                status="error", dialect=profile_writer.contract_dialect(dialect),
                sql=request.sql, error=str(e),
            )
        except Exception as e:
            return DemoProfileDraftResponse(
                status="error", dialect=profile_writer.contract_dialect(dialect),
                sql=request.sql, error=safe_error(e, str(db_engine.url)),
            )
    else:
        try:
            engine = await asyncio.to_thread(state.get_nlp_engine)
            sql, data, error, _retry, _viz, _rag = await engine.query_database(
                question=question, engine=db_engine, dialect=dialect
            )
        except Exception as e:
            return DemoProfileDraftResponse(
                status="error", dialect=profile_writer.contract_dialect(dialect),
                error=safe_error(e, str(db_engine.url)),
            )
        if error:
            return DemoProfileDraftResponse(
                status="error", dialect=profile_writer.contract_dialect(dialect),
                sql=sql, error=error,
            )
        rows = data or []

    return DemoProfileDraftResponse(
        status="ok",
        dialect=profile_writer.contract_dialect(dialect),
        sql=sql,
        rows=rows,
        row_count=len(rows),
        category=profile_writer.categorize_sql(sql, dialect),
    )


@router.post("/demo/profile/save", response_model=DemoProfileSaveResponse)
async def demo_profile_save(
    request: DemoProfileSaveRequest,
    state: GlobalStateManager = Depends(get_state_manager),
):
    """Write a visitor's answers as an ordinary profile (ADR 0014).

    Every result example is executed before anything is written, so a profile
    never teaches the system SQL that cannot run. Existing profiles are only
    replaced with an explicit overwrite flag.
    """
    db_engine = state.db_engine
    if db_engine is None:
        raise HTTPException(status_code=503, detail="ยังไม่ได้เชื่อมต่อฐานข้อมูล")

    dialect = sqlglot_dialect_name(db_engine.dialect.name)
    try:
        profile_writer.validate_profile_name(request.name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if os.path.isdir(profiles.profile_dir(request.name)) and not request.overwrite:
        raise HTTPException(
            status_code=409,
            detail=f"มี profile {request.name!r} อยู่แล้ว — ต้องยืนยันเขียนทับ",
        )

    for index, example in enumerate(request.examples, start=1):
        try:
            await asyncio.to_thread(run_readonly, db_engine, example.sql, dialect)
        except SQLSafetyError as e:
            raise HTTPException(
                status_code=400, detail=f"ตัวอย่างที่ {index} ใช้ไม่ได้: {e}"
            )
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"ตัวอย่างที่ {index} รันไม่สำเร็จ: "
                    f"{safe_error(e, str(db_engine.url))}"
                ),
            )

    try:
        examples = profile_writer.build_examples(
            [example.model_dump() for example in request.examples],
            profile_writer.contract_dialect(dialect),
        )
        coverage = await asyncio.to_thread(
            profile_writer.write_profile,
            request.name,
            hints=request.hints,
            schema_mappings=request.schema_mappings,
            examples=examples,
            overwrite=request.overwrite,
        )
    except FileExistsError:
        raise HTTPException(
            status_code=409,
            detail=f"มี profile {request.name!r} อยู่แล้ว — ต้องยืนยันเขียนทับ",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    logger.info(
        "Demo wizard wrote profile %r (%s examples)", request.name, coverage["examples"]
    )
    return DemoProfileSaveResponse(
        profile=request.name,
        coverage=DemoProfileCoverage(**coverage),
    )
