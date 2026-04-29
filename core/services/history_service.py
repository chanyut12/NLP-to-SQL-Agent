"""
Service for managing query history logs.
"""
import json
import os
from typing import List, Optional

from core.domain.history_models import HistoryEntry


class HistoryService:
    """Handles reading and updating query execution history."""

    def __init__(self, history_file: str):
        self.history_file = history_file

    def load_history(
        self,
        limit: int = 50,
        status_filter: Optional[str] = None,
        dialect_filter: Optional[str] = None
    ) -> List[HistoryEntry]:
        """Load query history from JSONL file."""
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
                            retry_count=data.get("retry_count", 0),
                            tables_used=data.get("tables_used", []),
                            join_count=data.get("join_count", 0),
                            has_aggregation=data.get("has_aggregation", False),
                            has_subquery=data.get("has_subquery", False),
                            has_group_by=data.get("has_group_by", False),
                            result_row_count=data.get("result_row_count", -1),
                            rag_examples_count=data.get("rag_examples_count", 0),
                            model_name=data.get("model_name", ""),
                        )

                        if status_filter and status_filter not in entry.status:
                            continue
                        if dialect_filter and entry.dialect != dialect_filter:
                            continue

                        entries.append(entry)
                    except json.JSONDecodeError:
                        continue
        except Exception:
            return []

        entries.sort(key=lambda x: x.timestamp, reverse=True)
        return entries[:limit]

    def get_history_entry(self, log_id: str) -> Optional[HistoryEntry]:
        """Get a specific history entry by log_id."""
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
                                retry_count=data.get("retry_count", 0),
                                tables_used=data.get("tables_used", []),
                                join_count=data.get("join_count", 0),
                                has_aggregation=data.get("has_aggregation", False),
                                has_subquery=data.get("has_subquery", False),
                                has_group_by=data.get("has_group_by", False),
                                result_row_count=data.get("result_row_count", -1),
                                rag_examples_count=data.get("rag_examples_count", 0),
                                model_name=data.get("model_name", ""),
                            )
                    except json.JSONDecodeError:
                        continue
        except Exception:
            pass

        return None

    def update_feedback(self, log_id: str, feedback: str, feedback_text: str = None) -> bool:
        """Update feedback for a history entry."""
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
                        f_out.write(line)
            
            if updated:
                os.replace(temp_file, self.history_file)
                return True
            else:
                os.remove(temp_file)
                return False
                
        except Exception:
            if os.path.exists(temp_file):
                os.remove(temp_file)
            return False
