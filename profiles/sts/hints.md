<!--
STS (Student Tracking System) prompt hints — Tier-1 adoption of TEXT_TO_SQL_STS_GUIDE.md
sections 4-7 and 10. PostgreSQL only. Aggregate analytical questions.
The full scope-enforcement / PII gateway in the guide is out of scope here
(see docs/adr/0002-sts-guide-tier-1-adoption.md).
-->

### PostgreSQL dialect (this database is PostgreSQL — never use MySQL/SQLite functions)
- Date parts: `EXTRACT(YEAR|MONTH|QUARTER FROM col)`.
- Time buckets: `date_trunc('day'|'week'|'month'|'quarter'|'year', col)`.
- Thai-local grouping on `timestamptz`: `date_trunc('month', col AT TIME ZONE 'Asia/Bangkok')`.
- Nullable name parts: `concat_ws(' ', a, b, c)`. Case-insensitive search: `col ILIKE '%x%'`.
- Conditional aggregation: `COUNT(*) FILTER (WHERE cond)`.
- Safe division / percent: `ROUND(100.0 * num / NULLIF(den, 0), 1)` — never integer division.
- Half-open ranges on `timestamptz`: `col >= start AND col < end`.
- Never use `YEAR()`, `MONTH()`, `DATEDIFF()`, `IFNULL()`, `strftime()`, `julianday()`.

### STS core semantics
- **"นักเรียน" / "นักเรียนปัจจุบัน"** = the single active current enrollment. Join
  `student_current_enrollment_resolution` on `person_uuid` and `selected_student_uuid = student_term.student_uuid`
  with `resolution_state = 'ACTIVE'`. Do NOT use `student_status_code = 10` as a substitute.
  Historical / "เคยเรียน" / "ทั้งหมดในประวัติ" questions are the exception — then count people with
  `COUNT(DISTINCT person_uuid)`.
- One `student_term` row is an **enrollment** (`student_uuid`), not necessarily one person (`person_uuid`).
- Attendance source of truth by grain:
  - one student / session → `attendance_effective_records`
  - one student / day, "อัตราการมาเรียน", วันขาด, ขาดต่อเนื่อง → `attendance_day`
  - one student / subject / day → `attendance_subject_day`
  - session counts / เปิด-ปิดเช็กชื่อ → `attendance_sessions`
  - Do NOT derive attendance totals from `attendance_exceptions` — missing exception = present, materialized only in the effective views.
- Attendance status codes: `1` มาเรียน, `2` ขาด, `3` มาสาย, `4` ลา.
  "มาเรียน/ถือว่ามา" → `IN (1, 3)`. "วันที่วัดได้" (denominator of attendance rate) → status `<> 4`.
- Current student risk = `student_risk_profiles.risk_tier` ∈ `HIGH` (เสี่ยง), `WATCH` (เฝ้าระวัง), `NORMAL`.
  Do NOT substitute `cases.risk_tier` (different semantics). `student_risk_profiles` is a snapshot —
  if freshness is asked, use its `profile_calculated_at`; never imply the query recomputed it.
- Case workflow status (`cases.workflow_status`): `OPEN` รอมอบหมาย, `IN_PROGRESS` รอติดตาม,
  `PENDING_REVIEW` รอพิจารณา, `RESOLVED` เสร็จสิ้น, `STUDENT_NOT_FOUND` ไม่พบนักเรียน.
  Workflow phase: `FOLLOW_UP` ติดตาม, `ASSISTANCE` ให้ความช่วยเหลือ.
- Task type (`tasks.task_type`): `VISIT` ลงพื้นที่ติดตาม, `ASSIST` ให้ความช่วยเหลือ.
- Academic year / semester come from the academic columns (`school_terms.academic_year`,
  `student_term."AcademicYear_Onec"` / `"Semester_Onec"`), NOT from the Gregorian year and never by adding 543.
  Current academic term = `school_terms.status = 'ACTIVE'` per school.
- Every operational fact with `deleted_at` gets `deleted_at IS NULL` unless the user explicitly asks for
  deleted rows. Membership / offering / assignment tables filter their `ACTIVE` status when the question is
  present tense ("ครูที่สอน", "วิชาที่เปิด", "ห้องปัจจุบัน"). Do not let a current-status filter erase a
  historical fact.

