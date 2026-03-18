
import unittest
import sys
import os

# Add project root to path to allow importing core modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from core.utils.dialect_transpiler import DialectTranspiler


class TestDialectTranspilerTranspile(unittest.TestCase):
    """ทดสอบการแปลง SQL ข้าม dialects"""

    def test_mysql_to_postgresql(self):
        """แปลง MySQL → PostgreSQL: ได้ผลลัพธ์ที่ parse ได้"""
        sql = "SELECT YEAR(created_at) AS year FROM sales"
        result = DialectTranspiler.transpile(sql, "MySQL", "PostgreSQL")
        self.assertIsNotNone(result)
        self.assertIn("YEAR", result.upper())
        self.assertIn("CREATED_AT", result.upper())

    def test_postgresql_to_mysql(self):
        """แปลง PostgreSQL → MySQL: EXTRACT ยังคงอยู่ (sqlglot keeps structure)"""
        sql = "SELECT EXTRACT(YEAR FROM created_at) AS year FROM sales"
        result = DialectTranspiler.transpile(sql, "PostgreSQL", "MySQL")
        self.assertIsNotNone(result)
        self.assertIn("YEAR", result.upper())
        self.assertIn("CREATED_AT", result.upper())

    def test_sqlite_to_mysql(self):
        """แปลง SQLite syntax → MySQL"""
        sql = "SELECT name FROM users LIMIT 10"
        result = DialectTranspiler.transpile(sql, "SQLite", "MySQL")
        self.assertIsNotNone(result)
        self.assertIn("SELECT", result.upper())

    def test_same_dialect_returns_same(self):
        """dialect เดียวกันไม่เปลี่ยน logic"""
        sql = "SELECT id, name FROM users WHERE id = 1"
        result = DialectTranspiler.transpile(sql, "MySQL", "MySQL")
        self.assertIn("SELECT", result.upper())
        self.assertIn("users", result.lower())

    def test_transpile_returns_string(self):
        """return type เป็น string"""
        sql = "SELECT 1"
        result = DialectTranspiler.transpile(sql, "MySQL", "PostgreSQL")
        self.assertIsInstance(result, str)


class TestDialectTranspilerErrors(unittest.TestCase):
    """ทดสอบ error handling"""

    def test_unsupported_dialect_raises_error(self):
        """dialect ไม่รู้จัก → ValueError"""
        with self.assertRaises(ValueError) as ctx:
            DialectTranspiler.transpile("SELECT 1", "Oracle", "MySQL")
        self.assertIn("Unsupported dialect", str(ctx.exception))

    def test_invalid_sql_raises_error(self):
        """SQL ผิด syntax → ValueError"""
        with self.assertRaises(ValueError):
            DialectTranspiler.transpile("NOT VALID SQL !!!", "MySQL", "PostgreSQL")

    def test_empty_sql(self):
        """empty string → คืน empty string"""
        result = DialectTranspiler.transpile("", "MySQL", "PostgreSQL")
        self.assertEqual(result, "")


class TestDialectTranspilerValidation(unittest.TestCase):
    """ทดสอบ validate_compatibility()"""

    def test_compatible_sql_returns_dict(self):
        """SQL ที่ถูกต้อง → คืน dict ที่มี key ครบ"""
        result = DialectTranspiler.validate_compatibility(
            "SELECT id, name FROM users WHERE id = 1", "MySQL"
        )
        self.assertIn("compatible", result)
        self.assertIn("issues", result)
        self.assertIn("suggestions", result)
        self.assertIsInstance(result["compatible"], bool)
        self.assertIsInstance(result["issues"], list)

    def test_incompatible_functions_detected(self):
        """ตรวจจับ MySQL functions ใน PostgreSQL context"""
        sql = "SELECT IFNULL(name, 'N/A') FROM users"
        result = DialectTranspiler.validate_compatibility(sql, "PostgreSQL")
        self.assertFalse(result["compatible"])
        self.assertTrue(len(result["issues"]) > 0)

    def test_unknown_dialect_returns_false(self):
        """dialect ไม่รู้จัก → compatible: False"""
        result = DialectTranspiler.validate_compatibility("SELECT 1", "Oracle")
        self.assertFalse(result["compatible"])
        self.assertIn("Unknown dialect", result["issues"][0])


class TestDialectTranspilerSupported(unittest.TestCase):
    """ทดสอบ supported dialects"""

    def test_supported_dialects_contains_three(self):
        """มี 3 dialects"""
        self.assertEqual(len(DialectTranspiler.SUPPORTED_DIALECTS), 3)

    def test_supported_dialect_keys(self):
        """key names ถูกต้อง"""
        keys = set(DialectTranspiler.SUPPORTED_DIALECTS.keys())
        self.assertEqual(keys, {"SQLite", "MySQL", "PostgreSQL"})


if __name__ == '__main__':
    unittest.main()
