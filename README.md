# 🇹🇭 Thai NLP-to-SQL Agent

**Thai NL-to-SQL microservice** — รับคำถามภาษาไทย แล้วตอบกลับเป็น SQL, ผลลัพธ์, column metadata, summary และคำแนะนำกราฟ สำหรับให้ Consumer (เช่น backend ของ STS) นำไปแสดงผลเอง

![Architecture](https://img.shields.io/badge/Architecture-Client_Server-blue?style=for-the-badge) ![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white) ![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white) ![Chart.js](https://img.shields.io/badge/Chart.js-FF6384?style=for-the-badge&logo=chartdotjs&logoColor=white)

---

## ✨ Features

- 🇹🇭 **Thai Language Understanding** - ใช้ RAG จาก Example set ของ Domain profile
- 🧠 **Smart Schema Retrieval** - ค้นหา Table ที่เกี่ยวข้องอัตโนมัติ ลดขนาด Prompt
- 🔐 **SQL Safety** - Read-Only Enforcement, ป้องกันคำสั่งทำลายข้อมูล
- 📊 **Smart Visualization** - แนะนำกราฟอัตโนมัติ (Rule-based หรือ AI-powered)
- 🔄 **Self-Correction** - แก้ไข SQL อัตโนมัติถ้าเจอ Error พร้อม context ช่วยเหลือ
- 💬 **Conversational agent** - stateless sessions, clarification/refusal และข้อความภาษาไทยในทุกคำตอบ
- 🗄️ **Datasource-agnostic core** - หนึ่ง deployment ต่อหนึ่ง datasource (อ่านอย่างเดียว) — วันนี้รองรับ STS PostgreSQL ผ่าน Domain profile
- 🧪 **Two deployment modes** - standalone demo UI (local SQLite sample, no key) หรือ Consumer-only microservice (`APP_MODE=service` + `API_KEY`)
- ⚡ **Performance Optimized** - Schema Caching, Lazy Loading, Shared Embedder
- 🤖 **Multi-LLM Support** - รองรับ Ollama (Local), OpenAI, Google Gemini, OpenRouter และ Zhipu

---

## 🎯 Scope & Supported Datasources

Service หนึ่ง instance ตอบคำถามกับ **Datasource เดียว** ที่ถูก fix ตอน deploy ผ่าน `DATABASE_URL` (อ่านอย่างเดียว) — ไม่มี runtime `/connect` และ Consumer ไม่ส่ง credential ของ Datasource มา

| Datasource | Engine | สถานะ |
|---|---|---|
| **STS (Student Tracking System)** | PostgreSQL | **รองรับ** — active Domain profile `sts` |
| **Standalone demo** | SQLite `local_database.db` | **demo only** — `APP_MODE=demo` + `./start_demo.sh`; ไม่ใช่ production datasource |
| `receipt_sample` | MySQL/SQLite examples | legacy sample สำหรับพัฒนาเท่านั้น ไม่ใช่ datasource ที่รองรับ |
| อื่น ๆ | — | ยังไม่รองรับ — เป็นทิศทางอนาคต |

การรองรับ database ใหม่ = เพิ่ม Domain profile ใหม่ + ผ่าน evaluation ไม่ใช่การสลับ DB ตอน runtime ดูรายละเอียดที่ [docs/guides/PROFILES.md](docs/guides/PROFILES.md)

---

## 🏗️ Architecture

```
┌──────────────────────┐   ┌──────────────────────┐
│ Consumer             │   │ Demo UI (demo mode)  │
│ e.g. sts-backend     │   │ web/ + Chart.js      │
└──────────┬───────────┘   └──────────┬───────────┘
           │  POST /api/query         │
           │  X-API-Key               │
           └────────────┬─────────────┘
                        ▼
           ┌──────────────────────┐
           │ Backend Server       │  Python + LangChain
           │ api/ + core/         │
           └──────────┬───────────┘
                      │
             ┌────────┴────────┐
             ▼                 ▼
       ┌───────────┐     ┌──────────────┐
       │    LLM    │     │ Datasource   │
       │ provider  │     │ STS Postgres │
       └───────────┘     │ (read-only)  │
                         └──────────────┘
```

### Request Flow

1. **Consumer / Demo UI** → ส่งคำถามภาษาไทย
2. **RAG** → ค้นหาตัวอย่างคล้ายกันจาก `profiles/<profile>/examples.json`
3. **LLM / agent** → สร้าง SQL จาก Prompt + Examples + Schema
4. **Validation** → ตรวจสอบความปลอดภัย
5. **Execution** → รัน Query กับ Datasource แบบ read-only
6. **Response** → คืน SQL + rows + metadata + คำแนะนำกราฟ (Consumer เป็นคน render)

---

## ⚙️ Installation

### Prerequisites

- **Python 3.10+**
- **LLM Provider** — เลือกอย่างใดอย่างหนึ่ง:
  - **Local (ฟรี):** [Ollama](https://ollama.com/) + RAM 8GB+
  - **Cloud (ง่ายกว่า):** Google Gemini API key ([ฟรี 1,500 req/day](https://makersuite.google.com/app/apikey)) หรือ OpenAI

---

### 🚀 Quick Start

#### 🪟 Windows

```bat
:: 1. Clone repository
git clone https://github.com/chanyut12/NLP-to-SQL-Agent.git
cd NLP-to-SQL-Agent

:: 2. Run setup script (สร้าง venv + ติดตั้ง dependencies + สร้าง .env)
setup.bat

:: 3. แก้ไข .env — ตั้ง DATABASE_URL (read-only), DOMAIN_PROFILE=sts และ LLM provider
::    ใช้ Notepad หรือ VSCode เปิดไฟล์ .env

:: 4. Start server (dev — auto-reload)
start_server.bat
```

#### 🍎 macOS

```bash
# 1. Clone repository
git clone https://github.com/chanyut12/NLP-to-SQL-Agent.git
cd NLP-to-SQL-Agent

# 2. Run setup script
chmod +x setup.sh && ./setup.sh

# 3. แก้ไข .env — ตั้ง DATABASE_URL (read-only), DOMAIN_PROFILE=sts และ LLM provider
nano .env  # หรือ open -e .env

# 4. Start server (dev — auto-reload, เคลียร์ port 8000 ให้เอง)
./start_server.sh
```

#### 🐧 Linux

```bash
# 1. Clone repository
git clone https://github.com/chanyut12/NLP-to-SQL-Agent.git
cd NLP-to-SQL-Agent

# 2. Run setup script
chmod +x setup.sh && ./setup.sh

# 3. แก้ไข .env — ตั้ง DATABASE_URL (read-only), DOMAIN_PROFILE=sts และ LLM provider
nano .env

# 4. Start server (dev — auto-reload, เคลียร์ port 8000 ให้เอง)
./start_server.sh
```

> `setup.sh` / `setup.bat` สร้าง `local_database.db` เป็น sample สำหรับ development เท่านั้น — service จะตอบ `503` จนกว่าจะตั้ง `DATABASE_URL` ของ STS

#### 🧪 Standalone demo (ไม่ต้องใช้ STS)

```bash
./start_demo.sh
# เปิด http://127.0.0.1:8001/
```

- ใช้ `local_database.db` + `profiles/demo` โดยไม่แตะ `DATABASE_URL` จาก `.env`
- `APP_MODE=demo`: UI อยู่ที่ `/`, `/api` ไม่ต้องใช้ key, และ bind `127.0.0.1` เท่านั้น
- แท็บ **🔌 Connect** ในหน้าเว็บสลับไปฐานข้อมูลของคุณเองได้ (SQLite / PostgreSQL / MySQL) โดยไม่ต้อง restart — เลือก Domain Profile ให้ตรงกับ DB ด้วย (ADR 0013)
- อยากชี้ DB อื่นตั้งแต่เริ่ม: `DEMO_DATABASE_URL="postgresql+psycopg2://user:pass@host:5432/db" DEMO_DOMAIN_PROFILE=sts ./start_demo.sh`
- ถ้าไม่มี `local_database.db` สคริปต์จะสร้าง sample database ให้ก่อน
- เปลี่ยน port ได้ด้วย `DEMO_PORT=8002 ./start_demo.sh`

> โหมดนี้ไม่มี authentication จึงใช้ได้เฉพาะบนเครื่องตัวเองและกับข้อมูลตัวอย่างเท่านั้น
> สำหรับ production ให้ใช้ `APP_MODE=service` พร้อม `API_KEY` ตามหัวข้อถัดไป
>
> Windows: ตั้ง `APP_MODE=demo`, `DATABASE_URL=sqlite:///./local_database.db`, `DOMAIN_PROFILE=demo` และ `API_KEY=` ใน `.env` แล้วรัน `start_server.bat`

---

### ⚙️ ตั้งค่า .env

หลัง setup เสร็จ แก้ไขไฟล์ `.env` ตามที่ต้องการ — ดู [.env.example](.env.example) เป็นแหล่งอ้างอิงหลัก:

```bash
# Deployment mode: auto (default) | demo | service
# auto = UI เปิดเมื่อ API_KEY ว่าง; service = Consumer-only และต้องมี API_KEY
APP_MODE=auto

# Datasource — read-only connection, fix ตอน startup
DATABASE_URL=postgresql+psycopg2://nl2sql_ro:password@host:5432/postgres?sslmode=require
DOMAIN_PROFILE=sts

# Shared secret สำหรับ Consumer (เว้นว่าง = dev mode และ demo UI จะ mount ที่ /)
API_KEY=

# LLM Provider: openai | google | ollama | openrouter | zhipu
MODEL_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini

# ตัวอย่าง provider อื่น
# MODEL_PROVIDER=google
# GOOGLE_API_KEY=your-api-key-here
# GOOGLE_MODEL=gemini-2.0-flash-exp
# MODEL_PROVIDER=ollama
# OLLAMA_MODEL=qwen2.5-coder:7b
```

หลัง start server เปิดเบราว์เซอร์ที่ `http://localhost:8000` (เฉพาะ `APP_MODE=demo` หรือ `auto` ที่ `API_KEY` ว่าง)

> **หมายเหตุ:** ครั้งแรกที่รัน ระบบจะ download embedding model (~500MB) อัตโนมัติ ต้องใช้ internet
>
> `APP_MODE=service` บังคับให้มี `API_KEY`; เมื่อมี key แล้ว demo UI และ `/docs` จะถูกปิด — Consumer เรียก `/api/*` พร้อม header `X-API-Key` เท่านั้น
> `APP_MODE=auto` (ค่าเริ่มต้น) ทำงานเหมือนเดิม: UI เปิดเมื่อ `API_KEY` ว่าง

---

### 🖥️ การรันเซิร์ฟเวอร์ (3 โหมด)

| โหมด | คำสั่ง | เมื่อไหร่ควรใช้ |
|---|---|---|
| **Standalone demo** | `./start_demo.sh` | เปิด UI + SQLite sample ที่ port 8001 โดยไม่ต้องมี STS หรือ API key |
| **Dev server** | `./start_server.sh` | แก้โค้ด `api/` หรือ `core/` — auto-reload เห็นผลทันที |
| **Background service** (macOS) | `nlq-start` | ใช้งาน/เดโมทั่วไป — รันต่อเนื่อง พังรีสตาร์ทเอง ปิด terminal ไม่ตาย |

**โหมด Dev (`start_server.sh`):**
- **เคลียร์ port 8000 ให้เอง** — ถ้า launchd service ยึด port อยู่ จะปิดให้ก่อนแล้วสตาร์ทต่อ (ไม่ต้องพิมพ์ `launchctl` เอง); ถ้า process อื่นยึด จะหยุดพร้อมบอก PID
- `API_KEY` มาจาก `.env` หรือ shell: ว่าง → `APP_MODE=auto` จะ mount demo UI ที่ `http://localhost:8000`; มีค่า → UI ปิด
- ถ้าอยากรันเป็น service: `APP_MODE=service API_KEY=secret ./start_server.sh` — `/` จะ 404 ตามดีไซน์, ยิง `/api/*` พร้อม header `X-API-Key`
- ถ้าต้องการ UI โดยไม่แตะ `.env` ของ production: ใช้ `./start_demo.sh` ที่ port 8001

**โหมด Service (macOS — launchd, plist ที่ `~/Library/LaunchAgents/com.chanyut.nlq-server.plist`):**

| Alias | ทำอะไร |
|---|---|
| `nlq-start` | เปิดเซิร์ฟเวอร์เป็น background service (login แล้วเปิดเอง พังรีสตาร์ทเอง) |
| `nlq-stop` | หยุด service |
| `nlq-status` | สถานะ + HTTP code ของ UI |
| `nlq-log` | ดู log สด (`/tmp/nlq_server.log`) |

**คำสั่ง `launchctl` ตรง ๆ** (สิ่งที่ alias ข้างบนรันให้ — ใช้ได้แม้ไม่มี alias):

```bash
# Start — โหลด service (RunAtLoad ทำให้สตาร์ททันที)
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.chanyut.nlq-server.plist

# Stop — ถอด service ออก (แค่ kill ไม่พอ: KeepAlive จะเปิด process ใหม่เอง)
launchctl bootout gui/$(id -u)/com.chanyut.nlq-server

# Restart — ใช้หลังแก้ profiles/sts/examples.json, table_notes.json, schema_mappings.json หรือโค้ด
#           (service ไม่มี --reload; ตัวอย่าง RAG sync เข้า Chroma ตอนสตาร์ทเท่านั้น)
launchctl kickstart -k gui/$(id -u)/com.chanyut.nlq-server

# Status — มี PID = กำลังรัน
launchctl list | grep nlq-server
curl -s http://localhost:8000/api/health

# Logs — access log / app log (ดูบรรทัด "Syncing N new examples to RAG store.")
tail -f /tmp/nlq_server.log
tail -f /tmp/nlq_server.err.log
```

> หลัง `bootout` service จะกลับมาเองตอน login ครั้งถัดไป (plist ยังอยู่ และตั้ง `RunAtLoad`)

> alias ถูกเพิ่มใน `~/.zshrc` — terminal ใหม่ใช้ได้เลย (แท็บเดิมพิมพ์ `reload` ก่อนหนึ่งครั้ง)
> สลับโหมดไม่ต้องแกะเอง: รัน `./start_server.sh` ตอน service ยึด port = สคริปต์ปิดให้เอง; พิมพ์ `nlq-start` ตอน dev server ปิดแล้ว = กลับโหมด service

**URL ที่ใช้ (dev):** UI `http://localhost:8000` · API Docs `http://localhost:8000/docs` · Health `http://localhost:8000/api/health`

---

## 🗄️ Datasource Configuration

Datasource ถูก fix ตอน start จาก `DATABASE_URL` — ไม่มี `/connect` และ Consumer ไม่ส่ง credential ของ Datasource มา

```bash
DATABASE_URL=postgresql+psycopg2://nl2sql_ro:password@host:5432/postgres?sslmode=require
DOMAIN_PROFILE=sts
```

- ต้องเป็นบัญชี **read-only** — วิธีสร้าง role และตรวจ RLS อยู่ใน [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)
- ถ้า `DATABASE_URL` ว่างหรือต่อไม่ติด `/api/query` และ `/api/schema` จะตอบ `503`
- การเพิ่ม database ใหม่ = เพิ่ม Domain profile (ดู [docs/guides/PROFILES.md](docs/guides/PROFILES.md)) ไม่ใช่สลับ connection ตอน runtime

---

## 🎯 Usage Examples

### การถามคำถาม (STS profile)

```
✅ จำนวนนักเรียนปัจจุบันแยกตามโรงเรียน
✅ จำนวนนักเรียนเสี่ยงปัจจุบันแยกตามระดับความเสี่ยง
✅ อัตราการมาเรียนรายโรงเรียน ปีการศึกษา 2569 ภาคเรียน 1
✅ ห้องที่มีนักเรียนเสี่ยง HIGH ปัจจุบันมากกว่า 5 คน ขอเป็นกราฟแท่ง
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
NLP-to-SQL-Agent/
├── api/                      # Backend API
│   ├── main.py              # FastAPI entry point
│   ├── routes.py            # API endpoints
│   ├── schemas.py           # Request/Response models
│   └── dependencies.py      # Dependency injection
│
├── core/                     # Core Business Logic
│   ├── services/            # Application Use Cases
│   │   ├── engine.py        # NLPEngine (main orchestrator)
│   │   ├── agent.py         # Conversational agent loop (ADR 0006)
│   │   ├── favorite_service.py # Favorite queries management
│   │   ├── history_service.py  # History log management
│   │   └── query_history.py # Legacy query history
│   ├── domain/              # Business Rules
│   │   ├── history_models.py# Data models for history
│   │   ├── schema_pruning.py# Pruning large database schemas
│   │   ├── schema_utils.py  # Database schema fetching
│   │   └── sql_safety.py    # Read-only enforcement
│   ├── data/                # Data Infrastructure
│   │   ├── database.py      # Connection logic
│   │   ├── rag_store.py     # Few-shot RAG retrieval
│   │   └── schema_rag.py    # Schema RAG retrieval
│   ├── viz/                 # Visualization
│   │   └── viz_recommender.py  # VizService
│   ├── utils/               # Shared Utilities
│   │   └── common.py        # ID generation, SQL cleaning
│   └── config.py            # Centralized settings (LLM, SQL limits, RAG params)
│
├── web/                      # Demo UI (APP_MODE=demo)
│   ├── index.html           # Main UI
│   ├── css/style.css        # Styling
│   └── js/                  # Client logic (ES Modules)
│       ├── main.js          # Entry point
│       └── modules/         # Feature modules
│           ├── api.js       # API calls
│           ├── chart.js     # Chart.js rendering
│           ├── config.js    # Configuration
│           ├── feedback.js  # Feedback modal
│           ├── format.js    # Value formatting
│           ├── result.js    # Result table rendering
│           ├── state.js     # State management
│           ├── ui.js        # DOM manipulation
│           └── utils.js     # Utility functions
│
├── profiles/                 # Domain profiles (one per Datasource)
│   ├── sts/                  # Active: hints, examples, schema mappings, table notes
│   ├── demo/                 # Standalone SQLite demo (local_database.db)
│   └── receipt_sample/       # Legacy sample profile
├── scripts/                  # Utilities (setup_db, git tools, migration)
├── tests/unit/               # Unit tests
├── eval/                     # Evaluation metrics and code
├── docs/                     # Documentation (Specs, Guides, ADRs)
├── rag_db/                   # Local vector store for examples
├── schema_rag_db/            # Local vector store for schemas
│
├── pyproject.toml            # Python dependencies (uv)
├── docker-compose.yml        # Docker configuration
├── setup.sh / setup.bat      # Environment setup scripts
├── start_demo.sh             # Standalone demo (SQLite + UI, port 8001)
└── start_server.sh           # Backend start script
```

---

## 🔧 Configuration

### Environment Variables

ใช้ [.env.example](.env.example) เป็นแหล่งอ้างอิงหลัก — ตัวแปรที่สำคัญ:

| Variable | ความหมาย |
|---|---|
| `APP_MODE` | `auto` (default), `demo` (UI + no auth) หรือ `service` (Consumer-only + ต้องมี `API_KEY`) |
| `DATABASE_URL` | Read-only connection ของ Datasource (fix ตอน startup) |
| `DOMAIN_PROFILE` | Profile ที่ใช้ เช่น `sts` (production) หรือ `demo` (standalone demo) |
| `API_KEY` | Shared secret ที่ Consumer ส่งมาใน `X-API-Key`; `service` ต้องมี, `demo` ต้องว่าง |
| `MODEL_PROVIDER` | `openai`, `google`, `ollama`, `openrouter` หรือ `zhipu` |
| `SCHEMA_STRATEGY` | `pruned` (top-K tables) หรือ `full` |
| `MAX_SQL_LIMIT` / `MAX_RETRIES` | Row cap (default 500) และจำนวน self-correction retries |
| `ENABLE_INTELLIGENT_VIZ` | เปิด AI-powered chart recommendation (ช้ากว่า rule-based) |

---

## 🛡️ Security & Safety

ระบบป้องกันคำสั่งอันตราย:

1. ✅ **Read-Only Enforcement** - บล็อก `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`
2. ✅ **LIMIT Auto-Injection** - บังคับ `LIMIT 500` เพื่อป้องกันดึงข้อมูลมากเกิน
3. ✅ **SQL Parsing** - ใช้ `sqlglot` ตรวจสอบ syntax
4. ✅ **Table Validation** - ตรวจว่าเข้าถึงเฉพาะตารางที่มีจริง
5. ✅ **Read-only DB role** - ใช้บัญชี `nl2sql_ro` ที่มีแค่ `SELECT` (ADR 0001)
6. ✅ **Schema denylist** - ซ่อนตาราง backup/audit/token/PII จาก prompt

---

## 📊 Improving Accuracy

### เพิ่มตัวอย่างใหม่

แก้ไขไฟล์ `profiles/<profile>/examples.json` — ตัวอย่างของ STS อยู่ที่ [profiles/sts/examples.json](profiles/sts/examples.json):

```json
{
  "examples": [
    {
      "id": "unique_example_id",
      "question": "คำถามภาษาไทย",
      "sql": "SELECT ...",
      "category": "count_groupby",
      "dialect": "postgresql",
      "retrieval_tags": ["คำพ้อง", "คำค้น"]
    }
  ]
}
```

**Tips:**
- เพิ่มตัวอย่างที่เฉพาะเจาะจงกับ Datasource และ grain ของมัน
- ใส่ตัวอย่าง JOIN ที่ซับซ้อนตาม canonical join path
- ครอบคลุม category ให้สมดุลกับ Golden set
- หลังแก้ profile ให้ restart service หรือลบ `rag_db/` เพื่อให้ embed ใหม่

### ปรับ Prompt

แก้ไข `profiles/<profile>/hints.md` (dialect + domain semantics) และ `profiles/<profile>/table_notes.json` (ความหมาย/population ของตาราง) — ดู checklist ทั้งหมดที่ [docs/guides/PROFILES.md](docs/guides/PROFILES.md)

---

## 🧪 Testing

### การทดสอบ Deployment Modes

```bash
# ตรวจ demo/service/auto mode + demo profile โดยไม่ต้องใช้ STS
uv run --extra dev pytest tests/unit/test_app_modes.py tests/unit/test_demo_profile.py -q
```

### การทดสอบ Datasource

1. ตรวจว่า service ต่อ STS ได้:
   ```bash
   curl http://localhost:8000/api/health
   # {"status":"ok","datasource":true}
   ```

2. ลองถามคำถาม STS ผ่าน API:
   ```bash
   curl -X POST http://localhost:8000/api/query \
     -H "Content-Type: application/json" \
     -H "X-API-Key: $API_KEY" \
     -d '{"question":"จำนวนนักเรียนปัจจุบันแยกตามโรงเรียน"}'
   ```

### การตรวจสอบ Code

```bash
# Run unit tests
uv run --extra dev pytest tests/unit -q

# Deployment modes + demo profile only
uv run --extra dev pytest tests/unit/test_app_modes.py tests/unit/test_demo_profile.py -q

# Validate Python syntax
uv run python -m py_compile core/*.py api/*.py

# Check API health
curl http://localhost:8000/api/health
```

Evaluation (Golden set + metrics) ดูที่ [eval/STS_EVAL.md](eval/STS_EVAL.md)

---

## 📈 Demo UI History & Feedback

ส่วนนี้เป็นของ demo UI (`web/`) สำหรับ development เท่านั้น:

- Query จะถูกบันทึกใน `query_logs.jsonl`
- กด 👍 หรือ 👎 ในหน้า History เพื่อให้ Feedback
- Query ที่ถูกต้องสามารถเพิ่มเข้า `profiles/<profile>/examples.json` เพื่อปรับปรุงระบบ

Consumer ที่ใช้งานจริงควรเก็บ Log store ของตัวเองจาก fields ใน response envelope — ดู [docs/INTEGRATION.md](docs/INTEGRATION.md)

---

## 🚀 Production Deployment

### Checklist (current STS deployment)

- [x] Read-only Datasource role + `SELECT`-only grants (ADR 0001)
- [x] `APP_MODE=service` + shared-secret `API_KEY`; Consumer เรียกแบบ server-to-server
- [x] HTTPS ผ่าน Tailscale Funnel (ADR 0005)
- [ ] Rate limiting
- [ ] Monitoring / alerting
- [ ] Always-on host — `Dockerfile` พร้อมสำหรับผู้ให้บริการแบบเสียเงิน

### Deploying the microservice

For the current STS setup — the service runs on-demand on one dev machine,
exposed to `sts-backend` (Render) via Tailscale Funnel, querying Supabase —
follow **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)** (`docs/adr/0005-*` for why).
The `Dockerfile` stays ready for a paid always-on host later.

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

- [API Reference](docs/API.md) - Endpoint contract
- [Consumer Integration](docs/INTEGRATION.md) - Session, clarification/refusal และ streaming
- [Domain Profiles](docs/guides/PROFILES.md) - เพิ่ม datasource/domain ใหม่
- [STS Text-to-SQL Guide](docs/guides/TEXT_TO_SQL_STS_GUIDE.md) - STS semantics และ join paths
- [Deployment](docs/DEPLOYMENT.md) - Read-only role และ Tailscale Funnel
- [Architecture Decisions](docs/adr/) - ADR 0001–0012
- [Model Setup](docs/MODEL_SETUP.md) - LLM configuration
- [Tuning Guide](docs/TUNING_GUIDE.md) - Performance optimization
- [Issues & Roadmap](docs/ISSUES_ROADMAP.md) - Known issues and development plan

---

## 🐛 Known Issues

1. **Complex JOINs** - LLM อาจเลือก table ผิดเมื่อต้อง JOIN หลายตาราง (ดู [Issues Roadmap](docs/ISSUES_ROADMAP.md))
2. **Large Result Sets** - ไม่มี pagination สำหรับตารางขนาดใหญ่
3. **Query Cancellation** - ไม่สามารถยกเลิก Query ที่ใช้เวลานานได้

### Accepted limitations (ADR 0002 — STS)

- **No row-level scope enforcement** — คำถามถูกตอบกับทั้ง database ไม่ใช่เฉพาะ slice ที่ผู้ถามมีสิทธิ์
- **No PII classification or capability gating** — prompt สั่งไม่ให้ select PII แต่ไม่มีอะไรบังคับ; ชื่อคอลัมน์และคำถามถูกส่งไปยัง LLM provider
- **Validation ไม่ใช่ full AST gateway** — ใช้ `sqlglot` parsing + prompt rules + read-only role ตาม Tier 1 ของ guide
- **No small-group suppression / `data_as_of` freshness signal** — ตัวเลขจาก snapshot เช่น `student_risk_profiles` ไม่มีสัญญาณความสดของข้อมูล

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