### Canonical join paths (use these FKs; do not guess joins from similar-looking names)
```
schools.id
  ├─ school_terms.school_id
  │    └─ school_classrooms.school_term_id
  ├─ student_term."SchoolID_Onec"
  ├─ school_teacher_memberships.school_id
  ├─ school_subjects.school_id
  └─ cases.school_id

student_person.person_uuid
  └─ student_term.person_uuid
       ├─ student_current_enrollment_resolution.selected_student_uuid = student_term.student_uuid
       ├─ attendance_* .student_uuid
       ├─ student_risk_profiles.student_uuid
       └─ cases.student_uuid

school_classrooms.id
  ├─ student_term.classroom_id
  ├─ classroom_subjects.classroom_id
  ├─ classroom_homeroom_teacher_assignments.classroom_id
  └─ attendance_sessions.classroom_id

subjects.id
  └─ school_subjects.subject_id
       └─ classroom_subjects.school_subject_id

teachers.id
  └─ school_teacher_memberships.teacher_id
       └─ classroom_homeroom_teacher_assignments.teacher_membership_id

cases.id
  ├─ case_risk_signals.case_id
  ├─ case_reviews.case_id
  ├─ case_referrals.case_id
  └─ tasks.case_id
       ├─ task_links.task_id
       │    └─ task_submissions.task_link_id
       └─ task_assistance_measures.task_id
```
When a child has both an ID FK and a `school_id`, join on both to fail closed on the school boundary.

### Counting and grain
- First decide the output grain and which identity is being counted.
- People → `COUNT(DISTINCT person_uuid)`. Enrollments → `COUNT(DISTINCT student_uuid)`.
  Sessions → `COUNT(DISTINCT attendance_sessions.id)`. Cases → `COUNT(DISTINCT cases.id)`.
  Tasks → `COUNT(DISTINCT tasks.id)`. Teachers → `COUNT(DISTINCT teachers.id)`.
- Pre-aggregate one-to-many child tables (CTE) before joining the parent — never
  `JOIN cases → tasks → task_links` then `COUNT(cases.id)` without `DISTINCT`.
- A ratio aggregates numerator and denominator at the same grain, `* 100.0`, `NULLIF` the denominator.
- "อันดับ N ของแต่ละ<กลุ่ม>" → window function `ROW_NUMBER()/RANK()` partitioned by that group, not a global `LIMIT N`.
- Always add a deterministic tie-breaker to `ORDER BY` (e.g. `, id ASC`).

### Thai intent hints
- จำนวน / กี่... → `COUNT` of the correct `DISTINCT` identity.  รวม / ยอดรวม → `SUM`.  เฉลี่ย / ค่าเฉลี่ย → `AVG`.
- แต่ละ / แยกตาม / จำแนกตาม → `GROUP BY` that entity.
- ที่มี...มากกว่า / เฉพาะกลุ่มที่ → `HAVING` after aggregation.
- มากที่สุด / สูงสุด → `ORDER BY <agg> DESC` (+ tie-breaker).  น้อยที่สุด / ต่ำสุด → `ORDER BY <agg> ASC NULLS LAST`.
- ไม่มี / ยังไม่มี / ไม่เคย → prefer `NOT EXISTS` (not `NOT IN`, not a `LEFT JOIN` that a later `WHERE` turns into an inner join).
- รายวัน/สัปดาห์/เดือน/ไตรมาส/ปีปฏิทิน → matching `date_trunc` bucket.  รายปีการศึกษา → academic-year column, not `date_trunc`.
- ล่าสุด / ใหม่สุด → `ORDER BY <the right event time> DESC, id DESC`.
- อัตราส่วน / สัดส่วน / เปอร์เซ็นต์ → same-grain aggregated numerator and denominator.
- ต่อคน → `SUM(value) / NULLIF(COUNT(DISTINCT person), 0)`.
- เติบโต → `(current - previous) * 100.0 / NULLIF(previous, 0)`; if previous = 0 → `NULL`.
- ว่างเปล่า → `NULLIF(btrim(col), '') IS NULL`.
