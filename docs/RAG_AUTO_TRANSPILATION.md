# RAG Auto-Transpilation Feature

## 🎯 ปัญหาที่แก้ไข

เมื่อใช้ RAG (Retrieval-Augmented Generation) สำหรับ few-shot learning ใน NLP-to-SQL system เราพบปัญหา:

**ปัญหา:** ตัวอย่าง SQL ใน `thai_sql_examples.json` มี syntax สำหรับหลาย dialects:
- 27 examples ไม่ระบุ dialect (default: SQLite)
- 25 examples เป็น MySQL syntax
- 0 examples สำหรับ PostgreSQL

**ผลกระทบ:**
- ถ้าเชื่อมต่อกับ **MySQL database** แต่ได้ SQLite examples → SQL จะใช้ไม่ได้
- ถ้าเชื่อมต่อกับ **PostgreSQL database** → ไม่ได้ examples เลย (หรือได้ syntax ที่ผิด)

## ✅ วิธีแก้ปัญหา: Auto-Transpilation

ระบบจะ**แปลง SQL examples ให้ตรงกับ target dialect อัตโนมัติ** ก่อนส่งให้ LLM

### การทำงาน (3 ขั้นตอน):

```
1. Query RAG Store
   ├─ ค้นหา examples ที่ใกล้เคียงกับคำถาม
   └─ Filter ตาม dialect ที่ต้องการ (ถ้ามี)

2. Fallback (ถ้าไม่เจอ)
   ├─ ถ้าไม่มี examples สำหรับ dialect นั้น
   └─ ค้นหาใหม่โดยไม่ filter dialect

3. Auto-Transpile
   ├─ แปลง SQL จาก source dialect → target dialect
   ├─ ใช้ sqlglot สำหรับการแปลง
   └─ Return SQL ที่แปลงแล้ว
```

### ตัวอย่างการแปลง:

#### MySQL → PostgreSQL

**Before (MySQL):**
```sql
SELECT
    YEAR(orderDate) as year,
    MONTH(orderDate) as month,
    SUM(total_price) as sales
FROM orders
GROUP BY YEAR(orderDate), MONTH(orderDate)
```

**After (PostgreSQL):**
```sql
SELECT
  EXTRACT(YEAR FROM orderDate) AS year,
  EXTRACT(MONTH FROM orderDate) AS month,
  SUM(total_price) AS sales
FROM orders
GROUP BY
  EXTRACT(YEAR FROM orderDate),
  EXTRACT(MONTH FROM orderDate)
```

#### SQLite → MySQL

**Before (SQLite):**
```sql
SELECT
    strftime('%Y', sale_date) as year,
    first_name || ' ' || last_name as full_name
FROM sales
```

**After (MySQL):**
```sql
SELECT
  YEAR(sale_date) AS year,
  CONCAT(first_name, ' ', last_name) AS full_name
FROM sales
```

---

## 🔧 การใช้งาน

### 1. Default Behavior (Auto-Transpile เปิดอยู่)

```python
from core.data.rag_store import create_example_store

store = create_example_store()

# ระบบจะแปลงอัตโนมัติ
examples = store.get_similar_examples(
    query="ยอดขายรวมทั้งหมด",
    top_k=3,
    dialect="postgresql",  # Target dialect
    auto_transpile=True    # ✅ Default: True
)

# ได้ SQL ที่เป็น PostgreSQL syntax แล้ว!
```

### 2. ปิด Auto-Transpile (ใช้ SQL ต้นฉบับ)

```python
examples = store.get_similar_examples(
    query="ยอดขายรวมทั้งหมด",
    top_k=3,
    dialect="mysql",
    auto_transpile=False  # ❌ ไม่แปลง
)

# ได้ SQL ต้นฉบับตามที่เก็บไว้ใน JSON
```

### 3. ใช้ผ่าน NLPEngine (Automatic)

```python
from core.services.engine import NLPEngine
from core.data.database import ConnectionManager

# เชื่อมต่อ PostgreSQL
engine, _ = ConnectionManager.get_db_engine("PostgreSQL", config)

# Query ผ่าน NLPEngine
nlp = NLPEngine()
result = await nlp.query_database(
    question="ยอดขายรวมทั้งหมด",
    engine=engine,
    dialect="postgresql"  # ระบบจะแปลง examples อัตโนมัติ!
)
```

**ระบบจะ:**
1. ดึง examples จาก RAG store
2. แปลงเป็น PostgreSQL syntax
3. ส่งให้ LLM เป็น few-shot examples
4. LLM จะเรียนรู้ PostgreSQL syntax จาก examples ที่แปลงแล้ว

---

## 🧪 ทดสอบการทำงาน

### รัน Test Script

```bash
# ทดสอบทั้งหมด
python scripts/test_rag_dialect_transpilation.py

# ทดสอบเฉพาะ comparison
python scripts/test_rag_dialect_transpilation.py --mode comparison

# ทดสอบเฉพาะ fallback mechanism
python scripts/test_rag_dialect_transpilation.py --mode fallback
```

### ตัวอย่าง Output

```
📝 Question: ยอดขายรวมปี 2004

🎯 Target Dialect: POSTGRESQL
----------------------------------------------------------------------

📊 Example 1:
   Question: ยอดขายรวมปี 2004
   Dialect: postgresql
   Distance: 0.0012
   SQL:
      SELECT
        SUM(od.quantityOrdered * od.priceEach) AS total_sales
      FROM orders AS o
        JOIN orderdetails AS od
          ON o.orderNumber = od.orderNumber
      WHERE
        EXTRACT(YEAR FROM o.orderDate) = 2004

✓ RAG: Transpiled example from MySQL to PostgreSQL
```

