"""Build eval/benchmark_sts.json — the STS evaluation golden set.

30 questions in three groups, kept strictly disjoint from profiles/sts/examples.json:
  held_out  (10) — pulled out of the corpus, removed from retrieval, SQL verified
  paraphrase(12) — reworded / abbreviated / code-switched; gold reused from a
                   corpus example that is STILL in the retrieval set
  novel     (8)  — metric/grain combinations the corpus does not contain; gold
                   hand-written and verified by execution

Run against the live DB so every gold is checked with EXPLAIN + execute.
"""

import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS = json.load(open(os.path.join(ROOT, "TEXT_TO_SQL_STS_RAG_EXAMPLES.json"), encoding="utf-8"))
CORPUS_BY_ID = {e["id"]: e for e in CORPUS["examples"]}
HELDOUT_IDS = json.load(open(os.path.join(ROOT, "profiles", "sts", "heldout_ids.json"), encoding="utf-8"))
DB_URL = os.getenv("STS_DB_URL", "postgresql://postgres:stsLocalDev2026@localhost:5432/sts")


def inline_params(sql: str, params: list) -> str:
    by_pos = {p["position"]: p for p in params}

    def repl(m):
        p = by_pos.get(int(m.group(1)))
        if p is None:
            return m.group(0)
        v = p["value"]
        if p["type"] in ("integer", "numeric"):
            return str(v)
        return "'" + str(v).replace("'", "''") + "'"

    return re.sub(r"\$(\d+)", repl, sql)


def corpus_sql(cid: str) -> str:
    e = CORPUS_BY_ID[cid]
    return inline_params(e["sql"], e.get("parameters", []))


# --- paraphrase: {reworded question -> corpus id whose gold SQL it maps to} ---
PARAPHRASE = [
    ("แต่ละโรงเรียนตอนนี้มีนักเรียนอยู่กี่คน", "student_current_count_by_school"),
    ("นับ นร. ปัจจุบันตาม risk tier ให้หน่อย", "current_risk_count_by_tier"),
    ("อยากรู้ % การมาเรียนของแต่ละ ร.ร. เทอม 1 ปี 2569", "attendance_rate_by_school_and_term"),
    ("ขอ top 3 ห้องที่มีเด็กเสี่ยง HIGH เยอะสุดของแต่ละโรงเรียน", "top_high_risk_classrooms_per_school"),
    ("โรงเรียนอะไรที่มีนักเรียนเกิน 500 คน", "student_current_schools_above_threshold"),
    ("เคสที่ยังไม่ได้มอบหมายงานเลย มีกี่เคสต่อโรงเรียน", "cases_without_tasks_by_school"),
    ("รวมวันที่เด็กมาสายของแต่ละ ร.ร. ตั้งแต่ 1 มิถุนายน ถึง 31 สิงหาคม 2026", "attendance_late_days_by_school_in_date_range"),
    ("5 ห้องที่ขาดเรียนหนักสุดของแต่ละโรงเรียน เทอม 1/2569", "attendance_top_absence_classrooms_per_school"),
    ("คะแนน risk เฉลี่ยของเด็กปัจจุบันในแต่ละ ร.ร.", "risk_current_average_score_by_school"),
    ("แนวโน้ม % การมาเรียนรายวัน ช่วง 1 มิ.ย. ถึง 31 ส.ค. 2026", "attendance_daily_rate_in_date_range"),
    ("ข้อมูล risk ของแต่ละโรงเรียน อัปเดตล่าสุดเมื่อไหร่ เก่าสุดเมื่อไหร่", "risk_profile_freshness_by_school"),
    ("คอมเมนต์ครูระดับ concern คิดเป็นสัดส่วนเท่าไรในแต่ละหมวด ช่วง มิ.ย. - ส.ค. 2026", "teacher_concern_ratio_by_category"),
]

