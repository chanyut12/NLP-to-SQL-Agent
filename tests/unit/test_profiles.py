"""Domain profile loader + shipped profile sanity."""

import json
import os
import sys
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from core import profiles


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
