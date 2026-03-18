"""
Database Migration Helper - ย้ายข้อมูลระหว่าง database engines
"""
import pandas as pd
from sqlalchemy import create_engine, MetaData, Table, inspect
from sqlalchemy.engine import Engine
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class DatabaseMigrator:
    """
    ช่วยย้ายข้อมูลจาก database engine หนึ่งไปอีก engine หนึ่ง
    รองรับ SQLite, MySQL, PostgreSQL
    """

    def __init__(self, source_engine: Engine, target_engine: Engine):
        """
        Args:
            source_engine: SQLAlchemy engine ต้นทาง
            target_engine: SQLAlchemy engine ปลายทาง
        """
        self.source = source_engine
        self.target = target_engine

    def migrate_schema(self, tables: Optional[List[str]] = None) -> Dict[str, bool]:
        """
        คัดลอก schema (table structures) จาก source -> target

        Args:
            tables: รายชื่อตารางที่ต้องการย้าย (ถ้าไม่ระบุจะย้ายทั้งหมด)

        Returns:
            {table_name: success_status}
        """
        results = {}

        try:
            # อ่าน metadata จาก source
            source_metadata = MetaData()
            source_metadata.reflect(bind=self.source)

            # กรอง tables ที่ต้องการ
            if tables:
                tables_to_migrate = [
                    source_metadata.tables[t] for t in tables
                    if t in source_metadata.tables
                ]
            else:
                tables_to_migrate = source_metadata.tables.values()

            # สร้าง tables ใน target database
            for table in tables_to_migrate:
                try:
                    # ใช้ to_metadata() เพื่อ clone table definition
                    target_metadata = MetaData()
                    table.to_metadata(target_metadata)
                    target_metadata.create_all(self.target)

                    results[table.name] = True
                    logger.info(f"✓ Schema migrated: {table.name}")
                except Exception as e:
                    results[table.name] = False
                    logger.error(f"✗ Schema migration failed for {table.name}: {e}")

        except Exception as e:
            logger.error(f"Schema migration error: {e}")

        return results

    def migrate_data(
        self,
        tables: Optional[List[str]] = None,
        batch_size: int = 1000
    ) -> Dict[str, Dict[str, int]]:
        """
        คัดลอกข้อมูลจาก source -> target

        Args:
            tables: รายชื่อตารางที่ต้องการย้าย
            batch_size: จำนวนแถวต่อ batch (ป้องกัน memory overflow)

        Returns:
            {
                table_name: {
                    "rows_migrated": int,
                    "success": bool
                }
            }
        """
        results = {}
        inspector = inspect(self.source)

        # ดึงรายชื่อตารางทั้งหมด
        all_tables = inspector.get_table_names()
        tables_to_migrate = tables if tables else all_tables

        for table_name in tables_to_migrate:
            try:
                logger.info(f"Migrating data from {table_name}...")

                # อ่านข้อมูลจาก source
                query = f"SELECT * FROM {table_name}"
                df = pd.read_sql(query, self.source)

                # เขียนไปยัง target (batch mode)
                row_count = 0
                for start in range(0, len(df), batch_size):
                    end = min(start + batch_size, len(df))
                    batch = df.iloc[start:end]

                    batch.to_sql(
                        table_name,
                        self.target,
                        if_exists='append',
                        index=False
                    )
                    row_count += len(batch)
                    logger.info(f"  Progress: {row_count}/{len(df)} rows")

                results[table_name] = {
                    "rows_migrated": row_count,
                    "success": True
                }
                logger.info(f"✓ Data migrated: {table_name} ({row_count} rows)")

            except Exception as e:
                results[table_name] = {
                    "rows_migrated": 0,
                    "success": False,
                    "error": str(e)
                }
                logger.error(f"✗ Data migration failed for {table_name}: {e}")

        return results

    def full_migration(
        self,
        tables: Optional[List[str]] = None,
        batch_size: int = 1000
    ) -> Dict:
        """
        ย้ายทั้ง schema และ data ในคำสั่งเดียว

        Returns:
            {
                "schema": {table_name: success},
                "data": {table_name: {rows, success}}
            }
        """
        logger.info("Starting full database migration...")

        # Step 1: Schema
        schema_results = self.migrate_schema(tables)

        # Step 2: Data (เฉพาะตารางที่ schema สำเร็จ)
        successful_tables = [t for t, success in schema_results.items() if success]
        data_results = self.migrate_data(successful_tables, batch_size)

        logger.info("Migration completed!")
        return {
            "schema": schema_results,
            "data": data_results
        }


