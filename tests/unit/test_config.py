"""
Unit tests for Config module.

Tests for:
- All settings have valid default values
- Settings are accessible via the singleton instance
- Type validation for critical settings
"""

import unittest
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from core.config import settings, Settings


class TestConfigDefaults(unittest.TestCase):
    """Test that all config settings have valid default values."""
    
    def test_max_sql_limit_is_positive_int(self):
        """MAX_SQL_LIMIT should be a positive integer."""
        self.assertIsInstance(settings.MAX_SQL_LIMIT, int)
        self.assertGreater(settings.MAX_SQL_LIMIT, 0)
    
    def test_max_retries_is_non_negative_int(self):
        """MAX_RETRIES should be a non-negative integer."""
        self.assertIsInstance(settings.MAX_RETRIES, int)
        self.assertGreaterEqual(settings.MAX_RETRIES, 0)
    
    def test_rag_top_k_is_positive_int(self):
        """RAG_TOP_K should be a positive integer."""
        self.assertIsInstance(settings.RAG_TOP_K, int)
        self.assertGreater(settings.RAG_TOP_K, 0)
    
    def test_schema_top_k_is_positive_int(self):
        """SCHEMA_TOP_K should be a positive integer."""
        self.assertIsInstance(settings.SCHEMA_TOP_K, int)
        self.assertGreater(settings.SCHEMA_TOP_K, 0)
    
    def test_rag_distance_threshold_is_positive_float(self):
        """RAG_DISTANCE_THRESHOLD should be a positive float."""
        self.assertIsInstance(settings.RAG_DISTANCE_THRESHOLD, (int, float))
        self.assertGreater(settings.RAG_DISTANCE_THRESHOLD, 0)
    
    def test_embedding_model_is_non_empty_string(self):
        """EMBEDDING_MODEL should be a non-empty string."""
        self.assertIsInstance(settings.EMBEDDING_MODEL, str)
        self.assertTrue(len(settings.EMBEDDING_MODEL) > 0)


class TestConfigModelProvider(unittest.TestCase):
    """Test LLM provider configuration."""
    
    def test_model_provider_is_valid(self):
        """MODEL_PROVIDER should be one of: ollama, openai, google."""
        valid_providers = {"ollama", "openai", "google"}
        self.assertIn(settings.MODEL_PROVIDER, valid_providers)
    
    def test_ollama_base_url_has_valid_format(self):
        """OLLAMA_BASE_URL should start with http://."""
        self.assertTrue(
            settings.OLLAMA_BASE_URL.startswith("http://") or 
            settings.OLLAMA_BASE_URL.startswith("https://")
        )
    
    def test_ollama_model_is_non_empty(self):
        """OLLAMA_MODEL should be a non-empty string."""
        self.assertIsInstance(settings.OLLAMA_MODEL, str)
        self.assertTrue(len(settings.OLLAMA_MODEL) > 0)


class TestConfigLogFiles(unittest.TestCase):
    """Test log file configuration."""
    
    def test_log_file_jsonl_has_extension(self):
        """LOG_FILE_JSONL should have .jsonl extension."""
        self.assertTrue(settings.LOG_FILE_JSONL.endswith(".jsonl"))
    
    def test_log_file_csv_has_extension(self):
        """LOG_FILE_CSV should have .csv extension."""
        self.assertTrue(settings.LOG_FILE_CSV.endswith(".csv"))


class TestConfigSingleton(unittest.TestCase):
    """Test that settings is a proper singleton."""
    
    def test_settings_is_instance_of_settings_class(self):
        """settings should be an instance of Settings class."""
        self.assertIsInstance(settings, Settings)
    
    def test_settings_attributes_are_accessible(self):
        """All expected attributes should be accessible."""
        required_attrs = [
            'MODEL_PROVIDER', 'OLLAMA_MODEL', 'OLLAMA_BASE_URL',
            'MAX_SQL_LIMIT', 'MAX_RETRIES', 'RAG_TOP_K', 'SCHEMA_TOP_K',
            'RAG_DISTANCE_THRESHOLD', 'EMBEDDING_MODEL',
            'ENABLE_INTELLIGENT_VIZ', 'LOG_FILE_JSONL', 'LOG_FILE_CSV'
        ]
        for attr in required_attrs:
            self.assertTrue(hasattr(settings, attr), f"Missing attribute: {attr}")


if __name__ == '__main__':
    unittest.main()
