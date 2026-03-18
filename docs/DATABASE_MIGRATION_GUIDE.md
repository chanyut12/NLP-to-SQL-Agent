# คู่มือการเปลี่ยน Database Engine

เอกสารนี้อธิบายวิธีการย้าย database จาก engine หนึ่งไปอีก engine หนึ่ง (เช่น SQLite → PostgreSQL, MySQL → PostgreSQL ฯลฯ)

## 🎯 ภาพรวม

ระบบรองรับ 3 database engines:
- **SQLite** (file-based, เหมาะสำหรับ development)
- **MySQL** (เหมาะสำหรับ production ขนาดกลาง)
- **PostgreSQL** (เหมาะสำหรับ production ขนาดใหญ่, รองรับ feature สูง)

## 📋 ขั้นตอนการ Migration (แนะนำ)

### 1️⃣ เตรียม Database ปลายทาง

#### สำหรับ PostgreSQL:
```bash
# สร้าง database
createdb -U postgres sales_db

# หรือใช้ SQL
psql -U postgres
CREATE DATABASE sales_db;
\q
```

#### สำหรับ MySQL:
```bash
mysql -u root -p
CREATE DATABASE sales_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
EXIT;
```

### 2️⃣ Install Dependencies

ตรวจสอบว่าติดตั้ง driver แล้ว:
```bash
pip install -r requirements.txt

# หรือติดตั้งแยก
pip install psycopg2-binary  # PostgreSQL
pip install pymysql           # MySQL
```

### 3️⃣ ทดสอบการเชื่อมต่อ

```bash
# สำหรับ PostgreSQL
python scripts/test_postgres_connection.py

# สำหรับ MySQL (สร้างไฟล์ test_mysql_connection.py ตามแบบเดียวกัน)
```

### 4️⃣ Migrate Schema และ Data

```python
from core.utils.db_migration import migrate_sqlite_to_postgres

# ตัวอย่าง: SQLite → PostgreSQL
result = migrate_sqlite_to_postgres(
    sqlite_path="example_sales.db",
    postgres_config={
        "user": "postgres",
        "password": "yourpassword",
        "host": "localhost",
        "port": 5432,
        "database": "sales_db"
    },
    tables=["sales", "customers", "products"]  # ระบุตารางที่ต้องการย้าย
)

print(f"Schema: {result['schema']}")
print(f"Data: {result['data']}")
```

**ฟังก์ชันที่มี:**
- `migrate_sqlite_to_mysql()` - SQLite → MySQL
- `migrate_sqlite_to_postgres()` - SQLite → PostgreSQL
- `migrate_mysql_to_postgres()` - MySQL → PostgreSQL

### 5️⃣ Migrate RAG Examples

```bash
# แปลง SQL examples จาก SQLite → PostgreSQL
python scripts/migrate_rag_examples.py \
    --input thai_sql_examples.json \
    --output thai_sql_examples_postgresql.json \
    --from-dialect SQLite \
    --to-dialect PostgreSQL \
    --validate
```

### 6️⃣ อัพเดท Connection Config

**วิธีที่ 1: ใช้ Environment Variables (แนะนำ)**
```bash
# สร้างไฟล์ .env
cat > .env << EOF
# Database Configuration
DB_TYPE=PostgreSQL
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=yourpassword
DB_NAME=sales_db
EOF
```

**วิธีที่ 2: ปรับใน Frontend**

แก้ไขไฟล์ `web/index.html` หรือ UI ให้ผู้ใช้เลือก database type:

```javascript
// ตัวอย่างใน web/js/modules/api.js
async function connectDatabase(dbType, dbConfig) {
    const response = await fetch('/api/connect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            db_type: dbType,  // "SQLite", "MySQL", "PostgreSQL"
            db_config: dbConfig
        })
    });
    return response.json();
}
```

### 7️⃣ ทดสอบ Query

```python
from core.services.engine import NLPEngine
from core.data.database import ConnectionManager

# เชื่อมต่อ PostgreSQL
engine, error = ConnectionManager.get_db_engine(
    "PostgreSQL",
    {
        "user": "postgres",
        "password": "yourpassword",
        "host": "localhost",
        "port": 5432,
        "database": "sales_db"
    }
)

if error:
    print(f"Error: {error}")
else:
    # ทดสอบ query
    nlp = NLPEngine()
    result = await nlp.query_database(
        question="แสดงยอดขายทั้งหมด",
        engine=engine,
        dialect="postgresql"  # ⚠️ ต้องระบุ dialect ให้ถูกต้อง
    )
    print(result)
```

---

## 🔍 ปัญหาที่พบบ่อยและวิธีแก้

### 1. SQL Syntax ต่างกัน

**ปัญหา:** MySQL ใช้ `CONCAT()`, PostgreSQL ใช้ `||`

**วิธีแก้:**
```python
from core.utils.dialect_transpiler import DialectTranspiler

# แปลง SQL อัตโนมัติ
sql = "SELECT CONCAT(first_name, ' ', last_name) FROM users"
pg_sql = DialectTranspiler.transpile(sql, "MySQL", "PostgreSQL")
print(pg_sql)
# Output: SELECT first_name || ' ' || last_name FROM users
```

### 2. Date Functions ต่างกัน

| ฟังก์ชัน | MySQL | PostgreSQL | SQLite |
|---------|-------|------------|--------|
| ดึงปี | `YEAR(date)` | `EXTRACT(YEAR FROM date)` | `strftime('%Y', date)` |
| ดึงเดือน | `MONTH(date)` | `EXTRACT(MONTH FROM date)` | `strftime('%m', date)` |
| วันนี้ | `CURDATE()` | `CURRENT_DATE` | `DATE('now')` |

