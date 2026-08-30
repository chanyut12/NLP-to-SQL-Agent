"""Denylist for non-analytical database objects."""

import os
import sys
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from core.domain.schema_utils import is_denylisted


class TestDenylist(unittest.TestCase):
    def test_blocks_migration_and_backup_objects(self):
        for name in [
            "attendance_calendar_reason_20260827_backup",
            "user_scope_backfill_20260702_backup",
            "demo_provenance_case_review_backup_20260724",
            "master_data_reconcile_backup_20260824",
            "migration_20260827313400_burapha_user_scope_backup",
            "araid_identity_records",
            "audit_log",
            "system_settings",
        ]:
            self.assertTrue(is_denylisted(name), name)

    def test_keeps_real_analytical_tables(self):
        for name in [
            "student_term",
            "attendance_day",
            "attendance_sessions",
            "attendance_session_roster",
            "student_current_enrollment_resolution",
            "cases",
            "school_teacher_memberships",
        ]:
            self.assertFalse(is_denylisted(name), name)


if __name__ == "__main__":
    unittest.main()
