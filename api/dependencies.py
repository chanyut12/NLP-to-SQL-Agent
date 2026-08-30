import logging
import threading
from typing import Optional

from fastapi import Header, HTTPException
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from core.services.engine import NLPEngine
from core.services.query_history import QueryHistoryManager
from core.config import settings

logger = logging.getLogger(__name__)


class GlobalStateManager:
    """Process-wide singletons.

    The datasource connection is fixed at startup from ``DATABASE_URL`` and never
    mutated at runtime — there is no ``/connect`` flow and no session file.
    """

    def __init__(self):
        # Lazy-init NLPEngine to avoid heavy model loading during module import.
        self.nlp_engine: Optional[NLPEngine] = None
        self._nlp_engine_lock = threading.Lock()
        self.history_manager = QueryHistoryManager()
        self.db_engine: Optional[Engine] = self._build_db_engine()

    @staticmethod
    def _build_db_engine() -> Optional[Engine]:
        if not settings.DATABASE_URL:
            logger.warning("DATABASE_URL is not set; /query and /schema will return 503.")
            return None
        try:
            engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
            with engine.connect():
                pass
            logger.info("Datasource connection established.")
            return engine
        except Exception as e:
            logger.warning("Datasource connection failed at startup: %s", e)
            return None

    def get_nlp_engine(self) -> NLPEngine:
        """Get NLPEngine singleton, creating it lazily on first use."""
        if self.nlp_engine is None:
            with self._nlp_engine_lock:
                if self.nlp_engine is None:
                    self.nlp_engine = NLPEngine()
        return self.nlp_engine


# Singleton Instance
state_manager = GlobalStateManager()


def get_nlp_engine() -> NLPEngine:
    return state_manager.get_nlp_engine()


def get_state_manager() -> GlobalStateManager:
    return state_manager


def require_api_key(x_api_key: str = Header(default="")) -> None:
    """Reject the request unless it carries the shared secret.

    No-op when ``API_KEY`` is unset, so local dev and the bundled demo UI work
    without a key.
    """
    if settings.API_KEY and x_api_key != settings.API_KEY:
        raise HTTPException(status_code=401, detail="invalid or missing API key")
