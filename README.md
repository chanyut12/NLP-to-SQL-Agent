# 🇹🇭 Thai NLP-to-SQL Agent (Local LLM)

โปรเจกต์นี้คือ **AI Data Analyst** อัจฉริยะที่ช่วยให้คุณสอบถามข้อมูลจาก Database ได้ด้วย **"ภาษาไทยธรรมชาติ"** โดยไม่ต้องมีความรู้ SQL ระบบจะแปลงคำถามภาษาไทยของคุณเป็น SQL Query, ดึงข้อมูลจากฐานข้อมูล, และนำเสนอเป็นกราฟให้อัตโนมัติ ทั้งหมดทำงานบนเครื่องคุณ 100% (Local Privacy)

![Streamlit UI Example](https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=Streamlit&logoColor=white) ![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white) ![Ollama](https://img.shields.io/badge/Ollama-Local_LLM-000000?style=for-the-badge) ![LangChain](https://img.shields.io/badge/LangChain-🦜️🔗-319795?style=for-the-badge)

---

## 🌟 จุดเด่น (Key Features)

-   🗣️ **Thai Language Centric:** ออกแบบมาเพื่อเข้าใจบริบทภาษาไทยโดยเฉพาะ ผ่าน Advanced Prompt Engineering + RAG-based Few-shot Learning
-   🏠 **100% Local Execution:** ใช้โมเดล **Qwen2.5-Coder:7b** ผ่าน Ollama ข้อมูลของคุณจะไม่ออกจากเครื่อง (Privacy & Security)
-   🔌 **Multi-Database Support:** รองรับ SQLite, MySQL, PostgreSQL พร้อม UI สำหรับเปลี่ยน Database โดยไม่ต้องแก้โค้ด
-   🧠 **Smart Schema Mapping:** ระบบแมพคำภาษาไทยเข้ากับ Column Name อัตโนมัติ + Dynamic Schema Detection
-   🔄 **Self-Correction Loop:** AI แก้ไข SQL อัตโนมัติเมื่อเจอ Error (ลด Error Rate 20-30%)
-   📊 **Persistent Visualization:** ระบบจดจำผลลัพธ์ (Session State) ทำให้เปลี่ยนรูปแบบกราฟได้โดยไม่ต้อง Query ใหม่
-   🎯 **RAG-powered Examples:** ดึงตัวอย่าง Thai→SQL ที่เกี่ยวข้องจาก Vector Store (ChromaDB) แบบ Dynamic

---

## 🛠️ Tech Stack

-   **Frontend:** [Streamlit](https://streamlit.io/) (Interactive Web UI)
-   **LLM Orchestration:** [LangChain](https://www.langchain.com/) (LCEL Architecture)
-   **Model:** Qwen2.5-Coder:7b/14b (Running on Ollama)
-   **Database:** SQLite, MySQL, PostgreSQL (via SQLAlchemy)
-   **Vector Store:** ChromaDB (for RAG-based few-shot)
-   **Embeddings:** Sentence-Transformers (Multilingual support)
-   **Data Processing:** Pandas

---

## ⚙️ การติดตั้ง (Installation)

### 1. สิ่งที่ต้องมี (Prerequisites)
-   **Python 3.10+**
-   **[Ollama](https://ollama.com/)** (สำหรับรัน Local LLM)

### 2. เตรียม Model
เปิด Terminal และรันคำสั่งนี้เพื่อดาวน์โหลด Model (ทำครั้งเดียว):
```bash
ollama pull qwen2.5-coder:7b
```

### 3. Clone & Setup
```bash
# 1. Clone หรือดาวน์โหลดโปรเจกต์นี้
git clone <your-repo-url>
cd nlp_sql_project

# 2. สร้าง Virtual Environment
python -m venv venv
# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

# 3. ติดตั้ง Library ที่จำเป็น
pip install -r requirements.txt
```

### 4. สร้าง Mock Database (Optional)
เรามีสคริปต์สำหรับสร้างข้อมูลจำลอง (Sales Transaction) ให้ทดสอบทันที:
```bash
python setup_db.py
```
*(เมื่อรันเสร็จ คุณจะได้ไฟล์ `local_database.db` ในโฟลเดอร์)*

หรือจะข้ามขั้นตอนนี้และเชื่อมต่อกับ **Database จริงของคุณ** (MySQL, PostgreSQL) ได้เลย

---

## ▶️ วิธีใช้งาน (Usage)

### Quick Start (SQLite - ไม่ต้อง Setup Database)

1.  **Start Ollama:**
    ```bash
    ollama serve
    ```

2.  **Start App:**
    ```bash
    streamlit run app.py
    ```

3.  **เชื่อมต่อ Database:**
    - ที่ Sidebar เลือก **SQLite**
    - Database File: `local_database.db` (ใช้ mock data ที่สร้างไว้)
    - กดปุ่ม **🔗 Connect to Database**

4.  **ลองถามคำถาม:**
    -   *"ยอดขายรวมทั้งหมดของปีนี้แบ่งตามเดือน"*
    -   *"ลูกค้าคนไหนมียอดซื้อเยอะที่สุด 5 อันดับแรก"*

---

### เชื่อมต่อ MySQL (XAMPP / Standalone)

#### สำหรับ XAMPP:
1.  **Start XAMPP:**
    - เปิด XAMPP Control Panel
    - กด **Start** ที่ MySQL (รอจนสถานะเป็นสีเขียว)

2.  **เชื่อมต่อใน App:**
    ```
    Database Type: MySQL
    Host: localhost
    Port: 3306
    Username: root
    Password: (ปล่อยว่างถ้าไม่ได้ตั้ง)
    Database Name: ชื่อ database ของคุณ (เช่น classicmodels)
    ```

3.  กดปุ่ม **🔗 Connect to Database**

#### สำหรับ MySQL Standalone:
```bash
# Mac
brew services start mysql

# Linux
sudo service mysql start

# Windows
เปิด MySQL Service จาก Services.msc
```

---

### เชื่อมต่อ PostgreSQL

1.  **Start PostgreSQL:**
    ```bash
    # Mac
    brew services start postgresql
    
    # Linux
    sudo service postgresql start
    ```

2.  **เชื่อมต่อใน App:**
    ```
    Database Type: PostgreSQL
    Host: localhost
    Port: 5432
    Username: postgres
    Password: your_password
    Database Name: your_database
    ```

---

### Driver Requirements

| Database | Driver | คำสั่งติดตั้ง |
|----------|--------|---------------|
| SQLite | (Built-in) | - |
| MySQL | pymysql | `pip install pymysql` |
| PostgreSQL | psycopg2 | `pip install psycopg2-binary` |

---

## 🔧 การปรับแต่ง (Configuration)

### เปลี่ยน Database
ใช้ **UI ใน Sidebar** สำหรับเปลี่ยน Database โดยไม่ต้องแก้โค้ด:

1. เลือก Database Type (SQLite / MySQL / PostgreSQL)
2. กรอกข้อมูลการเชื่อมต่อ
3. กดปุ่ม **🔗 Connect to Database**

ระบบจะ:
- ตรวจสอบ Schema อัตโนมัติ
- แสดง Tables และ Columns ที่มีจริง
- ปรับ AI Prompt ให้เหมาะกับ Database นั้นๆ

### เพิ่มตัวอย่าง Thai→SQL
เพิ่มตัวอย่างใหม่ใน `thai_sql_examples.json`:

```json
{
  "question": "คำถามภาษาไทยใหม่",
  "sql": "SELECT ... FROM ...",
  "category": "aggregation"
}
```

ระบบจะดึงตัวอย่างที่เกี่ยวข้องมาใช้อัตโนมัติ (RAG-based)

### ปรับแต่งความเข้าใจภาษาไทย
แก้ไขตัวแปร `template` ใน `app.py` (ฟังก์ชัน `get_llm_chain()`):

```python
### Thai-to-English Schema Mapping:
- "กำไรสุทธิ" -> (revenue - cost)
- "ภาคอีสาน" -> region = 'Northeast'
...
```

---

## 📂 โครงสร้างโปรเจกต์

```text
nlp_sql_project/
├── app.py                    # 🧠 หัวใจหลัก: Streamlit UI + LangChain Logic
├── rag_store.py              # 🔍 RAG System: ChromaDB + Vector Search
├── thai_sql_examples.json    # 📚 Dataset: 25 Thai→SQL examples
├── local_database.db         # 💽 Mock Database (SQLite)
├── setup_db.py               # ⚙️ สคริปต์สร้าง Mock Data
├── requirements.txt          # 📦 Dependencies
├── TUNING_GUIDE.md           # 📖 LLM Tuning Guide (Advanced)
└── README.md                 # 📖 คู่มือเล่มนี้
```

---

## 🤝 Troubleshooting

### ❌ Connection Errors

**`ConnectError: [Errno 61] Connection refused`**
- **สาเหตุ:** Ollama server ไม่ได้ทำงาน
- **แก้ไข:** เปิด Terminal รัน `ollama serve` หรือเปิด Ollama Desktop App

**`Connection refused` (Database)**
- **สาเหตุ:** Database Service ไม่ได้ Start
- **แก้ไข:**
  - **XAMPP:** เปิด XAMPP Control Panel → Start MySQL
  - **MySQL:** `brew services start mysql` (Mac) หรือ `sudo service mysql start` (Linux)
  - **PostgreSQL:** `brew services start postgresql` (Mac)

### 🔧 Other Issues

**`ModuleNotFoundError`**
- รัน `pip install -r requirements.txt` ใหม่

**กราฟไม่ขึ้น**
- ลองถามคำถามที่ผลลัพธ์เป็นหลายแถว (เช่น "ยอดขายแต่ละเดือน")

**AI เขียน SQL ผิด**
- ลองเพิ่มตัวอย่างใน `thai_sql_examples.json`
- อ่าน `TUNING_GUIDE.md` สำหรับวิธีปรับปรุง

---

## 📚 เอกสารเพิ่มเติม

- **[TUNING_GUIDE.md](TUNING_GUIDE.md)** - คู่มือการ Tune LLM แบบละเอียด (Prompt Engineering, RAG, Fine-tuning)

---

Made with ❤️ for Thai Developers.
