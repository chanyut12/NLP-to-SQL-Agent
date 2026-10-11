"""Grounding check (ADR 0010, ticket #36): numbers in a message must come from rows."""

import os
import sys
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from core.services.answer_grounding import (
    drop_ungrounded_sentences, extract_numbers, fallback_message, ungrounded_numbers,
)

ROWS = [[{"province": "นครปฐม", "c": 5}, {"province": "ชลบุรี", "c": 1}]]


class TestExtract(unittest.TestCase):
    def test_thai_digits_commas_and_decimals(self):
        self.assertEqual(extract_numbers("๖,๐๐๐ คน และ 18.7%"), [6000.0, 18.7])

    def test_calendar_dates_are_not_claims(self):
        self.assertEqual(extract_numbers("ข้อมูล ณ วันที่ 27 กันยายน 2569 มี 5 รายการ"), [5.0])
        self.assertEqual(extract_numbers("as of 2026-09-27T07:45:16Z"), [])


class TestUngrounded(unittest.TestCase):
    def test_numbers_from_rows_pass(self):
        self.assertEqual(ungrounded_numbers("นครปฐม 5 รายการ ชลบุรี 1", ROWS), [])

    def test_derived_values_pass(self):
        # row count, sum, share of the column total (5/6 = 83.3%)
        self.assertEqual(ungrounded_numbers("รวม 6 รายการ จาก 2 จังหวัด นครปฐมคิดเป็น 83.3%", ROWS), [])

    def test_figure_from_another_population_is_caught(self):
        # the Oct 2026 failure: 76 at-risk students quoted against a signals result
        self.assertEqual(ungrounded_numbers("กรุงเทพฯ สูงสุด 76 คน", ROWS), [76.0])

    def test_user_stated_numbers_pass(self):
        self.assertEqual(ungrounded_numbers("5 อันดับแรก", ROWS, "ขอ 5 อันดับแรก"), [])

    def test_threshold_text_inside_cells_passes(self):
        rows = [[{"signal_reason": "ขาดสะสม 8 วัน (เกณฑ์ 7 วัน)", "c": 1}]]
        self.assertEqual(ungrounded_numbers("ขาดสะสม 8 วัน เกณฑ์ 7 วัน", rows), [])

    def test_rounding_tolerance_follows_stated_precision(self):
        rows = [[{"rate": 18.66}]]
        self.assertEqual(ungrounded_numbers("อัตรา 18.7%", rows), [])
        self.assertEqual(ungrounded_numbers("อัตรา 19.5%", rows), [19.5])

    def test_numbers_from_any_query_this_turn_pass(self):
        sets = [[{"a": 76}], [{"b": 19}]]
        self.assertEqual(ungrounded_numbers("76 และ 19", sets), [])


class TestRepair(unittest.TestCase):
    def test_drops_only_the_bad_sentence(self):
        msg = "นครปฐมมี 5 รายการ\nกรุงเทพฯ สูงสุด 76 คน"
        self.assertEqual(drop_ungrounded_sentences(msg, ROWS), "นครปฐมมี 5 รายการ")

    def test_fallback_states_only_the_row_count(self):
        self.assertEqual(fallback_message(0), "ไม่พบข้อมูลที่ตรงกับเงื่อนไขที่ระบุ")
        self.assertIn("3", fallback_message(3))


if __name__ == "__main__":
    unittest.main()
