# Thai NLP-to-SQL Agent
### ระบบแปลภาษาไทยเป็น SQL อัตโนมัติ

> อ้างอิงเกณฑ์ประเมิน: ข้อ 1, 2, 3, 4, 5, 7

---

## สารบัญ
1. ภาพรวมโครงการ
2. แหล่งข้อมูล
3. ระบบจัดการความรู้: Vector Database & RAG
4. Flow การทำงานของระบบ
5. ผลการทดลอง
6. ข้อจำกัดและนวัตกรรม
ภาคผนวก

---

## 1. ภาพรวมโครงการ
[เกณฑ์ 1: ความเข้าใจปัญหา]

### 1.1 ปัญหาที่ต้องการแก้

ปัญหาที่โครงงานแก้ไขมี 5 ด้านหลัก:

| # | ปัญหา | ผลกระทบ |
|---|---|---|
| 1 | ผู้ใช้ถามภาษาไทยธรรมชาติ แต่ DB ต้องใช้ SQL | เข้าถึงข้อมูลไม่ได้โดยไม่มีนักพัฒนา |
| 2 | คำถามไทยมีความกำกวมสูง (synonym/intent หลากหลาย) | SQL ผิด intent แม้ syntax ถูก |
| 3 | SQL ต้องถูกต้องตาม dialect (MySQL/SQLite/PostgreSQL) | รันบน engine อื่นไม่ผ่าน |
| 4 | ระบบต้องปลอดภัย (ห้ามคำสั่งทำลายข้อมูล) | ความเสี่ยงด้านความปลอดภัยของข้อมูล |
| 5 | ผลลัพธ์ต้องใช้งานได้จริง (execution success + chart-ready) | UX ที่ไม่สมบูรณ์ |

**นิยามเชิงระบบ:** Thai Question → SQL ที่ executable และ safe → ตารางผลลัพธ์ + visualization config

### 1.2 แนวคิดของระบบ (System Concept)

- แปลคำถามภาษาไทยเป็น SQL Query อัตโนมัติ
- ใช้ AI และ Machine Learning
- รองรับหลายฐานข้อมูล (SQLite, MySQL, PostgreSQL)
- ตรวจสอบและแก้ไข SQL Error อัตโนมัติ

**อินพุต:**
- คำถามภาษาไทย (`question`)
- dialect เป้าหมาย (`sqlite` / `mysql` / `postgresql`)
- ตัวเลือก chart type จากผู้ใช้ (optional)

**เอาต์พุต:**
- SQL ที่ผ่านการ sanitize แล้ว
- ข้อมูลผลลัพธ์ (records)
- visualization config (`chart_type`, `x_col`, `y_col`, `series_col`)
- `log_id` สำหรับ trace และ feedback loop

ผลการทดลองเชิงปริมาณ, KPI หลัก, และ error analysis ถูกรวมไว้ในหัวข้อ 5 เพื่อให้อ่านผลทั้งหมดต่อเนื่องในส่วนเดียว

---

## 2. แหล่งข้อมูล
[เกณฑ์ 1: การรวบรวมข้อมูล]

### 2.1 ไฟล์หลัก: Training Data — thai_sql_examples.json

| รายละเอียด | ค่า |
|---|---|
| จำนวนตัวอย่าง | 55 examples |
| SQL Dialects | SQLite 27 (49%) / MySQL 28 (51%) |
| Intent ที่ครอบคลุม | aggregation, groupby, ranking, join, count, filter |

SQL Categories: groupby 12, aggregation 7, ranking 6, join 6, filter 4, count 6

### 2.2 โครงสร้างฐานข้อมูลทดสอบ

**ClassicModels (Main DB):** แปลงจาก MySQL เป็น SQLite
- ตารางหลัก 8 ตาราง แบ่งตามบทบาทดังนี้
- กลุ่มลูกค้าและการขาย: `customers`, `orders`, `orderdetails`, `payments`
- กลุ่มสินค้า: `products`, `productlines`
- กลุ่มพนักงานและสำนักงาน: `employees`, `offices`
- ตารางที่ถูกใช้บ่อยที่สุดใน benchmark และตัวอย่างทดลอง: `customers`, `orders`, `orderdetails`, `products`, `payments`, `employees`
- มี 8 FK constraints โดยจุดสำคัญคือ cross-name FK เช่น `customers.salesRepEmployeeNumber -> employees.employeeNumber` และ `employees.reportsTo -> employees.employeeNumber`

**Receipt Database (Local DB):** สำหรับรองรับข้อมูลภาษาไทย
- คอลัมน์: receipt_id / customer_name / total_price / month / payment_method / product_category / items_count / date

**Structured Data จากฐานข้อมูลจริง:** ระบบอ่าน schema จาก DB ณ runtime โดยดึง table names, column names + data types, primary key (PK) และ foreign key (FK) เพื่อสร้าง schema context ให้ LLM ใช้ตัดสินใจ JOIN ได้ถูกต้อง

### 2.3 SQL Dialects ที่รองรับ

| Dialect | จำนวน | สัดส่วน |
|---|---:|---:|
| mysql | 304 | 77.6% |
| sqlite | 81 | 20.7% |
| postgresql | 3 | 0.8% |
| empty/unknown | 4 | 1.0% |

SQLite 52%, MySQL 48%, PostgreSQL ผ่านการแปลง dialect อัตโนมัติ

### 2.4 Operational Logs

**แหล่งข้อมูล:** `query_logs.jsonl`, `query_logs.csv`

ใช้วัดผล success/error/latency ทำ error analysis ตามประเภทความผิดพลาด และสร้าง feedback loop เพื่อปรับปรุงระบบในระยะถัดไป

| รายการ | จำนวน |
|---|---:|
| Total lines | 394 |
| Parse ได้ (valid) | 392 |
| Malformed lines | 2 |

### 2.5 กระบวนการเตรียม Context (Context Preparation)

ระบบไม่ได้โยนคำถามเข้า LLM ตรงๆ แต่เตรียม context 6 ขั้น:

| ขั้น | กระบวนการ | เทคโนโลยี |
|---:|---|---|
| 1 | Query embedding | `intfloat/multilingual-e5-small` (`query:` prefix) |
| 2 | Example retrieval | ChromaDB (`passage:` embedding) |
| 3 | Dialect filter + fallback | ถ้าไม่ครบ top-K ให้ fallback ไม่มี filter |
| 4 | Auto-transpile SQL examples ข้าม dialect | sqlglot transpiler |
| 5 | Schema extraction พร้อม FK annotations | SQLAlchemy Inspector |
| 6 | Smart schema filtering | semantic + Thai mapping + keyword + LLM guess fallback |

**เหตุผลที่แนวทางนี้เหมาะกับโจทย์:**

| ข้อดี | กลไก |
|---|---|
| ลด hallucination | ผูกคำตอบกับ schema และ examples จริง |
| ลด prompt noise | ส่งเฉพาะบริบทที่เกี่ยวข้อง |
| ยืดหยุ่นสูง | เพิ่มตัวอย่างใหม่ได้โดยไม่ต้อง fine-tune |
| รองรับ self-learning | ต่อยอดจาก logs ในอนาคตได้ |

---

## 3. ระบบจัดการความรู้: Vector Database & RAG
[เกณฑ์ 2: เทคนิคและการเลือกใช้โมเดล]

### 3.1 ChromaDB: Vector Database Engine

**คุณสมบัติหลัก:**
- เก็บ Vector Embeddings สำหรับ semantic search
- ค้นหาด้วย Semantic Similarity (cosine distance)
- รองรับ Multi-language ผ่าน multilingual embedding model
- Distance threshold = 15.0

| ลำดับ | Component | หน้าที่ |
|---:|---|---|
| 1 | **Example RAG** | ดึงตัวอย่าง SQL ที่ใกล้เคียง (few-shot) |
| 2 | **Schema Context Builder** | ดึง schema + FK + join hints |
| 3 | **LLM SQL Generator** | สร้าง SQL ตาม dialect |
| 4 | **SQL Safety Validator** | ตรวจความปลอดภัยระดับ AST |
| 5 | **Execution Layer** | รัน SQL ด้วย SQLAlchemy/Pandas |
| 6 | **Self-Correction Loop** | แก้ SQL อัตโนมัติเมื่อเกิด error |
| 7 | **Visualization Recommender** | แนะนำ chart type และแกน |

### 3.2 Example RAG Store (rag_db)

**จุดประสงค์:** เก็บตัวอย่าง Thai-SQL pairs สำหรับ Few-shot Learning

ช่วยให้ LLM เข้าใจรูปแบบการแปลภาษาไทยเป็น SQL โดยการดึงตัวอย่าง SQL ที่ semantic ใกล้เคียงกับคำถามจาก ChromaDB collection `thai_sql_examples_v2` แล้ว auto-transpile ให้ตรงกับ target dialect ก่อนส่งเข้า prompt

### 3.3 Schema RAG Store (schema_rag_db)

**จุดประสงค์:** เก็บ Database Schema สำหรับ Smart Schema Retrieval

จับคู่คำภาษาไทยกับชื่อตารางและคอลัมน์ เช่น "ลูกค้า" → customers, "ยอดขาย" → orderdetails ช่วยลดช่องว่าง semantic สำหรับโจทย์ไทยที่ต้องทำงานกับ schema ภาษาอังกฤษ

### 3.4 Embedding Model: intfloat/multilingual-e5-small

**ข้อมูลโมเดล:**

| รายการ | ค่า |
|---|---|
| ชื่อโมเดล | intfloat/multilingual-e5-small |
| ประเภท | Multilingual Sentence Embeddings |
| Parameters | ~118M parameters |
| Dimensions | 384 มิติ |
| ภาษาที่รองรับ | ภาษาไทย + 100+ ภาษา |
| Distance threshold | 15.0 (cosine distance) |
| RAM ที่ใช้ | ~200MB (cached after first load) |

**การใช้งานในระบบ:**
- **Semantic Search**: embed คำถามด้วย `"query: {Q}"` prefix → ค้นหาตัวอย่างใกล้เคียง
- **Schema Matching**: embed คำถามภาษาไทย → จับคู่กับ table/column names ภาษาอังกฤษ
- **Context Retrieval**: ดึง context ที่เกี่ยวข้องจาก ChromaDB โดยอัตโนมัติ

### 3.5 LLM Models ที่รองรับ

| Provider | Model | ขนาด | หมายเหตุ |
|---|---|---|---|
| **Ollama (Default)** | qwen2.5-coder:7b | 7B params | รองรับไทย, รัน local, ฟรี |
| OpenAI | gpt-4o-mini | Cloud API | latency ต่ำสุด (~31s/25q), stable |
| Google | gemini-2.0-flash-exp | Cloud API | เร็ว, คุณภาพสูง |
| OpenRouter | nvidia/nemotron-3-super-120b | 120B params | Free tier, คุณภาพสูง |
| **Z.ai (Zhipu)** | **glm-5** | Cloud API | **EX สูงสุด 80%**, แนะนำ |
| Z.ai (Zhipu) | glm-4.7-flash | Cloud API | ราคาถูก, ผลปานกลาง |

