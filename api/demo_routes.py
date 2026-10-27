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

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import Engine, make_url

from api.dependencies import GlobalStateManager, get_state_manager
from api.schemas import DemoConnectRequest, DemoConnectResponse, DemoStateResponse
from core.config import settings
from core.domain.schema_utils import is_denylisted
from core.profiles import PROFILES_DIR
from core.utils.dialect_transpiler import sqlglot_dialect_name

logger = logging.getLogger(__name__)

router = APIRouter()


def available_profiles() -> list:
    """Names under profiles/ that carry an Example set, i.e. a usable profile."""
    if not os.path.isdir(PROFILES_DIR):
        return []
    return sorted(
        name
        for name in os.listdir(PROFILES_DIR)
        if os.path.isfile(os.path.join(PROFILES_DIR, name, "examples.json"))
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
        tables = sorted(
            name
            for name in inspect(engine).get_table_names()
            if not is_denylisted(name)
        )
    except Exception:
        engine.dispose()
        raise
    return engine, tables


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
    """Switch the running demo to another Datasource (ADR 0013)."""
    dsn = request.database_url.strip()
    try:
        make_url(dsn)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Connection string ไม่ถูกต้อง: {e}")

    profile = (request.profile or settings.DOMAIN_PROFILE).strip()
    profiles = available_profiles()
    if profile not in profiles:
        raise HTTPException(
            status_code=400,
            detail=f"ไม่พบ profile {profile!r} — ที่มีอยู่: {', '.join(profiles) or '(ไม่มี)'}",
        )

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
