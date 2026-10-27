"""Domain profile loader + shipped profile sanity."""

import json
import os
import sys
import unittest

import sqlglot

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from core import profiles


# Profiles that claim production support. Add a profile here only after it has
# its own Golden set and evaluation run (see docs/guides/PROFILES.md).
SUPPORTED_PROFILES = ("sts",)

REQUIRED_PROFILE_FILES = ("hints.md", "examples.json")
REQUIRED_EXAMPLE_FIELDS = ("id", "question", "sql", "category", "dialect")
SQLGLOT_DIALECTS = {
    "postgres": "postgres",
    "postgresql": "postgres",
    "mysql": "mysql",
    "sqlite": "sqlite",
}


class TestProfileLoader(unittest.TestCase):
    def test_sts_hints_load(self):
        hints = profiles.load_hints("sts")
        self.assertIn("PostgreSQL", hints)
        self.assertIn("student_current_enrollment_resolution", hints)

    def test_missing_profile_returns_empty(self):
        self.assertEqual(profiles.load_hints("does-not-exist"), "")

    def test_examples_path(self):
        p = profiles.examples_path("sts")
        self.assertTrue(p.endswith(os.path.join("profiles", "sts", "examples.json")))

    def test_schema_mappings(self):
        m = profiles.load_schema_mappings("sts")
        self.assertIn("นักเรียน", m)
        self.assertIn("student_term", m["นักเรียน"])
        self.assertEqual(profiles.load_schema_mappings("does-not-exist"), {})


class TestSupportedProfileContract(unittest.TestCase):
    """The contract a profile must meet before it is called supported."""

    def _examples(self, name):
        with open(profiles.examples_path(name), encoding="utf-8") as f:
            return json.load(f)["examples"]

    def test_required_files_exist(self):
        for name in SUPPORTED_PROFILES:
            directory = profiles.profile_dir(name)
            self.assertTrue(os.path.isdir(directory), name)
            for filename in REQUIRED_PROFILE_FILES:
                self.assertTrue(
                    os.path.isfile(os.path.join(directory, filename)),
                    f"{name} is missing {filename}",
                )

    def test_example_ids_are_unique(self):
        for name in SUPPORTED_PROFILES:
            ids = [ex["id"] for ex in self._examples(name)]
            self.assertEqual(len(ids), len(set(ids)), f"duplicate example id in {name}")

    def test_examples_follow_the_contract(self):
        for name in SUPPORTED_PROFILES:
            for ex in self._examples(name):
                self._assert_example_contract(name, ex)

    def _assert_example_contract(self, name, ex):
        for field in REQUIRED_EXAMPLE_FIELDS:
            self.assertIn(field, ex, f"{name}/{ex.get('id', '?')} is missing {field}")
        for field in ("id", "question", "category"):
            self.assertTrue(str(ex[field]).strip(), f"{name}/{ex.get('id')} has empty {field}")
        self.assertIn(
            ex["dialect"], SQLGLOT_DIALECTS,
            f"{name}/{ex['id']} has unsupported dialect {ex['dialect']!r}",
        )

        answer_type = ex.get("expected_answer_type")
        if answer_type:
            self.assertIn(answer_type, ("clarification", "refusal"), ex["id"])
            self.assertEqual(ex["sql"].strip(), "", f"{ex['id']} must not carry SQL")
            self.assertTrue(
                str(ex.get("expected_message", "")).strip(),
                f"{ex['id']} needs expected_message",
            )
        else:
            self.assertTrue(str(ex["sql"]).strip(), f"{ex['id']} has empty SQL")

    def test_result_sql_parses_as_one_statement(self):
        for name in SUPPORTED_PROFILES:
            for ex in self._examples(name):
                if ex.get("expected_answer_type"):
                    continue
                self.assertNotIn("$1", ex["sql"], f"{ex['id']} still has placeholders")
                dialect = SQLGLOT_DIALECTS[ex["dialect"]]
                statements = sqlglot.parse(ex["sql"], read=dialect)
                self.assertEqual(len(statements), 1, f"{ex['id']} is not one statement")

    def test_schema_mappings_are_well_formed(self):
        for name in SUPPORTED_PROFILES:
            mappings = profiles.load_schema_mappings(name)
            self.assertIsInstance(mappings, dict)
            for term, fragments in mappings.items():
                self.assertTrue(str(term).strip())
                self.assertIsInstance(fragments, list, f"{name}/{term}")
                self.assertTrue(fragments, f"{name}/{term} is empty")
                self.assertTrue(all(isinstance(f, str) and f.strip() for f in fragments))

    def test_table_notes_are_well_formed_when_present(self):
        for name in SUPPORTED_PROFILES:
            path = os.path.join(profiles.profile_dir(name), "table_notes.json")
            if not os.path.isfile(path):
                continue
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            self.assertIsInstance(data.get("tables"), dict, name)
            for table, entry in data["tables"].items():
                self.assertIsInstance(entry, dict, f"{name}/{table}")
                self.assertTrue(str(entry.get("meaning", "")).strip(), f"{name}/{table}")
                self.assertTrue(str(entry.get("population", "")).strip(), f"{name}/{table}")
                for field in ("key_columns", "joins", "notes"):
                    if field in entry:
                        self.assertIsInstance(entry[field], list, f"{name}/{table}/{field}")
                        self.assertTrue(all(isinstance(v, str) for v in entry[field]))


class TestShippedProfiles(unittest.TestCase):
    def _load(self, name):
        with open(profiles.examples_path(name), encoding="utf-8") as f:
            return json.load(f)["examples"]

    def test_sts_examples_present_and_postgres(self):
        ex = self._load("sts")
        self.assertGreater(len(ex), 40)
        self.assertTrue(all(e["dialect"] == "postgresql" for e in ex))
        # parameters were inlined — no positional placeholders remain
        self.assertFalse(any("$1" in e["sql"] for e in ex))

    def test_sts_heldout_disjoint_from_examples(self):
        ids = {e["id"] for e in self._load("sts")}
        with open(os.path.join(profiles.profile_dir("sts"), "heldout_ids.json"), encoding="utf-8") as f:
            heldout = set(json.load(f))
        self.assertEqual(len(heldout), 10)
        self.assertEqual(ids & heldout, set())

    def test_receipt_sample_examples_present(self):
        self.assertGreater(len(self._load("receipt_sample")), 40)


if __name__ == "__main__":
    unittest.main()
