from dotenv import load_dotenv
load_dotenv()

import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.dependencies import state_manager
from api.routes import router
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    preload_task = asyncio.create_task(_preload_nlp_engine())
    app.state.preload_task = preload_task
    try:
        yield
    finally:
        if not preload_task.done():
            preload_task.cancel()
            with suppress(asyncio.CancelledError):
                await preload_task


app = FastAPI(title="Thai NLP-to-SQL API", version="1.0.0", lifespan=lifespan)

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")

# Mount Frontend (Must be after API routes)
from fastapi.staticfiles import StaticFiles
import os

# Ensure web directory exists
if os.path.exists("web"):
    app.mount("/", StaticFiles(directory="web", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