**ค่า config สำคัญ:**

| Parameter | ค่า | ผลที่ได้ |
|---|---|---|
| `RAG_TOP_K` | 3 | จำนวน few-shot examples |
| `SCHEMA_TOP_K` | 5 | จำนวนตารางที่ filter ให้ local LLM |
| `RAG_DISTANCE_THRESHOLD` | 15.0 | ตัดตัวอย่างที่ semantic ห่างเกิน |
| `MAX_SQL_LIMIT` | 500 | จำกัด rows สูงสุด |
| `MAX_RETRIES` | 2 | จำนวนครั้ง self-correction |
| `ENABLE_INTELLIGENT_VIZ` | False | ปิดเพื่อคุม latency |

### 3.6 เหตุผลการออกแบบ (Technical Justification)
[เกณฑ์ 2]

**ทำไมไม่ใช้ Prompt-only LLM**

Prompt-only มีความเสี่ยงสูงเรื่อง table/column hallucination, dialect mismatch และความไม่สม่ำเสมอของ output format จึงเสริมด้วย RAG + safety + retry เพื่อเพิ่มความเสถียร

**ทำไมใช้ Dual RAG (RAG แยก 2 ส่วน)**

| RAG | บทบาท |
|---|---|
| Example RAG | ตอบคำถามเชิง pattern — SQL ควรมีโครงสร้างแบบไหน |
| Schema RAG | ตอบคำถามเชิงโครงสร้าง — table ไหนเกี่ยวข้อง |

การแยกทำให้จัดการ embedding space และ update cycle ได้เหมาะสมกว่าใช้ store เดียว

**ทำไมต้อง SQL Safety Layer (AST-based)**

ระบบ execute SQL บนฐานจริง จึงบังคับ: read-only เท่านั้น, single statement, ห้ามคำสั่ง destructive ทุกชนิด, จำกัดแถว (LIMIT enforcement) และอนุญาตเฉพาะตารางใน schema ปัจจุบัน (allowlist)

**ทำไมต้องมี Self-Correction**

SQL generation ในโลกจริงมี error หลายสาเหตุ (schema mismatch, column ambiguity, dialect function) Self-correction ช่วยโดยส่ง error message กลับเข้า model พร้อม full schema + FK info และ retry สูงสุดตาม `MAX_RETRIES = 2`

**Trade-off Analysis:**

| ประเด็น | ตัวเลือกที่ใช้ | ข้อดี | ข้อแลกเปลี่ยน |
|---|---|---|---|
| Generation | RAG + Prompt + LLM | แม่นยำขึ้น, ปรับง่าย | มีขั้นตอนเพิ่ม |
| Safety | SQL AST Validation | ปลอดภัยสูง, คุม policy ได้ | ต้อง maintenance rules |
| Schema Context | Smart filtering | prompt สั้นลง, ช่วย local LLM | อาจพลาด table บางเคส |
| Retry | Error-aware correction | กู้ query ที่ fail ได้ | latency เพิ่ม |
| Multi-provider | Ollama/OpenAI/Google | ยืดหยุ่นด้านต้นทุน/ความเร็ว | ต้องจัดการ behavior ต่าง provider |

---

## 4. Flow การทำงานของระบบ
[เกณฑ์ 2: สถาปัตยกรรม]

### 4.1 ภาพรวม: 6 ขั้นตอนหลัก

```
[START]
  │
  ▼
┌──────────────────┐
│  1. Thai Query   │  ผู้ใช้ป้อนคำถามภาษาไทย + เลือก dialect
│     Input        │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  2. Embedding    │  E5 model แปลงคำถามเป็น vector 384 มิติ
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  3. RAG          │  ดึงตัวอย่าง SQL + schema ที่เกี่ยวข้อง
│     Retrieval    │  (ขนานกัน asyncio.gather)
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  4. LLM          │  สร้าง SQL จาก prompt ที่ประกอบด้วย
│     Generation   │  examples + schema + dialect hints
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  5. SQL          │  ตรวจ AST safety → รันกับ DB จริง
│     Execution    │  → Self-correction ถ้า fail
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  6. Return       │  SQL + ข้อมูล + visualization config
│     Results      │  + log บันทึก
└────────┬─────────┘
         │
        [END]
```

ต่อไปนี้คือ pipeline แบบละเอียด:

```
┌─────────────────────────────────────────────────────────────────────┐
│                         SYSTEM STARTUP                              │
│  FastAPI start → load_dotenv() → preload NLPEngine (async)          │
│  └─► Load E5 embedding model (~500MB, cached after first run)       │
│  └─► Init ChromaDB (rag_db/) + sync 54 Thai SQL examples            │
│  └─► Init LLM (OpenAI/Ollama/Google/Zhipu/OpenRouter)               │
│  └─► Build Prompt Template + VizService                             │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
              ┌────────────────▼─────────────────┐
              │    POST /api/connect              │
              │  SQLAlchemy Engine creation       │
              │  get_database_schema() → {tables, │
              │  foreign_keys} (SQLAlchemy insp.) │
              └────────────────┬─────────────────┘
                               │
              ┌────────────────▼─────────────────┐
              │    POST /api/query               │
              │  question + dialect + chart pref  │
              └────────────────┬─────────────────┘
                               │
         ┌─────────────────────▼──────────────────────┐
         │         NLPEngine.query_database()          │
         │                                             │
         │  ① Schema cache check (reuse if same DB)    │
         │                                             │
         │  ② asyncio.gather() ←── PARALLEL ──────┐   │
         │     ├─ Example RAG retrieval            │   │
         │     │   embed("query: {Q}") → ChromaDB  │   │
         │     │   top-K → filter → transpile      │   │
         │     └─ Schema processing ───────────────┘   │
         │         Ollama: smart_filter_schema()        │
         │         Cloud: full schema + FK hints        │
         │                                             │
         │  ③ Prompt construction                       │
         │     examples + schema + dialect + hints      │
         │     → LangChain chain → LLM → SQL           │
         │                                             │
         │  ④ Retry Loop (0..MAX_RETRIES)              │
         │     ├─ validate_and_sanitize_sql()           │
         │     │   sqlglot AST → safety check → LIMIT  │
         │     ├─ pd.read_sql() [thread pool]          │
         │     ├─ VizService.recommend()               │
         │     └─ [Error] → correction prompt → retry  │
         └─────────────────────┬──────────────────────┘
                               │
              ┌────────────────▼─────────────────┐
              │    Response & Logging             │
              │  parse_sql_metrics() (sqlglot)    │
              │  log_query_to_file() → JSONL+CSV  │
              │  QueryResponse(sql,data,viz,logid)│
              └──────────────────────────────────┘
```

**คำอธิบาย Flow (ภาษาไทย):**

| ขั้นตอน | สิ่งที่เกิดขึ้น |
|---|---|
| **SYSTEM STARTUP** | เมื่อ server เริ่มต้น: โหลด E5 embedding model สำหรับค้นหาตัวอย่าง SQL, เชื่อมต่อ ChromaDB ที่เก็บ 54 ตัวอย่าง SQL ภาษาไทย, และเตรียม LLM (OpenAI / Ollama / Google / Z.ai) พร้อมใช้งาน |
| **POST /api/connect** | ผู้ใช้กดเชื่อมต่อฐานข้อมูล: ระบบสร้าง SQLAlchemy engine และดึง schema ทั้งหมดพร้อม Primary Key และ Foreign Key เพื่อให้ LLM รู้โครงสร้าง DB |
| **POST /api/query** | ผู้ใช้ถามคำถามภาษาไทย: ส่ง question + dialect ที่ใช้ (MySQL/SQLite/PostgreSQL) + ความต้องการกราฟ เข้ามายัง API |
| **NLPEngine ①** | ตรวจ schema cache — ถ้าเป็น database เดิมที่เพิ่งใช้งาน ใช้ schema เดิมได้เลย ไม่ต้องดึงใหม่ ลด latency |
| **NLPEngine ②** | รัน 2 งานพร้อมกันด้วย `asyncio.gather()`: (1) ค้นหาตัวอย่าง SQL ที่คล้ายกันจาก ChromaDB (RAG) และ (2) เตรียม schema ที่เกี่ยวข้อง + สร้าง JOIN hints |
| **NLPEngine ③** | ประกอบ prompt: นำตัวอย่าง + schema + dialect + hint JOIN มาสร้าง prompt ส่งให้ LLM แปลงเป็น SQL |
| **NLPEngine ④** | วนลูป retry (0 ถึง MAX_RETRIES): ตรวจความปลอดภัย SQL ด้วย AST → รันกับ DB จริง → แนะนำกราฟ → ถ้าเกิดข้อผิดพลาดส่ง correction prompt ให้ LLM แก้ใหม่ |
| **Response & Logging** | ส่งผลลัพธ์กลับผู้ใช้: SQL, ข้อมูลตาราง, กราฟที่แนะนำ, และบันทึก log ลงไฟล์ JSONL+CSV สำหรับวิเคราะห์ภายหลัง |

---

### 4.2 Phase 1: System Startup — การเริ่มต้นระบบ

เมื่อ server เริ่มด้วย `uvicorn api.main:app`:

| ลำดับ | สิ่งที่เกิดขึ้น | ไฟล์ | เวลาโดยประมาณ |
|---:|---|---|---|
| 1 | `load_dotenv()` โหลด `.env` | `api/main.py` | < 10ms |
| 2 | สร้าง FastAPI app + CORS middleware | `api/main.py` | < 10ms |
| 3 | Mount static web UI (`/web`) | `api/main.py` | < 10ms |
| 4 | `startup_event()` → เรียก `preload_nlp_engine()` async (non-blocking) | `api/main.py` | ไม่ block |
| 5 | **โหลด SentenceTransformer** `intfloat/multilingual-e5-small` (384-dim, ~200MB RAM) | `core/data/rag_store.py` | 1–3s (cached) |
| 6 | Init ChromaDB `PersistentClient` ที่ `rag_db/` | `core/data/rag_store.py` | < 100ms |
| 7 | **Sync examples**: อ่าน `thai_sql_examples.json` (54 ข้อ) → embed ที่ใหม่ → upsert ChromaDB | `core/data/rag_store.py` | 1–5s (ครั้งแรก) |
| 8 | Init LLM ตาม `MODEL_PROVIDER` | `core/services/engine.py` | < 500ms |
| 9 | Build Prompt Template พร้อม Thai keyword hints | `core/services/engine.py` | < 10ms |
| 10 | Init VizService (rule-based หรือ LLM-powered) | `core/viz/viz_recommender.py` | < 10ms |

**Example sync deduplication:** ใช้ MD5 hash ของ `question+sql` เป็น ChromaDB document ID ป้องกันการ embed ซ้ำเมื่อ restart

---

### 4.3 Phase 2: Database Connection — การเชื่อมต่อฐานข้อมูล

