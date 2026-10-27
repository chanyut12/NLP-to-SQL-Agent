from pydantic import BaseModel
from typing import Optional, List, Dict, Any, Literal

# ADR 0006: STEP_BUDGET_EXCEEDED is reserved for the agent loop (ticket #20)
# exhausting its step budget; today it can only come from a future Consumer
# contract, but the vocabulary is pinned here so Consumers can match on it.
ERROR_CODES = ("LLM_FAILED", "SQL_INVALID", "EXEC_FAILED", "STEP_BUDGET_EXCEEDED")

class QueryRequest(BaseModel):
    question: str
    dialect: str = "postgres"
    preferred_chart_type: Optional[str] = None  # User selected chart type from dropdown
    # Conversational Sessions (ADR 0006): the Consumer sends structured prior
    # Turns with each request; the service itself stays stateless. Rows are
    # deliberately not part of a Turn — only question / answer_type / SQL /
    # row_count, mirroring the envelope minus the payload.
    history: Optional[List["PriorTurn"]] = None

class PriorTurn(BaseModel):
    """One completed Turn of a Session, as replayed by the Consumer."""
    question: str
    answer_type: Literal["result", "clarification", "refusal"]
    # A result Turn carries the SQL that produced it; clarification/refusal
    # turns must not (there was no query to run).
    sql: Optional[str] = None
    row_count: Optional[int] = None
    # ADR 0010 / #34: the envelope's `turn_digest` of this Turn, stored by the
    # Consumer and replayed here. Optional — absent history stays SQL-only.
    digest: Optional[Dict[str, Any]] = None

    def model_post_init(self, __context) -> None:
        has_sql = bool(self.sql and self.sql.strip())
        if self.answer_type == "result" and not has_sql:
            raise ValueError("a result Turn must carry the SQL that produced it")
        if self.answer_type in ("clarification", "refusal") and has_sql:
            raise ValueError(
                f"a {self.answer_type} Turn must not carry SQL")
        if not self.question.strip():
            raise ValueError("a Turn must carry its question")
        if self.row_count is not None and self.row_count < 0:
            raise ValueError("row_count must be non-negative")

# Visualization Model
class VizConfig(BaseModel):
    chart_type: str
    x_col: Optional[str]
    y_col: Optional[str]
    series_col: Optional[str] = None  # Column for multi-series grouping
    options: List[str]
    title: Optional[str] = None
    x_label: Optional[str] = None
    y_label: Optional[str] = None
    top_n: Optional[int] = None  # fold categories past this into one "other" slice
    reason: Optional[str] = None

# Schema Models
class ColumnInfo(BaseModel):
    name: str
    type: str
    numeric: bool = False
    # count | number | percent | gpa | date | id | category | name | text
    semantic_type: str = "text"

class ResultSummary(BaseModel):
    row_count: int
    truncated: bool = False
    # column name -> {"sum","min","max","mean"} (non-finite values dropped)
    numeric_aggregates: Dict[str, Dict[str, float]] = {}
    single_value: bool = False  # 1 row x 1 numeric column

class QueryError(BaseModel):
    code: Literal[ERROR_CODES]  # LLM_FAILED | SQL_INVALID | EXEC_FAILED | STEP_BUDGET_EXCEEDED
    message: str

class QueryResponse(BaseModel):
    status: str  # "ok" | "error"
    request_id: str
    question: str
    # Answer (ADR 0006): result | clarification | refusal. Today's one-shot
    # pipeline only ever produces "result"; the vocabulary ships with the
    # envelope so Consumers can dispatch on it before the agent loop lands.
    answer_type: Literal["result", "clarification", "refusal"] = "result"
    # Thai text carrying the Answer's readable part: the clarification
    # question, the refusal explanation, or (since the grilled “every Answer
    # speaks” decision, Oct 2026) a 2–3-sentence Thai summary of a result —
    # the same text the agent puts in final_answer's message. A Consumer shows
    # it as a chat bubble beside the table/chart. Advisory like the rest of
    # the presentation fields, but the service always tries to fill it for
    # every non-error Answer.
    message: Optional[str] = None
    steps_used: int = 1
    # Context-preparation duration in ms (retrieval + schema filtering) —
    # additive (spec #27/#31): Consumers must ignore unknown fields. Lets a
    # Consumer separate the service's own work from the structural LLM step
    # cost when explaining elapsed_ms.
    prep_ms: Optional[int] = None
    # Deterministic description of a Result Turn (tables, populations, filters,
    # grouping, top rows) for the Consumer to replay in `history` (ADR 0010 / #34).
    # Additive and advisory: Consumers that ignore it lose nothing.
    turn_digest: Optional[Dict[str, Any]] = None
    sql: Optional[str] = None
    columns: List[ColumnInfo] = []
    rows: Optional[List[Dict[str, Any]]] = None
    row_count: int = 0
    truncated: bool = False
    summary: Optional[ResultSummary] = None
    visualization: Optional[VizConfig] = None
    retry_count: int = 0
    elapsed_ms: int = 0
    error: Optional[QueryError] = None

class TableInfo(BaseModel):
    name: str
    columns: List[ColumnInfo]

class SchemaResponse(BaseModel):
    tables: List[TableInfo]

# History Models
class HistoryItem(BaseModel):
    log_id: str
    timestamp: str
    question: str
    sql: str
    status: str
    dialect: str
    feedback: Optional[str] = None
    feedback_text: Optional[str] = None  # User-typed feedback comment

class HistoryResponse(BaseModel):
    history: List[HistoryItem]

# Favorites Models
class FavoriteItem(BaseModel):
    favorite_id: str
    question: str
    sql: str
    dialect: str
    name: Optional[str] = None
    use_count: int = 0

class FavoritesResponse(BaseModel):
    favorites: List[FavoriteItem]

class CreateFavoriteRequest(BaseModel):
    question: str
    sql: str
    dialect: str
    log_id: Optional[str] = None
    name: Optional[str] = None

class FeedbackRequest(BaseModel):
    feedback: str  # "positive" or "negative"
    feedback_text: Optional[str] = None  # Optional user-typed comment

# =============================================================================
# Demo-mode Datasource switching (APP_MODE=demo / auto without a key; ADR 0013)
# =============================================================================
# These models are not part of the Consumer contract: the endpoints are mounted
# only where the bundled UI is served, and a service deployment keeps ADR 0011's
# one-Datasource-per-deployment rule.

class DemoConnectRequest(BaseModel):
    database_url: str  # SQLAlchemy DSN, e.g. sqlite:///./local_database.db
    profile: Optional[str] = None  # profiles/<name>; defaults to the active one

class DemoConnectResponse(BaseModel):
    datasource: str  # the accepted DSN, password redacted
    profile: str
    tables: List[str] = []  # readable tables (denylist applied) on the new Datasource

class DemoStateResponse(BaseModel):
    datasource: Optional[str] = None  # redacted DSN; None until one is configured
    profile: str
    profiles: List[str] = []  # profile names the demo can switch to

