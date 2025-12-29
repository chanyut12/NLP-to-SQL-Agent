# 🇹🇭 Thai NLP-to-SQL Agent (Local LLM)

โปรเจกต์นี้คือ **AI Data Analyst** อัจฉริยะที่ช่วยให้คุณสอบถามข้อมูลจาก Database ได้ด้วย **"ภาษาไทยธรรมชาติ"** โดยไม่ต้องมีความรู้ SQL ระบบจะแปลงคำถามภาษาไทยของคุณเป็น SQL Query, ดึงข้อมูลจากฐานข้อมูล, และนำเสนอเป็นกราฟให้อัตโนมัติ ทั้งหมดทำงานบนเครื่องคุณ 100% (Local Privacy)

![Streamlit UI Example](https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=Streamlit&logoColor=white) ![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white) ![Ollama](https://img.shields.io/badge/Ollama-Local_LLM-000000?style=for-the-badge) ![LangChain](https://img.shields.io/badge/LangChain-🦜️🔗-319795?style=for-the-badge)

---

## 🌟 จุดเด่น (Key Features)

-   🗣️ **Thai Language Centric:** ออกแบบมาเพื่อเข้าใจบริบทภาษาไทยโดยเฉพาะ (เช่น "ยอดขาย", "ลูกค้า", "ไตรมาส") ผ่าน Prompt Engineering
-   🏠 **100% Local Execution:** ใช้โมเดล **Qwen2.5-Coder:7b** ผ่าน Ollama ข้อมูลของคุณจะไม่ออกจากเครื่อง (Privacy & Security)
-   🧠 **Smart Schema Mapping:** ระบบสามารถแมพคำภาษาไทยเข้ากับ Column Name ภาษาอังกฤษใน Database ได้อย่างแม่นยำ
-   📊 **Persistent Visualization:** ระบบจดจำผลลัพธ์การค้นหาล่าสุด (Session State) ทำให้คุณสามารถเปลี่ยนรูปแบบกราฟ (Bar/Line/Area) ไปมาได้โดยไม่ต้อง Query ใหม่
-   🛡️ **Self-Correction SQL:** มี Logic ในการ Clean SQL (ตัด Markdown/Code Fences ออก) เพื่อลด Error เวลา Execute

---

## 🛠️ Tech Stack

-   **Frontend:** [Streamlit](https://streamlit.io/) (Interactive Web UI)
-   **LLM Orchestration:** [LangChain](https://www.langchain.com/) (LCEL Architecture)
-   **Model:** Qwen2.5-Coder:7b (Running on Ollama)
-   **Database:** SQLite (SQLAlchemy Connectable)
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

### 4. สร้าง Mock Database
เรามีสคริปต์สำหรับสร้างข้อมูลจำลอง (Sales Transaction) ให้ทดสอบทันที:
```bash
python setup_db.py
```
*(เมื่อรันเสร็จ คุณจะได้ไฟล์ `local_database.db` ในโฟลเดอร์)*

---

## ▶️ วิธีใช้งาน (Usage)

1.  **Start App:**
    ```bash
    streamlit run app.py
    ```

2.  **Access:**
    Browser จะเปิดขึ้นที่ `http://localhost:8501`

3.  **Example Questions (ลองถามดู):**
    -   *"ยอดขายรวมทั้งหมดของปีนี้แบ่งตามเดือน"*
    -   *"ลูกค้าคนไหนมียอดซื้อเยอะที่สุด 5 อันดับแรก"*
    -   *"แสดงสัดส่วนยอดขายแยกตามหมวดหมู่สินค้า"*
    -   *"ในเดือนธันวาคม มีลูกค้ามาช้อปปิ้งกี่คน"*

---

## 🔧 การปรับแต่ง (Configuration)

### ปรับแต่งความเข้าใจภาษาไทย (Prompt Tuning)
หากต้องการให้ AI เข้าใจคำศัพท์เฉพาะทางในองค์กรคุณมากขึ้น ให้แก้ไขตัวแปร `template` ในไฟล์ `app.py`:

```python
template = """
...
Schema Mapping Examples:
  - "กำไรสุทธิ" -> (revenue - cost)
  - "ภาคอีสาน" -> region = 'Northeast'
  - "สินค้าขายดี" -> ORDER BY total_sales DESC LIMIT 10
...
"""
```

### เปลี่ยน Database
แก้ `db_path` ใน `app.py` เพื่อต่อกับ Database จริงของคุณ (PostgreSQL, MySQL, etc.):

```python
# ตัวอย่าง PostgreSQL
db_path = "postgresql+psycopg2://user:pass@localhost:5432/mydatabase"
```

---

## 📂 โครงสร้างโปรเจกต์

```text
nlp_sql_project/
├── app.py               # 🧠 หัวใจหลัก: Streamlit UI + LangChain Logic
├── local_database.db    # 💽 ฐานข้อมูล SQLite (สร้างจาก setup_db.py)
├── setup_db.py          # ⚙️ สคริปต์สร้าง Mock Data
├── requirements.txt     # 📦 รายชื่อ Library
└── README.md            # 📖 คู่มือเล่มนี้
```

---

## 🤝 Troubleshooting

-   **Error `ModuleNotFoundError: No module named 'langchain.chains'`**:
    -   โปรเจกต์นี้ใช้ LangChain แบบ Modern (LCEL) แล้ว ไม่ควรเจอ Error นี้ หากเจอให้ลอง `pip install -r requirements.txt` ใหม่
-   **กราฟไม่ขึ้น**:
    -   ลองถามคำถามที่ผลลัพธ์เป็นกลุ่มข้อมูล (Aggregate) เช่น "ยอดขายรวม...", "จำนวน..." หาก Query ออกมาแค่ 1 แถว กราฟอาจจะไม่แสดงผล

---

Made with ❤️ for Thai Developers.
