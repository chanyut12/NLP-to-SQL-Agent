"""
PostgreSQL Connection Test - ทดสอบการเชื่อมต่อ PostgreSQL

ไฟล์นี้ใช้ทดสอบว่า PostgreSQL connection ทำงานได้หรือไม่
และแสดงตัวอย่างการ query ข้อมูล
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.data.database import ConnectionManager
from sqlalchemy import text


def test_postgres_connection():
    """
    ทดสอบการเชื่อมต่อ PostgreSQL

    Requirements:
    1. PostgreSQL server ต้องทำงานอยู่
    2. Database ต้องถูกสร้างไว้แล้ว
    3. User ต้องมีสิทธิ์ access database
    """

    print("=" * 60)
    print("PostgreSQL Connection Test")
    print("=" * 60)

    # Configuration (ปรับแก้ตามค่าจริงของคุณ)
    db_config = {
        "user": "postgres",          # PostgreSQL username
        "password": "yourpassword",  # PostgreSQL password
        "host": "localhost",          # PostgreSQL host
        "port": 5432,                 # PostgreSQL port (default: 5432)
        "database": "sales_db"        # Database name
    }

    print(f"\n📋 Configuration:")
    print(f"   Host: {db_config['host']}:{db_config['port']}")
    print(f"   Database: {db_config['database']}")
    print(f"   User: {db_config['user']}")

    # Test 1: Connection
    print(f"\n🔌 Test 1: Connection Test")
    engine, error = ConnectionManager.get_db_engine("PostgreSQL", db_config)

    if error:
        print(f"❌ Connection failed: {error}")
        print(f"\n💡 Troubleshooting:")
        print(f"   1. Check if PostgreSQL is running:")
        print(f"      $ pg_isready -h {db_config['host']} -p {db_config['port']}")
        print(f"   2. Check if database exists:")
        print(f"      $ psql -h {db_config['host']} -U {db_config['user']} -l")
        print(f"   3. Check if password is correct")
        print(f"   4. Check if psycopg2-binary is installed:")
        print(f"      $ pip install psycopg2-binary")
        return False

    print(f"✅ Connection successful!")

    # Test 2: List tables
    print(f"\n📊 Test 2: List Tables")
    try:
        with engine.connect() as conn:
            # PostgreSQL-specific query
            query = text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name
            """)
            result = conn.execute(query)
            tables = [row[0] for row in result]

            if tables:
                print(f"✅ Found {len(tables)} tables:")
                for table in tables:
                    print(f"   - {table}")
            else:
                print(f"⚠ No tables found in database")
    except Exception as e:
        print(f"❌ Failed to list tables: {e}")
        return False

    # Test 3: Sample query
    print(f"\n🔍 Test 3: Sample Query")
    try:
        with engine.connect() as conn:
            # ทดสอบ query ง่ายๆ
            query = text("SELECT version()")
            result = conn.execute(query)
            version = result.fetchone()[0]
            print(f"✅ PostgreSQL version:")
            print(f"   {version}")
    except Exception as e:
        print(f"❌ Query failed: {e}")
        return False

    # Test 4: Dialect-specific functions
    print(f"\n⚙️  Test 4: Dialect-Specific Functions")
    try:
        with engine.connect() as conn:
            # PostgreSQL date functions
            query = text("""
                SELECT
                    CURRENT_DATE as today,
                    EXTRACT(YEAR FROM CURRENT_DATE) as year,
                    EXTRACT(MONTH FROM CURRENT_DATE) as month,
                    'Hello' || ' ' || 'World' as concat_example
            """)
            result = conn.execute(query)
            row = result.fetchone()

            print(f"✅ PostgreSQL-specific functions work correctly:")
            print(f"   Today: {row[0]}")
            print(f"   Year: {row[1]}")
            print(f"   Month: {row[2]}")
            print(f"   Concat: {row[3]}")
    except Exception as e:
        print(f"❌ Function test failed: {e}")
        return False

    print(f"\n" + "=" * 60)
    print(f"✅ All tests passed! PostgreSQL is working correctly.")
    print(f"=" * 60)

    return True


def create_sample_table():
    """
    สร้างตารางตัวอย่างสำหรับทดสอบ
    """
    print("\n" + "=" * 60)
    print("Create Sample Table (Optional)")
    print("=" * 60)

    db_config = {
        "user": "postgres",
        "password": "yourpassword",
        "host": "localhost",
        "port": 5432,
        "database": "sales_db"
    }

    engine, error = ConnectionManager.get_db_engine("PostgreSQL", db_config)
    if error:
        print(f"❌ Connection failed: {error}")
        return False

    try:
        with engine.connect() as conn:
            # สร้างตารางตัวอย่าง
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS test_products (
                    product_id SERIAL PRIMARY KEY,
                    product_name VARCHAR(100),
                    price DECIMAL(10, 2),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))

            # Insert sample data
            conn.execute(text("""
                INSERT INTO test_products (product_name, price) VALUES
                ('Laptop', 25000.00),
                ('Mouse', 350.00),
                ('Keyboard', 1200.00)
                ON CONFLICT DO NOTHING
            """))

            conn.commit()

            print(f"✅ Sample table 'test_products' created successfully")

            # Query sample data
            result = conn.execute(text("SELECT * FROM test_products"))
            rows = result.fetchall()

            print(f"\n📊 Sample data:")
            for row in rows:
                print(f"   {row}")

    except Exception as e:
        print(f"❌ Failed to create sample table: {e}")
        return False

    return True


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test PostgreSQL connection")
    parser.add_argument(
        "--create-sample",
        action="store_true",
        help="Create a sample table for testing"
    )

    args = parser.parse_args()

    # Run connection test
    success = test_postgres_connection()

    # Optionally create sample table
    if success and args.create_sample:
        create_sample_table()

    exit(0 if success else 1)
