# 🇹🇭 Thai NLP-to-SQL Agent

**AI Data Analyst** ที่ช่วยให้คุณสอบถามข้อมูลจาก Database ได้ด้วย **ภาษาไทยธรรมชาติ** พร้อมแสดงผลเป็นกราฟอัตโนมัติ

![Architecture](https://img.shields.io/badge/Architecture-Client_Server-blue?style=for-the-badge) ![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white) ![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white) ![Chart.js](https://img.shields.io/badge/Chart.js-FF6384?style=for-the-badge&logo=chartdotjs&logoColor=white)

---

## ✨ Features

- 🇹🇭 **Thai Language Understanding** - ใช้ RAG พร้อม 50+ examples และ Dialect Filter
- 🧠 **Smart Schema Retrieval** - ค้นหา Table ที่เกี่ยวข้องอัตโนมัติ ลดขนาด Prompt
- 🔐 **SQL Safety** - Read-Only Enforcement, ป้องกันคำสั่งทำลายข้อมูล
- 📊 **Smart Visualization** - แนะนำกราฟอัตโนมัติ (Rule-based หรือ AI-powered)
- 🔄 **Self-Correction** - แก้ไข SQL อัตโนมัติถ้าเจอ Error พร้อม context ช่วยเหลือ
- 🗄️ **Multi-Database** - รองรับ SQLite, MySQL, PostgreSQL พร้อม Dialect-aware Examples
- 📝 **Query History** - บันทึกประวัติพร้อมระบบ Feedback (👍/👎 + ข้อความ)
- ⭐ **Favorites** - บันทึก Query ที่ชอบไว้ใช้ซ้ำ
- ⚡ **Performance Optimized** - Schema Caching, Lazy Loading, Shared Embedder
- 🤖 **Multi-LLM Support** - รองรับ Ollama (Local), OpenAI, Google Gemini

---

## 🏗️ Architecture

```
┌─────────────────────┐
│   Web Frontend      │  HTML/CSS/JS + Chart.js
│   web/              │
└──────────┬──────────┘
           │ REST API (FastAPI)
           ▼
┌─────────────────────┐
│   Backend Server    │  Python + LangChain
│   api/ + core/      │
└──────────┬──────────┘
           │
      ┌────┴─────┐
      ▼          ▼
  ┌──────┐  ┌─────────┐
  │  LLM │  │Database │
  │Ollama│  │SQLAlchemy│
  └──────┘  └─────────┘
```

### Request Flow

1. **User** → ถามคำถามภาษาไทย
2. **RAG** → ค้นหาตัวอย่างคล้ายกันจาก `thai_sql_examples.json`
3. **LLM** → สร้าง SQL จาก Prompt + Examples + Schema
4. **Validation** → ตรวจสอบความปลอดภัย
5. **Execution** → รัน Query
6. **Visualization** → แนะนำชนิดกราฟและแสดงผล

---

## ⚙️ Installation

### Prerequisites

- **Python 3.10+**
- **[Ollama](https://ollama.com/)** (สำหรับรัน LLM ในเครื่อง)

### Quick Start

```bash
# 1. Clone repository
git clone <your-repo-url>
cd nlp_sql_project

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Download LLM model
ollama pull qwen2.5-coder:7b

# 5. Create sample database (for testing)
python scripts/setup_db.py

# 6. Start backend API
uvicorn api.main:app --reload

# 7. Open frontend
# เปิดไฟล์ web/index.html ในเบราว์เซอร์
# หรือใช้ live server (e.g., VSCode Live Server extension)
```

Server จะรันที่ `http://localhost:8000`  
Frontend เปิดได้ที่ `file:///.../web/index.html` หรือใช้ live server

---

## 🗄️ Database Connection

### SQLite (ไฟล์ในเครื่อง)

1. เลือก **SQLite** ในหน้า Connection
2. ใส่ Path: `/absolute/path/to/database.db`
3. กด **Connect**

**ตัวอย่าง:**
```
/Users/yourname/Documents/nlp_sql_project/classicmodels.db
```

### MySQL

1. เลือก **MySQL**
2. ใส่ข้อมูล:
   - Host: `localhost`
   - Port: `3306`
   - User: `root`
   - Password: `yourpassword` (หรือเว้นว่างถ้าไม่มี)
   - Database: `yourdatabase`
3. กด **Connect**

### PostgreSQL

1. เลือก **PostgreSQL**
2. ใส่ข้อมูลเช่นเดียวกับ MySQL (Port: `5432`)

---

## 🎯 Usage Examples

### การถามคำถาม

```
✅ ยอดขายรวมทั้งหมด
✅ ลูกค้าที่ซื้อเยอะที่สุด 5 อันดับแรก
✅ ยอดขายปี 2004 แบ่งตาม Product Line ขอเป็นกราฟวงกลม
✅ แนวโน้มยอดขายรายเดือนปี 2004
```

### Chart Type Keywords

ระบบจะจับคำสั่งจากคำถาม:
- **"กราฟวงกลม"** / **"pie"** → Pie Chart
- **"กราฟแท่ง"** / **"bar"** → Bar Chart
- **"แนวโน้ม"** / **"line"** → Line Chart

หรือเปลี่ยนภายหลังได้จาก Dropdown (มีตัวเลือก **✨ Auto** ที่ให้ระบบเลือกให้)

---

## 📁 Project Structure

```
nlp_sql_project/
├── api/                      # Backend API
│   ├── main.py              # FastAPI entry point
│   ├── routes.py            # API endpoints
│   ├── schemas.py           # Request/Response models
│   └── dependencies.py      # Dependency injection
│
├── core/                     # Core Business Logic
│   ├── services/            # Application Use Cases
│   │   ├── engine.py        # NLPEngine (main orchestrator)
│   │   └── query_history.py
│   ├── domain/              # Business Rules
│   │   ├── schema_utils.py
│   │   └── sql_safety.py
│   ├── data/                # Data Infrastructure
│   │   ├── database.py
│   │   ├── rag_store.py
│   │   └── schema_rag.py
│   ├── viz/                 # Visualization
│   │   └── viz_recommender.py  # VizService
│   ├── utils/               # Shared Utilities
│   │   └── common.py        # ID generation, SQL cleaning
│   └── config.py            # Centralized settings (LLM, SQL limits, RAG params)
│
├── web/                      # Frontend
│   ├── index.html           # Main UI
│   ├── css/style.css        # Styling
│   └── js/                  # Client logic (ES Modules)
│       ├── main.js          # Entry point
│       └── modules/         # Feature modules
│           ├── api.js       # API calls
│           ├── chart.js     # Chart.js rendering
│           ├── config.js    # Configuration
│           ├── feedback.js  # Feedback modal
│           ├── state.js     # State management
│           ├── ui.js        # DOM manipulation
│           └── utils.js     # Utility functions
│
├── scripts/                  # Utilities
│   ├── setup_db.py          # สร้าง sample database
│   └── convert_mysql_to_sqlite.py
│
├── thai_sql_examples.json    # RAG training data
├── requirements.txt          # Python dependencies
└── docs/                     # Documentation
    ├── PRODUCT_SPEC.md      # Developer guide
    ├── MODEL_SETUP.md       # LLM configuration
    └── TUNING_GUIDE.md      # Performance optimization
```

---

## 🔧 Configuration

### Environment Variables

สร้างไฟล์ `.env` (optional):

```bash
# LLM Provider (ollama, openai, or google)
MODEL_PROVIDER=google

# Google Gemini Settings (recommended for speed + accuracy)
GOOGLE_API_KEY=your-api-key-here
GOOGLE_MODEL=gemini-2.0-flash-exp

# Ollama Settings (for local/offline use)
OLLAMA_MODEL=qwen2.5-coder:7b
OLLAMA_BASE_URL=http://localhost:11434

# OpenAI Settings
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini

# Performance Settings
ENABLE_INTELLIGENT_VIZ=false  # Set to true for AI-powered chart recommendations
```

---

## 🛡️ Security & Safety

ระบบป้องกันคำสั่งอันตราย:

1. ✅ **Read-Only Enforcement** - บล็อก `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`
2. ✅ **LIMIT Auto-Injection** - บังคับ `LIMIT 500` เพื่อป้องกันดึงข้อมูลมากเกิน
3. ✅ **SQL Parsing** - ใช้ `sqlglot` ตรวจสอบ syntax
4. ✅ **Table Validation** - ตรวจว่าเข้าถึงเฉพาะตารางที่มีจริง

---

## 📊 Improving Accuracy

### เพิ่มตัวอย่างใหม่

แก้ไขไฟล์ `thai_sql_examples.json`:

```json
{
  "description": "Thai to SQL examples",
  "version": "1.0",
  "examples": [
    {
      "question": "คำถามภาษาไทย",
      "sql": "SELECT ...",
      "category": "aggregation"
    }
  ]
}
```

**Tips:**
- เพิ่มตัวอย่างที่เฉพาะเจาะจงกับ Database ของคุณ
- ใส่ตัวอย่าง JOIN ที่ซับซ้อน
- ครอบคลุมทุก category (aggregation, filter, ranking, etc.)

### ปรับ Prompt

แก้ไขไฟล์ `core/engine.py` (line 56-91) เพื่อปรับ System Prompt

---

## 🧪 Testing

### การทดสอบ Database

1. **ClassicModels Sample DB:**
   ```bash
   # Convert MySQL dump to SQLite
   python scripts/convert_mysql_to_sqlite.py
   
   # Result: classicmodels.db
   ```

2. **Test Queries:**
   ```
   ยอดขายปี 2004 แบ่งตาม Product Line
   ลูกค้าที่ใช้เงินมากที่สุด 5 อันดับแรก
   ```

### การตรวจสอบ Code

```bash
# Run unit tests (31 tests)
python -m pytest tests/ -v

# Validate Python syntax
python -m py_compile core/*.py api/*.py

# Check API health
curl http://localhost:8000/api/health
```

---

## 📈 Query History & Feedback

- ทุก Query จะบันทึกใน `query_logs.jsonl`
- กด 👍 หรือ 👎 ในหน้า History เพื่อให้ Feedback
- Query ที่ถูกต้องสามารถเพิ่มเข้า `thai_sql_examples.json` เพื่อปรับปรุงระบบ

---

## 🚀 Production Deployment

### Checklist

- [ ] ใช้ `MODEL_PROVIDER=openai` สำหรับความแม่นยำสูงสุด
- [ ] เพิ่ม Rate Limiting (e.g., SlowAPI)
- [ ] ตั้งค่า CORS อย่างถูกต้อง
- [ ] ใช้ HTTPS
- [ ] เพิ่ม Authentication/Authorization
- [ ] ตั้ง Database Connection Pool
- [ ] เพิ่ม Monitoring (Prometheus/Grafana)

### Docker (Coming Soon)

```dockerfile
# Dockerfile example
FROM python:3.10-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## 🤝 Contributing

1. Fork the project
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Open a Pull Request

ดูรายละเอียดเพิ่มเติมที่ `docs/PRODUCT_SPEC.md`

---

## 📚 Documentation

- [Product Specification](docs/PRODUCT_SPEC.md) - Developer guide
- [Model Setup](docs/MODEL_SETUP.md) - LLM configuration
- [Tuning Guide](docs/TUNING_GUIDE.md) - Performance optimization
- [Issues & Roadmap](docs/ISSUES_ROADMAP.md) - Known issues and development plan

---

## 🐛 Known Issues

1. **Complex JOINs** - LLM อาจเลือก table ผิดเมื่อต้อง JOIN หลายตาราง (ดู [Issues Roadmap](docs/ISSUES_ROADMAP.md))
2. **Large Result Sets** - ไม่มี pagination สำหรับตารางขนาดใหญ่
3. **Query Cancellation** - ไม่สามารถยกเลิก Query ที่ใช้เวลานานได้

---

## 📝 License

MIT License - feel free to use for commercial or personal projects

---

## 🙏 Acknowledgments

- **LangChain** - LLM orchestration framework
- **Ollama** - Local LLM runtime
- **Chart.js** - Beautiful charts
- **FastAPI** - Modern Python web framework
- **Qwen Team** - Excellent coding model

---

**Made with ❤️ for Thai Developers**

สร้างโดยนักพัฒนาไทย เพื่อนักพัฒนาไทย 🇹🇭
