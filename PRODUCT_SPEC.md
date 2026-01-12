# 📋 Product Specification: Thai NLP-to-SQL Agent

**Version:** 2.3  
**Last Updated:** 2026-01-12  
**Architecture:** Client-Server (REST API)

---

## 🎯 Overview

A Thai-language Natural Language Processing system that converts Thai questions into SQL queries, executes them against databases, and automatically generates visualizations. Supports multiple database types (SQLite, MySQL, PostgreSQL) with intelligent chart recommendations.

### Key Features
- 🇹🇭 Thai language understanding (with RAG-based few-shot learning + Dialect Filter)
- 🔐 SQL safety validation (read-only enforcement)
- 📊 Smart visualization (Rule-based or AI-powered, configurable)
- 🔄 Self-correction mechanism (retry on error with expanded schema context)
- 📝 Query history with feedback system (👍/👎 + text comments)
- ⭐ Favorite queries management
- 🎯 Dialect-aware prompting and examples (MySQL/SQLite)
- 🧠 Smart Schema Retrieval (reduces prompt tokens by ~50%)
- ⚡ Performance Optimizations (Schema Caching, Lazy Loading, Shared Embedder)
- 🤖 Multi-LLM Support (Ollama, OpenAI, Google Gemini)

---

## 🏗️ Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        WEB FRONTEND                             │
│    web/index.html  +  js/main.js  +  css/style.css  +  Chart.js │
└──────────────────────────────┬──────────────────────────────────┘
                               │ HTTP REST API (JSON)
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                       FASTAPI SERVER                            │
│         api/main.py ─► api/routes.py ─► api/schemas.py          │
└──────────────────────────────┬──────────────────────────────────┘
                               │
         ┌─────────────────────┼─────────────────────┐
         ▼                     ▼                     ▼
┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
│   Query History │   │    NLPEngine    │   │   SQL Safety    │
│query_history.py │   │   engine.py     │   │  sql_safety.py  │
│  (Logging/      │   │  (Orchestrator) │   │  (Validation)   │
│   Feedback)     │   └────────┬────────┘   └─────────────────┘
└─────────────────┘            │
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
    ┌─────────────────┐ ┌─────────────┐ ┌──────────────────┐
    │    RAG Store    │ │Schema Utils │ │ Viz Recommender  │
    │  rag_store.py   │ │schema_utils │ │viz_recommender.py│
    │  + ChromaDB     │ │    .py      │ │ (Chart Suggest)  │
    └────────┬────────┘ └──────┬──────┘ └──────────────────┘
             │                 │
             │                 ▼
             │         ┌──────────────────┐
             │         │     Database     │
             │         │   database.py    │
             │         │   (SQLAlchemy)   │
             │         └──────────────────┘
             │                  ▲
             │                  │
             │          ┌───────┴───────┐
             │          │  Schema RAG   │
             │          │ schema_rag.py │
             │          │ schema_rag_db │
             │          └───────┬───────┘
             │                  │
             ▼                  ▼
    ┌─────────────────────────────────────┐
    │      LLM Provider (config.py)       │
    │  ┌─────────┐ ┌────────┐ ┌────────┐  │
    │  │ Ollama  │ │ OpenAI │ │ Gemini │  │
    │  │ (Local) │ │ (Cloud)│ │(Google)│  │
    │  └─────────┘ └────────┘ └────────┘  │
    │      + Self-Correction Loop         │
    └─────────────────────────────────────┘
```

### Component Descriptions

| Component | File(s) | Responsibility |
|-----------|---------|----------------|
| **Web Frontend** | `web/` | UI, Chart.js rendering, API calls |
| **FastAPI Server** | `api/` | REST endpoints, request validation |
| **NLPEngine** | `engine.py` | Main orchestrator - coordinates all steps |
| **RAG Store** | `rag_store.py` | Semantic search for similar examples (`rag_db`) |
| **Schema RAG** | `schema_rag.py` | [NEW] Semantic search for relevant tables (`schema_rag_db`) |
| **Schema Utils** | `schema_utils.py` | Extract & filter database schema (Hybrid Search) |
| **SQL Safety** | `sql_safety.py` | Block destructive SQL, enforce LIMIT |
| **Viz Recommender** | `viz_recommender.py` | Suggest chart type based on data shape |
| **Query History** | `query_history.py` | Log queries, manage feedback |
| **Database** | `database.py` | SQLAlchemy connection management |
| **Config** | `config.py` | LLM provider settings (Ollama/OpenAI/Gemini), Performance flags |

### Data Flow

```
User Question (Thai)
        │
        ▼
