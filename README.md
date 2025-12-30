# 🇹🇭 Thai NLP-to-SQL Agent (Multi-DB & Hardened)

โปรเจกต์นี้คือ **AI Data Analyst** อัจฉริยะที่ช่วยให้คุณสอบถามข้อมูลจาก Database ได้ด้วย **"ภาษาไทยธรรมชาติ"** แปลงเป็น SQL Query และแสดงผลกราฟให้อัตโนมัติ รองรับทั้ง SQLite, MySQL และ PostgreSQL พร้อมระบบความปลอดภัยและการวัดผลที่รัดกุม

![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=Streamlit&logoColor=white) ![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white) ![Ollama](https://img.shields.io/badge/Ollama-Local_LLM-000000?style=for-the-badge) ![LangChain](https://img.shields.io/badge/LangChain-🦜️🔗-319795?style=for-the-badge)

---

## 🌟 ฟีเจอร์ใหม่ (v2.0 Upgrade)

-   🛡️ **Enterprise-Grade SQL Safety:**
    -   **Read-Only Guarantee:** บล็อกคำสั่งอันตราย (INSERT/UPDATE/DELETE/DROP) ทันที
    -   **Limit Enforcement:** บังคับใส่ `LIMIT 500` อัตโนมัติ ป้องกันข้อมูลล้น
    -   **Dialect-Aware:** รองรับ syntax เฉพาะของ SQLite, MySQL, PostgreSQL อย่างถูกต้อง
-   🧠 **Smart Schema Injection:** คัดเลือกเฉพาะตารางที่เกี่ยวข้องส่งให้ AI เพื่อลด token และเพิ่มความแม่นยำ
-   📊 **Auto Visualization:** เลือกกราฟที่เหมาะสม (Bar/Line/Scatter/Pie) ให้อัตโนมัติด้วย **Plotly**
-   📈 **Evaluation Baseline:** ระบบวัดผล (Success Rate, Execution Match) จาก Log การใช้งานจริง
-   🤝 **Team Sharing:** รองรับ JSONL logs และ Persisted RAG Store สำหรับทำงานร่วมกัน

---

## 🛠️ Tech Stack

-   **Frontend:** [Streamlit](https://streamlit.io/) + Plotly
-   **LLM Orchestration:** [LangChain](https://www.langchain.com/)
-   **Model:** Qwen2.5-Coder:7b (via Ollama)
-   **Vector Store:** ChromaDB (Persisted in `rag_db/`)
-   **SQL Parsing:** sqlglot
-   **Database:** SQLite, MySQL, PostgreSQL (via SQLAlchemy)

---

## ⚙️ การติดตั้ง (Installation)

### 1. Prerequisites
-   Python 3.10+
-   [Ollama](https://ollama.com/) (รัน `ollama serve`)

### 2. Setup
```bash
# Clone
git clone <your-repo-url>
cd nlp_sql_project

# Venv
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install
pip install -r requirements.txt

# Pull Model
ollama pull qwen2.5-coder:7b
```

### 3. Create Mock DB (Optional)
```bash
python setup_db.py
```

### 4. Run App
```bash
streamlit run app.py
```

---

## 🛡️ Security & Safety

ระบบนี้ออกแบบมาให้ปลอดภัยสำหรับการใช้งานแบบ Read-Only:
1.  **Parser Check:** ใช้ `sqlglot` ตรวจสอบ structure ของ SQL ว่าเป็น `SELECT` เท่านั้น
2.  **Keyword Block:** ปฏิเสธคำสั่ง destructive (DROP, TRUNCATE, ALTER)
3.  **Output Clamp:** ป้องกันการดึงข้อมูลเกินขนาดด้วยการ inject `LIMIT`

---

## 📊 Evaluation & Development

### การสร้าง Dataset จาก Log
เมื่อใช้งานไปสักพัก ให้แปลง Log ที่ได้ Feedback ดีเป็นชุดทดสอบ:
```bash
python eval/build_dataset.py --log-file query_logs.jsonl --output eval/golden_dataset.json
```

### การรันวัดผล (Evaluation)
รันสคริปต์เพื่อวัด Success Rate เทียบกับ Dataset:
```bash
python eval/run_eval.py eval/golden_dataset.json
```

---

## 📂 โครงสร้างโปรเจกต์
```text
nlp_sql_project/
├── app.py                  # Main Application
├── sql_safety.py           # 🛡️ SQL Guardrails & Sanitization
├── schema_utils.py         # 🧠 Schema Summarization
├── rag_store.py            # 🔍 Persisted RAG Store (ChromaDB)
├── viz_recommender.py      # 📊 Auto-Chart Logic
├── eval/                   # 📈 Evaluation Scripts
│   ├── build_dataset.py
│   └── run_eval.py
├── thai_sql_examples.json  # Base Dataset
└── query_logs.jsonl        # Rich Event Logs
```

---

Made with ❤️ for Thai Developers.
