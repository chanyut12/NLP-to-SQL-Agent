from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class DatabaseConfig(BaseModel):
    db_type: str = Field(..., description="SQLite, MySQL, or PostgreSQL")
    host: Optional[str] = "localhost"
    port: Optional[str] = None
    user: Optional[str] = None
    password: Optional[str] = None
    database: str = Field(..., description="Database name or file path")

class ConnectRequest(BaseModel):
    config: DatabaseConfig

class ConnectResponse(BaseModel):
    status: str
    message: str

class QueryRequest(BaseModel):
    question: str
    dialect: str = "sqlite"
    preferred_chart_type: Optional[str] = None  # User selected chart type from dropdown

# Visualization Model
class VizConfig(BaseModel):
    chart_type: str
    x_col: Optional[str]
    y_col: Optional[str]
    series_col: Optional[str] = None  # NEW: Column for multi-series grouping
    options: List[str]

class QueryResponse(BaseModel):
    sql: str
    data: Optional[List[Dict[str, Any]]] = None
    error: Optional[str] = None
    retry_count: int = 0
    log_id: Optional[str] = None
    visualization: Optional[VizConfig] = None # Added viz config

# Schema Models
class ColumnInfo(BaseModel):
    name: str
    type: str

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