┌───────────────────┐
│ 1. RAG Retrieval  │ ─── Find similar examples from thai_sql_examples.json
└─────────┬─────────┘
          ▼
┌───────────────────┐     ┌───────────────────┐
│ 2. Schema Finding │ ─── │ 2.1 Schema RAG    │ (Find relevant tables via vector search)
└─────────┬─────────┘     └─────────┬─────────┘
          │                         │
          ▼                         ▼
┌───────────────────┐     ┌───────────────────┐
│ 3. Schema Filter  │ ─── │ 3.1 Keyword Map   │ (Thai-English Mapping)
└─────────┬─────────┘     └───────────────────┘
          ▼
┌───────────────────┐
│ 3. LLM Generation │ ─── Prompt + Examples + Schema → SQL
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ 4. SQL Validation │ ─── Check safety, add LIMIT
└─────────┬─────────┘
          ▼
┌───────────────────┐     ┌─────────────────┐
│ 5. Execute Query  │────►│ Error? Retry    │ (Self-Correction Loop)
└─────────┬─────────┘     └─────────────────┘
          ▼
┌───────────────────┐
│ 6. Viz Recommend  │ ─── Analyze DataFrame → Suggest chart type
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ 7. Return Result  │ ─── SQL + Data + Chart Config → Frontend
└───────────────────┘
```

---

## 📁 Project Structure

```
nlp_sql_project/
├── api/                    # Backend API Layer
│   ├── main.py            # FastAPI app entry point
│   ├── routes.py          # API endpoints (/query, /connect, /schema, etc.)
│   ├── schemas.py         # Pydantic models for request/response
│   └── dependencies.py    # Dependency injection (DB state, LLM engine)
│
├── core/                   # Core Business Logic
│   ├── engine.py          # NLPEngine - main query orchestration
│   ├── database.py        # Database connection management
│   ├── rag_store.py       # RAG vector store for examples (Lazy Loading)
│   ├── schema_rag.py      # RAG vector store for schema metadata (Shared Embedder)
│   ├── schema_utils.py    # Schema extraction and smart filtering
│   ├── sql_safety.py      # SQL validation and sanitization
│   ├── viz_recommender.py # Chart type recommendation (Rule-based + AI)
│   ├── query_history.py   # History and feedback management
│   └── config.py          # Configuration settings + Performance flags
│
├── web/                    # Frontend
│   ├── index.html         # Main UI
│   ├── css/
│   │   └── style.css      # Styling (dark mode, glassmorphism)
│   └── js/
│       └── main.js        # Frontend logic (API calls, rendering)
│
├── scripts/                # Utility Scripts
│   ├── setup_db.py        # Create sample database for testing
│   └── convert_mysql_to_sqlite.py  # MySQL dump → SQLite converter
│
├── thai_sql_examples.json  # RAG Training Examples (50+ examples)
├── requirements.txt        # Python dependencies
│
├── README.md               # Quick start guide
├── PRODUCT_SPEC.md         # Developer specification (this file)
├── TUNING_GUIDE.md         # LLM tuning and optimization guide
└── MODEL_SETUP.md          # LLM provider configuration
```

---

## 🔧 Key Components

### 1. Backend API (`api/`)

#### `routes.py` - API Endpoints
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/connect` | POST | Establish database connection |
| `/query` | POST | Execute NLP query |
| `/schema` | GET | Get database schema |
| `/history` | GET | Retrieve query history |
| `/history/{id}/feedback` | PATCH | Update feedback |
| `/favorites` | GET/POST/DELETE | Manage favorite queries |
| `/health` | GET | Health check |

**Modify here to:**
- Add new API endpoints
- Change request/response formats
- Add authentication/authorization