**วิธีแก้:** ระบบจะแปลงอัตโนมัติผ่าน `DialectTranspiler`

### 3. Connection Error

```
psycopg2.OperationalError: could not connect to server
```

**วิธีแก้:**
```bash
# 1. ตรวจสอบว่า PostgreSQL ทำงานอยู่
pg_isready -h localhost -p 5432

# 2. ตรวจสอบ authentication
psql -h localhost -U postgres -d sales_db

# 3. แก้ไข pg_hba.conf (ถ้าจำเป็น)
# เพิ่มบรรทัดนี้ใน /var/lib/postgresql/data/pg_hba.conf
host    all             all             0.0.0.0/0            md5
```

### 4. Driver ไม่ได้ติดตั้ง

```
ModuleNotFoundError: No module named 'psycopg2'
```

**วิธีแก้:**
```bash
pip install psycopg2-binary
```

### 5. Schema ไม่ตรงกัน

**ปัญหา:** ตารางใน database ใหม่มีชื่อหรือ column ต่างจากเดิม

**วิธีแก้:**
```python
# ใช้ Schema RAG re-index
from core.data.schema_rag import create_schema_rag

schema_rag = create_schema_rag()
schema_rag.index_schema_from_db(new_engine)  # Index schema ใหม่
```

---

## 🚀 Best Practices

### 1. ทดสอบก่อน Migrate Production

```bash
# สร้าง test database
createdb -U postgres sales_db_test

# Migrate ไปยัง test DB ก่อน
python scripts/db_migration.py --target test

# ทดสอบ query
python scripts/test_postgres_connection.py
```

### 2. Backup ก่อน Migrate

```bash
# SQLite
cp example_sales.db example_sales.db.backup

# MySQL
mysqldump -u root -p sales_db > sales_db_backup.sql

# PostgreSQL
pg_dump -U postgres sales_db > sales_db_backup.sql
```

### 3. ใช้ Transaction สำหรับ Data Migration

```python
# Migration script จะใช้ batch mode อัตโนมัติ
# แต่ถ้าต้องการควบคุมเอง:
with target_engine.begin() as conn:
    # Migration operations
    conn.execute(...)
    # Auto-rollback if error
```

### 4. Monitor Performance

```python
import time

start = time.time()
result = migrate_sqlite_to_postgres(...)
elapsed = time.time() - start

print(f"Migration took {elapsed:.2f} seconds")
print(f"Rows per second: {result['data']['sales']['rows_migrated'] / elapsed:.0f}")
```

---

## 📊 Performance Comparison

| Engine | Recommended Use Case | Pros | Cons |
|--------|---------------------|------|------|
| **SQLite** | Development, Small datasets (<1GB) | ✅ ไม่ต้อง setup server<br>✅ เร็วสำหรับ read | ❌ ไม่รองรับ concurrent writes<br>❌ ไม่เหมาะสำหรับ production |
| **MySQL** | Production (Medium scale) | ✅ Mature ecosystem<br>✅ Good performance | ❌ Setup ซับซ้อนกว่า SQLite<br>❌ ค่า default ไม่เหมาะสำหรับ ACID |
| **PostgreSQL** | Production (Large scale) | ✅ รองรับ ACID เต็มรูปแบบ<br>✅ Advanced features (JSON, Full-text search)<br>✅ Better for complex queries | ❌ ใช้ memory มากกว่า MySQL<br>❌ Setup ซับซ้อนที่สุด |

---

## 🔧 Advanced: Custom Migration

ถ้าต้องการควบคุม migration เอง:

```python
from sqlalchemy import create_engine, MetaData, Table
import pandas as pd

# 1. Connect to both databases
source = create_engine("sqlite:///old.db")
target = create_engine("postgresql://user:pass@localhost/new_db")

# 2. Reflect schema
metadata = MetaData()
metadata.reflect(bind=source)

# 3. Create tables in target
metadata.create_all(target)

# 4. Migrate data table by table
for table_name in metadata.tables.keys():
    df = pd.read_sql_table(table_name, source)

    # ⚠️ Custom transformation (ถ้าจำเป็น)
    if table_name == "sales":
        df['created_at'] = pd.to_datetime(df['created_at'])

    df.to_sql(table_name, target, if_exists='append', index=False)
    print(f"✓ Migrated {table_name}: {len(df)} rows")
```

---

## 📞 ติดปัญหา?

1. ตรวจสอบ logs ที่ `query_logs.jsonl`
2. รัน validation script: `python scripts/migrate_rag_examples.py --validate`
3. ดู error messages ใน console output
4. ถ้ายังแก้ไม่ได้ ให้ rollback ไปใช้ database เดิมและ investigate ต่อ

---

## 🎓 สรุป

การเปลี่ยน database engine ใน NLP-to-SQL system ต้องจัดการ:

1. ✅ **Schema & Data Migration** - ใช้ `core/utils/db_migration.py`
2. ✅ **SQL Dialect Conversion** - ใช้ `core/utils/dialect_transpiler.py`
3. ✅ **RAG Examples Update** - ใช้ `scripts/migrate_rag_examples.py`
4. ✅ **Connection Configuration** - อัพเดท environment variables หรือ UI
5. ✅ **Testing** - ใช้ `scripts/test_postgres_connection.py`

**ระบบได้ออกแบบให้รองรับ multi-database ตั้งแต่แรก** ดังนั้นการเปลี่ยน engine ทำได้ง่ายโดยใช้ tools ที่มีให้!
