"""
Data models for query history and favorites.
"""
from dataclasses import dataclass
from typing import Optional

@dataclass
class HistoryEntry:
    """Represents a single query history entry."""
    log_id: str
    timestamp: str
    question: str
    sql: str
    status: str
    error_msg: str = ""
    duration_sec: float = 0.0
    feedback: str = ""
    feedback_text: str = ""  # User-typed feedback comment
    dialect: str = "sqlite"
    retry_count: int = 0
    # Richer metrics fields (optional, safe defaults for backward compatibility)
    tables_used: list = None
    join_count: int = 0
    has_aggregation: bool = False
    has_subquery: bool = False
    has_group_by: bool = False
    result_row_count: int = -1
    rag_examples_count: int = 0
    model_name: str = ""

    def __post_init__(self):
        if self.tables_used is None:
            self.tables_used = []

@dataclass
class FavoriteEntry:
    """Represents a saved favorite query."""
    favorite_id: str
    question: str
    sql: str
    dialect: str
    created_at: str
    last_used: str
    use_count: int = 0
    log_id: Optional[str] = None
    name: Optional[str] = None
