"""
SQL Dialect Transpiler - แปลง SQL ระหว่าง database engines อัตโนมัติ
"""
import sqlglot
from typing import Optional


class DialectTranspiler:
    """
    ช่วยแปลง SQL query ระหว่าง dialects ต่างๆ
    เพื่อรองรับการย้าย database engine
    """

    SUPPORTED_DIALECTS = {
        "SQLite": "sqlite",
        "MySQL": "mysql",
        "PostgreSQL": "postgres"
    }

    @classmethod
    def transpile(
        cls,
        sql: str,
        from_dialect: str,
        to_dialect: str,
        pretty: bool = True
    ) -> Optional[str]:
        """
        แปลง SQL จาก dialect หนึ่งไปอีก dialect

        Args:
            sql: SQL query ต้นฉบับ
            from_dialect: dialect ต้นทาง (SQLite, MySQL, PostgreSQL)
            to_dialect: dialect ปลายทาง (SQLite, MySQL, PostgreSQL)
            pretty: format SQL ให้อ่านง่าย

        Returns:
            SQL query ที่แปลงแล้ว หรือ None ถ้าแปลงไม่ได้

        Example:
            >>> sql = "SELECT YEAR(created_at) as year FROM sales"
            >>> transpiled = DialectTranspiler.transpile(sql, "MySQL", "PostgreSQL")
            >>> print(transpiled)
            SELECT EXTRACT(YEAR FROM created_at) AS year FROM sales
        """
        try:
            source = cls.SUPPORTED_DIALECTS.get(from_dialect)
            target = cls.SUPPORTED_DIALECTS.get(to_dialect)

            if not source or not target:
                raise ValueError(f"Unsupported dialect: {from_dialect} -> {to_dialect}")

            # sqlglot รองรับ auto-conversion ระหว่าง dialects
            result = sqlglot.transpile(
                sql,
                read=source,
                write=target,
                pretty=pretty
            )

            return result[0] if result else None

        except Exception as e:
            raise ValueError(f"Transpilation failed: {str(e)}")

    @classmethod
    def validate_compatibility(cls, sql: str, dialect: str) -> dict:
        """
        ตรวจสอบว่า SQL query ใช้ได้กับ dialect นี้ไหม

        Returns:
            {
                "compatible": bool,
                "issues": [list of potential issues],
                "suggestions": [list of fixes]
            }
        """
        try:
            target = cls.SUPPORTED_DIALECTS.get(dialect)
            if not target:
                return {
                    "compatible": False,
                    "issues": [f"Unknown dialect: {dialect}"],
                    "suggestions": []
                }

            # Parse SQL to check for syntax errors
            parsed = sqlglot.parse_one(sql, read=target)

            # Check for common incompatibilities
            issues = []
            suggestions = []

            # ตรวจสอบ functions ที่อาจไม่รองรับ
            functions = [node.name for node in parsed.find_all(sqlglot.exp.Function)]

            # MySQL-specific functions
            mysql_only = {"IFNULL", "UNIX_TIMESTAMP", "DATE_FORMAT"}
            # PostgreSQL-specific functions
            postgres_only = {"EXTRACT", "DATE_PART", "TO_CHAR"}
            # SQLite-specific functions
            sqlite_only = {"STRFTIME", "JULIANDAY"}

            if dialect == "PostgreSQL" and any(f in mysql_only for f in functions):
                issues.append("Contains MySQL-specific functions")
                suggestions.append("Use COALESCE instead of IFNULL")

            elif dialect == "MySQL" and any(f in postgres_only for f in functions):
                issues.append("Contains PostgreSQL-specific functions")
                suggestions.append("Use YEAR()/MONTH() instead of EXTRACT()")

            return {
                "compatible": len(issues) == 0,
                "issues": issues,
                "suggestions": suggestions
            }

        except Exception as e:
            return {
                "compatible": False,
                "issues": [f"Parse error: {str(e)}"],
                "suggestions": ["Check SQL syntax"]
            }


# ตัวอย่างการใช้งาน
if __name__ == "__main__":
    # ตัวอย่าง: แปลง MySQL -> PostgreSQL
    mysql_query = """
    SELECT
        YEAR(sale_date) as year,
        MONTH(sale_date) as month,
        CONCAT(customer_name, ' - ', product_name) as description,
        SUM(total_price) as total
    FROM sales
    GROUP BY year, month
    """

    print("=== MySQL to PostgreSQL ===")
    pg_query = DialectTranspiler.transpile(mysql_query, "MySQL", "PostgreSQL")
    print(pg_query)

    print("\n=== Validation ===")
    result = DialectTranspiler.validate_compatibility(mysql_query, "PostgreSQL")
    print(f"Compatible: {result['compatible']}")
    if result['issues']:
        print(f"Issues: {result['issues']}")
        print(f"Suggestions: {result['suggestions']}")
