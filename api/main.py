from dotenv import load_dotenv
load_dotenv()

import asyncio
import logging
import os
from contextlib import asynccontextmanager, suppress
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from api.dependencies import require_api_key, state_manager
from api.demo_routes import router as demo_router
from api.routes import router
from core.config import settings, validate_app_mode
from core.utils.embedding import configure_third_party_logging

logger = logging.getLogger(__name__)
configure_third_party_logging()


async def _preload_nlp_engine():
    """Warm the NLP engine without blocking app startup."""
    try:
        await asyncio.to_thread(state_manager.get_nlp_engine)
        logger.info("NLPEngine preloaded successfully.")
    except asyncio.CancelledError:
        logger.info("NLPEngine preload cancelled during shutdown.")
        raise
    except Exception as e:
        # Keep server running; /connect and /query can retry initialization later.
        logger.warning("NLPEngine preload failed on startup: %s", e)


async def _warm_engine(db_engine, engine) -> None:
    """Build the question-independent warm state for one engine (spec #27/#28).
    The engine's warm routine offloads its heavy work to worker threads."""
    await engine.warm(db_engine)


async def _run_startup_warmup() -> None:
    """Startup warmup: schema introspection + schema-RAG indexing in the
    background so the first Question never pays the cold-cache cost.
    Best-effort: failures are logged; the per-Question on-demand path stays.
    """
    if state_manager.db_engine is None:
        logger.info("Startup warmup skipped: no datasource configured.")
        return
    try:
        engine = await asyncio.to_thread(state_manager.get_nlp_engine)
    except Exception as e:
        logger.warning("Startup warmup skipped (engine init failed): %s", e)
        return
    try:
        await _warm_engine(state_manager.db_engine, engine)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.warning("Startup warmup failed (non-fatal): %s", e)


_rewarm_in_progress = False


async def _rewarm_if_stale() -> bool:
    """Rebuild the warm state if it went stale (TTL expiry or the admin
    refresh flag) so no Question pays the rebuild cost (spec #27 / #29).
    Returns True when a rebuild ran. A single guard prevents overlapping
    maintenance rebuilds; the per-Question on-demand path is unaffected
    and remains the safety net while a rebuild is in flight."""
    global _rewarm_in_progress
    engine = state_manager.nlp_engine
    if engine is None or state_manager.db_engine is None:
        return False
    state = engine.warm_state() if hasattr(engine, "warm_state") else {"schema_cached": False}
    if state.get("schema_cached", False):
        return False
    if _rewarm_in_progress:
        return False
    _rewarm_in_progress = True
    try:
        await _warm_engine(state_manager.db_engine, engine)
        return True
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.warning("Background re-warm failed (non-fatal): %s", e)
        return False
    finally:
        _rewarm_in_progress = False


async def _warmup_maintenance_loop(interval: float = None) -> None:
    """Periodically check warm-state staleness and rebuild in the background.
    Runs for the process lifetime; cancelled on shutdown. The interval is
    configurable for testing via WARMUP_MAINTENANCE_INTERVAL_SECONDS."""
    if interval is None:
        interval = float(os.getenv("WARMUP_MAINTENANCE_INTERVAL_SECONDS", "300"))
    # Sleep first: the startup warmup already runs at boot; checking before it
    # finishes would start a duplicate rebuild.
    try:
        await asyncio.sleep(interval)
        while True:
            try:
                await _rewarm_if_stale()
            except Exception:
                logger.warning("Warmup maintenance pass errored", exc_info=True)
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    # On a platform with a short startup healthcheck (e.g. a Hugging Face Space),
    # warming the engine here starves the event loop while the embedding model
    # loads and the probe is killed. SKIP_ENGINE_PRELOAD=1 defers it to the first
    # request instead.
    if os.getenv("SKIP_ENGINE_PRELOAD") == "1":
        logger.info("NLPEngine preload skipped (SKIP_ENGINE_PRELOAD=1); lazy-init on first request.")
        yield
        return
    preload_task = asyncio.create_task(_preload_nlp_engine())
    warmup_task = asyncio.create_task(_run_startup_warmup())
    maintenance_task = asyncio.create_task(_warmup_maintenance_loop())
    app.state.preload_task = preload_task
    try:
        yield
    finally:
        for task in (preload_task, warmup_task, maintenance_task):
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task


def create_app() -> FastAPI:
    """Build the FastAPI app for the configured deployment mode.

    demo    — mount the bundled UI and leave /api unauthenticated (local demo).
    service — Consumer-only: no UI, /api requires X-API-Key.
    auto    — preserve the pre-APP_MODE behaviour: UI on iff API_KEY is empty.
    """
    validate_app_mode(settings.APP_MODE, settings.API_KEY)

    # Hide the interactive API docs once a key is required (a real deployment):
    # the service is Consumer-only and there is no reason to expose its endpoint
    # schema to anyone who hits the public URL.
    docs_kwargs = (
        {"docs_url": None, "redoc_url": None, "openapi_url": None}
        if settings.api_key_enforced()
        else {}
    )
    application = FastAPI(
        title="Thai NLP-to-SQL API",
        version="1.0.0",
        lifespan=lifespan,
        **docs_kwargs,
    )

    allow_origins = (
        ["*"]
        if settings.CORS_ORIGINS == "*"
        else [origin.strip() for origin in settings.CORS_ORIGINS.split(",")]
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.get("/api/health")
    async def health_check():
        body = {"status": "ok", "datasource": state_manager.db_engine is not None}
        engine = state_manager.nlp_engine
        if engine is not None and hasattr(engine, "warm_state"):
            body.update(engine.warm_state())
        else:
            body.update({"schema_cached": False, "warming": True})
        return body

    application.include_router(
        router, prefix="/api", dependencies=[Depends(require_api_key)]
    )

    if settings.demo_ui_enabled():
        # Runtime Datasource switching lives only where the unauthenticated demo
        # UI is served (ADR 0013); service mode keeps ADR 0011's one Datasource
        # per deployment and never exposes these routes.
        application.include_router(demo_router, prefix="/api")

        if not os.path.exists("web"):
            logger.warning("Demo UI requested but web/ was not found; skipping mount.")
            return application

        @application.middleware("http")
        async def _no_store_demo_ui(request, call_next):
            response = await call_next(request)
            path = request.url.path
            if not (
                path.startswith("/api")
                or path.startswith("/docs")
                or path.startswith("/openapi")
            ):
                response.headers["Cache-Control"] = "no-store"
            return response

        application.mount("/", StaticFiles(directory="web", html=True), name="static")
        logger.info("Demo UI mounted at / (APP_MODE=%s).", settings.APP_MODE)
    else:
        logger.info(
            "Demo UI not mounted (APP_MODE=%s); /api requires X-API-Key.",
            settings.APP_MODE,
        )

    return application


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