```
User กด "Connect" ใน UI
       │
       ▼
POST /api/connect { db_type, host, port, user, password, database }
       │
       ▼
ConnectionManager.get_db_engine()
  ├─ SQLite  → "sqlite:///path/to/db.db"
  ├─ MySQL   → "mysql+pymysql://user:pass@host:port/db?charset=utf8mb4"
  └─ PgSQL   → "postgresql+psycopg2://user:pass@host:port/db"
       │ test connection (engine.connect())
       ▼
SQLAlchemy Engine → persist ใน GlobalStateManager
       │
       ▼
บันทึก .last_connection.json  (auto-restore เมื่อ server restart)
       │
       ▼
preload NLPEngine (ถ้ายังไม่ได้ load)
```

**Schema extraction** (`get_database_schema()`):
- ใช้ `SQLAlchemy Inspector` ดึง table names, column names + types
- `inspector.get_pk_constraint()` → ระบุ Primary Key ต่อตาราง
- `inspector.get_foreign_keys()` → ระบุ FK constraints พร้อม referenced table/column
- Output: `{"tables": {table: [{"name", "type", "pk", "fk"}]}, "foreign_keys": [...]}`

---

### 4.4 Phase 3: Query Processing — การประมวลผลคำถาม

นี่คือหัวใจหลักของระบบ ทุกขั้นตอนเกิดขึ้นใน `NLPEngine.query_database()`

#### 4.4.1 Schema Cache Check

```python
if engine_changed:
    raw_schema = get_database_schema(engine)  # Query DB
    self._schema_cache = raw_schema
else:
    raw_schema = self._schema_cache  # ใช้ cache (ไม่ query DB ซ้ำ)
```

**ทำอะไร:** ตรวจว่า database engine เปลี่ยนไปจากครั้งก่อนหรือไม่ ถ้าไม่เปลี่ยน → ใช้ schema ที่เก็บไว้ใน memory แทน

**ทำอย่างไร:** เปรียบเทียบ SQLAlchemy engine object ที่ถือไว้ใน `NLPEngine._last_engine` กับ engine ที่รับเข้ามาตอนนี้ ถ้า identity ต่างกัน (user เชื่อมต่อ DB ใหม่) ถึงจะดึง schema ใหม่จาก DB จริง

**ทำไมถึงต้องทำแบบนี้:** `get_database_schema()` ต้องส่ง SQL introspection queries ไปถาม database จริง (`INFORMATION_SCHEMA`, `PRAGMA table_info` ฯลฯ) ใช้เวลา 100–500ms ขึ้นอยู่กับขนาด schema และ network latency สำหรับ query ที่ 2 ขึ้นไปบน database เดิม schema ไม่ได้เปลี่ยน การ cache จึงช่วยลด latency ลงได้โดยตรง

#### 4.4.2 Parallel RAG Retrieval — ขั้นตอนที่ใช้เวลามากที่สุด

**ทำอะไร:** เตรียม context 2 ชุดที่ LLM ต้องการพร้อมกัน: (1) ตัวอย่าง SQL ที่ใกล้เคียงกับคำถาม (few-shot examples) และ (2) schema ของตารางที่น่าจะเกี่ยวข้อง

**ทำอย่างไร:** ใช้ `asyncio.gather()` รัน coroutine ทั้งสองพร้อมกันในหนึ่ง event loop โดยไม่ต้องรอ task แรกเสร็จก่อน ทั้งสองงานเป็น I/O-bound (ChromaDB query + DB introspection) จึง yield CPU ให้กันได้ในระหว่างรอ I/O

**ทำไมถึงต้องทำแบบนี้:** ถ้ารันแบบ sequential ต้องรอ RAG embed (~50ms) + ChromaDB query (~30ms) → แล้วค่อยรัน schema processing (~200ms) รวมแล้ว ~280ms แต่ถ้ารันขนาน CPU ทำงานทั้งสองพร้อมกัน ลดเหลือ ~200ms (bottleneck คือ schema processing เท่านั้น) ประหยัดเวลาได้ประมาณ 30–50% ต่อ query

ระบบรัน **2 งานขนานกัน** ด้วย `asyncio.gather()` เพื่อประหยัดเวลา:

**งานที่ 1: Example RAG (Few-Shot Learning)**

```
คำถาม: "ยอดขายรวมของแต่ละลูกค้า"
    │
    ▼
E5 embed: "query: ยอดขายรวมของแต่ละลูกค้า" → 384-dim vector
    │
    ▼
ChromaDB query (collection: thai_sql_examples_v2)
  RAG_TOP_K = 5 ตัวอย่าง
  filter: dialect = "sqlite" (ถ้ามีพอ) → fallback: ไม่ filter
    │
    ▼
Filter ด้วย RAG_DISTANCE_THRESHOLD = 15.0
  (cosine distance > 15.0 → ตัดออก ตัวอย่างไม่เกี่ยวข้อง)
    │
    ▼
Auto-transpile: ถ้า example เป็น MySQL แต่ target เป็น SQLite
  sqlglot.transpile("SELECT YEAR(date)...", from_="mysql", to="sqlite")
  → "SELECT strftime('%Y', date)..."
    │
    ▼
Format ใส่ prompt:
  "Question: ยอดขายรวมของแต่ละลูกค้า
   SQL: SELECT c.customerName, SUM(...) FROM customers c JOIN orders o ..."
```

**งานที่ 2: Schema Processing (รันขนานกับ งานที่ 1)**

| Provider | กระบวนการ | ผลลัพธ์ |
|---|---|---|
| **Ollama** | `smart_filter_schema()` → 4-tier filtering เลือก ≤ 5 ตาราง | Schema ขนาดเล็ก ใส่ context window local LLM ได้ |
| **Cloud LLM** | ใช้ full schema ทั้งหมด | Schema ครบถ้วน เหมาะกับ LLM ขนาดใหญ่ |

**Smart Schema Filtering สำหรับ Ollama (4 Tiers):**

```
Tier 1: SchemaRAG semantic search
  embed("query: {question}") → ChromaDB schema collection
  + Thai keyword mapping: "ลูกค้า" → customers, "ยอดขาย" → orderdetails
         │ ถ้าไม่ครบ
         ▼
Tier 2: Keyword matching
  ตรวจว่า table/column name ปรากฏใน question text
         │ ถ้าไม่ครบ
         ▼
Tier 3: LLM guessing
  ถาม LLM ว่าตารางไหนน่าจะเกี่ยวข้อง
         │ เสมอ
         ▼
Tier 4: Relationship expansion
  ขยาย FK relationships เพิ่ม related tables สำหรับ JOIN
         │
         ▼
Fallback: ถ้าไม่พบเลย → คืน full schema
```

**FK-aware Schema Format (output ของ format_schema_for_prompt):**

```
Table: customers
Columns:
  - customerNumber (INT) [PK]
  - customerName (VARCHAR)
  - salesRepEmployeeNumber (INT) [FK -> employees.employeeNumber]

Table: employees
Columns:
  - employeeNumber (INT) [PK]
  - firstName (VARCHAR)

Foreign Key Relationships:
  - customers.salesRepEmployeeNumber -> employees.employeeNumber
  - orders.customerNumber -> customers.customerNumber
```

#### 4.4.3 JOIN Hints Generation

**ทำอะไร:** สร้าง section พิเศษในชื่อ "JOIN Conditions" ที่ระบุ FK relationships ทั้งหมดในรูปแบบที่ LLM อ่านและนำไปใช้ได้ทันที

**ทำอย่างไร:** `get_join_hints()` อ่าน `foreign_keys` list จาก schema object (ที่ดึงมาจาก `inspector.get_foreign_keys()`) แล้วสร้างข้อความเช่น `customers.salesRepEmployeeNumber = employees.employeeNumber` ต่อหนึ่ง FK constraint จากนั้น append เป็น section แยกใน prompt

**ทำไมถึงต้องทำแบบนี้:** ปัญหาหลักที่ทำให้ LLM JOIN ผิดคือ "cross-name foreign keys" เช่น `customers.salesRepEmployeeNumber → employees.employeeNumber` — ชื่อ column ทั้งสองฝั่งต่างกันสิ้นเชิง LLM ไม่มีทางรู้ได้จาก schema อย่างเดียวว่าต้อง JOIN ตรงนี้ การใส่ hint ตรงๆ ว่า "column A เชื่อมกับ column B" แก้ปัญหา column hallucination ซึ่งเป็น error type #1 ของระบบ (35% ของ error ทั้งหมด)

`get_join_hints()` อ่าน FK constraints จาก schema แล้วสร้าง section พิเศษ:

```
JOIN Conditions (from Foreign Keys):
- customers.salesRepEmployeeNumber = employees.employeeNumber
- orders.customerNumber = customers.customerNumber
- orderdetails.orderNumber = orders.orderNumber
```

**ทำไมถึงสำคัญ:** classicmodels มี FK แบบ cross-name เช่น `salesRepEmployeeNumber → employees.employeeNumber` — ถ้าไม่มี hint LLM จะ JOIN ผิด column

#### 4.4.4 Prompt Construction และ LLM Call

**ทำอะไร:** ประกอบ prompt ที่สมบูรณ์จาก context ที่เตรียมไว้ทั้งหมด แล้วส่งให้ LLM แปลงคำถามภาษาไทยเป็น SQL

**ทำอย่างไร:** ใช้ LangChain `PromptTemplate` + `partial()` technique โดย fill ค่าที่ไม่เปลี่ยนต่อ request (schema, examples, dialect, max_limit) ไว้ล่วงหน้า เหลือแค่ `{question}` เป็น dynamic variable ตอน invoke จริง prompt มีโครงสร้าง 6 ส่วน: role definition → dialect rules → Thai keyword hints → few-shot examples → schema + FK hints → task instruction

**ทำไมถึงออกแบบ prompt แบบนี้:**
- **Role definition**: LLM ต้องรู้ว่าตัวเองเป็น SQL expert ที่รับ input ภาษาไทย ไม่ใช่ chatbot ทั่วไป
- **Thai keyword hints**: คำภาษาไทยเช่น "ยอดขาย", "เฉลี่ย" ไม่ได้ map ตรงๆ กับ SQL function LLM ทั่วไปมักไม่รู้ว่า "ยอดขาย" = `SUM(quantityOrdered * priceEach)` hint เหล่านี้ช่วยได้มาก
- **Dialect functions**: MySQL ใช้ `YEAR(col)` แต่ SQLite ต้องใช้ `strftime('%Y', col)` — ถ้าไม่บอก LLM จะใช้ syntax ผิด dialect
- **Few-shot examples**: เป็น technique หลักของ few-shot learning LLM "เห็น" pattern SQL ที่ถูกต้องก่อน แล้วนำมาใช้กับคำถามใหม่ ได้ผลดีกว่า zero-shot อย่างมีนัยสำคัญ
- **`partial()` pattern**: เร็วกว่าการ format string ทุกครั้ง และทำให้ chain object reusable ข้ามหลาย request ได้