# =============================================================================
# Quick Migration Helpers
# =============================================================================

def migrate_sqlite_to_mysql(
    sqlite_path: str,
    mysql_config: dict,
    tables: Optional[List[str]] = None
) -> Dict:
    """
    ย้ายข้อมูลจาก SQLite -> MySQL

    Args:
        sqlite_path: path ไปยังไฟล์ SQLite
        mysql_config: {user, password, host, port, database}
        tables: รายชื่อตารางที่ต้องการย้าย

    Example:
        >>> result = migrate_sqlite_to_mysql(
        ...     sqlite_path="data/sales.db",
        ...     mysql_config={
        ...         "user": "root",
        ...         "password": "pass",
        ...         "host": "localhost",
        ...         "port": 3306,
        ...         "database": "sales_db"
        ...     }
        ... )
    """
    source = create_engine(f"sqlite:///{sqlite_path}")
    target = create_engine(
        f"mysql+pymysql://{mysql_config['user']}:{mysql_config['password']}@"
        f"{mysql_config['host']}:{mysql_config['port']}/{mysql_config['database']}"
    )

    migrator = DatabaseMigrator(source, target)
    return migrator.full_migration(tables)


def migrate_sqlite_to_postgres(
    sqlite_path: str,
    postgres_config: dict,
    tables: Optional[List[str]] = None
) -> Dict:
    """
    ย้ายข้อมูลจาก SQLite -> PostgreSQL

    Args:
        sqlite_path: path ไปยังไฟล์ SQLite
        postgres_config: {user, password, host, port, database}
        tables: รายชื่อตารางที่ต้องการย้าย
    """
    source = create_engine(f"sqlite:///{sqlite_path}")
    target = create_engine(
        f"postgresql+psycopg2://{postgres_config['user']}:{postgres_config['password']}@"
        f"{postgres_config['host']}:{postgres_config['port']}/{postgres_config['database']}"
    )

    migrator = DatabaseMigrator(source, target)
    return migrator.full_migration(tables)


def migrate_mysql_to_postgres(
    mysql_config: dict,
    postgres_config: dict,
    tables: Optional[List[str]] = None
) -> Dict:
    """
    ย้ายข้อมูลจาก MySQL -> PostgreSQL

    Args:
        mysql_config: {user, password, host, port, database}
        postgres_config: {user, password, host, port, database}
        tables: รายชื่อตารางที่ต้องการย้าย
    """
    source = create_engine(
        f"mysql+pymysql://{mysql_config['user']}:{mysql_config['password']}@"
        f"{mysql_config['host']}:{mysql_config['port']}/{mysql_config['database']}"
    )
    target = create_engine(
        f"postgresql+psycopg2://{postgres_config['user']}:{postgres_config['password']}@"
        f"{postgres_config['host']}:{postgres_config['port']}/{postgres_config['database']}"
    )

    migrator = DatabaseMigrator(source, target)
    return migrator.full_migration(tables)


# =============================================================================
# ตัวอย่างการใช้งาน
# =============================================================================
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # ตัวอย่าง: ย้ายจาก SQLite -> PostgreSQL
    result = migrate_sqlite_to_postgres(
        sqlite_path="example_sales.db",
        postgres_config={
            "user": "postgres",
            "password": "yourpassword",
            "host": "localhost",
            "port": 5432,
            "database": "sales_db"
        },
        tables=["sales", "customers", "products"]  # ระบุเฉพาะตารางที่ต้องการ
    )

    print("\n=== Migration Summary ===")
    print(f"Schema: {result['schema']}")
    print(f"Data: {result['data']}")
