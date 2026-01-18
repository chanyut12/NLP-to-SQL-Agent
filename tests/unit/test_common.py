
import unittest
import sys
import os

# Add project root to path to allow importing core modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from core.utils.common import format_timestamp, normalize_sql_code
from core.domain.sql_safety import validate_and_sanitize_sql
from core.services.engine import NLPEngine

class TestCommonUtils(unittest.TestCase):
    
    def test_format_timestamp(self):
        """Test timestamp formatting logic."""
        # Valid ISO case
        self.assertEqual(format_timestamp("2023-10-27T10:30:00"), "2023-10-27 10:30")
        
        # Invalid case (should return original)
        self.assertEqual(format_timestamp("invalid-date"), "invalid-date")

    def test_normalize_sql_code(self):
        """Test SQL extraction and normalization."""
        # 1. Basic SQL (nothing to change)
        raw = "SELECT * FROM users"
        self.assertEqual(normalize_sql_code(raw), raw)
        
        # 2. Markdown block (remove ```sql ... ```)
        md = "```sql\nSELECT * FROM users\n```"
        self.assertEqual(normalize_sql_code(md), "SELECT * FROM users")
        
        # 3. XML Tags (Arctic format)
        xml = "<sql>SELECT * FROM users</sql>"
        self.assertEqual(normalize_sql_code(xml), "SELECT * FROM users")

    def test_integration_sql_safety(self):
        """Test if validation logic correctly uses normalization."""
        raw_dirty = "```sql\nSELECT * FROM products LIMIT 10\n```"
        # validate_and_sanitize_sql calls normalize_sql_code internally
        safe_obj = validate_and_sanitize_sql(raw_dirty, dialect="sqlite")
        self.assertEqual(safe_obj.sql, "SELECT * FROM products LIMIT 10")

if __name__ == '__main__':
    unittest.main()