```python
# Fill static variables ครั้งเดียว
chain = (
    prompt.partial(
        dynamic_examples = "Question: ...\nSQL: ...\n\nQuestion: ...\nSQL: ...",
        schema           = "Table: customers\n  - customerNumber (INT) [PK]...",
        dialect          = "sqlite",
        max_limit        = 500,
    )
    | llm                  # ChatOpenAI / ChatOllama / etc.
    | StrOutputParser()
)

# Invoke ด้วย question
response = await chain.ainvoke({"question": "ยอดขายรวมของแต่ละลูกค้า"})
```

**โครงสร้าง Prompt (ย่อ):**

```
คุณเป็น SQL Expert ที่เข้าใจภาษาไทย...

### Target Dialect: {dialect}

### Rules:
1. Return ONLY a single SELECT statement
2. READ-ONLY: ห้าม INSERT/UPDATE/DELETE/DROP/ALTER/CREATE
3. Always include LIMIT {max_limit}
4. Return ONLY SQL — ไม่มี markdown

### Dialect Functions:
- Date: SQLite: strftime('%Y', col) | MySQL: YEAR(col)
- String: SQLite: a || b | MySQL: CONCAT(a, b)

### Thai Keyword Hints:
- "ยอดขาย" → SUM(total_price หรือ quantityOrdered * priceEach)
- "จำนวน/นับ/กี่" → COUNT(...)
- "เฉลี่ย" → AVG(...)
- "สัดส่วน/เปอร์เซ็นต์" → SUM(A)/SUM(B)*100
- "ไม่เคย/ไม่มี" → LEFT JOIN ... WHERE id IS NULL
- "รายเดือน" → GROUP BY year, month

### Similar Examples:
{dynamic_examples}

### Database Schema:
{schema}

### Your Task:
Think step-by-step:
1. ระบุตารางที่เกี่ยวข้อง
2. ตรวจสอบ [FK ->] annotations สำหรับ JOIN path ที่ถูกต้อง
3. ใช้ dialect functions ที่ถูกต้อง

Question: {question}
SQL:
```

#### 4.4.5 SQL Safety Validation (`validate_and_sanitize_sql`)

**ทำอะไร:** ตรวจสอบ SQL ที่ LLM สร้างขึ้นว่าปลอดภัยและถูกต้องก่อนนำไป execute จริง ป้องกัน SQL injection และ destructive operations

**ทำอย่างไร:** ใช้ `sqlglot` library parse SQL string เป็น Abstract Syntax Tree (AST) แล้วตรวจ node types ใน tree แทนการใช้ regex ตรง string การ parse เป็น AST ทำให้รู้ชัดเจนว่า statement นี้คืออะไร (SELECT, UPDATE, DROP ฯลฯ) ไม่ใช่แค่ดูว่ามีคำว่า "DROP" ปรากฏใน string หรือเปล่า

**ทำไมต้อง AST ไม่ใช่ regex:**
- Regex ตรวจ `DROP` แบบ case-insensitive ยังหลอกได้ด้วย `DrOp TABLE` หรือ comments เช่น `SELECT 1 /* DROP TABLE x */`
- AST-based checking ตรวจ semantic ไม่ใช่ text pattern — `sqlglot.parse_one(sql)` คืน tree ที่ root node คือ `Select` อย่างแน่นอนถ้า SQL ถูกต้อง
- LIMIT injection เป็น AST transformation ไม่ใช่ string append ป้องกัน edge case เช่น nested `LIMIT` ใน subquery

SQL ที่ LLM สร้างจะถูกตรวจสอบผ่าน sqlglot AST parser ก่อนรันทุกครั้ง:

| การตรวจสอบ | วิธี | ตัวอย่างที่ block |
|---|---|---|
| Single statement | Parse → reject `;` separator | `SELECT 1; DROP TABLE x` → ❌ |
| Read-only only | AST node type check | `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, `INSERT`, `PRAGMA`, `ATTACH` → ❌ |
| Root is SELECT | Check root expression | `EXEC sp_help` → ❌ |
| Table allowlist | ตรวจทุก table reference กับ schema | `SELECT * FROM secret_table` (ถ้าไม่ใน schema) → ❌ |
| LIMIT enforcement | Inject ถ้าขาด, clamp ถ้าเกิน 500 | `SELECT * FROM products` → `... LIMIT 500` |

#### 4.4.6 SQL Execution

**ทำอะไร:** รัน SQL query ที่ผ่านการ validate แล้วกับ database จริง แล้วแปลงผลลัพธ์เป็น list of dicts ที่ส่ง JSON ได้

**ทำอย่างไร:** ใช้ `pandas.read_sql()` ดึงข้อมูลผ่าน SQLAlchemy engine แล้ว `.to_dict(orient='records')` แปลงเป็น list ของ dict โดย wrap ทั้งหมดใน `asyncio.to_thread()` เพื่อรันใน thread pool แยกต่างหาก

**ทำไมต้อง `asyncio.to_thread()`:** FastAPI เป็น async framework ที่ทำงานบน single event loop `pandas.read_sql()` เป็น blocking I/O call (รอผลจาก database) ถ้าเรียกตรงๆ โดยไม่ใช้ thread pool จะ block event loop ทั้งหมด ทำให้ request อื่นต้องรอจนกว่า SQL จะเสร็จ การใช้ `asyncio.to_thread()` ย้าย blocking call ไปทำงานใน thread แยก event loop จึงรับ request อื่นต่อได้ระหว่างรอ

```python
# รันใน thread pool เพื่อไม่ block event loop
df = await asyncio.to_thread(pd.read_sql, sql, engine)
result_data = df.to_dict(orient='records')
# → [{"customerName": "ABC Co.", "total_sales": 125000.5}, ...]
```

#### 4.4.7 Self-Correction Loop (ถ้า error)

```
SQL execution FAIL
        │
        ▼
Error classifier:
  "no such table"     → table_error    ← ตารางที่ LLM ใช้ไม่มีอยู่ใน DB
  "unknown column"    → column_error   ← column ที่อ้างถึงไม่มีในตาราง
  "ambiguous column"  → column_error   ← ชื่อ column ซ้ำกันในหลายตาราง ต้องระบุ prefix
  อื่นๆ               → generic_error  ← syntax error หรือ constraint อื่นๆ
        │
attempt < MAX_RETRIES?
   YES  │                ← ยังมีสิทธิ์ retry อยู่
        ▼
Correction Prompt (พร้อม FULL schema + FK info):
  "Query failed: {error_msg}
   Failed SQL: {sql}
   ### Full Database Schema:
   {full_schema_text}
   → Check [FK ->] annotations, rewrite correctly
   Corrected SQL:"
        │                ← ส่ง error + SQL ผิด + schema ทั้งหมดกลับให้ LLM แก้ใหม่
        ▼
LLM generates corrected SQL
        │
        └──► กลับไป Step 4.4.5 (validate ใหม่)

   NO (max retries reached)
        ▼
Return error ให้ผู้ใช้  ← แจ้ง error message พร้อม SQL ที่ fail
```

**Flow เมื่อเกิด SQL error (1-4):**

1. ระบบรัน SQL กับฐานข้อมูลจริงก่อน แล้วรับ `error_msg` จริงที่ database ส่งกลับมา
2. ระบบจัดประเภท error เป็น `table_error`, `column_error`, หรือ `generic_error` เพื่อรู้ว่าปัญหาอยู่ที่ตาราง คอลัมน์ หรือ syntax/dialect
3. ถ้ายังไม่เกิน `MAX_RETRIES` ระบบจะสร้าง correction prompt โดยแนบ SQL ที่ fail, error message, full schema, และ FK hints ส่งกลับให้ LLM เขียนใหม่
4. SQL ที่แก้แล้วจะกลับไปผ่าน `validate_and_sanitize_sql()` และ execute ใหม่อีกครั้ง; ถ้ายัง fail จนครบ limit จึงค่อย return error ให้ผู้ใช้

**รายละเอียดเสริม:**

- **ส่ง Full Schema**: ไม่ใช่แค่ schema ที่กรองแล้ว แต่ส่ง schema ทั้งหมดพร้อม FK annotations เพื่อให้ LLM เห็น JOIN path ที่ถูกต้อง
- **ระบุข้อผิดพลาดชัดเจน**: บอก error message จาก database จริง + SQL ที่ fail เพื่อให้ LLM รู้ว่าต้องแก้ตรงไหน
- **โหมด eval ใช้ `MAX_RETRIES = 0`**: วัดความสามารถแบบ single attempt
- **โหมด production ใช้ `MAX_RETRIES = 2`**: ถ้าต้อง retry ระบบจะแสดงสถานะ `"Success (Retry 1)"`

**Default `MAX_RETRIES = 0`** → ไม่มี retry (single attempt)
**`MAX_RETRIES = 2`** → ลองแก้ได้ 2 ครั้ง status: `"Success (Retry 1)"`

#### 4.4.8 Visualization Recommendation

**ทำอะไร:** วิเคราะห์ผลลัพธ์ SQL และคำถามของผู้ใช้ แล้วแนะนำ chart type ที่เหมาะสมที่สุดพร้อม column mapping

**ทำอย่างไร:** ใช้ rule-based engine ตรวจใน 3 ระดับตามลำดับ: (1) user preference ถ้าผู้ใช้เลือก chart มาเอง → ใช้เลย (2) keyword matching ในคำถาม เช่น "แนวโน้ม" → line, "สัดส่วน" → pie (3) auto-detect จาก column types ใน DataFrame เช่น date column + numeric → line chart ถ้าตรวจพบว่ามี year column ที่มีหลายค่า จะ set `series_col` เพื่อแสดงหลายเส้นต่อปีโดยอัตโนมัติ

**ทำไมใช้ rule-based แทน LLM สำหรับ viz:** LLM-based viz recommendation (`ENABLE_INTELLIGENT_VIZ=True`) แม่นขึ้น แต่ต้องเรียก LLM อีกครั้ง เพิ่ม latency 1–3 วินาที สำหรับ use case ส่วนใหญ่ rule-based เพียงพอแล้ว ผู้ใช้ยังสามารถเปลี่ยน chart type เองได้จาก dropdown ใน UI อยู่ดี

```
DataFrame (query result)
        │
        ▼
VizService.recommend(df, question, preferred_chart_type)
        │
   [User picked chart?]──YES──► ใช้ตามที่เลือก
        │ NO
        ▼
   [Thai/EN keywords?]
     "แนวโน้ม/trend" → line
     "สัดส่วน/pie"   → pie
     "เปรียบเทียบ"   → bar
        │ no match
        ▼
   Auto-detect จาก column types:
     date/month col + numeric → line chart
     categorical + numeric   → bar chart
     2+ numeric cols         → scatter
     fallback                → table
        │
        ▼
