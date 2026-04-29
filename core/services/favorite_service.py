"""
Service for managing favorite queries.
"""
import json
import os
import uuid
from datetime import datetime
from typing import List, Dict, Optional, Any
from dataclasses import asdict

from core.domain.history_models import FavoriteEntry
from core.utils.common import truncate_text
from core.services.history_service import HistoryService


class FavoriteService:
    """Handles saving, loading, and managing favorite queries."""

    def __init__(self, favorites_file: str, history_service: HistoryService = None):
        self.favorites_file = favorites_file
        self.history_service = history_service

    def _load_favorites_file(self) -> Dict[str, Any]:
        """Load favorites from JSON file."""
        if not os.path.isfile(self.favorites_file):
            return {"favorites": []}

        try:
            with open(self.favorites_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, Exception):
            return {"favorites": []}

    def _save_favorites_file(self, data: Dict[str, Any]) -> None:
        """Save favorites to JSON file."""
        with open(self.favorites_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_favorites(self) -> List[FavoriteEntry]:
        """Load all favorites from JSON file."""
        data = self._load_favorites_file()
        favorites = []

        for item in data.get("favorites", []):
            try:
                fav = FavoriteEntry(
                    favorite_id=item.get("favorite_id", ""),
                    question=item.get("question", ""),
                    sql=item.get("sql", ""),
                    dialect=item.get("dialect", "sqlite"),
                    created_at=item.get("created_at", ""),
                    last_used=item.get("last_used", ""),
                    use_count=item.get("use_count", 0),
                    log_id=item.get("log_id"),
                    name=item.get("name")
                )
                favorites.append(fav)
            except Exception:
                continue

        # Sort by use_count descending
        favorites.sort(key=lambda x: x.use_count, reverse=True)
        return favorites

    def save_favorite(
        self,
        question: str,
        sql: str,
        dialect: str = "sqlite",
        name: Optional[str] = None,
        log_id: Optional[str] = None
    ) -> FavoriteEntry:
        """Save a query as a favorite."""
        now = datetime.now().isoformat()

        fav = FavoriteEntry(
            favorite_id=str(uuid.uuid4()),
            question=question,
            sql=sql,
            dialect=dialect,
            created_at=now,
            last_used=now,
            use_count=0,
            log_id=log_id,
            name=name or truncate_text(question, 40)
        )

        data = self._load_favorites_file()
        data["favorites"].append(asdict(fav))
        self._save_favorites_file(data)

        return fav

    def delete_favorite(self, favorite_id: str) -> bool:
        """Delete a favorite by ID."""
        data = self._load_favorites_file()
        original_len = len(data["favorites"])

        data["favorites"] = [
            f for f in data["favorites"]
            if f.get("favorite_id") != favorite_id
        ]

        if len(data["favorites"]) < original_len:
            self._save_favorites_file(data)
            return True

        return False

    def record_favorite_use(self, favorite_id: str) -> None:
        """Update last_used and increment use_count when a favorite is re-run."""
        data = self._load_favorites_file()

        for fav in data["favorites"]:
            if fav.get("favorite_id") == favorite_id:
                fav["last_used"] = datetime.now().isoformat()
                fav["use_count"] = fav.get("use_count", 0) + 1
                break

        self._save_favorites_file(data)

    def is_favorite(self, question: str, sql: str) -> Optional[str]:
        """Check if a query is already saved as favorite."""
        data = self._load_favorites_file()

        for fav in data.get("favorites", []):
            if fav.get("question") == question and fav.get("sql") == sql:
                return fav.get("favorite_id")

        return None

    def save_favorite_from_history(
        self,
        log_id: str,
        name: Optional[str] = None
    ) -> Optional[FavoriteEntry]:
        """Save a history entry as a favorite."""
        if not self.history_service:
            return None
            
        entry = self.history_service.get_history_entry(log_id)
        if entry is None:
            return None

        return self.save_favorite(
            question=entry.question,
            sql=entry.sql,
            dialect=entry.dialect,
            name=name,
            log_id=log_id
        )
