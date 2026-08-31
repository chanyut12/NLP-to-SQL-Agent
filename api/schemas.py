from pydantic import BaseModel
from typing import Optional, List, Dict, Any

class QueryRequest(BaseModel):
    question: str
    dialect: str = "postgres"
    preferred_chart_type: Optional[str] = None  # User selected chart type from dropdown

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
    code: str  # LLM_FAILED | SQL_INVALID | EXEC_FAILED
    message: str

class QueryResponse(BaseModel):
    status: str  # "ok" | "error"
    request_id: str
    question: str
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

