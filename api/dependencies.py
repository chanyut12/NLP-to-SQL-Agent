from core.services.engine import NLPEngine
from core.data.database import ConnectionManager
from core.services.query_history import QueryHistoryManager
from sqlalchemy.engine import Engine
from typing import Optional

class GlobalStateManager:
    def __init__(self):
        self.nlp_engine = NLPEngine()
        self.history_manager = QueryHistoryManager()
        self.db_engine: Optional[Engine] = None
        self.db_config: dict = {}

    def connect_db(self, db_type: str, config: dict):
        engine, error = ConnectionManager.get_db_engine(db_type, config)
        if error:
            raise Exception(error)
        self.db_engine = engine
        self.db_config = config
        return True

# Singleton Instance
state_manager = GlobalStateManager()

def get_nlp_engine() -> NLPEngine:
    return state_manager.nlp_engine

def get_state_manager() -> GlobalStateManager:
    return state_manager
