from dotenv import load_dotenv
load_dotenv()

import asyncio
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.dependencies import state_manager
from api.routes import router

app = FastAPI(title="Thai NLP-to-SQL API", version="1.0.0")
logger = logging.getLogger(__name__)

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")

@app.on_event("startup")
async def preload_nlp_engine():
    """Preload NLPEngine at app startup to avoid first-query cold start."""
    try:
        await asyncio.to_thread(state_manager.get_nlp_engine)
        logger.info("NLPEngine preloaded successfully.")
    except Exception as e:
        # Keep server running; /connect and /query can retry initialization later.
        logger.warning("NLPEngine preload failed on startup: %s", e)

# Mount Frontend (Must be after API routes)
from fastapi.staticfiles import StaticFiles
import os

# Ensure web directory exists
if os.path.exists("web"):
    app.mount("/", StaticFiles(directory="web", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
