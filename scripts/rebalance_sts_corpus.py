"""One-shot rebalance of the STS Example set to the ADR 0007 quotas (ticket #15).

Reads TEXT_TO_SQL_STS_RAG_EXAMPLES.json and writes:
- TEXT_TO_SQL_STS_RAG_EXAMPLES.json          balanced corpus (8/bucket + 3+3 exemplars)
- TEXT_TO_SQL_STS_RAG_EXAMPLES_ARCHIVE.json  demoted surplus examples (reversible)

Policy (ADR 0007, decided in the grilling session):
- keep the 8 domain-richest examples per bucket; demote the rest to the archive
- retag the 3 multi_join_aggregation examples to their primary shape; where the
  receiving bucket would overflow, demote its weakest overlapping member instead
- author the missing ranking / having-threshold / time-groupby examples from the
  same STS table patterns (9 examples: 6 ranking, 1 having, 2 time)
- add 3 clarification + 3 refusal exemplars (no SQL — outside the shape quotas)

Idempotence: refuses to run if the corpus already matches the quota, and refuses
to overwrite an existing archive.

Usage:
    python scripts/rebalance_sts_corpus.py            # apply
    python scripts/rebalance_sts_corpus.py --dry-run  # show the plan only
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS_PATH = os.path.join(ROOT, "data", "corpus", "TEXT_TO_SQL_STS_RAG_EXAMPLES.json")
ARCHIVE_PATH = os.path.join(ROOT, "data", "corpus", "archive", "TEXT_TO_SQL_STS_RAG_EXAMPLES_ARCHIVE.json")

# --- ADR 0007 quotas ----------------------------------------------------------
BUCKET_QUOTA = 8
CLARIFY_REFUSAL_QUOTA = 3

# --- Demotion policy ----------------------------------------------------------
# For each bucket: keep these ids (domain-richest / shape-informative), demote
# the rest. Buckets at or under quota keep everything.
KEEP = {
    "count_groupby": [
        # one per domain/axis: school, province, grade, term-history,
        # risk-tier, case-status, task-type, teacher-comment
        "student_current_count_by_school",
        "student_current_count_by_province",
        "student_current_count_by_grade",
        "student_historical_enrollment_count_by_term",
        "current_risk_count_by_tier",
        "case_count_by_workflow_status",
        "task_count_by_type",
        "teacher_comment_count_by_category",
    ],
    "count_filter_groupby": [
        "student_current_count_for_term",          # plain filtered total (no GROUP BY)
        "risk_current_count_by_school",            # filter + join + distinct
        "cases_without_tasks_by_school",           # NOT EXISTS shape
        "attendance_late_days_by_school_in_date_range",  # date-range filter
        "risk_current_consecutive_absence_threshold_by_school",
        "risk_current_without_open_case_by_school",
        "active_classrooms_without_subject_teacher_by_school",
        "case_without_review_count_by_school",
    ],
    "aggregation_groupby": [
        "student_average_term_gpa_by_grade",
        "student_current_classroom_occupancy_summary_by_school",
        "attendance_late_periods_by_school",
        "risk_current_average_score_by_school",
        "risk_current_attendance_summary_by_tier",
        "assistance_measure_count_summary_by_school",
        "active_average_subjects_per_teacher_by_school",
        # 8th slot: the retagged multi-join summary (below)
        "active_teacher_subject_summary_by_school",
    ],
    "ratio_groupby": [
        "attendance_rate_by_school_and_term",
        "attendance_rate_by_grade_and_term",
        "attendance_rate_by_classroom_and_term",
        "attendance_monthly_rate_in_date_range",
        "attendance_subject_rate_in_date_range",
        "attendance_rate_comparison_by_term",
        "attendance_session_recording_ratio_by_school",
        "teacher_concern_ratio_by_category",
    ],
    "having_threshold": [
        "student_current_schools_above_threshold",   # count > constant
        "high_risk_classrooms_above_threshold",      # having after filter
        "attendance_classrooms_below_rate_threshold",  # ratio < constant
        "case_count_with_multiple_tasks_by_school",
        "teacher_concern_classrooms_above_threshold",
        # 7th/8th slots: retagged multi-join counts (below)
        "active_teacher_count_by_subject",
        "active_classroom_count_by_subject",
    ],
    "time_groupby": [
        "task_count_by_thai_month",
        "attendance_absence_by_weekday",
        "risk_profile_freshness_by_school",
        "case_created_count_by_month",
        "task_submission_count_by_month",
        "task_created_count_by_week",
        "teacher_comment_monthly_count_by_concern_level",
        # 8th slot: authored below (attendance_delay_by_week)
    ],
    "ranking": [
        "top_high_risk_classrooms_per_school",       # ROW_NUMBER per school
        "attendance_top_absence_classrooms_per_school",
        # slots 3-8: authored below
    ],
}

# Retags: multi_join_aggregation -> primary shape (ADR 0007: join depth is a
# secondary metric, not a bucket). Where the receiver would overflow, the weakest
# overlapping member is demoted instead (see _weakest_demote).
RETAGS = {
    "active_teacher_subject_summary_by_school": "aggregation_groupby",
    "active_teacher_count_by_subject": "having_threshold",
    "active_classroom_count_by_subject": "having_threshold",
}

# Overlapping members demoted because a retagged item took their slot.
_WEAKEST_DEMOTE = {
    "aggregation_groupby": "attendance_recorded_student_days_by_school",
    "having_threshold": "case_count_with_multiple_tasks_by_school",
}

# time_groupby's 8th slot is an authored example whose id overlaps nothing.
_AUTHORED_TIME_FILL = "attendance_delay_periods_by_week"

# --- Authored examples (real STS table patterns; parameters pre-inlined) ------
SQL_FNS = (
    "SELECT school.id AS school_id, school.name AS school_name, "
    "COUNT(DISTINCT enrollment.person_uuid)::int AS student_count "
    "FROM student_term enrollment "
    "JOIN student_current_enrollment_resolution current_enrollment "
    "ON current_enrollment.person_uuid = enrollment.person_uuid "
    "AND current_enrollment.selected_student_uuid = enrollment.student_uuid "
    "AND current_enrollment.resolution_state = 'ACTIVE' "
    "JOIN schools school ON school.id = enrollment.\"SchoolID_Onec\" "
    "WHERE enrollment.deleted_at IS NULL AND school.school_status = 'ACTIVE'"
)
SQL_ATTENDANCE_JOIN = (
    "FROM attendance_day day "
    "JOIN student_term enrollment ON enrollment.student_uuid = day.student_uuid "
    "JOIN schools school ON school.id = enrollment.\"SchoolID_Onec\" "
    "WHERE day.\"AcademicYear_Onec\" = 2569 AND day.\"Semester_Onec\" = 1 "
    "AND enrollment.deleted_at IS NULL"
)

AUTHORED = [
    # --- ranking: top-N per group (ROW_NUMBER) -------------------------------
    {
        "id": "top_schools_by_current_student_count",
        "question": "โรงเรียนที่มีนักเรียนปัจจุบันมากที่สุด 10 อันดับแรก",
        "sql": (
            "WITH school_counts AS (" + SQL_FNS
            + " GROUP BY school.id, school.name), "
            "ranked AS (SELECT school_counts.school_id, school_counts.school_name, "
            "school_counts.student_count, ROW_NUMBER() OVER ("
            "ORDER BY school_counts.student_count DESC, school_counts.school_id ASC) "
            "AS rank_overall FROM school_counts) "
            "SELECT school_id, school_name, student_count, rank_overall "
            "FROM ranked WHERE rank_overall <= 10 "
            "ORDER BY rank_overall ASC"
        ),
        "category": "ranking_per_group",
        "dialect": "postgresql",
        "grain": "exactly 10 school rows (or fewer if fewer schools exist)",
        "schema_packs": ["student_enrollment"],
        "retrieval_tags": [
            "อันดับโรงเรียน", "มากที่สุด", "10 อันดับ", "top 10",
            "top n overall", "window function", "ROW_NUMBER",
        ],
    },
    {
        "id": "top_classrooms_by_attendance_rate_per_school",
        "question": "3 ห้องที่มีอัตราการมาเรียนสูงสุดของแต่ละโรงเรียน ปีการศึกษา 2569 ภาคเรียน 1",
        "sql": (
            "WITH classroom_rates AS ("
            "SELECT classroom.school_id, classroom.id AS classroom_id, "
            "classroom.room_name, ROUND(100.0 * COUNT(*) FILTER ("
            "WHERE day.\"AttendanceStatus\" IN (1, 3)) / NULLIF(COUNT(*) FILTER ("
            "WHERE day.\"AttendanceStatus\" <> 4), 0), 1) AS attendance_rate_percent "
            "FROM attendance_day day "
            "JOIN student_term enrollment ON enrollment.student_uuid = day.student_uuid "
            "JOIN school_classrooms classroom ON classroom.id = enrollment.classroom_id "
            "AND classroom.school_id = enrollment.\"SchoolID_Onec\" "
            "WHERE day.\"AcademicYear_Onec\" = 2569 AND day.\"Semester_Onec\" = 1 "
            "AND enrollment.deleted_at IS NULL AND classroom.deleted_at IS NULL "
            "GROUP BY classroom.school_id, classroom.id, classroom.room_name), "
            "ranked AS (SELECT classroom_rates.school_id, classroom_rates.classroom_id, "
            "classroom_rates.room_name, classroom_rates.attendance_rate_percent, "
            "ROW_NUMBER() OVER (PARTITION BY classroom_rates.school_id "
            "ORDER BY classroom_rates.attendance_rate_percent DESC NULLS LAST, "
            "classroom_rates.classroom_id ASC) AS rank_in_school FROM classroom_rates) "
            "SELECT school_id, classroom_id, room_name, attendance_rate_percent, "
            "rank_in_school FROM ranked WHERE rank_in_school <= 3 "
            "ORDER BY school_id ASC, rank_in_school ASC"
        ),
        "category": "ranking_per_group",
        "dialect": "postgresql",
        "grain": "up to 3 classroom rows per school",
        "schema_packs": ["student_enrollment", "attendance"],
        "retrieval_tags": [
            "ห้องที่มาเรียนสูงสุด", "อัตราการมาเรียนสูงสุด", "top 3 per school",
            "อันดับห้องเรียน", "window function", "ROW_NUMBER",
        ],
    },
    {
        "id": "top_schools_by_task_completion_ratio",
        "question": "5 โรงเรียนที่มีอัตรางานเสร็จสูงสุด",
        "sql": (
            "WITH school_completion AS ("
            "SELECT task.school_id, "
            "ROUND(100.0 * COUNT(*) FILTER (WHERE task.status = 'DONE') / "
            "NULLIF(COUNT(*), 0), 1) AS completion_rate_percent "
            "FROM tasks task WHERE task.deleted_at IS NULL "
            "GROUP BY task.school_id), "
            "ranked AS (SELECT school_completion.school_id, "
            "school_completion.completion_rate_percent, ROW_NUMBER() OVER ("
            "ORDER BY school_completion.completion_rate_percent DESC NULLS LAST, "
            "school_completion.school_id ASC) AS rank_overall FROM school_completion) "
            "SELECT school_id, completion_rate_percent, rank_overall "
            "FROM ranked WHERE rank_overall <= 5 ORDER BY rank_overall ASC"
        ),
        "category": "ranking_per_group",
        "dialect": "postgresql",
        "grain": "exactly 5 school rows (or fewer if fewer schools exist)",
        "schema_packs": ["task_assistance"],
        "retrieval_tags": [
            "อัตรางานเสร็จสูงสุด", "งานเสร็จมากที่สุด", "top 5",
            "อันดับโรงเรียน", "window function", "ROW_NUMBER",
        ],
    },
    {
        "id": "bottom_schools_by_attendance_rate",
        "question": "โรงเรียนที่มีอัตราการมาเรียนต่ำที่สุด 5 อันดับ",
        "sql": (
            "WITH school_rates AS ("
            "SELECT school.id AS school_id, school.name AS school_name, "
            "ROUND(100.0 * COUNT(*) FILTER (WHERE day.\"AttendanceStatus\" IN (1, 3)) "
            "/ NULLIF(COUNT(*) FILTER (WHERE day.\"AttendanceStatus\" <> 4), 0), 1) "
            "AS attendance_rate_percent "
            "FROM attendance_day day "
            "JOIN student_term enrollment ON enrollment.student_uuid = day.student_uuid "
            "JOIN schools school ON school.id = enrollment.\"SchoolID_Onec\" "
            "WHERE enrollment.deleted_at IS NULL "
            "GROUP BY school.id, school.name), "
            "ranked AS (SELECT school_rates.school_id, school_rates.school_name, "
            "school_rates.attendance_rate_percent, ROW_NUMBER() OVER ("
            "ORDER BY school_rates.attendance_rate_percent ASC NULLS LAST, "
            "school_rates.school_id ASC) AS rank_overall FROM school_rates) "
            "SELECT school_id, school_name, attendance_rate_percent, rank_overall "
            "FROM ranked WHERE rank_overall <= 5 ORDER BY rank_overall ASC"
        ),
        "category": "ranking_per_group",
        "dialect": "postgresql",
        "grain": "exactly 5 school rows (or fewer if fewer schools exist)",
        "schema_packs": ["student_enrollment", "attendance"],
        "retrieval_tags": [
            "อัตราการมาเรียนต่ำสุด", "โรงเรียนที่มาเรียนน้อยสุด", "bottom 5",
            "lowest", "window function", "ROW_NUMBER",
        ],
    },
    {
        # ranking_global: single top row without partition/window
        "id": "school_with_most_high_risk_students",
        "question": "โรงเรียนที่มีนักเรียนเสี่ยง HIGH ปัจจุบันมากที่สุด",
        "sql": (
            "SELECT school.id AS school_id, school.name AS school_name, "
            "COUNT(DISTINCT enrollment.person_uuid)::int AS high_risk_student_count "
            "FROM student_risk_profiles risk "
            "JOIN student_term enrollment ON enrollment.student_uuid = risk.student_uuid "
            "JOIN student_current_enrollment_resolution current_enrollment "
            "ON current_enrollment.person_uuid = enrollment.person_uuid "
            "AND current_enrollment.selected_student_uuid = enrollment.student_uuid "
            "AND current_enrollment.resolution_state = 'ACTIVE' "
            "JOIN schools school ON school.id = risk.school_id "
            "WHERE risk.risk_tier = 'HIGH' AND enrollment.deleted_at IS NULL "
            "GROUP BY school.id, school.name "
            "ORDER BY high_risk_student_count DESC, school.id ASC LIMIT 1"
        ),
        "category": "ranking_global",
        "dialect": "postgresql",
        "grain": "one row — the top school only",
        "schema_packs": ["student_enrollment", "risk_case"],
        "retrieval_tags": [
            "โรงเรียนเสี่ยงสูงสุด", "มากที่สุด", "top 1", "มากที่สุดโรงเรียนเดียว",
            "LIMIT 1", "global ranking",
        ],
    },
    {
        # ranking via a threshold on a rank value: top-N by explicit ordering
        "id": "top_grades_by_absence_count",
        "question": "ระดับชั้นที่มีวันขาดเรียนมากที่สุด 3 อันดับ",
        "sql": (
            "SELECT grade.id AS grade_level_id, grade.label AS grade_label, "
            "COUNT(*) FILTER (WHERE day.\"AttendanceStatus\" = 2)::int "
            "AS absent_student_day_count "
            "FROM attendance_day day "
            "JOIN student_term enrollment ON enrollment.student_uuid = day.student_uuid "
            "JOIN grade_levels grade ON grade.id = enrollment.\"GradeLevelID_Onec\" "
            "WHERE day.\"AcademicYear_Onec\" = 2569 AND day.\"Semester_Onec\" = 1 "
            "AND enrollment.deleted_at IS NULL "
            "GROUP BY grade.id, grade.label "
            "ORDER BY absent_student_day_count DESC, grade.id ASC LIMIT 3"
        ),
        "category": "ranking_global",
        "dialect": "postgresql",
        "grain": "up to 3 grade-level rows",
        "schema_packs": ["student_enrollment", "attendance"],
        "retrieval_tags": [
            "ชั้นที่ขาดเรียนมากสุด", "อันดับระดับชั้น", "top 3",
            "ORDER BY DESC LIMIT", "ranking",
        ],
    },
    # --- having_threshold: ratio above a constant ----------------------------
    {
        "id": "classrooms_with_attendance_rate_below_75",
        "question": "ห้องเรียนที่มีอัตราการมาเรียนต่ำกว่า 75 เปอร์เซ็นต์ ปีการศึกษา 2569 ภาคเรียน 1",
        "sql": (
            "SELECT classroom.school_id, classroom.id AS classroom_id, "
            "classroom.room_name, "
            "ROUND(100.0 * COUNT(*) FILTER (WHERE day.\"AttendanceStatus\" IN (1, 3)) "
            "/ NULLIF(COUNT(*) FILTER (WHERE day.\"AttendanceStatus\" <> 4), 0), 1) "
            "AS attendance_rate_percent "
            "FROM attendance_day day "
            "JOIN student_term enrollment ON enrollment.student_uuid = day.student_uuid "
            "JOIN school_classrooms classroom ON classroom.id = enrollment.classroom_id "
            "AND classroom.school_id = enrollment.\"SchoolID_Onec\" "
            "WHERE day.\"AcademicYear_Onec\" = 2569 AND day.\"Semester_Onec\" = 1 "
            "AND enrollment.deleted_at IS NULL AND classroom.deleted_at IS NULL "
            "GROUP BY classroom.school_id, classroom.id, classroom.room_name "
            "HAVING (100.0 * COUNT(*) FILTER (WHERE day.\"AttendanceStatus\" IN (1, 3)) "
            "/ NULLIF(COUNT(*) FILTER (WHERE day.\"AttendanceStatus\" <> 4), 0)) < 75 "
            "ORDER BY attendance_rate_percent ASC NULLS LAST, classroom.id ASC"
        ),
        "category": "having_ratio",
        "dialect": "postgresql",
        "grain": "one row per classroom below the threshold",
        "schema_packs": ["student_enrollment", "attendance"],
        "retrieval_tags": [
            "ห้องมาเรียนต่ำกว่าเกณฑ์", "อัตราการมาเรียนต่ำ", "HAVING",
            "ต่ำกว่า 75", "threshold",
        ],
    },
    # --- time_groupby: weekday bucket ----------------------------------------
    {
        "id": "attendance_delay_periods_by_week",
        "question": "จำนวนคาบที่มาสายรวมแยกตามสัปดาห์ ตั้งแต่ 1 มิถุนายน 2026 ถึง 31 สิงหาคม 2026",
        "sql": (
            "SELECT date_trunc('week', day.\"AttendanceDate\")::date AS week_start, "
            "SUM(day.late_periods)::bigint AS late_period_count "
            "FROM attendance_day day "
            "WHERE day.\"AttendanceDate\" >= '2026-06-01'::date "
            "AND day.\"AttendanceDate\" < '2026-09-01'::date "
            "GROUP BY week_start ORDER BY week_start ASC"
        ),
        "category": "time_groupby",
        "dialect": "postgresql",
        "grain": "one row per ISO week in the range",
        "schema_packs": ["attendance"],
        "retrieval_tags": [
            "คาบสายรายสัปดาห์", "สายรวมรายสัปดาห์", "date_trunc week",
            "แยกตามสัปดาห์", "ช่วงวันที่",
        ],
    },
    # --- count_groupby 8th slot kept from KEEP["count_groupby"] is file-resident;
    # time_groupby's 8th slot is this authored example (see _AUTHORED_TIME_FILL).
]

# --- Clarify / refusal exemplars (no SQL; outside the shape quotas) -----------
EXEMPLARS = [
    {
        "id": "clarify_vague_risk_measure",
        "question": "โรงเรียนที่เสี่ยงสุดคือไหน",
        "sql": "",
        "category": "clarification_exemplar",
        "expected_answer_type": "clarification",
        "expected_message": (
            "คำถามนี้ยังระบุไม่ชัดครับ — 'เสี่ยง' หมายถึงตามตัวชี้วัดใด: "
            "ระดับความเสี่ยง HIGH, คะแนนความเสี่ยงเฉลี่ย, การขาดเรียนต่อเนื่อง, "
            "หรืออัตราการมาเรียนต่ำ? ระบุตัวชี้วัดและช่วงเวลาที่ต้องการได้เลยครับ"
        ),
        "dialect": "postgresql",
        "grain": "no query — asks the user to pick a risk measure",
        "schema_packs": ["student_enrollment", "risk_case"],
        "retrieval_tags": [
            "เสี่ยงสุด", "ไม่ชัด", "กำกวม", "ถามกลับ", "clarification",
            "ตัวชี้วัดความเสี่ยง",
        ],
    },
    {
        "id": "clarify_vague_time_range",
        "question": "จำนวนนักเรียนที่มาสายช่วงนี้เท่าไหร่",
        "sql": "",
        "category": "clarification_exemplar",
        "expected_answer_type": "clarification",
        "expected_message": (
            "ต้องการดูช่วงเวลาใดครับ — ภาคเรียนไหน หรือระบุวันที่เริ่มต้น–สิ้นสุด "
            "(เช่น ตั้งแต่ 1 มิถุนายน ถึง 31 สิงหาคม 2026) เพื่อให้ผลลัพธ์ตรงกับที่ต้องการครับ"
        ),
        "dialect": "postgresql",
        "grain": "no query — asks the user for a date range",
        "schema_packs": ["attendance"],
        "retrieval_tags": [
            "ช่วงนี้", "ไม่ระบุช่วงเวลา", "ถามกลับ", "clarification", "ช่วงวันที่",
        ],
    },
    {
        "id": "clarify_ambiguous_grouping",
        "question": "เปรียบเทียบผลการเรียนแต่ละกลุ่มหน่อย",
        "sql": "",
        "category": "clarification_exemplar",
        "expected_answer_type": "clarification",
        "expected_message": (
            "'ผลการเรียน' อยากดูที่ระดับใด และ 'กลุ่ม' หมายถึงอะไรครับ — "
            "แยกตามระดับชั้น ห้องเรียน โรงเรียน หรือสถานะนักเรียน "
            "และต้องการค่าเฉลี่ย GPA หรือจำนวนผ่าน/ไม่ผ่าน?"
        ),
        "dialect": "postgresql",
        "grain": "no query — asks the user to pick grouping and measure",
        "schema_packs": ["student_enrollment"],
        "retrieval_tags": [
            "ผลการเรียน", "กลุ่ม", "กำกวม", "ถามกลับ", "clarification", "GPA",
        ],
    },
    {
        "id": "refusal_pii_student_roster",
        "question": "ขอรายชื่อนักเรียนทั้งหมดในโรงเรียนบ้านห้วยทราย",
        "sql": "",
        "category": "refusal_exemplar",
        "expected_answer_type": "refusal",
        "expected_message": (
            "ขออภัยครับ ระบบนี้ให้บริการเฉพาะข้อมูลเชิงสถิติและการวิเคราะห์รวม "
            "ไม่สามารถแสดงรายชื่อหรือข้อมูลส่วนบุคคลของนักเรียนรายบุคคลได้ "
            "หากต้องการจำนวนนักเรียนแยกตามเกณฑ์ต่าง ๆ ยินดีช่วยค้นหาให้ครับ"
        ),
        "dialect": "postgresql",
        "grain": "no query — personal data is out of scope",
        "schema_packs": ["student_enrollment"],
        "retrieval_tags": [
            "รายชื่อนักเรียน", "ข้อมูลส่วนบุคคล", "ปฏิเสธ", "refusal", "PII",
            "นักเรียนรายบุคคล",
        ],
    },
    {
        "id": "refusal_pii_named_student_lookup",
        "question": "ขอข้อมูลนักเรียนชื่อ ด.ต. สมศรี ในโรงเรียนบ้านห้วยทราย",
        "sql": "",
        "category": "refusal_exemplar",
        "expected_answer_type": "refusal",
        "expected_message": (
            "ขออภัยครับ ระบบไม่สามารถค้นหาหรือแสดงข้อมูลของนักเรียนรายบุคคลได้ "
            "เนื่องด้วยความเป็นส่วนตัวของข้อมูล "
            "หากต้องการสถิติระดับห้องเรียนหรือโรงเรียน ระบบสามารถช่วยได้ครับ"
        ),
        "dialect": "postgresql",
        "grain": "no query — personal data is out of scope",
        "schema_packs": ["student_enrollment"],
        "retrieval_tags": [
            "ข้อมูลนักเรียน", "รายบุคคล", "ปฏิเสธ", "refusal", "PII",
            "ค้นหานักเรียน",
        ],
    },
    {
        "id": "refusal_out_of_scope_write_request",
        "question": "อัปเดตสถานะนักเรียนเป็นปัจจุบันให้หน่อย",
        "sql": "",
        "category": "refusal_exemplar",
        "expected_answer_type": "refusal",
        "expected_message": (
            "ระบบนี้เป็นฐานข้อมูลแบบอ่านอย่างเดียวสำหรับการวิเคราะห์ "
            "จึงไม่สามารถแก้ไข เพิ่ม หรือลบข้อมูลได้ครับ "
            "หากต้องการเปลี่ยนแปลงข้อมูล กรุณาใช้ระบบงานประจำที่รองรับการบันทึกข้อมูล"
        ),
        "dialect": "postgresql",
        "grain": "no query — the datasource is read-only",
        "schema_packs": [],
        "retrieval_tags": [
            "อัปเดต", "แก้ไขข้อมูล", "เขียนข้อมูล", "ปฏิเสธ", "refusal",
            "read-only",
        ],
    },
]


def main():
    dry_run = "--dry-run" in sys.argv
    corpus = json.load(open(CORPUS_PATH, encoding="utf-8"))
    examples = corpus["examples"]
    by_id = {e["id"]: e for e in examples}

    # Idempotence guards
    exemplar_ids = {e["id"] for e in examples if e["category"] in
                    ("clarification_exemplar", "refusal_exemplar")}
    if exemplar_ids:
        print("Corpus already contains exemplar block — refusing to rebalance twice.")
        return 1
    if os.path.exists(ARCHIVE_PATH):
        print(f"Archive already exists: {ARCHIVE_PATH} — refusing to overwrite.")
        return 1

    # Dry-run validation of the policy tables
    known_keep = {i for ids in KEEP.values() for i in ids}
    unknown = known_keep - set(by_id)
    if unknown:
        print(f"ERROR: KEEP references unknown ids: {sorted(unknown)}")
        return 2

    survivors, demoted = [], []
    retag_applied = set()
    for e in examples:
        eid, cat = e["id"], e["category"]
        target = RETAGS.get(eid)
        if target and eid in KEEP.get(target, []):
            e = dict(e, category=target)  # retag to primary shape (ADR 0007)
            retag_applied.add(eid)
            survivors.append(e)
            continue
        if eid in known_keep:
            survivors.append(e)
            continue
        demoted.append(e)

    # Retags must all have fired
    if retag_applied != set(RETAGS):
        print(f"ERROR: retags not covered by KEEP: {set(RETAGS) - retag_applied}")
        return 2

    authored = []
    for a in AUTHORED:
        if a["id"] in by_id:
            print(f"ERROR: authored id already exists: {a['id']}")
            return 2
        authored.append(a)

    balanced = survivors + authored + EXEMPLARS

    # Verify against the audit's own counting before writing
    sys.path.insert(0, ROOT)
    from eval.distribution_audit import (
        CATEGORY_BUCKETS, count_buckets, count_exemplar_block,
    )
    buckets, unmapped = count_buckets(balanced)
    off = {b: (buckets[b], buckets[b] - BUCKET_QUOTA) for b in CATEGORY_BUCKETS
           if buckets[b] != BUCKET_QUOTA}
    if off:
        print(f"ERROR: post-rebalance buckets off quota: {off}")
        print("Adjust KEEP / AUTHORED so every bucket lands on 8.")
        return 2
    if unmapped:
        print(f"ERROR: unmapped categories after rebalance: {unmapped}")
        return 2
    block = count_exemplar_block(balanced)
    if block != {"clarify": CLARIFY_REFUSAL_QUOTA, "refusal": CLARIFY_REFUSAL_QUOTA}:
        print(f"ERROR: exemplar block wrong: {block}")
        return 2
    # Corpus items must never carry the Golden set's membership markers
    # (source_tag / gold_sql) — the two sets stay disjoint by construction.
    leaky = [e["id"] for e in balanced if "source_tag" in e or "gold_sql" in e]
    if leaky:
        print(f"ERROR: corpus items carrying golden-set markers: {leaky}")
        return 2

    # --- Write outputs (only after every guard passes) -------------------------
    if dry_run:
        print(f"DRY RUN: would keep {len(survivors)}, author {len(authored)}, "
              f"add {len(EXEMPLARS)} exemplars, demote {len(demoted)}.")
        return 0
    archive_corpus = {
        "description": (
            "Archive of count-monoculture examples demoted during the ADR 0007 "
            "rebalance. Kept for future re-balancing; never loaded by retrieval."
        ),
        "version": corpus["version"],
        "source": "TEXT_TO_SQL_STS_RAG_EXAMPLES.json (pre-rebalance)",
        "examples": demoted,
    }
    with open(ARCHIVE_PATH, "w", encoding="utf-8") as f:
        json.dump(archive_corpus, f, ensure_ascii=False, indent=2)

    new_corpus = dict(corpus)
    new_corpus["description"] = (
        "STS few-shot Example set, rebalanced to ADR 0007 quotas "
        "(8 per Category bucket + 3 clarify + 3 refusal exemplars). "
        "Surplus examples live in TEXT_TO_SQL_STS_RAG_EXAMPLES_ARCHIVE.json."
    )
    new_corpus["version"] = "3.0"
    new_corpus["examples"] = balanced
    with open(CORPUS_PATH, "w", encoding="utf-8") as f:
        json.dump(new_corpus, f, ensure_ascii=False, indent=2)

    print(f"survivors {len(survivors)} + authored {len(authored)} + "
          f"exemplars {len(EXEMPLARS)} = {len(balanced)}")
    print(f"demoted to archive: {len(demoted)}")
    for b in CATEGORY_BUCKETS:
        print(f"  {b}: {buckets[b]}")
    print("post-rebalance audit would PASS (all buckets on quota, block present)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
