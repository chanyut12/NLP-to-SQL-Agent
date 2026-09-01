# 🗺️ NLP-to-SQL Agent: Detailed Feature Roadmap

เอกสารนี้รวบรวมแผนการพัฒนาโปรเจกต์ NLP-to-SQL Agent อย่างละเอียด โดยแบ่งเป็นระยะ (Phases) พร้อมอธิบาย Business Value, แนวทางการนำไปสร้างจริง (Technical Implementation) และระดับความยาก เพื่อเป็นคู่มือสำหรับนักพัฒนาในการวางแผนการทำงาน

---

## ✅ Phase 0: สถานะปัจจุบัน (Current Capabilities)

*ระบบปัจจุบันสามารถทำงานได้ในระดับ Core Workflow แล้ว:*
- **Schema-Aware Generation:** AI เข้าใจโครงสร้าง Database ผ่านระบบ Schema RAG
- **Self-Correction Loop:** ตรวจสอบและแก้ไข SQL อัตโนมัติเมื่อเกิด Error ได้ถึงระดับหนึ่ง
- **Multi-Dialect Support:** รองรับ SQLite, MySQL, และ PostgreSQL
- **Security & Safety:** ป้องกัน SQL Injection และบล็อกคำสั่ง DML/DDL (Read-Only Mode)
- **Result Visualization:** ส่งต่อผลลัพธ์เป็น Chart.js 
- **Audit & History:** บันทึกประวัติและรับ Feedback ผ่าน UI

---

## 🚀 Phase 1: การเพิ่มความแม่นยำและ UX ระดับพื้นฐาน (High Priority)
*เป้าหมาย: ลด Hallucination, เพิ่มความมั่นใจให้ผู้ใช้งาน, และทำให้รู้สึกเหมือนคุยกับ Agent จริงๆ*

### 1.1 Business Glossary (Data Dictionary Integration)
* **Business Value:** บ่อยครั้งที่ชื่อคอลัมน์ใน Database ไม่สื่อความหมาย (เช่น `stt_cd`, `flg_act`) การมีคำอธิบายภาษาไทยจะช่วยให้ LLM แมปคำถามของ User เข้ากับคอลัมน์ได้แม่นยำขึ้น ลดการสร้าง SQL ผิดพลาด
* **Technical Implementation:**
  1. สร้างไฟล์ `glossary.json` หรือตารางในฐานข้อมูลเพื่อเก็บคำอธิบาย (Description), คำพ้องความหมาย (Synonyms), และประเภทข้อมูลทางธุรกิจ (เช่น "ยอดขายสุทธิ", "สถานะลูกค้า") ของแต่ละคอลัมน์
  2. แก้ไข `core/domain/schema_utils.py` เพื่อดึงข้อมูล Glossary นี้ไปผสมกับ DDL Schema ดั้งเดิม
  3. ส่ง Schema + Glossary เข้าไปใน System Prompt เพื่อให้ LLM ใช้ในการตัดสินใจ
* **Complexity:** 🟡 ปานกลาง (Medium)

### 1.2 Query Preview, Explanation & Dry Run
* **Business Value:** ป้องกันปัญหา User ดึงข้อมูลมหาศาลโดยไม่ตั้งใจ และสร้างความโปร่งใส (Trust) ให้ระบบ โดยอธิบายให้ User เข้าใจว่าระบบกำลังจะทำอะไรก่อนที่จะทำจริง
* **Technical Implementation:**
  1. **API Split:** แยก Endpoint `/api/chat` ออกเป็น 2 ขั้นตอน: `/api/generate_sql` และ `/api/execute_sql`
  2. **Data Lineage:** เมื่อได้ SQL มา ให้ใช้ LLM อีกตัว (หรือ Prompt พิเศษ) สรุป SQL เป็นภาษาไทย (เช่น "ดึงข้อมูลยอดขายรวม แยกตามเดือน ในปี 2023")
  3. **Dry Run:** นำ SQL ไปรันผ่านคำสั่ง `EXPLAIN` (สำหรับ MySQL/Postgres) เพื่อตรวจสอบ Syntax และหา Estimated Cost โดยที่ยังไม่ดึงข้อมูลจริง
  4. **UI Update:** แสดง SQL, คำอธิบายภาษาไทย, และปุ่ม "ยืนยันการรัน" หรือ "แก้ไขคำสั่ง" ให้ User ดูบน Web
* **Complexity:** 🔴 สูง (High) - ต้องปรับแก้ทั้ง Flow ของ Backend และ Frontend

### 1.3 Multi-turn Conversational UX
* **Business Value:** ผู้ใช้ไม่จำเป็นต้องพิมพ์คำถามยาวๆ ใหม่ทุกครั้ง สามารถสั่งงานแบบต่อเนื่องได้ เช่น "ขอเปลี่ยนเป็นกราฟเส้น", "เอาเฉพาะของสาขากรุงเทพ"
* **Technical Implementation:**
  1. **Session Management:** สร้างระบบเก็บ History ของแชท (อาจใช้ `history_service.py` หรือเก็บใน Frontend State)
  2. **Prompt Engineering:** เปลี่ยนจากการส่งแค่คำถามเดียว (Single User Message) เป็นการส่ง Chat History (Array of messages) เข้าไปใน `engine.py` 
  3. **Context Awareness:** ปรับ System Prompt ให้ LLM รู้ว่า "คุณสามารถนำ SQL ล่าสุดมาแก้ตามคำสั่งใหม่ได้"