#### `schemas.py` - Data Models
Defines Pydantic models for type validation.

**Modify here to:**
- Add new fields to requests/responses
- Change validation rules

---

### 2. Core Engine (`core/`)

#### `engine.py` - NLPEngine
The brain of the system. Orchestrates:
1. RAG example retrieval
2. Schema extraction
3. LLM prompt construction
4. SQL generation
5. Validation
6. Execution
7. Visualization recommendation
8. Retry logic

**Modify here to:**
- Change LLM prompt template (line 55-100)
- Adjust retry strategy
- Add new LLM providers (Claude, etc.)
- Modify SQL formatting rules
- Update dialect cheat sheet

#### `rag_store.py` - RAG System
Uses FAISS + Sentence Transformers for semantic search.

**Modify here to:**
- Change embedding model
- Adjust similarity threshold
- Add new example sources
- Implement hybrid search (BM25 + semantic)

#### `sql_safety.py` - Security Layer
Validates SQL to prevent:
- Destructive operations (DROP, DELETE, etc.)
- Unauthorized table access
- Query without LIMIT

**Modify here to:**
- Add/remove forbidden operations
- Change LIMIT enforcement rules
- Add custom security rules

#### `viz_recommender.py` - Smart Visualization
Analyzes DataFrame and recommends chart type with intelligent column selection.

**Key Logic:**
- Detects metric columns (count, sum, total) for Y-axis
- Identifies dimension columns (year, month, id) for X-axis
- Supports user keyword preferences ("สัดส่วน", "แนวโน้ม")

**Modify here to:**
- Add new chart types
- Improve recommendation logic
- Add user preference keywords (e.g., "กราฟ 3D")

---

### 3. Frontend (`web/`)

#### `main.js` - Client Logic
Key functions:
- `connectDB()` - Database connection
- `sendMessage()` - Query submission
- `renderChart()` - Chart.js rendering
- `renderTable()` - Data table display

**Modify here to:**
- Add new UI features
- Change chart styling
- Implement real-time query updates
- Add export functionality (CSV, PDF)

#### `style.css` - Styling
Uses modern CSS with:
- Dark mode
- Glassmorphism
- Gradient effects

**Modify here to:**
- Change color scheme
- Add themes (light/dark toggle)
- Improve responsive design

---

## 🛠️ Common Development Tasks

### 1. Add Support for a New Database Type

**Files to modify:**
1. `core/database.py` - Add connection string logic
2. `core/sql_safety.py` - Add dialect-specific validation
3. `web/index.html` - Add option to DB type selector
4. `api/schemas.py` - Update DatabaseConfig model

**Example:**
```python
# core/database.py
elif db_type == "Oracle":
    db_path = f"oracle+cx_oracle://{user}:{password}@{host}:{port}/{database}"
```

---

### 2. Improve Thai Language Understanding

**Files to modify:**
1. `thai_sql_examples.json` - Add more training examples
2. `core/engine.py` - Update Thai-to-English mapping (line 72-80)
3. `core/rag_store.py` - Adjust similarity threshold

**Best Practice:**
- Add examples for new databases/schemas
- Include edge cases (typos, slang)
- Balance examples across query types

---

### 3. Add a New Chart Type

**Files to modify:**
1. `core/viz_recommender.py`:
   ```python
   # Add new chart condition
   if has_geolocation_data:
       return "map", lat_col, lon_col
   ```

2. `web/js/main.js`:
   ```javascript
   // Add rendering logic
   type: config.chart_type === 'map' ? 'chartjs-chart-geo' : ...
   ```

3. `web/index.html`:
   ```html
   <option value="map">🗺️ Map</option>
   ```

---

### 4. Implement User Authentication

**New files needed:**
1. `api/auth.py` - JWT token management
2. `core/users.py` - User database models

**Files to modify:**
1. `api/routes.py` - Add `Depends(get_current_user)`
2. `api/dependencies.py` - Add authentication dependency
3. `web/js/main.js` - Store and send JWT tokens

---

### 5. Add Model Fine-tuning Support

