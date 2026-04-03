from core.services.engine import NLPEngine
from core.data.database import ConnectionManager
from core.services.query_history import QueryHistoryManager
from sqlalchemy.engine import Engine
from typing import Optional
import json
import os
import threading

_SESSION_FILE = ".last_connection.json"

class GlobalStateManager:
    def __init__(self):
        # Lazy-init NLPEngine to avoid heavy model loading during module import/startup.
        self.nlp_engine: Optional[NLPEngine] = None
        self._nlp_engine_lock = threading.Lock()
        self.history_manager = QueryHistoryManager()
        self.db_engine: Optional[Engine] = None
        self.db_config: dict = {}
        self._try_restore_connection()

    def _try_restore_connection(self):
        """Restore last DB connection after server reload."""
        if not os.path.exists(_SESSION_FILE):
            return
        try:
            with open(_SESSION_FILE, "r") as f:
                saved = json.load(f)
            engine, error = ConnectionManager.get_db_engine(saved["db_type"], saved["config"])
            if not error:
                self.db_engine = engine
                self.db_config = saved["config"]
        except Exception:
            pass  # Silently skip if restore fails

    def connect_db(self, db_type: str, config: dict):
        engine, error = ConnectionManager.get_db_engine(db_type, config)
        if error:
            raise Exception(error)
        self.db_engine = engine
        self.db_config = config
        # Persist for auto-restore on reload
        try:
            with open(_SESSION_FILE, "w") as f:
                json.dump({"db_type": db_type, "config": config}, f)
        except Exception:
            pass
        return True

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