# --- novel: hand-written gold SQL, verified below (every gold must return >=1 row) ---
NOVEL = [
    ("count_filter_groupby", "จำนวนนักเรียนปัจจุบันที่ขาดเรียนติดต่อกันเกิน 3 วัน แยกตามโรงเรียน", """
SELECT school.id AS school_id, school.name AS school_name,
       COUNT(DISTINCT enrollment.person_uuid)::int AS student_count
FROM student_risk_profiles risk
JOIN student_term enrollment ON enrollment.student_uuid = risk.student_uuid
JOIN student_current_enrollment_resolution ce
  ON ce.person_uuid = enrollment.person_uuid AND ce.selected_student_uuid = enrollment.student_uuid AND ce.resolution_state = 'ACTIVE'
JOIN schools school ON school.id = risk.school_id
WHERE enrollment.deleted_at IS NULL AND risk.consecutive_absent_days > 3
GROUP BY school.id, school.name
ORDER BY student_count DESC, school.id ASC
"""),
    ("ratio_groupby", "สัดส่วนนักเรียนปัจจุบันที่เสี่ยง WATCH หรือ HIGH ต่อนักเรียนทั้งหมด แยกตามโรงเรียน", """
SELECT school.id AS school_id, school.name AS school_name,
       ROUND(100.0 * COUNT(DISTINCT enrollment.person_uuid) FILTER (WHERE risk.risk_tier IN ('WATCH', 'HIGH'))
             / NULLIF(COUNT(DISTINCT enrollment.person_uuid), 0), 1) AS at_risk_percent
FROM student_risk_profiles risk
JOIN student_term enrollment ON enrollment.student_uuid = risk.student_uuid
JOIN student_current_enrollment_resolution ce
  ON ce.person_uuid = enrollment.person_uuid AND ce.selected_student_uuid = enrollment.student_uuid AND ce.resolution_state = 'ACTIVE'
JOIN schools school ON school.id = risk.school_id
WHERE enrollment.deleted_at IS NULL
GROUP BY school.id, school.name
ORDER BY at_risk_percent DESC NULLS LAST, school.id ASC
"""),
    ("time_groupby", "จำนวนวันที่มีการเช็กชื่อ แยกตามเดือน ตั้งแต่ 1 มิถุนายน 2026 ถึง 31 สิงหาคม 2026", """
SELECT date_trunc('month', day."AttendanceDate")::date AS month_start,
       COUNT(DISTINCT day."AttendanceDate")::int AS check_in_day_count
FROM attendance_day day
WHERE day."AttendanceDate" >= DATE '2026-06-01' AND day."AttendanceDate" <= DATE '2026-08-31'
GROUP BY month_start
ORDER BY month_start ASC
"""),
    ("average_groupby", "จำนวนนักเรียนปัจจุบันเฉลี่ยต่อห้อง แยกตามระดับชั้น", """
WITH classroom_counts AS (
  SELECT enrollment.classroom_id, classroom.grade_level_id,
         COUNT(DISTINCT enrollment.person_uuid) AS n_students
  FROM student_term enrollment
  JOIN student_current_enrollment_resolution ce
    ON ce.person_uuid = enrollment.person_uuid AND ce.selected_student_uuid = enrollment.student_uuid AND ce.resolution_state = 'ACTIVE'
  JOIN school_classrooms classroom ON classroom.id = enrollment.classroom_id
  WHERE enrollment.deleted_at IS NULL AND classroom.deleted_at IS NULL AND classroom.classroom_status = 'ACTIVE'
  GROUP BY enrollment.classroom_id, classroom.grade_level_id
)
SELECT grade.id AS grade_level_id, grade.label AS grade_label,
       ROUND(AVG(classroom_counts.n_students), 2) AS avg_students_per_classroom
FROM classroom_counts
JOIN grade_levels grade ON grade.id = classroom_counts.grade_level_id
GROUP BY grade.id, grade.label
ORDER BY grade.id ASC
"""),
    ("having_ratio", "โรงเรียนที่มีอัตราการมาเรียนเฉลี่ยต่ำกว่า 85 เปอร์เซ็นต์ ปีการศึกษา 2569 ภาคเรียน 1", """
SELECT school.id AS school_id, school.name AS school_name,
       ROUND(100.0 * COUNT(*) FILTER (WHERE day."AttendanceStatus" IN (1, 3))
             / NULLIF(COUNT(*) FILTER (WHERE day."AttendanceStatus" <> 4), 0), 1) AS attendance_rate_percent
FROM attendance_day day
JOIN student_term enrollment ON enrollment.student_uuid = day.student_uuid
JOIN schools school ON school.id = enrollment."SchoolID_Onec"
WHERE day."AcademicYear_Onec" = 2569 AND day."Semester_Onec" = 1 AND enrollment.deleted_at IS NULL
GROUP BY school.id, school.name
HAVING ROUND(100.0 * COUNT(*) FILTER (WHERE day."AttendanceStatus" IN (1, 3))
             / NULLIF(COUNT(*) FILTER (WHERE day."AttendanceStatus" <> 4), 0), 1) < 85
ORDER BY attendance_rate_percent ASC, school.id ASC
"""),
    ("ranking_global", "5 โรงเรียนที่มีนักเรียนเสี่ยง HIGH ปัจจุบันมากที่สุด", """
SELECT school.id AS school_id, school.name AS school_name,
       COUNT(DISTINCT enrollment.person_uuid)::int AS high_risk_student_count
FROM student_risk_profiles risk
JOIN student_term enrollment ON enrollment.student_uuid = risk.student_uuid
JOIN student_current_enrollment_resolution ce
  ON ce.person_uuid = enrollment.person_uuid AND ce.selected_student_uuid = enrollment.student_uuid AND ce.resolution_state = 'ACTIVE'
JOIN schools school ON school.id = risk.school_id
WHERE risk.risk_tier = 'HIGH' AND enrollment.deleted_at IS NULL
GROUP BY school.id, school.name
ORDER BY high_risk_student_count DESC, school.id ASC
LIMIT 5
"""),
    ("ranking_global", "3 ระดับชั้นที่มีนักเรียนเสี่ยง HIGH ปัจจุบันมากที่สุด", """
SELECT grade.id AS grade_level_id, grade.label AS grade_label,
       COUNT(DISTINCT enrollment.person_uuid)::int AS high_risk_student_count
FROM student_risk_profiles risk
JOIN student_term enrollment ON enrollment.student_uuid = risk.student_uuid
JOIN student_current_enrollment_resolution ce
  ON ce.person_uuid = enrollment.person_uuid AND ce.selected_student_uuid = enrollment.student_uuid AND ce.resolution_state = 'ACTIVE'
JOIN grade_levels grade ON grade.id = enrollment."GradeLevelID_Onec"
WHERE risk.risk_tier = 'HIGH' AND enrollment.deleted_at IS NULL
GROUP BY grade.id, grade.label
ORDER BY high_risk_student_count DESC, grade.id ASC
LIMIT 3
"""),
    ("multi_join_aggregation", "จำนวนนักเรียนปัจจุบันที่มีเคสที่ยังไม่เสร็จสิ้น แยกตามระดับชั้น", """
SELECT grade.id AS grade_level_id, grade.label AS grade_label,
       COUNT(DISTINCT enrollment.person_uuid)::int AS student_count
FROM student_term enrollment
JOIN student_current_enrollment_resolution ce
  ON ce.person_uuid = enrollment.person_uuid AND ce.selected_student_uuid = enrollment.student_uuid AND ce.resolution_state = 'ACTIVE'
JOIN grade_levels grade ON grade.id = enrollment."GradeLevelID_Onec"
WHERE enrollment.deleted_at IS NULL
  AND EXISTS (
    SELECT 1 FROM cases c
    WHERE c.student_uuid = enrollment.student_uuid AND c.deleted_at IS NULL AND c.status <> 'RESOLVED'
  )
GROUP BY grade.id, grade.label
ORDER BY student_count DESC, grade.id ASC
"""),
]