**Files to modify:**
1. `core/engine.py` - Add fine-tuned model loading
2. `core/config.py` - Add fine-tuning config options
3. Create new `training/` directory for fine-tuning scripts

---

### 6. Improve Error Handling

**Files to modify:**
1. `api/routes.py` - Add custom exception handlers
2. `core/engine.py` - Add more specific error types
3. `web/js/main.js` - Display user-friendly error messages

**Example:**
```javascript
// main.js
if (error.includes("connection refused")) {
    showError("ไม่สามารถเชื่อมต่อฐานข้อมูลได้ กรุณาตรวจสอบการตั้งค่า");
}
```

---

## 🧪 Testing Strategy

### Unit Tests (To be implemented)
```python
# tests/test_sql_safety.py
def test_blocks_destructive_sql():
    result = validate_and_sanitize_sql("DROP TABLE users", "sqlite")
    assert result.error == "Forbidden operation detected"
```

### Integration Tests
```python
# tests/test_engine.py
def test_end_to_end_query():
    engine = NLPEngine()
    sql, data, error, _, _ = engine.query_database(
        "ยอดขายรวม", test_db_engine, "sqlite"
    )
    assert error is None
    assert "SUM" in sql
```

### Manual Testing
Use queries in `validation_report.md` → Test Recommendations section.

---

## 🚀 Deployment Considerations

### Production Checklist
- [ ] Set `MODEL_PROVIDER=openai` for better accuracy
- [ ] Add rate limiting to API endpoints
- [ ] Implement query result caching
- [ ] Set up HTTPS for frontend
- [ ] Add monitoring (Prometheus/Grafana)
- [ ] Configure CORS properly
- [ ] Add database connection pooling
- [ ] Implement query timeout limits

### Environment Variables
```bash
# Required
MODEL_PROVIDER=ollama|openai|google
GOOGLE_API_KEY=...       # If using Google Gemini
OPENAI_API_KEY=sk-...    # If using OpenAI

# Optional
OLLAMA_MODEL=qwen2.5-coder:7b
OLLAMA_BASE_URL=http://localhost:11434
GOOGLE_MODEL=gemini-2.0-flash-exp
OPENAI_MODEL=gpt-4o-mini

# Performance Flags
ENABLE_INTELLIGENT_VIZ=false  # Set true for AI-powered chart recommendations
```

---

## 📊 Performance Optimization

### Implemented Optimizations
1. **Schema Caching** - Database schema is cached in `NLPEngine` to avoid repeated metadata queries
2. **Lazy Loading** - Embedding models load only when first needed, not at startup
3. **Shared Embedder** - `ExampleStore` and `SchemaRAG` share the same `SentenceTransformer` instance (~50% RAM reduction)
4. **Skip Redundant Encoding** - RAG store checks existing IDs before re-encoding examples
5. **Configurable Viz** - `ENABLE_INTELLIGENT_VIZ=false` skips AI visualization call (~30-50% faster)

### Backend (Future)
1. **RAG Store** - Cache embeddings in Redis
2. **LLM** - Implement request batching for multiple queries

### Frontend
1. **Chart Rendering** - Destroy old charts before creating new ones
2. **Data Tables** - Add pagination for large results
3. **API Calls** - Debounce user input

---

## 🐛 Known Limitations

1. **Model Accuracy** - Local 7B models may struggle with complex queries without examples
2. **Memory Leaks** - Chart.js instances not properly destroyed
3. **No Query Cancellation** - Long-running queries cannot be stopped

---

## 📚 Further Reading

- [FastAPI Documentation](https://fastapi.tiangolo.com)
- [LangChain Documentation](https://python.langchain.com)
- [Chart.js Documentation](https://www.chartjs.org)
- [SQLAlchemy Documentation](https://docs.sqlalchemy.org)

---

## 🤝 Contributing

### Adding New Features
1. Update this PRODUCT_SPEC.md
2. Add unit tests
3. Update validation_report.md with test cases
4. Document in comments

### Code Style
- Python: PEP 8
- JavaScript: Standard JS
- Use type hints in Python
- Add docstrings to functions

---

**Happy Coding! 🎉**
