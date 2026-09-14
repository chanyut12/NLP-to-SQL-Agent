"""Corpus balance tests (ticket #15, ADR 0007).

The Example set must hold ~8 examples per shared Category bucket plus the
clarify/refusal exemplar block; surplus count examples live in the on-disk
archive, never loaded by retrieval; the rebuilt profile keeps every bucketed
example and the exemplars.
"""

import json
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
sys.path.insert(0, ROOT)

from eval.distribution_audit import (
    CATEGORY_BUCKETS,
    CLARIFY_REFUSAL_QUOTA,
    EXAMPLE_BUCKET_QUOTA,
    bucket_for,
    count_buckets,
    count_exemplar_block,
)

CORPUS_PATH = os.path.join(ROOT, "TEXT_TO_SQL_STS_RAG_EXAMPLES.json")
ARCHIVE_PATH = os.path.join(ROOT, "TEXT_TO_SQL_STS_RAG_EXAMPLES_ARCHIVE.json")
PROFILE_PATH = os.path.join(ROOT, "profiles", "sts", "examples.json")

CORPUS = json.load(open(CORPUS_PATH, encoding="utf-8"))
EXAMPLES = CORPUS["examples"]


class TestCorpusBalance(unittest.TestCase):
    def test_every_bucket_holds_the_quota(self):
        buckets, unmapped = count_buckets(EXAMPLES)
        for b in CATEGORY_BUCKETS:
            self.assertEqual(
                buckets[b], EXAMPLE_BUCKET_QUOTA,
                f"bucket {b} holds {buckets[b]}, quota is {EXAMPLE_BUCKET_QUOTA}")

    def test_no_unmapped_categories_remain(self):
        _, unmapped = count_buckets(EXAMPLES)
        self.assertEqual(unmapped, {},
                         "every example must carry a taxonomy category")

    def test_clarify_refusal_block_present_and_symmetric(self):
        block = count_exemplar_block(EXAMPLES)
        self.assertEqual(block["clarify"], CLARIFY_REFUSAL_QUOTA)
        self.assertEqual(block["refusal"], CLARIFY_REFUSAL_QUOTA)

    def test_exemplars_sit_outside_bucket_quotas(self):
        # count_buckets ignores exemplar categories (they are UNMAPPED tags);
        # the quota test above must therefore hold WITH exemplars in the file.
        buckets, _ = count_buckets(EXAMPLES)
        self.assertEqual(sum(buckets.values()), EXAMPLE_BUCKET_QUOTA * len(CATEGORY_BUCKETS))

    def test_bucketed_examples_carry_executable_sql(self):
        for e in EXAMPLES:
            if bucket_for(e["category"]):
                self.assertTrue(e["sql"].strip(),
                                f"{e['id']} is a bucketed example and must carry SQL")

    def test_exemplars_carry_expected_answer_contract(self):
        for e in EXAMPLES:
            if e["category"] in ("clarification_exemplar", "refusal_exemplar"):
                self.assertFalse(e["sql"].strip(), f"{e['id']} must not carry SQL")
                self.assertIn(e.get("expected_answer_type"), ("clarification", "refusal"))
                self.assertTrue(e.get("expected_message", "").strip(),
                                f"{e['id']} must carry its expected message text")


class TestArchive(unittest.TestCase):
    def test_archive_exists_and_is_disjoint(self):
        self.assertTrue(os.path.exists(ARCHIVE_PATH),
                        "demoted examples must live in the archive, not be deleted")
        archive = json.load(open(ARCHIVE_PATH, encoding="utf-8"))["examples"]
        corpus_ids = {e["id"] for e in EXAMPLES}
        archive_ids = {e["id"] for e in archive}
        self.assertEqual(corpus_ids & archive_ids, set())
        self.assertEqual(len(archive), 38)  # 86 original - 48 survivors (45 + 3 retags)
        self.assertEqual(len(corpus_ids) + len(archive_ids), 86 + 8 + 6)

    def test_archive_preserves_original_categories(self):
        archive = json.load(open(ARCHIVE_PATH, encoding="utf-8"))["examples"]
        for e in archive:
            self.assertIn("category", e)
            self.assertTrue(e["sql"].strip(), f"archived {e['id']} keeps its SQL")


class TestRebuiltProfile(unittest.TestCase):
    HELDOUT_PATH = os.path.join(ROOT, "profiles", "sts", "heldout_ids.json")

    def test_profile_covers_corpus_minus_holdout_plus_all_exemplars(self):
        profile = json.load(open(PROFILE_PATH, encoding="utf-8"))["examples"]
        heldout = set(json.load(open(self.HELDOUT_PATH, encoding="utf-8")))
        profile_ids = {e["id"] for e in profile}
        for e in EXAMPLES:
            if e["category"] in ("clarification_exemplar", "refusal_exemplar"):
                self.assertIn(e["id"], profile_ids,
                              f"exemplar {e['id']} must stay in retrieval")
            else:
                self.assertTrue(e["id"] in profile_ids or e["id"] in heldout,
                                f"{e['id']} is neither in the profile nor held out")
        # the eval carve never touches exemplars — no SQL to leak
        self.assertEqual(heldout & {e["id"] for e in EXAMPLES
                                    if e["category"] in ("clarification_exemplar",
                                                         "refusal_exemplar")}, set())

    def test_profile_entries_carry_retrieval_fields(self):
        profile = json.load(open(PROFILE_PATH, encoding="utf-8"))["examples"]
        for e in profile:
            self.assertTrue(e.get("question", "").strip(), e["id"])
            self.assertTrue(e.get("category"), e["id"])
            self.assertTrue(e.get("retrieval_tags") is not None, e["id"])


if __name__ == "__main__":
    unittest.main()
