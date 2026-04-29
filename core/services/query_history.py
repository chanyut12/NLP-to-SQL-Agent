"""
Query History & Favorites Management Module (Facade).

This module provides a unified interface for history and favorites,
delegating to specific services under the hood.
"""
from typing import List, Optional

from core.domain.history_models import HistoryEntry, FavoriteEntry
from core.services.history_service import HistoryService
from core.services.favorite_service import FavoriteService

# File paths (defaults)
HISTORY_FILE = "query_logs.jsonl"
FAVORITES_FILE = "favorites.json"


class QueryHistoryManager:
    """
    Facade for managing query history and favorites for the Thai NLP-to-SQL application.
    Maintains backward compatibility by providing the same interface.
    """

    def __init__(
        self,
        history_file: str = HISTORY_FILE,
        favorites_file: str = FAVORITES_FILE
    ):
        """Initialize the QueryHistoryManager facade."""
        self.history_service = HistoryService(history_file)
        self.favorite_service = FavoriteService(favorites_file, self.history_service)

    # --- History Methods (Delegated) ---

    def load_history(
        self,
        limit: int = 50,
        status_filter: Optional[str] = None,
        dialect_filter: Optional[str] = None
    ) -> List[HistoryEntry]:
        return self.history_service.load_history(limit, status_filter, dialect_filter)

    def get_history_entry(self, log_id: str) -> Optional[HistoryEntry]:
        return self.history_service.get_history_entry(log_id)

    def update_feedback(self, log_id: str, feedback: str, feedback_text: str = None) -> bool:
        return self.history_service.update_feedback(log_id, feedback, feedback_text)

    # --- Favorites Methods (Delegated) ---

    def load_favorites(self) -> List[FavoriteEntry]:
        return self.favorite_service.load_favorites()

    def save_favorite(
        self,
        question: str,
        sql: str,
        dialect: str = "sqlite",
        name: Optional[str] = None,
        log_id: Optional[str] = None
    ) -> FavoriteEntry:
        return self.favorite_service.save_favorite(question, sql, dialect, name, log_id)

    def delete_favorite(self, favorite_id: str) -> bool:
        return self.favorite_service.delete_favorite(favorite_id)

    def record_favorite_use(self, favorite_id: str) -> None:
        self.favorite_service.record_favorite_use(favorite_id)

    def is_favorite(self, question: str, sql: str) -> Optional[str]:
        return self.favorite_service.is_favorite(question, sql)

    def save_favorite_from_history(
        self,
        log_id: str,
        name: Optional[str] = None
    ) -> Optional[FavoriteEntry]:
        return self.favorite_service.save_favorite_from_history(log_id, name)