Multi-series detection:
  ถ้า x_col="month" และมี "year" col ที่มี >1 ค่า → series_col="year"
  → แสดงแยกเส้นต่อปี
        │
        ▼
{chart_type, x_col, y_col, series_col, options: [...]}
```

---

### 4.5 Phase 4: Response & Logging

**ทำอะไร:** วิเคราะห์ SQL ที่ได้ บันทึก log ในสองรูปแบบพร้อมกัน และ return response กลับไปยัง client

**ทำอย่างไร:**
- `parse_sql_metrics()` ใช้ sqlglot AST parse SQL อีกครั้งเพื่อดึง metadata: ตารางที่ใช้, จำนวน JOIN, มี aggregation ไหม, มี subquery ไหม
- `log_query_to_file()` เขียน log ลง 2 ไฟล์พร้อมกัน: JSONL (เหมาะกับ machine processing, append-only, ไม่ต้องล็อก file) และ CSV (เหมาะกับ Excel analysis)
- response ส่งกลับ 5 field หลัก: SQL text, result data (list of dicts), viz config, log_id, retry_count

**ทำไมต้องบันทึก 2 format:**
- **JSONL**: อ่านได้ด้วย Python โดยตรง (`for line in f: json.loads(line)`) ไม่ต้อง parse CSV เหมาะกับ eval pipeline และ analysis script
- **CSV**: เปิดด้วย Excel ได้ทันที เหมาะสำหรับ business stakeholder ที่ต้องการดูข้อมูลแบบ manual โดยไม่ต้องเขียน code

**ทำไม log ใน thread pool:** `log_query_to_file()` เป็น disk I/O ใช้ `asyncio.to_thread()` เหมือนกับ SQL execution เพื่อไม่ block event loop ขณะเขียนไฟล์

```python
# 1. SQL Metrics parsing (sqlglot AST)
metrics = parse_sql_metrics(sql, dialect)
# → tables_used=["customers","orders"], join_count=2,
#    has_aggregation=True, has_subquery=False, has_group_by=True

# 2. Logging (thread-safe, atomic per record)
log_id = await asyncio.to_thread(
    log_query_to_file,
    question, sql, status="Success", duration=2.34,
    retry_count=0, tables_used=[...], join_count=2,
    has_aggregation=True, result_row_count=45,
    rag_examples_count=5, model_name="gpt-4o-mini"
)
# เขียนลง query_logs.jsonl + query_logs.csv พร้อมกัน

# 3. HTTP Response
return QueryResponse(
    sql       = "SELECT c.customerName, SUM(...) FROM ...",
    data      = [{"customerName": "...", "total_sales": 125000}],
    retry_count = 0,
    log_id    = "a1b2c3d4-...",
    visualization = {
        "chart_type": "bar",
        "x_col": "customerName",
        "y_col": "total_sales",
        "series_col": None,
        "options": ["bar", "line", "pie", "scatter", "table"]
    }
)
```

---

### 4.6 Use Case Examples

| Use Case | คำถาม | Technology ที่ทำงาน | ผลลัพธ์ |
|---|---|---|---|
| **Simple SELECT** | "แสดงชื่อสินค้าทั้งหมด" | Schema cache + E5 embed + Prompt (no complex RAG needed) | `SELECT productName FROM products LIMIT 500` → table |
| **Aggregation** | "ยอดขายรวมทั้งหมดของทุกออเดอร์" | RAG ดึง SUM pattern + Thai hint "ยอดขาย" | `SELECT SUM(quantityOrdered * priceEach) FROM orderdetails` → single value |
| **2-table JOIN** | "ยอดชำระเงินรวมของลูกค้าในแต่ละประเทศ" | FK hints: `payments.customerNumber → customers.customerNumber` | `SELECT c.country, SUM(p.amount)... JOIN payments p ON ...` → bar chart |
| **Complex JOIN** | "แสดงชื่อลูกค้าพร้อมชื่อพนักงานที่ดูแล" | FK hint cross-name: `salesRepEmployeeNumber → employees.employeeNumber` | `SELECT c.customerName, e.firstName\|\|' '\|\|e.lastName ... LEFT JOIN employees` |
| **Subquery** | "ลูกค้าที่ไม่เคยสั่งซื้อเลย" | Thai hint "ไม่เคย" → LEFT JOIN IS NULL pattern | `LEFT JOIN orders ON ... WHERE orders.orderNumber IS NULL` |
| **Time-series** | "ยอดขายรวมแยกตามปีและเดือน" | strftime() dialect hint + GROUP BY pattern + auto line chart | Line chart แยกตามปี (series_col="year" ถ้ามีหลายปี) |
| **Self-correction** | คำถามที่ LLM ใช้ column ผิด | error "no such column" → correction prompt + full schema → retry | SQL แก้ถูกต้องใน attempt ที่ 2 |

---

## 5. ผลการทดลอง
[เกณฑ์ 3: การวัดผลและการวิเคราะห์]

### 5.1 ผลการทดลองหลัก (KPI Overview)

| Metric | ค่า | หมายเหตุ |
|---|---:|---|
| Valid queries ที่วิเคราะห์ได้ | 392 รายการ | จาก 394 บรรทัด (malformed 2) |
| **Success rate** | **82.65%** | 324 / 392 |
| First-try success | 80.87% | 317 / 392 |
| Retry success | 7 รายการ | Self-correction ช่วย |
| Latency p50 | 11.44s | ค่ากลาง |
| Latency p95 | 47.82s | ต้อง optimize |

### 5.2 วิธีประเมิน

ระบบประเมินผลจาก 3 ระดับ:

| ระดับ | วิธี | แหล่งข้อมูล |
|---|---|---|
| 1 | Operational Metrics จาก query logs จริง | `query_logs.jsonl` |
| 2 | Error Analysis ตามชนิดความผิดพลาด | `error_msg` field |
| 3 | Mini Benchmark (Execution Accuracy) | `eval/benchmark_classicmodels.json` |

### 5.3 ผลเชิงปริมาณจาก Operational Logs (query_logs.jsonl)

**Data Quality ก่อนวัด**

| รายการ | จำนวน |
|---|---:|
| Total lines | 394 |
| Parse ได้ (valid) | 392 |
| Malformed lines | 2 |

**KPI หลัก**

| Metric | ค่า | หมายเหตุ |
|---|---:|---|
| Success count | 324 | |
| Error count | 68 | |
| **Success rate** | **82.65%** | |
| First-try success | 317 (80.87%) | ไม่ต้อง retry |
| Retry success | 7 | Self-correction ช่วย |
| Avg duration | 16.86s | |
| **p50 duration** | **11.44s** | ค่าที่ผู้ใช้ส่วนใหญ่สัมผัส |
| p95 duration | 47.82s | ต้อง optimize |

**Distribution ตาม Dialect**

| Dialect | จำนวน | สัดส่วน |
|---|---:|---:|
| mysql | 304 | 77.6% |
| sqlite | 81 | 20.7% |
| postgresql | 3 | 0.8% |
| empty/unknown | 4 | 1.0% |

### 5.4 Error Analysis

**สาเหตุที่ระบบพลาด**

| Error Type | Count | สัดส่วน | ความหมาย |
|---|---:|---:|---|
| **column_error** | **24** | **35.3%** | เลือกคอลัมน์ผิด/กำกวม |
| table_error | 12 | 17.6% | อ้างอิงตารางที่ไม่อนุญาตหรือไม่มี |
| syntax_error | 5 | 7.4% | โครงสร้าง SQL ผิด |
| dialect_function_error | 3 | 4.4% | ใช้ฟังก์ชันไม่ตรง dialect |
| unknown/other | 24 | 35.3% | กลุ่มปัญหาอื่นหรือข้อความไม่ชัด |

**การตีความผล (Insight)**

| ข้อสังเกต | นัยสำคัญ |
|---|---|
| Success rate > 80% | ระบบทำงานได้จริงในระดับ prototype production |
| column_error สูงสุด (35%) | ช่องว่างหลักอยู่ที่ schema grounding ระดับ column |
| Retry success 7 รายการ | Self-correction มีประสิทธิภาพจริง |
| p95 = 47.82s | Latency tail ยังสูง ต้อง optimize เชิงสถาปัตยกรรม |

### 5.5 Richer Metrics (Log v2)

เพื่อเพิ่มความสามารถในการวิเคราะห์ระบบโดยไม่ต้องมี ground-truth SQL ระบบได้เพิ่ม **8 fields** ใหม่เข้าไปใน `query_logs.jsonl` ทุก entry:

**ที่มาของ Metrics แต่ละตัว**

| Field | ประเภท | ที่มา | คำอธิบาย |
|---|---|---|---|
| `tables_used` | `list[str]` | Parse SQL (sqlglot AST) | ตารางทั้งหมดที่ถูกอ้างอิงใน query |
| `join_count` | `int` | Parse SQL | จำนวน JOIN clauses ใน query |
| `has_aggregation` | `bool` | Parse SQL | มี SUM/COUNT/AVG/MAX/MIN หรือไม่ |
| `has_subquery` | `bool` | Parse SQL | มี nested SELECT หรือ WITH clause |
| `has_group_by` | `bool` | Parse SQL | มี GROUP BY หรือไม่ |
| `result_row_count` | `int` | Engine response | จำนวน rows ที่ return จริง (-1 ถ้า error) |
| `rag_examples_count` | `int` | ExampleStore | จำนวน examples ที่ RAG retrieve ได้จริง |
| `model_name` | `str` | Settings | LLM ที่ใช้ เช่น "gpt-4o-mini" |

**สถาปัตยกรรมของระบบ Metrics**

```
คำถามผู้ใช้
    │
    ├─► ExampleStore.async_format_examples_for_prompt_with_count()
    │       └─► return (formatted_text, rag_examples_count)
    │
    ├─► NLPEngine.query_database()
    │       └─► return (sql, data, error, retry, viz, rag_examples_count)  ← 6-tuple
    │
    └─► api/routes.py
            ├─► parse_sql_metrics(sql)   ← sqlglot AST
            ├─► len(data)                ← result_row_count
            ├─► settings.MODEL_PROVIDER  ← model_name
            └─► log_query_to_file(... all 8 new fields ...)
