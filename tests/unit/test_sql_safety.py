"""
Unit tests for SQL Safety module.

Tests for:
- Blocking dangerous SQL operations (DROP, DELETE, UPDATE, INSERT)
- Enforcing LIMIT clause
- Allowing only read-only SELECT queries
- Table allowlist validation
"""

import unittest
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from core.domain.sql_safety import validate_and_sanitize_sql, SQLSafetyError, SafeSQL


class TestSQLSafetyBlock(unittest.TestCase):
    """Test that dangerous SQL operations are blocked."""
    
    def test_block_drop_table(self):
        """DROP TABLE should be blocked."""
        with self.assertRaises(SQLSafetyError) as context:
            validate_and_sanitize_sql("DROP TABLE users", dialect="sqlite")
        self.assertIn("Disallowed", str(context.exception))
    
    def test_block_delete(self):
        """DELETE should be blocked."""
        with self.assertRaises(SQLSafetyError) as context:
            validate_and_sanitize_sql("DELETE FROM users WHERE id = 1", dialect="sqlite")
        self.assertIn("Disallowed", str(context.exception))
    
    def test_block_update(self):
        """UPDATE should be blocked."""
        with self.assertRaises(SQLSafetyError) as context:
            validate_and_sanitize_sql("UPDATE users SET name = 'hacked'", dialect="sqlite")
        self.assertIn("Disallowed", str(context.exception))
    
    def test_block_insert(self):
        """INSERT should be blocked."""
        with self.assertRaises(SQLSafetyError) as context:
            validate_and_sanitize_sql("INSERT INTO users VALUES (1, 'test')", dialect="sqlite")
        self.assertIn("Disallowed", str(context.exception))
    
    def test_block_truncate(self):
        """TRUNCATE should be blocked (via Command)."""
        with self.assertRaises(SQLSafetyError):
            validate_and_sanitize_sql("TRUNCATE TABLE users", dialect="mysql")
    
    def test_block_multi_statement(self):
        """Multiple statements should be blocked."""
        with self.assertRaises(SQLSafetyError) as context:
            validate_and_sanitize_sql("SELECT 1; DROP TABLE users;", dialect="sqlite")
        self.assertIn("single", str(context.exception).lower())


class TestSQLSafetyAllow(unittest.TestCase):
    """Test that valid SELECT queries are allowed."""
    
    def test_allow_simple_select(self):
        """Simple SELECT should pass."""
        result = validate_and_sanitize_sql("SELECT * FROM users", dialect="sqlite")
        self.assertIsInstance(result, SafeSQL)
        self.assertIn("SELECT", result.sql.upper())
    
    def test_allow_select_with_join(self):
        """SELECT with JOIN should pass."""
        sql = "SELECT u.name, o.total FROM users u JOIN orders o ON u.id = o.user_id"
        result = validate_and_sanitize_sql(sql, dialect="sqlite")
        self.assertIsInstance(result, SafeSQL)
        self.assertIn("users", result.tables)
        self.assertIn("orders", result.tables)
    
    def test_allow_with_cte(self):
        """WITH (CTE) queries should pass."""
        sql = "WITH top_users AS (SELECT * FROM users LIMIT 10) SELECT * FROM top_users"
        result = validate_and_sanitize_sql(sql, dialect="sqlite")
        self.assertIsInstance(result, SafeSQL)
    
    def test_allow_union(self):
        """UNION queries should pass."""
        sql = "SELECT name FROM users UNION SELECT name FROM admins"
        result = validate_and_sanitize_sql(sql, dialect="sqlite")
        self.assertIsInstance(result, SafeSQL)


class TestSQLSafetyLimit(unittest.TestCase):
    """Test LIMIT enforcement."""
    
    def test_inject_limit_when_missing(self):
        """LIMIT should be injected if missing."""
        result = validate_and_sanitize_sql("SELECT * FROM users", dialect="sqlite", max_limit=100)
        self.assertIn("LIMIT", result.sql.upper())
        self.assertEqual(result.limit, 100)
    
    def test_clamp_limit_when_too_high(self):
        """LIMIT should be clamped if higher than max."""
        result = validate_and_sanitize_sql("SELECT * FROM users LIMIT 9999", dialect="sqlite", max_limit=500)
        self.assertEqual(result.limit, 500)
    
    def test_preserve_limit_when_valid(self):
        """LIMIT should be preserved if within max."""
        result = validate_and_sanitize_sql("SELECT * FROM users LIMIT 50", dialect="sqlite", max_limit=500)
        self.assertEqual(result.limit, 50)


class TestSQLSafetyTableAllowlist(unittest.TestCase):
    """Test table allowlist validation."""
    
    def test_allow_permitted_table(self):
        """Query on allowed table should pass."""
        result = validate_and_sanitize_sql(
            "SELECT * FROM products", 
            dialect="sqlite", 
            allowed_tables=["products", "orders"]
        )
        self.assertIsInstance(result, SafeSQL)
    
    def test_block_forbidden_table(self):
        """Query on forbidden table should be blocked."""
        with self.assertRaises(SQLSafetyError) as context:
            validate_and_sanitize_sql(
                "SELECT * FROM secret_data",
                dialect="sqlite",
                allowed_tables=["products", "orders"]
            )
        self.assertIn("not allowed", str(context.exception))

    def test_cte_name_is_not_a_forbidden_table(self):
        """A WITH CTE referenced in FROM must not trip the table allowlist."""
        result = validate_and_sanitize_sql(
            "WITH c AS (SELECT a, COUNT(*) n FROM orders GROUP BY a) "
            "SELECT a, n FROM c ORDER BY n DESC",
            dialect="postgres",
            allowed_tables=["orders"],
        )
        self.assertEqual(result.tables, ("orders",))

    def test_cte_shadowing_a_real_forbidden_table_still_blocks_the_real_use(self):
        result = validate_and_sanitize_sql(
            "WITH orders AS (SELECT 1 AS a) SELECT a FROM orders",
            dialect="postgres",
            allowed_tables=["products"],
        )
        self.assertEqual(result.tables, ())


if __name__ == '__main__':
    unittest.main()