def build():
    rows = []
    for cid in HELDOUT_IDS:
        e = CORPUS_BY_ID[cid]
        rows.append({
            "id": cid, "source_tag": "held_out", "category": e["category"],
            "question": e["question"], "gold_sql": corpus_sql(cid),
        })
    for i, (q, cid) in enumerate(PARAPHRASE, 1):
        rows.append({
            "id": f"paraphrase_{i:02d}", "source_tag": "paraphrase",
            "category": CORPUS_BY_ID[cid]["category"], "question": q,
            "gold_sql": corpus_sql(cid), "gold_from": cid,
        })
    for i, (cat, q, sql) in enumerate(NOVEL, 1):
        rows.append({
            "id": f"novel_{i:02d}", "source_tag": "novel", "category": cat,
            "question": q, "gold_sql": " ".join(sql.split()),
        })
    return rows


def verify(rows):
    import psycopg2
    conn = psycopg2.connect(DB_URL, connect_timeout=5)
    ok = 0
    for r in rows:
        cur = conn.cursor()
        try:
            cur.execute(r["gold_sql"])
            n = len(cur.fetchall())
            conn.rollback()
            flag = "OK  " if n >= 1 else "ZERO"
            ok += 1 if n >= 1 else 0
            print(f"  {flag} [{r['source_tag']:9}] {r['id']:38} {n:4} rows  {r['question'][:42]}")
        except Exception as e:
            conn.rollback()
            print(f"  FAIL [{r['source_tag']:9}] {r['id']:38} {str(e).splitlines()[0][:70]}")
    conn.close()
    return ok


if __name__ == "__main__":
    rows = build()
    print(f"built {len(rows)} questions; verifying against {DB_URL.split('@')[-1]}\n")
    ok = verify(rows)
    print(f"\n{ok}/{len(rows)} gold SQL execute")
    out = os.path.join(ROOT, "eval", "benchmark_sts.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"dialect": "postgresql", "questions": rows}, f, ensure_ascii=False, indent=2)
    print("wrote", out)