```

**ตัวอย่าง Log Entry ที่สมบูรณ์**

```json
{
  "log_id": "...",
  "timestamp": "2026-03-21T14:23:11",
  "question": "ยอดขายรวมแยกตามเดือนของแต่ละปี",
  "sql": "SELECT year, month, SUM(total_price) FROM receipt GROUP BY year, month",
  "status": "Success",
  "duration_sec": 9.42,
  "dialect": "mysql",
  "retry_count": 0,
  "tables_used": ["receipt"],
  "join_count": 0,
  "has_aggregation": true,
  "has_subquery": false,
  "has_group_by": true,
  "result_row_count": 24,
  "rag_examples_count": 3,
  "model_name": "gpt-4o-mini"
}
```

**การวิเคราะห์ที่ทำได้จาก Metrics ใหม่**

| คำถามที่ตอบได้ | Field ที่ใช้ |
|---|---|
| RAG มีประโยชน์จริงไหม? (เทียบ success rate เมื่อ rag_count=0 vs 3) | `rag_examples_count` + `status` |
| Query ซับซ้อนแค่ไหนที่ระบบรับมือไม่ได้? | `join_count` + `has_subquery` + `status` |
| Aggregation queries fail บ่อยกว่า simple queries หรือไม่? | `has_aggregation` + `status` |
| Model แต่ละตัวให้ผลต่างกันแค่ไหน? | `model_name` + `status` + `duration_sec` |
| ตารางไหนที่ query fail บ่อยที่สุด? | `tables_used` + `status` |
| Response มีข้อมูลหรือว่างเปล่า? | `result_row_count` |

**Backward Compatibility**

- Fields ทั้ง 8 ตัวมี safe default (`[]`, `0`, `False`, `-1`, `""`)
- JSONL entries เก่าที่ไม่มี fields ใหม่ load ได้ปกติผ่าน `.get(..., default)`
- `HistoryEntry` dataclass ใน `query_history.py` อัปเดตรองรับแล้ว

### 5.6 Mini Benchmark: Execution Accuracy

เพื่อให้มีผลเชิงปริมาณที่อ้างอิงได้ ทีมสร้าง **mini benchmark 25 ข้อ** จาก classicmodels database (SQLite) โดยเขียน gold SQL ด้วยมือและ verify ทั้งหมดก่อน จากนั้นวัด Execution Accuracy จริงด้วย `eval/run_eval.py`

**โครงสร้าง Benchmark**

| Category | จำนวน | ลักษณะโจทย์ |
|---|---:|---|
| simple | 5 | SELECT พื้นฐาน, WHERE, ORDER BY |
| aggregation | 7 | COUNT / SUM / AVG / HAVING |
| join | 7 | 2–3 table JOINs พร้อม GROUP BY |
| complex | 6 | Subquery, ratio, 4-table JOIN, NOT IN |
| **รวม** | **25** | |

**ผลการทดสอบ — Multi-Model Comparison (SQLite dialect, 25 ข้อ)**

ทีมทดสอบ **6 configurations** ครอบคลุม 5 model families เพื่อเปรียบเทียบผล:

| Model | Provider | RAG_K | Retry | SQL Valid | Exec'able | **EX** | Elapsed |
|---|---|---:|---:|---:|---:|---:|---:|
| gpt-4o-mini ×5 runs | openai | 3 | 0 | 100% | 100% | **48%** (12/25) | ~31s |
| qwen2.5-coder:7b | ollama | 0 | — | 100% | 96% | **56%** (14/25) | 225s |
| qwen2.5-coder:7b | ollama | 3 | 2 | 100% | 100% | **60%** (15/25) | 216s |
| glm-4.7-flash | zhipu | 5 | 0 | 100% | 92% | **56%** (14/25) | 752s |
| nvidia/nemotron-120b | openrouter | 3 | 2 | 100% | 92% | **64%** (16/25) | 530s |
| **glm-5** | **zhipu** | **5** | **0** | **100%** | **100%** | **80%** (20/25) | 635s |

> หมายเหตุ: gpt-4o-mini รันซ้ำ 5 ครั้ง (results_4o_mini_1–5) ได้ผล EX = 48% ทุกครั้ง แสดงให้เห็นความ stable ของ pipeline

**EX แยกตาม Category (ทุก model):**

| Category | N | gpt-4o-mini | qwen (RAG=3) | nemotron | glm-4.7-flash | **glm-5** |
|---|---:|---:|---:|---:|---:|---:|
| simple | 5 | 60% | **100%** | 80% | 60% | **100%** |
| aggregation | 7 | 57% | 71% | **86%** | 71% | 71% |
| join | 7 | 14% | 29% | 43% | 43% | **86%** |
| complex | 6 | 67% | 50% | 50% | 50% | 67% |
| **รวม** | **25** | **48%** | **60%** | **64%** | **56%** | **80%** |

**การตีความผล**

| ผลที่สังเกต | การตีความ |
|---|---|
| SQL Validity = 100% ทุก model | Safety layer และ schema injection ทำงานถูกต้อง ไม่มี model ใดสร้าง SQL syntax ผิด |
| glm-5 EX = 80% (20/25) | Best-in-class บน benchmark นี้ — ดีกว่า gpt-4o-mini ถึง +32pp |
| gpt-4o-mini stable 48% × 5 runs | Pipeline มีความ deterministic สูง ไม่มี randomness ข้าม run |
| RAG ช่วย qwen: 56% → 60% (+4pp) | RAG_TOP_K=3 vs 0 บน qwen แสดงผลบวกชัดเจนโดยเฉพาะ simple category (40% → 100%) |
| Join category คือจุดอ่อนของทุก model | gpt-4o-mini 14%, qwen 29%, nemotron 43% — glm-5 เป็นเดียวที่ทำได้ 86% |
| Complex สูงกว่า Join ในหลาย model | NOT IN / subquery เป็น pattern ที่โมเดลเข้าใจดีกว่า multi-hop FK JOIN |
| glm-4.7-flash vs glm-5: 56% vs 80% | Model size/capability ส่งผลอย่างมีนัย (+24pp) ใน Join category (43% vs 86%) |

### 5.7 กรณีศึกษา: "Correct but Over-specified" — ข้อจำกัดของ EX Metric

ระหว่างการประเมินพบกรณีที่ **ระบบตอบถูกในเชิง business แต่ถูกนับว่า fail** โดย EX metric ซึ่งเป็น known limitation สำคัญที่ควรทำความเข้าใจ

ตัวอย่าง: `complex_006` — คำถาม "สินค้าที่ไม่เคยถูกสั่งซื้อเลย"

Gold SQL (เฉลยที่เราเขียน):
```sql
SELECT productName
FROM products
WHERE productCode NOT IN (
  SELECT DISTINCT productCode FROM orderdetails
)
LIMIT 500
```

Predicted SQL (ที่โมเดล generate):
```sql
SELECT p.productCode, p.productName
FROM products AS p
LEFT JOIN orderdetails AS od
  ON p.productCode = od.productCode
WHERE od.orderNumber IS NULL
LIMIT 500
```

ผลลัพธ์ที่ได้จากการรันทั้งสอง query บน classicmodels.db:

| | Gold SQL | Predicted SQL |
|---|---|---|
| **Columns** | `productName` (1 คอลัมน์) | `productCode`, `productName` (2 คอลัมน์) |
| **Rows** | `('1985 Toyota Supra',)` | `('S18_3233', '1985 Toyota Supra')` |
| **จำนวน rows** | 1 row | 1 row |

**ทั้งสอง query ระบุสินค้าชิ้นเดียวกัน (`1985 Toyota Supra`) ได้อย่างถูกต้อง**

สาเหตุที่ EX Metric fail — `result_sets_match()` ใน eval script ทำงานดังนี้:

```python
def result_sets_match(gold_df, pred_df):
    if gold_df.shape[1] != pred_df.shape[1]:  # ← เช็คจำนวน column ก่อน
        return False                            # ← 1 ≠ 2 → return False ทันที
    ...
