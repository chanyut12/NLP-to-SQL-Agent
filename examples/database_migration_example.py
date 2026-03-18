"""
ตัวอย่าง: ย้าย Database จาก MySQL → PostgreSQL

สมมติคุณมี Sales Database บน MySQL และต้องการย้ายไป PostgreSQL
ระบบจะทำงานอัตโนมัติโดยไม่ต้องแก้ code
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.services.engine import NLPEngine
from core.data.database import ConnectionManager


async def demo_database_migration():
    """
    แสดงการทำงานเมื่อย้าย database จาก engine หนึ่งไปอีก engine
    """

    print("=" * 70)
    print("Database Migration Demo: MySQL → PostgreSQL")
    print("=" * 70)

    # สร้าง NLPEngine (ใช้ตัวเดียวสำหรับทั้ง 2 database)
    nlp = NLPEngine()

    question = "ยอดขายรวมปี 2004"

    # ========================================================================
    # Scenario 1: เชื่อมต่อกับ MySQL (database เดิม)
    # ========================================================================
    print("\n📊 Scenario 1: MySQL Database")
    print("-" * 70)

    mysql_config = {
        "user": "root",
        "password": "password",
        "host": "localhost",
        "port": 3306,
        "database": "sales_db"
    }

    mysql_engine, error = ConnectionManager.get_db_engine("MySQL", mysql_config)

    if error:
        print(f"❌ MySQL connection failed: {error}")
        print("   (สำหรับ demo นี้ ถ้าไม่มี MySQL ก็ข้ามไปได้)")
    else:
        print(f"✅ Connected to MySQL database")

        # Query ผ่าน MySQL
        sql, data, error, retries, viz = await nlp.query_database(
            question=question,
            engine=mysql_engine,
            dialect="mysql"  # ระบุว่าเป็น MySQL
        )

        print(f"\n🔍 Question: {question}")
        print(f"📝 Generated SQL (MySQL):")
        print(f"{sql}")
        print(f"\n✓ Examples ที่ใช้: MySQL examples (ตรงกับ dialect)")

    # ========================================================================
    # Scenario 2: ย้ายไปใช้ PostgreSQL (database ใหม่)
    # ========================================================================
    print("\n\n📊 Scenario 2: PostgreSQL Database (หลังจากย้าย)")
    print("-" * 70)

    postgres_config = {
        "user": "postgres",
        "password": "password",
        "host": "localhost",
        "port": 5432,
        "database": "sales_db"  # ชื่อ database เดียวกัน แต่ต่าง engine
    }

    postgres_engine, error = ConnectionManager.get_db_engine("PostgreSQL", postgres_config)

    if error:
        print(f"❌ PostgreSQL connection failed: {error}")
        print("   (สำหรับ demo นี้ ถ้าไม่มี PostgreSQL ก็ข้ามไปได้)")
    else:
        print(f"✅ Connected to PostgreSQL database")

        # Query ผ่าน PostgreSQL (ใช้คำถามเดิม!)
        sql, data, error, retries, viz = await nlp.query_database(
            question=question,
            engine=postgres_engine,
            dialect="postgresql"  # แค่เปลี่ยน dialect
        )

        print(f"\n🔍 Question: {question}")
        print(f"📝 Generated SQL (PostgreSQL):")
        print(f"{sql}")
        print(f"\n✓ Examples ที่ใช้: MySQL examples → แปลงเป็น PostgreSQL อัตโนมัติ!")

    # ========================================================================
    # สรุป
    # ========================================================================
    print("\n" + "=" * 70)
    print("✅ สรุป:")
    print("=" * 70)
    print("""
    🎯 สิ่งที่คุณต้องทำ:
       1. Migrate database schema และ data (ใช้ db_migration.py)
       2. เปลี่ยน connection config (db_type, host, port, etc.)
       3. เปลี่ยน dialect parameter จาก "mysql" → "postgresql"

    🤖 สิ่งที่ระบบทำให้อัตโนมัติ:
       1. ดึง examples จาก RAG store
       2. แปลง MySQL examples → PostgreSQL syntax
       3. LLM เรียนรู้จาก PostgreSQL examples
       4. สร้าง SQL ที่ถูกต้องสำหรับ PostgreSQL

    ⚡ คุณไม่ต้องแก้:
       - thai_sql_examples.json
       - Prompt templates
       - Code logic

       แค่เปลี่ยน connection config เท่านั้น!
    """)


async def compare_sql_output():
    """
    เปรียบเทียบ SQL ที่สร้างจาก MySQL vs PostgreSQL
    """
    print("\n" + "=" * 70)
    print("SQL Output Comparison: MySQL vs PostgreSQL")
    print("=" * 70)

    from core.data.rag_store import create_example_store

    store = create_example_store()
    question = "ยอดขายแยกตามเดือน"

    # MySQL examples
    print("\n📊 MySQL Examples:")
    print("-" * 70)
    mysql_examples = store.format_examples_for_prompt(
        query=question,
        top_k=2,
        dialect="mysql",
        auto_transpile=False  # ไม่แปลง เพื่อดูต้นฉบับ
    )
    print(mysql_examples)

    # PostgreSQL examples (แปลงจาก MySQL)
    print("\n\n📊 PostgreSQL Examples (Auto-Transpiled):")
    print("-" * 70)
    postgres_examples = store.format_examples_for_prompt(
        query=question,
        top_k=2,
        dialect="postgresql",
        auto_transpile=True  # ✅ แปลงอัตโนมัติ
    )
    print(postgres_examples)

    print("\n" + "=" * 70)
    print("🔍 สังเกต:")
    print("   MySQL:      YEAR(orderDate), MONTH(orderDate)")
    print("   PostgreSQL: EXTRACT(YEAR FROM orderDate), EXTRACT(MONTH FROM orderDate)")
    print("=" * 70)


if __name__ == "__main__":
    print("\n🚀 Running Database Migration Demo...\n")

    # Run demo
    asyncio.run(demo_database_migration())

    # Compare SQL output
    asyncio.run(compare_sql_output())