* **Complexity:** 🔴 สูง (High)

---

## 🏗️ Phase 2: ความเสถียร, การบำรุงรักษา และการจัดการข้อผิดพลาด (Medium Priority)
*เป้าหมาย: ทำให้ระบบดูแลรักษาง่ายขึ้น และจัดการ Error ได้อย่างนุ่มนวล*

### 2.1 Prompt Templating & Versioning
* **Business Value:** ง่ายต่อการอัปเดต Prompt โดยไม่ต้องแก้โค้ด Python โดยตรง และสามารถทำ A/B Testing ได้
* **Technical Implementation:**
  1. ย้าย System Prompts ทั้งหมดออกจาก `core/services/engine.py` ไปไว้ในโฟลเดอร์ `core/prompts/` (อาจบันทึกเป็นไฟล์ `.yaml` หรือ `.j2` Jinja templates)
  2. สร้างฟังก์ชันโหลด Prompt แบบ Dynamic และสามารถเลือกเวอร์ชันของ Prompt จาก `.env` ได้
* **Complexity:** 🟢 ต่ำ (Low)

### 2.2 Natural Language Error Explanation
* **Business Value:** User ที่ไม่ใช่โปรแกรมเมอร์จะตกใจถ้าเห็น Error แบบ `SQLSTATE[42S22]: Column not found: 1054 Unknown column 'xyz' in 'field list'` ระบบควรแปลเป็นภาษาคนที่เข้าใจง่าย
* **Technical Implementation:**
  1. เมื่อฟังก์ชันใน `engine.py` พยายามทำ Self-correction จนครบจำนวนรอบแล้วแต่ยังพังอยู่ ให้ดักจับ Exception นั้น
  2. ส่ง Error String + คำถามของ User ให้ LLM ตัวเล็ก (เช่น gpt-4o-mini หรือ qwen) พร้อมคำสั่ง: "แปล Error นี้เป็นภาษาไทยให้ผู้ใช้งานทั่วไปเข้าใจ พร้อมแนะนำวิธีแก้คำถาม"
  3. ส่งกลับไปแสดงที่หน้า UI แทนข้อความ Error ดิบๆ
* **Complexity:** 🟡 ปานกลาง (Medium)

### 2.3 Query Timeout & Rate Limiting
* **Business Value:** ป้องกันระบบล่มจากการรันคำสั่งที่นานเกินไป หรือจากการถูกรัว API (Abuse)
* **Technical Implementation:**
  1. **DB Timeout:** คอนฟิก `connect_args` ใน SQLAlchemy ให้มี Execution Timeout (เช่น `{'options': '-c statement_timeout=30000'}` สำหรับ Postgres)
  2. **Rate Limit:** ใช้ไลบรารี `slowapi` ใน FastAPI เพื่อจำกัดจำนวน Request เช่น อนุญาต 10 query / นาที / IP
* **Complexity:** 🟢 ต่ำ (Low)

---

## 🔮 Phase 3: ฟีเจอร์ระดับองค์กรขั้นสูง (Advanced / Future Scope)
*เป้าหมาย: ขยายขีดความสามารถเพื่อรองรับโครงสร้างองค์กรขนาดใหญ่*

### 3.1 Dynamic Schema Sync & Refresh
* **Description:** ระบบดึง Metadata อัปเดตตารางใหม่ๆ เข้าสู่ Vector DB อัตโนมัติทุกๆ เที่ยงคืน หรือเมื่อมีการกดปุ่ม "Refresh Schema" ไม่ต้องมารันสคริปต์แบบ Manual
* **Implementation:** ตั้ง Cronjob หรือใช้ Celery / Background Tasks ใน FastAPI 

### 3.2 Row/Column-Level Access Control (RLS)
* **Description:** จำแนกสิทธิ์การเข้าถึงข้อมูลตาม User (เช่น ฝ่ายขายดูได้เฉพาะยอดขายภูมิภาคตัวเอง)
* **Implementation:** ผูก User Identity เข้ากับ Query โดยระบบจะต้องแปลง SQL ให้มี `WHERE region = 'user_region'` เสมอ หรือใช้ RLS policy ของ Database 

### 3.3 System Metrics & Admin Dashboard
* **Description:** หน้าจอสำหรับ Admin เพื่อติดตามการใช้งาน
* **Implementation:** เก็บสถิติ Token Usage, Latency, API Error Rate และส่งข้อมูลไปที่ Prometheus / Grafana หรือทำหน้า Dashboard ง่ายๆ จาก `query_logs.jsonl`

### 3.4 Integration & API Webhooks
* **Description:** การนำ Agent ตัวนี้ไปเชื่อมกับ Slack, Microsoft Teams, หรือฝัง (Embed) ลงใน BI Tools ขององค์กร
* **Implementation:** สร้าง REST API endpoint แยกที่รองรับ API Key / OAuth2 แบบไม่มี State (Stateless)