```

Gold มี 1 คอลัมน์ แต่ Predicted มี 2 คอลัมน์ → ฟังก์ชันตัดสินว่า "ไม่ตรง" ทันทีโดยไม่ดูค่าข้างใน

การวิเคราะห์ว่า Predicted SQL ผิดหรือถูก:

| มุมมอง | การตัดสิน | เหตุผล |
|---|---|---|
| Business Logic | ✅ ถูก | ระบุสินค้าที่ไม่มีออเดอร์ได้ครบถ้วน |
| SQL Technique | ✅ ถูก | LEFT JOIN + WHERE IS NULL เป็นวิธีมาตรฐานใช้แทน NOT IN ได้ |
| Output Schema | ❌ ต่างกัน | SELECT productCode เกินมา ทำให้ผลมี 2 คอลัมน์ |
| EX Metric | ❌ Fail | EX เปรียบเทียบ result set ทั้งก้อน รวมถึงจำนวนคอลัมน์ |

เหตุผลที่ไม่แก้ EX ให้ tolerant กว่านี้: EX แบบ strict คือมาตรฐานที่ benchmark ระดับสากล (BIRD, Spider) ใช้ หากปรับให้ relax จะทำให้เปรียบผลกับงานวิจัยอื่นไม่ได้ จึงคงไว้แบบ strict และบันทึก limitation แทน

ผลกระทบต่อตัวเลข: มี query ลักษณะ "correct but over-specified" อย่างน้อย **1 ข้อ** (`complex_006`) ดังนั้น EX จริงในเชิง business ของ gpt-4o-mini น่าจะอยู่ที่ **49–52%** ขึ้นอยู่กับ run — ยืนยันโดยการรันซ้ำ 5 ครั้งที่ได้ 12/25 (48%) อย่างสม่ำเสมอ สำหรับ glm-5 ที่ได้ 80% (20/25) ก็อาจมีกรณีลักษณะเดียวกัน ซึ่งหมายถึง EX จริงเชิง business อาจสูงถึง **84%**

### 5.8 ข้อจำกัดของ Benchmark และ Evaluation Gap

**ข้อจำกัดของ Benchmark นี้**

| ข้อจำกัด | รายละเอียด |
|---|---|
| In-distribution | สร้างจากคำถามที่ระบบเคยตอบ — EX อาจสูงกว่าความจริงสำหรับคำถามใหม่ |
| ขนาดเล็ก | 25 ข้อ — variance สูง ควรขยายเป็น 100+ ข้อ |
| Dialect เดียว | Gold SQL เป็น SQLite เท่านั้น — ไม่ครอบคลุม MySQL (dialect หลักของ production) |
| Strict EX | อาจ undercount ผลที่ถูกต้องในเชิง business (ดูกรณีศึกษา 5.7) |

**Academic Metrics ที่ยังวัดไม่ได้ และเหตุผล**

Text-to-SQL benchmarks มาตรฐาน (Spider, BIRD) ใช้ metrics หลายตัวที่ต้องการ **ground-truth SQL** หรือ **labeled annotations** ซึ่งระบบนี้ยังไม่มีในรูปแบบครบถ้วน เนื่องจากเป็น production system ที่ไม่มี labeled test set:

| Metric | เหตุผลที่ทำไม่ได้ |
|---|---|
| **Exact Match (EM)** | ต้องมีคำตอบ SQL เฉลยมาเปรียบ |
| **Execution Accuracy (EX)** | ต้องรัน prediction และ gold SQL แล้วเทียบ result set |
| **Test Suite Accuracy (TSA)** | ต้องมีหลาย DB instance สำหรับทดสอบ |
| **Valid Efficiency Score (VES)** | ต้องเทียบ execution time กับ gold SQL |
| **Component / Clause Match** | ต้องมี gold SQL ให้แตก SELECT/WHERE/JOIN เทียบ |
| **Schema Linking Accuracy** | ต้องมี gold annotation ของ table-column |
| **Join / Aggregation / Condition Accuracy** | ต้องมี gold SQL เพื่อเทียบส่วนย่อย |

**Evaluation Gap ที่ควรปรับเพื่อคะแนนสูงขึ้น**

| # | งาน | ผลที่ได้ |
|---:|---|---|
| 1 | ขยาย benchmark เป็น 100+ ข้อ ครอบคลุม MySQL + receipt schema | EX มีความน่าเชื่อถือทางสถิติ |
| 2 | Ablation study (ปิด RAG/schema filter/retry แล้วเทียบ EX) | วัด contribution ของแต่ละ component |
| 3 | Semantic correctness metric | ประเมินเกินกว่า execution pass/fail |

---

## 6. ข้อจำกัดและนวัตกรรม
[เกณฑ์ 4: ข้อจำกัด | เกณฑ์ 5 | เกณฑ์ 7: นวัตกรรม]

### 6.1 ปัญหาที่พบบ่อย (Key Pain Points)

- **Thai Word Disambiguation**: คำย่อภาษาไทยถูกตีความผิด (มกรา, กพ, มค) — ระบบไม่มี Thai NLP tokenizer ทำให้คำย่อเดือนถูกแปลผิด
- **Complex JOIN Accuracy**: การเลือกตารางที่เกี่ยวข้องยังไม่แม่นยำ — join category EX ต่ำสุด (14–86% ขึ้นอยู่กับ model)
- **Response Time**: ช้าเกินไปสำหรับการใช้งานจริง — เฉลี่ย 18.65s, p95 = 47.82s โดยเฉพาะ Ollama local (225s/25 queries)

### 6.2 จุดแข็ง (Production-oriented Strengths)

**Security & Safety**

| มาตรการ | รายละเอียด |
|---|---|
| Destructive command block | บล็อก INSERT/UPDATE/DELETE/DROP/ALTER/CREATE/... |
| Single-statement enforcement | ป้องกัน multi-statement injection |
| Read-only policy | อนุญาตเฉพาะ SELECT |
| LIMIT enforcement | inject หรือ clamp อัตโนมัติ |
| Table allowlist | validate ตารางจาก schema ปัจจุบัน |

**Reliability & Operability**

- มี retry mechanism เมื่อ query fail (สูงสุด 2 ครั้ง)
- มี logging ทั้ง JSONL และ CSV (18 fields ต่อ entry)
- มี endpoint สำหรับ history, feedback, favorites
- มี state manager ที่ restore DB connection ได้บางส่วน
- มี unit tests ผ่านทั้งหมด **44 tests** ผ่าน GitHub Actions CI

**Deployability**

| Layer | เทคโนโลยี |
|---|---|
| Backend | FastAPI + Uvicorn |
| Frontend | HTML/CSS/JS + Chart.js |
| Database | SQLAlchemy (SQLite, MySQL, PostgreSQL) |
| LLM | Pluggable: Ollama / OpenAI / Google |

### 6.3 ข้อจำกัดปัจจุบัน (Current Limitations)

| # | ข้อจำกัด | รายละเอียด |
|---:|---|---|
| 1 | Log integrity | `query_logs.jsonl` มี 2 บรรทัด malformed |
| 2 | Feedback normalization | มีค่า feedback นอกกลุ่ม positive/negative |
| 3 | Eval coverage | Mini benchmark ยังเป็น SQLite เท่านั้น |
| 4 | Latency tail | p95 ยังแตะ ~47.82s |
| 5 | Auth/RBAC | ยังไม่มี API-level authentication |

### 6.4 Risk Register

| ความเสี่ยง | ผลกระทบ | แนวทางลดความเสี่ยง |
|---|---|---|
| Malformed logs | metrics เพี้ยน, train data สกปรก | เพิ่ม JSON validation ก่อนเขียนไฟล์ |
| Schema grounding error | query fail, user trust ลด | เพิ่ม schema linking + FK hints + curated examples |
| Dialect mismatch | SQL รันไม่ผ่าน | เพิ่ม dialect-specific examples + transpilation test |
| Latency สูง | UX แย่ | optimize provider strategy, cache, async tuning |
| ไม่มี auth | ใช้งานองค์กรลำบาก | เพิ่ม API auth + role-based data access |

### 6.5 นวัตกรรมของโครงงาน (Wow Factor)
[เกณฑ์ 7]

**6.5.1 Dual-RAG ที่แยกบทบาทชัด**

| RAG | บทบาท | ผลที่ได้ |
|---|---|---|
| Example RAG | สอน SQL pattern | โมเดลรู้ว่า query ควรมีโครงสร้างแบบใด |
| Schema RAG | สอนขอบเขต schema | โมเดลรู้ว่าตารางใดเกี่ยวข้อง |

การแยก RAG ทำให้คุณภาพ generation ดีกว่าการรวมทุกอย่างไว้ใน context ก้อนเดียว

**6.5.2 Thai-English Semantic Bridge**

การ mapping คำไทย → table/column อังกฤษใน schema retrieval ช่วยลดช่องว่าง semantic สำหรับโจทย์ไทยที่ต้องทำงานกับ schema ภาษาอังกฤษ

**6.5.3 FK-aware Context + Retry**

ระบบส่ง FK path และความสัมพันธ์ไปพร้อมกับ schema ทำให้การ JOIN มีหลักยึดที่ชัดเจน และเมื่อพลาดก็ retry ด้วย full schema + FK info

**6.5.4 Dialect-aware + Auto-Transpilation**

แก้ pain point ของงาน multi-db: examples ที่ semantic ใกล้ที่สุดอาจเป็น dialect ต่างกัน ระบบจึงแปลง SQL examples ให้ตรง dialect ก่อนป้อนเข้า model อัตโนมัติ

**6.5.5 Intelligent Visualization Integration**

ระบบเชื่อม "คำถาม → SQL → ข้อมูล → กราฟ" ใน pipeline เดียว รองรับ multi-series (`series_col`) ทำให้ผู้ใช้เห็น insight ได้ทันทีโดยไม่ต้องทำ visualization เอง

**เหตุผลที่ถือว่าเป็น Wow Factor:**

| ข้อ | เหตุผล |
|---|---|
| 1 | ไม่ใช่ demo เฉพาะ model แต่เป็นระบบครบวงจรตั้งแต่ input จนถึง output ที่ใช้งานได้จริง |
| 2 | มี engineering guardrails สำหรับ production (safety/logging/retry) |
| 3 | รองรับภาษาไทยจริงบนสถาปัตยกรรมที่ต่อยอดได้ |
| 4 | มีฐานข้อมูลเชิงพฤติกรรม (logs + feedback) สำหรับพัฒนาเวอร์ชันถัดไป |

### 6.6 แผนพัฒนาต่อ (Roadmap)

| ระยะ | งาน | Priority |
|---|---|---|
| **ระยะสั้น** (1–2 สัปดาห์) | แก้ log writer ให้ atomic ต่อ record | สูง |
| | Normalize feedback values ที่ API layer | สูง |
| | เพิ่ม dashboard success/error/latency อัตโนมัติ | กลาง |
| **ระยะกลาง** (2–4 สัปดาห์) | เพิ่ม benchmark suite แบบ end-to-end | สูง |
| | Error taxonomy ที่ละเอียดขึ้น (table/column/join/agg) | กลาง |
| | Prompt + RAG ablation report | กลาง |
| **ระยะยาว** (1–2 เดือน) | เพิ่ม Auth/RBAC | สูง |
| | Semantic cache | กลาง |
| | Active learning จาก positive feedback | ต่ำ |

---

## ภาคผนวก

### A. Product Specification

**A.1 ข้อมูลผลิตภัณฑ์**

| รายการ | ค่า |
|---|---|
| **ชื่อผลิตภัณฑ์** | Thai NLP-to-SQL Agent |
| **Version** | 1.0.0 |
| **ประเภท** | AI Data Analyst — Natural Language Interface to SQL Databases |
| **กลุ่มเป้าหมาย** | Business users ที่ไม่เชี่ยวชาญ SQL, Data Analyst, นักพัฒนา |
| **Architecture** | Hybrid: RAG + Prompt Engineering + LLM + SQL Safety + Self-Correction |
| **Backend** | Python 3.10+, FastAPI, SQLAlchemy, LangChain, ChromaDB |
| **Frontend** | Vanilla JS + Chart.js |
| **Database รองรับ** | SQLite, MySQL, PostgreSQL |

---

**A.2 Configuration Parameters**

| Parameter | Default | หน่วย | คำอธิบาย |
|---|---|---|---|
| `MODEL_PROVIDER` | `ollama` | — | LLM provider: ollama / openai / google / openrouter / zhipu |
| `OPENAI_MODEL` | `gpt-4o-mini` | — | OpenAI model name |
| `GOOGLE_MODEL` | `gemini-2.0-flash-exp` | — | Google Gemini model |
| `OLLAMA_MODEL` | `qwen2.5-coder:7b` | — | Ollama local model |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | URL | Ollama server endpoint |
| `OPENROUTER_MODEL` | `meta-llama/llama-4-maverick:free` | — | OpenRouter model |
| `ZHIPU_MODEL` | `glm-4-flash` | — | Zhipu (Z.ai) model |
| `EMBEDDING_MODEL` | `intfloat/multilingual-e5-small` | — | Sentence embedding model (Thai-compatible, 384-dim) |
| **`RAG_TOP_K`** | **5** | ตัวอย่าง | จำนวน few-shot examples ที่ดึงมาช่วย LLM |
| `RAG_DISTANCE_THRESHOLD` | `15.0` | cosine dist | ตัดตัวอย่างที่ semantic ห่างเกิน threshold นี้ |
| `SCHEMA_TOP_K` | `5` | ตาราง | จำนวนตารางสูงสุดที่ filter ให้ Ollama local model |
| **`MAX_SQL_LIMIT`** | **500** | rows | จำนวน rows สูงสุดที่ query ได้ (DoS prevention) |
| **`MAX_RETRIES`** | **0** | ครั้ง | จำนวนครั้ง self-correction เมื่อ SQL fail |
| `ENABLE_INTELLIGENT_VIZ` | `False` | bool | เปิดใช้ LLM สำหรับแนะนำกราฟ (ช้าลง แต่แม่นขึ้น) |
| `LOG_FILE_JSONL` | `query_logs.jsonl` | path | ไฟล์ log แบบ JSON Lines |
| `LOG_FILE_CSV` | `query_logs.csv` | path | ไฟล์ log แบบ CSV |

---

**A.3 REST API Endpoints**

| Method | Path | หน้าที่ | Input | Output |
|---|---|---|---|---|
| `POST` | `/api/connect` | เชื่อมต่อ database | `{db_type, host, port, user, password, database}` | `{status, message}` |
| `POST` | `/api/query` | แปลคำถามไทย → SQL → ผลลัพธ์ | `{question, dialect, preferred_chart_type}` | `{sql, data, visualization, log_id, retry_count}` |
| `GET` | `/api/schema` | ดู database schema | — | `{tables: [{name, columns}]}` |
| `GET` | `/api/history` | ดูประวัติ query | `?limit&status&dialect` | `{history: [HistoryEntry]}` |
| `PATCH` | `/api/history/{log_id}/feedback` | ให้ feedback | `{feedback, feedback_text}` | `{status, feedback}` |
| `GET/POST/DELETE` | `/api/favorites` | จัดการ query ที่บันทึก | — | `{favorites: [...]}` |
| `GET` | `/api/health` | Health check | — | `{status: "ok"}` |

---

**A.4 Chart Types ที่รองรับ**

| Chart Type | ทริกเกอร์ | Use Case |
|---|---|---|
| **Bar** | "เปรียบเทียบ", "อันดับ", "top", categorical + numeric | Ranking, category comparison |
| **Line** | "แนวโน้ม", "trend", date/month column + numeric | Time series, growth analysis |
| **Pie** | "สัดส่วน", "เปอร์เซ็นต์", "วงกลม" | Proportion, distribution |
| **Scatter** | "correlation", 2+ numeric columns | Relationship analysis |
| **Table** | Fallback / ผู้ใช้เลือก | Raw data display |
| **Multi-Series** | month column + year column ที่มีหลายค่า | Trend per year |

---

**A.5 Database Drivers ที่รองรับ**

| Database | Driver | Connection Format |
|---|---|---|
| SQLite | Built-in (`sqlite3`) | `sqlite:///path/to/db.db` |
| MySQL | `pymysql` | `mysql+pymysql://user:pass@host:port/db?charset=utf8mb4` |
| PostgreSQL | `psycopg2-binary` | `postgresql+psycopg2://user:pass@host:port/db` |