---

## 📊 Dialect Support Matrix

| Source Dialect | Target Dialect | Auto-Transpile | Status |
|----------------|----------------|----------------|---------|
| SQLite | MySQL | ✅ Yes | Supported |
| SQLite | PostgreSQL | ✅ Yes | Supported |
| MySQL | SQLite | ✅ Yes | Supported |
| MySQL | PostgreSQL | ✅ Yes | Supported |
| PostgreSQL | MySQL | ✅ Yes | Supported |
| PostgreSQL | SQLite | ✅ Yes | Supported |

---

## 🔍 Implementation Details

### Code Changes

**File:** `core/data/rag_store.py`

**Changes:**
1. เพิ่ม `auto_transpile` parameter ใน `get_similar_examples()`
2. เพิ่ม fallback mechanism เมื่อไม่เจอ examples ที่ตรง dialect
3. ใช้ `DialectTranspiler` แปลง SQL อัตโนมัติ
4. Log การแปลงเพื่อ debugging

**Key Logic:**
```python
# Fallback if no dialect-specific examples found
if dialect and len(results['documents'][0]) < top_k:
    results_fallback = self.collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        where=None  # No filter
    )
    results = results_fallback

# Auto-transpile
if auto_transpile and dialect and source_dialect != dialect:
    transpiled_sql = DialectTranspiler.transpile(
        sql, source_dialect, dialect, pretty=True
    )
    if transpiled_sql:
        sql = transpiled_sql
```

---

## ⚠️ Limitations

### 1. Complex Queries อาจแปลงไม่สมบูรณ์
- Window functions, CTEs, recursive queries อาจมีปัญหา
- **แก้:** ให้ LLM แก้ไขเอง (มี retry mechanism)

### 2. Dialect-Specific Features
- PostgreSQL `ARRAY[]`, MySQL `GROUP_CONCAT()` อาจแปลงไม่ได้
- **แก้:** ถ้าแปลงไม่ได้จะใช้ SQL ต้นฉบับและให้ LLM จัดการ

### 3. Performance Impact
- การแปลง SQL ใช้เวลาเพิ่มเติม (~10-50ms ต่อ example)
- **แก้:** ใช้ async ทำให้ไม่ block main thread

---

## 🎓 Best Practices

### 1. Pre-Populate Examples สำหรับ Dialect ที่ใช้บ่อย

```bash
# สร้าง PostgreSQL version ของ examples ล่วงหน้า
python scripts/migrate_rag_examples.py \
    --from-dialect MySQL \
    --to-dialect PostgreSQL \
    --output thai_sql_examples_postgresql.json
```

### 2. Disable Auto-Transpile สำหรับ Production (ถ้าต้องการ Performance)

```python
# ใน core/config.py เพิ่ม:
RAG_AUTO_TRANSPILE = False

# ใน rag_store.py:
auto_transpile = settings.RAG_AUTO_TRANSPILE
```

### 3. Monitor Transpilation Logs

```python
import logging
logging.basicConfig(level=logging.INFO)

# จะเห็น logs:
# ✓ RAG: Transpiled example from MySQL to PostgreSQL
# ⚠ RAG: Transpilation failed (mysql → postgresql): ...
```

---

## 🔄 ทางเลือกอื่น

### วิธีที่ 1: Pre-Process Examples (Recommended for Production)

```bash
# สร้าง examples แยกตาม dialect
python scripts/migrate_rag_examples.py \
    --from-dialect MySQL \
    --to-dialect PostgreSQL

# แก้ไข config ให้ใช้ไฟล์ที่ถูกต้อง
# ใน core/data/rag_store.py:
examples_path = f"thai_sql_examples_{dialect}.json"
```

**ข้อดี:**
- ✅ เร็วกว่า (ไม่ต้องแปลง runtime)
- ✅ ควบคุมคุณภาพได้ (review examples ก่อนใช้)

**ข้อเสีย:**
- ❌ ต้อง maintain หลายไฟล์
- ❌ เพิ่มไฟล์ใหม่ต้องแปลงทุก dialect

### วิธีที่ 2: LLM-Only (No Auto-Transpile)

```python
# ปิด auto-transpile และพึ่ง LLM
auto_transpile = False
```

**ข้อดี:**
- ✅ ง่าย (ไม่ต้องทำอะไร)
- ✅ LLM ฉลาดพอที่จะแปลงเองได้

**ข้อเสีย:**
- ❌ อาจได้ SQL ผิด dialect
- ❌ ต้องใช้ retry มากกว่า

---

## 📚 สรุป

**Auto-Transpilation ทำให้:**
1. ✅ ไม่ต้องเตรียม examples แยกตาม dialect
2. ✅ รองรับ multi-database ได้ทันที
3. ✅ LLM ได้เรียนรู้จาก examples ที่ถูก dialect
4. ✅ ลด error rate จากการใช้ผิด syntax

**เหมาะสำหรับ:**
- Development environment
- Proof-of-concept
- Applications ที่ต้อง support หลาย databases

**ไม่เหมาะสำหรับ:**
- Production ที่ต้องการ performance สูงสุด (ใช้ pre-process แทน)
- Queries ที่ซับซ้อนมาก (อาจแปลงไม่ถูกต้อง)
