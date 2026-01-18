"""
Query History & Favorites Management Module for Thai NLP-to-SQL Agent.

This module provides functionality to:
- Load and display query history from JSONL logs
- Save/load/delete favorite queries
- Re-run queries from history
"""

import json
import os
import uuid
from datetime import datetime
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, asdict

from core.utils.common import truncate_text, format_timestamp


# File paths
HISTORY_FILE = "query_logs.jsonl"
FAVORITES_FILE = "favorites.json"


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


class QueryHistoryManager:
    """
    Manages query history and favorites for the Thai NLP-to-SQL application.
    """

    def __init__(
        self,
        history_file: str = HISTORY_FILE,
        favorites_file: str = FAVORITES_FILE
    ):
        """
        Initialize the QueryHistoryManager.

        Args:
            history_file: Path to the JSONL history file
            favorites_file: Path to the JSON favorites file
        """
        self.history_file = history_file
        self.favorites_file = favorites_file

    # --- History Methods ---

    def load_history(
        self,
        limit: int = 50,
        status_filter: Optional[str] = None,
        dialect_filter: Optional[str] = None
    ) -> List[HistoryEntry]:
        """
        Load query history from JSONL file.

        Args:
            limit: Maximum number of entries to return (most recent first)
            status_filter: Filter by status ("Success", "Error", or None for all)
            dialect_filter: Filter by dialect ("sqlite", "mysql", "postgres", or None)

        Returns:
            List of HistoryEntry objects, sorted by timestamp descending
        """
        if not os.path.isfile(self.history_file):
            return []

        entries = []
        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        entry = HistoryEntry(
                            log_id=data.get("log_id", ""),
                            timestamp=data.get("timestamp", ""),
                            question=data.get("question", ""),
                            sql=data.get("sql", ""),
                            status=data.get("status", ""),
                            error_msg=data.get("error_msg", ""),
                            duration_sec=data.get("duration_sec", 0.0),
                            feedback=data.get("feedback", ""),
                            feedback_text=data.get("feedback_text", ""),
                            dialect=data.get("dialect", "sqlite"),
                            retry_count=data.get("retry_count", 0)
                        )

                        # Apply filters
                        if status_filter and status_filter not in entry.status:
                            continue
                        if dialect_filter and entry.dialect != dialect_filter:
                            continue

                        entries.append(entry)
                    except json.JSONDecodeError:
                        continue
        except Exception:
            return []

        # Sort by timestamp descending and limit
        entries.sort(key=lambda x: x.timestamp, reverse=True)
        return entries[:limit]

    def get_history_entry(self, log_id: str) -> Optional[HistoryEntry]:
        """
        Get a specific history entry by log_id.

        Args:
            log_id: The unique identifier of the history entry

        Returns:
            HistoryEntry if found, None otherwise
        """
        if not os.path.isfile(self.history_file):
            return None

        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        if data.get("log_id") == log_id:
                            return HistoryEntry(
                                log_id=data.get("log_id", ""),
                                timestamp=data.get("timestamp", ""),
                                question=data.get("question", ""),
                                sql=data.get("sql", ""),
                                status=data.get("status", ""),
                                error_msg=data.get("error_msg", ""),
                                duration_sec=data.get("duration_sec", 0.0),
                                feedback=data.get("feedback", ""),
                                feedback_text=data.get("feedback_text", ""),
                                dialect=data.get("dialect", "sqlite"),
                                retry_count=data.get("retry_count", 0)
                            )
                    except json.JSONDecodeError:
                        continue
        except Exception:
            pass

    def update_feedback(self, log_id: str, feedback: str, feedback_text: str = None) -> bool:
        """
        Update feedback for a history entry.

        Args:
            log_id: The log ID to update
            feedback: "positive" or "negative"
            feedback_text: Optional user-typed comment

        Returns:
            True if updated, False otherwise
        """
        if not os.path.isfile(self.history_file):
            return False

        updated = False
        temp_file = self.history_file + ".tmp"
        
        try:
            with open(self.history_file, "r", encoding="utf-8") as f_in, \
                 open(temp_file, "w", encoding="utf-8") as f_out:
                
                for line in f_in:
                    try:
                        data = json.loads(line)
                        if data.get("log_id") == log_id:
                            data["feedback"] = feedback
                            if feedback_text is not None:
                                data["feedback_text"] = feedback_text
                            updated = True
                        f_out.write(json.dumps(data, ensure_ascii=False) + "\n")
                    except json.JSONDecodeError:
                        f_out.write(line) # Preserve malformed lines? Or skip? Let's preserve.
            
            if updated:
                os.replace(temp_file, self.history_file)
                return True
            else:
                os.remove(temp_file)
                return False
                
        except Exception as e:
            if os.path.exists(temp_file):
                os.remove(temp_file)
            return False

    # --- Favorites Methods ---

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
        """
        Load all favorites from JSON file.

        Returns:
            List of FavoriteEntry objects, sorted by use_count descending
        """
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
        """
        Save a query as a favorite.

        Args:
            question: The Thai question text
            sql: The SQL query
            dialect: Database dialect
            name: Optional custom name (defaults to truncated question)
            log_id: Optional reference to original history entry

        Returns:
            The created FavoriteEntry
        """
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
        """
        Delete a favorite by ID.

        Args:
            favorite_id: ID of the favorite to delete

        Returns:
            True if deleted, False if not found
        """
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
        """
        Update last_used and increment use_count when a favorite is re-run.

        Args:
            favorite_id: ID of the favorite that was used
        """
        data = self._load_favorites_file()

        for fav in data["favorites"]:
            if fav.get("favorite_id") == favorite_id:
                fav["last_used"] = datetime.now().isoformat()
                fav["use_count"] = fav.get("use_count", 0) + 1
                break

        self._save_favorites_file(data)

    def is_favorite(self, question: str, sql: str) -> Optional[str]:
        """
        Check if a query is already saved as favorite.

        Args:
            question: The question text
            sql: The SQL query

        Returns:
            favorite_id if exists, None otherwise
        """
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
        """
        Save a history entry as a favorite.

        Args:
            log_id: ID of the history entry to save
            name: Optional custom name

        Returns:
            Created FavoriteEntry if history entry found, None otherwise
        """
        entry = self.get_history_entry(log_id)
        if entry is None:
            return None

        return self.save_favorite(
            question=entry.question,
            sql=entry.sql,
            dialect=entry.dialect,
            name=name,
            log_id=log_id
        )


# --- Helper Functions ---