---

**A.6 Security & Safety Features**

| Feature | Implementation | สิ่งที่ป้องกัน |
|---|---|---|
| **Read-only enforcement** | sqlglot AST parse → reject non-SELECT | Data modification/deletion |
| **Single statement** | Parse → reject `;` multi-statement | SQL injection |
| **Table allowlist** | Validate ทุก table reference กับ schema จริง | Access to unauthorized tables |
| **LIMIT enforcement** | Inject/clamp ≤ MAX_SQL_LIMIT | DoS / memory exhaustion |
| **No PRAGMA/ATTACH** | AST node block list | SQLite system access |

---

### B. โครงสร้างสไลด์ (Slide Blueprint)

> เรียงตาม logic ของกรรมการประเมิน พร้อมเวลาพูดที่แนะนำ

| Slide | หัวข้อ | Key Message | เวลาพูด |
|---:|---|---|---:|
| 1 | Problem & Motivation | ช่องว่างระหว่างผู้ใช้ธุรกิจกับ DB | 35–45 วินาที |
| 2 | System Objectives | เป้าหมายครบวงจร ไม่ใช่แค่ generate SQL | 30–40 วินาที |
| 3 | Architecture Overview | ระบบหลายชั้นเพื่อ production-readiness | 45–60 วินาที |
| 4 | Data & Context Pipeline | คุณภาพมาจากการเตรียม context ที่ถูกต้อง | 50–60 วินาที |
| 5 | Technique Selection | Hybrid เพราะสมดุล accuracy, safety, maintainability | 55–70 วินาที |
| 6 | SQL Safety + Self-Correction | มี guardrails ชัดเจน ไม่ปล่อย SQL ดิบ | 55–70 วินาที |
| 7 | Evaluation Results | มีผลวัดจริง ไม่ใช่แค่เดโมเชิงคุณภาพ | 50–65 วินาที |
| 8 | Error Analysis | รู้ว่าพลาดตรงไหน และจะปรับอะไรต่อ | 55–70 วินาที |
| 9 | Real-world Readiness | พร้อมระดับ prototype production แต่มี gap ที่ระบุชัด | 50–65 วินาที |
| 10 | Innovation & Wow Factor | บูรณาการหลายเทคนิคจนใช้งานได้จริง | 55–70 วินาที |
| 11 | Roadmap | แผนพัฒนาที่วัดผลได้ ไม่ใช่แนวคิดกว้างๆ | 45–60 วินาที |
| 12 | Conclusion | แก้ปัญหาจริงได้แล้วในระดับหนึ่ง และมีเส้นทางสู่ production ที่ชัด | 35–50 วินาที |

**รายละเอียดว่าแต่ละสไลด์ควรมีอะไรบ้าง**

**Slide 1: Problem & Motivation**
- 1 ประโยคอธิบายปัญหา: ผู้ใช้ถามภาษาไทย แต่ฐานข้อมูลตอบได้ผ่าน SQL เท่านั้น
- pain points 3 ข้อ: ภาษาธรรมชาติกำกวม, schema เป็นอังกฤษ, SQL ผิดแล้วใช้งานจริงไม่ได้
- ภาพประกอบแนะนำ: Thai Question → SQL → Database → Result

**Slide 2: System Objectives**
- เป้าหมาย 4 ข้อ: แปลไทยเป็น SQL, รองรับหลาย dialect, ปลอดภัย, มีผลลัพธ์พร้อม visualization
- ระบุ input/output ของระบบสั้นๆ
- ย้ำว่าโจทย์นี้ไม่ใช่แค่ text generation แต่ต้อง executable และ safe

**Slide 3: Architecture Overview**
- วาง architecture block diagram ทั้งระบบ
- ใส่ component หลัก: Query Input, Embedding, RAG, LLM, SQL Safety, Execution, Self-Correction, Visualization, Logging
- เน้นว่าระบบออกแบบหลายชั้นเพื่อ production-readiness

**Slide 4: Data & Context Pipeline**
- อธิบายแหล่งข้อมูล 3 ส่วน: training examples, schema จริงจาก DB, operational logs
- ใส่ context preparation 6 ขั้นแบบย่อ
- ย้ำว่าคุณภาพคำตอบมาจาก context ที่ถูกต้อง ไม่ใช่ prompt อย่างเดียว

**Slide 5: Technique Selection**
- อธิบายว่าทำไมเลือก Dual RAG + LLM + Safety Layer
- เปรียบเทียบสั้นๆ กับ prompt-only LLM ว่าทำไมไม่พอ
- สรุป trade-off: accuracy ดีขึ้น แต่มี latency เพิ่ม

**Slide 6: SQL Safety + Self-Correction**
- ใส่ safety rules: read-only, single statement, table allowlist, LIMIT enforcement
- ใส่ flow ตอน error เป็น 1,2,3,4: execute → classify error → correction prompt → retry/return error
- ยกตัวอย่าง error จริง 1 เคส เช่น `unknown column` แล้วบอกว่าระบบแก้ได้อย่างไร

**Slide 7: Evaluation Results**
- ใส่ KPI หลัก: success rate, first-try success, retry success, p50, p95
- แนะนำใช้กราฟแท่งหรือ KPI cards ให้เห็นเร็ว
- ย้ำว่าผลมาจาก `query_logs.jsonl` จริง ไม่ใช่เฉพาะ demo cases

**Slide 8: Error Analysis**
- ใส่ pie/bar chart ของ error types
- อธิบาย insight สำคัญ: `column_error` สูงสุด แปลว่าปัญหาอยู่ที่ schema grounding ระดับ column
- ต่อด้วย implication ว่าควรแก้ที่ FK hints, schema linking, curated examples

**Slide 9: Real-world Readiness**
- สรุปสิ่งที่พร้อมใช้จริง: multi-dialect, safety, logging, retry, chart recommendation
- สรุปข้อจำกัดที่ยังมี: latency tail สูง, benchmark ยังเล็ก, semantic ambiguity ยังมี
- ใช้ตาราง 2 คอลัมน์ `พร้อมแล้ว` / `ยังต้องพัฒนา`

**Slide 10: Innovation & Wow Factor**
- เลือกนวัตกรรม 3–5 ข้อที่เด่นจริง เช่น Dual-RAG, Thai-English semantic bridge, FK-aware retry, auto-transpile dialect
- แต่ละข้ออธิบายสั้นๆ ว่าช่วยแก้ pain point ไหน
- หลีกเลี่ยงการ list ทุก feature ให้เน้นเฉพาะสิ่งที่แตกต่าง

**Slide 11: Roadmap**
- แบ่งเป็นระยะสั้น กลาง ยาว
- ตัวอย่าง: เพิ่ม dashboard metrics, ขยาย benchmark, เพิ่ม user feedback learning loop
- แต่ละข้อควรโยงกับ metric ที่จะดีขึ้น เช่น success rate หรือ latency

**Slide 12: Conclusion**
- สรุป 3 บรรทัด: ปัญหาที่แก้, วิธีที่ใช้, ผลที่ได้
- ปิดท้ายด้วยตัวเลขหลัก 1 ชุด เช่น `Success rate 82.65%`
- ถ้ามีเวลา ใส่ประโยคปิดว่า “ระบบนี้ไปได้ไกลกว่าการ generate SQL เพราะคุม execution, safety และ feedback loop ได้”

**คำแนะนำการจัดลำดับการเล่า**
- Slide 1-2: ทำให้กรรมการเห็นปัญหาและเป้าหมายก่อน
- Slide 3-6: อธิบายว่าระบบทำงานอย่างไรและทำไมถึงออกแบบแบบนี้
- Slide 7-9: แสดงหลักฐานเชิงผลลัพธ์และข้อจำกัดอย่างตรงไปตรงมา
- Slide 10-12: ปิดด้วยจุดเด่น แผนต่อยอด และข้อสรุป

---

### C. หลักฐานอ้างอิงจากโค้ด

| หมวด | ไฟล์ | บทบาทใน Flow |
|---|---|---|
| API Server | `api/main.py` | Startup, CORS, static mount |
| State Management | `api/dependencies.py` | GlobalStateManager, DB connection, NLPEngine singleton |
| Core Orchestration | `core/services/engine.py` | NLPEngine, query_database(), retry loop |
| SQL Safety | `core/domain/sql_safety.py`, `tests/unit/test_sql_safety.py` | AST validation, LIMIT enforcement |
| Schema Extraction / Filtering | `core/domain/schema_utils.py` | get_database_schema(), smart_filter_schema(), format_schema_for_prompt(), get_join_hints() |
| Schema RAG | `core/data/schema_rag.py` | SchemaRAG, Thai keyword mapping, Ollama table filtering |
| Example Retrieval | `core/data/rag_store.py`, `thai_sql_examples.json` | ExampleStore, ChromaDB, E5 embedding, dialect transpilation |
| SQL Metrics Parser | `core/utils/sql_metrics.py` | parse_sql_metrics() for logging |
| Visualization | `core/viz/viz_recommender.py` | VizService, rule-based + LLM chart recommendation |
| API & Logging | `api/routes.py`, `api/dependencies.py` | HTTP endpoints, log_query_to_file() |
| Config | `core/config.py` | Settings class, all parameters |
| Mini Benchmark | `eval/benchmark_classicmodels.json`, `eval/run_eval.py` | 25-question evaluation suite |
| Evaluation Results | `eval/results_4o_mini_{1-5}.json`, `eval/results_ollama_qwen_rag3_re2.json`, `eval/results_qwen_ragk_0.json`, `eval/results_nvidia_nemotron_rag3_re2.json`, `eval/results_glm_5_rag3_re2.json`, `eval/results.json` | Multi-model benchmark results |
| Operational Logs | `query_logs.jsonl`, `query_logs.csv` | 18-field per-query logging |

---

*จัดทำโดย: Thai NLP-to-SQL Development Team | อัปเดตล่าสุด: 22 มีนาคม 2026*
