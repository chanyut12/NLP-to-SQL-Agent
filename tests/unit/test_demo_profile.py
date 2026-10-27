"""Contract checks for profiles/demo — the standalone SQLite demo profile.

Every example must use only the demo schema, and every SQL statement must run on
SQLite. The test builds an empty schema in a temporary database so it does not
depend on local_database.db being present.
"""

import json
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from core.profiles import load_hints, load_schema_mappings, load_table_notes

PROFILE_DIR = os.path.join(
    os.path.dirname(__file__), "../../profiles/demo"
)
EXAMPLES_PATH = os.path.join(PROFILE_DIR, "examples.json")

DEMO_SCHEMA = """
CREATE TABLE receipt (
    receipt_id INTEGER PRIMARY KEY,
    date TEXT,
    month TEXT,
    customer_name TEXT,
    product_category TEXT,
    items_count INTEGER,
    total_price REAL,
    payment_method TEXT
);
CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY,
    customer_name TEXT,
    email TEXT,
    phone TEXT,
    membership_level TEXT
);
CREATE TABLE products (
    product_id INTEGER PRIMARY KEY,
    product_name TEXT,
    category TEXT,
    unit_price REAL,
    stock_quantity INTEGER
);
"""


class TestDemoProfileFiles(unittest.TestCase):
    def test_examples_have_the_required_contract(self):
        with open(EXAMPLES_PATH, encoding="utf-8") as f:
            examples = json.load(f)["examples"]

        self.assertGreaterEqual(len(examples), 20)
        ids = [example["id"] for example in examples]
        self.assertEqual(len(ids), len(set(ids)), "example ids must be unique")

        required = {"id", "question", "sql", "category", "dialect"}
        for example in examples:
            self.assertTrue(required <= example.keys(), example["id"])
            self.assertEqual(example["dialect"], "sqlite", example["id"])
            self.assertTrue(example["sql"].lstrip().upper().startswith("SELECT"), example["id"])

    def test_hints_and_notes_are_available(self):
        self.assertIn("SQLite", load_hints("demo"))
        self.assertTrue(load_schema_mappings("demo"))
        self.assertIn("receipt", load_table_notes("demo")["tables"])


class TestDemoExamplesRunOnSQLite(unittest.TestCase):
    def test_every_example_executes(self):
        with open(EXAMPLES_PATH, encoding="utf-8") as f:
            examples = json.load(f)["examples"]

        with tempfile.TemporaryDirectory() as tmpdir:
            connection = sqlite3.connect(os.path.join(tmpdir, "demo.db"))
            try:
                connection.executescript(DEMO_SCHEMA)
                for example in examples:
                    with self.subTest(example=example["id"]):
                        connection.execute(example["sql"]).fetchall()
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
