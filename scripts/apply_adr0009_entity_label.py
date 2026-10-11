"""ADR 0009 transform: add the entity label (school.name) to id-only per-school SQL.

Dry-run by default: rewrites in memory, verifies each pair (audit-compliance +
executes BOTH old and new against the live DB and asserts result equivalence).
--apply writes:
  - TEXT_TO_SQL_STS_RAG_EXAMPLES.json   (14 corpus examples rewritten)
  - eval/benchmark_sts.json             (5 gold SQLs rewritten)
Archives are copied to *.pre-adr0009.json before any write.

Shapes handled:
- FLAT: single-level per-school aggregate. Adds `JOIN schools school ON
  school.id = <ref>.school_id`, the `school_name` output column, the GROUP BY
  extension, and a deterministic ORDER BY tiebreak when missing.
- CTE (occupancy summary, top-schools ranking): hand-written literal rewrites
  (the label must be produced inside the CTE and carried through), verified
  the same way.
"""

import json
import os
import re
import shutil
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS_PATH = os.path.join(ROOT, "data", "corpus", "TEXT_TO_SQL_STS_RAG_EXAMPLES.json")
BENCH_PATH = os.path.join(ROOT, "eval", "benchmark_sts.json")

CORPUS_TARGETS = [
    "cases_without_tasks_by_school",
    "active_teacher_subject_summary_by_school",
    "student_current_classroom_occupancy_summary_by_school",
    "attendance_session_recording_ratio_by_school",
    "risk_current_average_score_by_school",
    "risk_current_consecutive_absence_threshold_by_school",
    "risk_current_without_open_case_by_school",
    "risk_profile_freshness_by_school",
    "case_without_review_count_by_school",
    "case_count_with_multiple_tasks_by_school",
    "assistance_measure_count_summary_by_school",
    "active_classrooms_without_subject_teacher_by_school",
    "active_average_subjects_per_teacher_by_school",
    "top_schools_by_task_completion_ratio",
]
GOLD_TARGETS = [
    "case_without_review_count_by_school",
    "student_current_classroom_occupancy_summary_by_school",
    "paraphrase_06",
    "paraphrase_09",
    "paraphrase_11",
]

# --- hand-written literal rewrites --------------------------------------------
CTE_REWRITES = {
    "student_current_classroom_occupancy_summary_by_school": {
        "from": "WITH classroom_counts AS (SELECT classroom.school_id, classroom.id AS classroom_id, COUNT(DISTINCT enrollment.person_uuid)::int AS student_count FROM student_term enrollment JOIN student_current_enrollment_resolution current_enrollment ON current_enrollment.person_uuid = enrollment.person_uuid AND current_enrollment.selected_student_uuid = enrollment.student_uuid AND current_enrollment.resolution_state = 'ACTIVE' JOIN school_classrooms classroom ON classroom.id = enrollment.classroom_id AND classroom.school_id = enrollment.\"SchoolID_Onec\" WHERE enrollment.deleted_at IS NULL AND classroom.deleted_at IS NULL AND classroom.classroom_status = 'ACTIVE' GROUP BY classroom.school_id, classroom.id) SELECT school_id, COUNT(*)::int AS occupied_classroom_count, ROUND(AVG(student_count), 1) AS average_students_per_classroom, MIN(student_count)::int AS minimum_students_per_classroom, MAX(student_count)::int AS maximum_students_per_classroom FROM classroom_counts GROUP BY school_id ORDER BY average_students_per_classroom DESC, school_id ASC",
        "to": "WITH classroom_counts AS (SELECT classroom.school_id, school.name AS school_name, classroom.id AS classroom_id, COUNT(DISTINCT enrollment.person_uuid)::int AS student_count FROM student_term enrollment JOIN student_current_enrollment_resolution current_enrollment ON current_enrollment.person_uuid = enrollment.person_uuid AND current_enrollment.selected_student_uuid = enrollment.student_uuid AND current_enrollment.resolution_state = 'ACTIVE' JOIN school_classrooms classroom ON classroom.id = enrollment.classroom_id AND classroom.school_id = enrollment.\"SchoolID_Onec\" JOIN schools school ON school.id = classroom.school_id WHERE enrollment.deleted_at IS NULL AND classroom.deleted_at IS NULL AND classroom.classroom_status = 'ACTIVE' GROUP BY classroom.school_id, school.name, classroom.id) SELECT school_id, school_name, COUNT(*)::int AS occupied_classroom_count, ROUND(AVG(student_count), 1) AS average_students_per_classroom, MIN(student_count)::int AS minimum_students_per_classroom, MAX(student_count)::int AS maximum_students_per_classroom FROM classroom_counts GROUP BY school_id, school_name ORDER BY average_students_per_classroom DESC, school_id ASC",
    },
    "top_schools_by_task_completion_ratio": {
        "from": "WITH school_completion AS (SELECT task.target_school_id, ROUND(100.0 * COUNT(*) FILTER (WHERE task.status = 'DONE') / NULLIF(COUNT(*), 0), 1) AS completion_rate_percent FROM tasks task WHERE task.deleted_at IS NULL GROUP BY task.target_school_id), ranked AS (SELECT school_completion.school_id, school_completion.completion_rate_percent, ROW_NUMBER() OVER (ORDER BY school_completion.completion_rate_percent DESC NULLS LAST, school_completion.school_id ASC) AS rank_overall FROM school_completion) SELECT school_id, completion_rate_percent, rank_overall FROM ranked WHERE rank_overall <= 5 ORDER BY rank_overall ASC",
        "to": "WITH school_completion AS (SELECT task.target_school_id AS school_id, school.name AS school_name, ROUND(100.0 * COUNT(*) FILTER (WHERE task.status = 'DONE') / NULLIF(COUNT(*), 0), 1) AS completion_rate_percent FROM tasks task JOIN schools school ON school.id = task.target_school_id WHERE task.deleted_at IS NULL GROUP BY task.target_school_id, school.name), ranked AS (SELECT school_completion.school_id, school_completion.school_name, school_completion.completion_rate_percent, ROW_NUMBER() OVER (ORDER BY school_completion.completion_rate_percent DESC NULLS LAST, school_completion.school_id ASC) AS rank_overall FROM school_completion) SELECT school_id, school_name, completion_rate_percent, rank_overall FROM ranked WHERE rank_overall <= 5 ORDER BY rank_overall ASC",
    },
}

# --- parametric rewrite: aggregate-in-CTE shapes ------------------------------
# The label is produced in the CTE (LEFT JOIN keeps the original rows) and
# carried through the outer aggregation. Anchors are corpus-unique strings.
CTE_PARAMS = {
    "case_count_with_multiple_tasks_by_school": {
        "sel_anchor": "SELECT case_row.school_id,",
        "join_after": "FROM cases case_row ",
        "join_on": "case_row.school_id",
        "gb_ref": "case_row.school_id",
    },
    "assistance_measure_count_summary_by_school": {
        "sel_anchor": "SELECT task.target_school_id AS school_id,",
        "join_after": "FROM tasks task ",
        "join_on": "task.target_school_id",
        "gb_ref": "task.target_school_id",
    },
    "active_average_subjects_per_teacher_by_school": {
        "sel_anchor": "SELECT assignment.school_id,",
        "join_after": "AND membership.school_id = assignment.school_id ",
        "join_on": "assignment.school_id",
        "gb_ref": "assignment.school_id",
    },
}


def rewrite_cte_outer_agg(ex_id, sql):
    p = CTE_PARAMS[ex_id]
    i = sql.find(p["sel_anchor"])
    if i < 0:
        return None
    cut = i + len(p["sel_anchor"])
    sql = sql[:cut] + " school.name AS school_name," + sql[cut:]
    j = sql.find(p["join_after"])
    if j < 0:
        return None
    cut = j + len(p["join_after"])
    sql = (sql[:cut] + f"LEFT JOIN schools school ON school.id = {p['join_on']} "
           + sql[cut:])
    gb = f"GROUP BY {p['gb_ref']}"
    k = sql.find(gb)
    if k < 0:
        return None
    sql = sql[:k] + gb + ", school.name" + sql[k + len(gb):]
    outer_sel = "SELECT school_id, "
    o = sql.rfind(outer_sel)
    if o < 0:
        return None
    sql = sql[:o + len(outer_sel)] + "school_name, " + sql[o + len(outer_sel):]
    outer_gb = "GROUP BY school_id"
    g = sql.rfind(outer_gb)
    if g < 0:
        return None
    sql = sql[:g + len(outer_gb)] + ", school_name" + sql[g + len(outer_gb):]
    return sql


def _top_level(sql, keywords=("SELECT", "FROM", "WHERE", "GROUP BY", "ORDER BY", "HAVING")):
    """First position of each keyword at paren depth 0 (CTE bodies are >= 1)."""
    depth = 0
    found = {}
    pat = (r"\(|\)|\bSELECT\b|\bFROM\b|\bWHERE\b|\bGROUP\s+BY\b"
           r"|\bORDER\s+BY\b|\bHAVING\b")
    for m in re.finditer(pat, sql, re.I):
        t = m.group(0)
        if t == "(":
            depth += 1
        elif t == ")":
            depth -= 1
        elif depth == 0:
            key = re.sub(r"\s+", " ", t.upper())
            if key in keywords and key not in found:
                found[key] = m.start()
    return found


def _depth_at(sql, index):
    depth = 0
    for ch in sql[:index]:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
    return depth


def rewrite_flat(sql):
    """Label-carrying rewrite of a flat per-school aggregate, or None."""
    top = _top_level(sql)
    sel_start = top.get("SELECT")
    from_pos = top.get("FROM")
    if sel_start is None or from_pos is None:
        return None
    select_seg = sql[sel_start:from_pos]

    edits = []

    # --- 1) the school_id output ref (top level of the SELECT list) --------
    refs = [m for m in re.finditer(r"(?i)([\w.]+)\.school_id\b", select_seg)
            if _depth_at(select_seg, m.start()) == 0]
    if not refs:
        return None
    ref = refs[-1].group(1)  # e.g. case_row / risk / session

    # --- 2) label column right after the school_id output column -----------
    m = refs[-1]
    tail = re.match(r"(?is)\s*(?:AS\s+\w+\s*)?,", select_seg[m.end():])
    if not tail:
        return None
    insert_at = sel_start + m.end() + tail.end()  # AFTER the comma
    edits.append((insert_at, " school.name AS school_name,"))

    # --- 3) JOIN schools at the END of the FROM clause (before WHERE) ------
    # Placing the join after ALL top-level joins guarantees every referenced
    # alias is already introduced (the ref table may be joined later, as in
    # classroom_subject_teachers -> school_teacher_memberships). An INNER
    # join on the school PK preserves row count wherever it sits.
    anchor = top.get("WHERE")
    if anchor is None or anchor < from_pos:
        anchor = top.get("GROUP BY")
    if anchor is None or anchor < from_pos:
        return None
    if not re.search(r"(?i)\bJOIN\s+schools\s+school\b", sql):
        # Some audited examples already join schools (for a status filter)
        # without selecting the label — add the join only when missing.
        edits.append((anchor, f" JOIN schools school ON school.id = {ref}.school_id "))

    # --- 4) GROUP BY extension ---------------------------------------------
    gb_pos = top.get("GROUP BY")
    if gb_pos is None:
        return None
    seg_end = min((p for k in ("ORDER BY", "HAVING")
                   if (p := top.get(k)) is not None and p > gb_pos),
                  default=len(sql))
    ref_m = re.search(rf"(?i)\b{re.escape(ref)}\.school_id\b", sql[gb_pos:seg_end])
    if not ref_m:
        return None
    edits.append((gb_pos + ref_m.end(), ", school.name"))

    # --- 5) ORDER BY deterministic tiebreak (only when school_id absent) ----
    ob_pos = top.get("ORDER BY")
    if ob_pos is not None:
        ob_tail = sql[ob_pos:]
        if not re.search(r"(?i)\bschool_id\b", ob_tail):
            lim = re.search(r"(?i)\bLIMIT\b", ob_tail)
            pos = ob_pos + (lim.start() if lim else len(ob_tail))
            edits.append((pos, ", school_id ASC"))

    out = sql
    for pos, text in sorted(edits, key=lambda e: -e[0]):
        out = out[:pos] + text + out[pos:]
    return out


# Pre-existing corpus drift vs the live schema (found while verifying):
# the tasks table carries target_school_id, not school_id — these examples
# were not executable before this change. Corrected so the label rewrite can
# be verified at all; both corrections are asserted against the live DB.
COLUMN_FIXES = {
    "task.school_id": "task.target_school_id",
}


def apply_column_fixes(sql):
    for wrong, right in COLUMN_FIXES.items():
        sql = re.sub(rf"(?i)\b{re.escape(wrong)}\b", right, sql)
    return sql


def rewrite_sql(ex_id, sql):
    sql = apply_column_fixes(sql)
    if ex_id in CTE_REWRITES:
        pair = CTE_REWRITES[ex_id]
        if sql.strip() != pair["from"].strip():
            return None  # corpus drifted from the audited shape — refuse
        return pair["to"]
    if ex_id in CTE_PARAMS:
        return rewrite_cte_outer_agg(ex_id, sql)
    return rewrite_flat(sql)


def verify_pair(old, new, params, engine):
    """Compliance + execution equivalence between old and new SQL.

    Both sides are parameter-inlined for execution; the stored SQL keeps its
    placeholders (matching the corpus convention).
    """
    import pandas as pd
    from eval.entity_label_audit import _violating_columns

    assert not _violating_columns(new), "rewrite still violates the audit"
    assert "school.name AS school_name" in new

    sys.path.insert(0, ROOT)
    from scripts.build_sts_profile import inline_params

    old_x = inline_params(old, params)
    new_x = inline_params(new, params)
    try:
        old_df = pd.read_sql(old_x, engine)
    except Exception as exc:
        # Pre-existing broken example (schema drift): no original result to
        # preserve — verify the rewrite executes and passes the audit only.
        print(f"  note: original SQL not executable ({type(exc).__name__}) — "
              f"verifying the rewrite only")
        pd.read_sql(new_x, engine)
        return
    new_df = pd.read_sql(new_x, engine)
    assert len(old_df) == len(new_df), \
        f"row count changed: {len(old_df)} -> {len(new_df)}"
    name_idx = list(new_df.columns).index("school_name")
    stripped = [tuple(r)[:name_idx] + tuple(r)[name_idx + 1:]
                for r in new_df.itertuples(index=False, name=None)]
    old_rows = [tuple(r) for r in old_df.itertuples(index=False, name=None)]
    assert Counter(old_rows) == Counter(stripped), \
        "result tuples differ beyond the added school_name column"


def main():
    apply = "--apply" in sys.argv
    sys.path.insert(0, ROOT)

    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(ROOT, ".env"))
    except ImportError:
        pass
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL missing — cannot verify against the live DB")
        sys.exit(1)
    from sqlalchemy import create_engine
    engine = create_engine(db_url, pool_size=2)

    corpus = json.load(open(CORPUS_PATH, encoding="utf-8"))
    bench = json.load(open(BENCH_PATH, encoding="utf-8"))

    changed_corpus, changed_gold = {}, {}
    for ex in corpus["examples"]:
        if ex["id"] in CORPUS_TARGETS:
            new = rewrite_sql(ex["id"], ex["sql"])
            if new is None:
                print(f"REFUSED corpus {ex['id']}: shape not recognised")
                continue
            verify_pair(ex["sql"], new, ex.get("parameters", []), engine)
            changed_corpus[ex["id"]] = new
    for q in bench["questions"]:
        if q["id"] in GOLD_TARGETS and (q.get("gold_sql") or "").strip():
            new = rewrite_sql(q["id"], q["gold_sql"])
            if new is None:
                print(f"REFUSED gold {q['id']}: shape not recognised")
                continue
            verify_pair(q["gold_sql"], new, [], engine)
            changed_gold[q["id"]] = new

    print(f"verified against DB: {len(changed_corpus)} corpus, {len(changed_gold)} gold")
    for qid, sql in list(changed_corpus.items())[:2] + list(changed_gold.items())[:2]:
        print(f"\n--- {qid} ---\n{sql}")

    if not apply:
        print("\nDRY RUN — pass --apply to write the files")
        return

    for path in (CORPUS_PATH, BENCH_PATH):
        stem, ext = os.path.splitext(path)
        shutil.copy2(path, stem + ".pre-adr0009" + ext)

    for ex in corpus["examples"]:
        if ex["id"] in changed_corpus:
            ex["sql"] = changed_corpus[ex["id"]]
    for q in bench["questions"]:
        if q["id"] in changed_gold:
            q["gold_sql"] = changed_gold[q["id"]]
    with open(CORPUS_PATH, "w", encoding="utf-8") as f:
        json.dump(corpus, f, ensure_ascii=False, indent=2)
    with open(BENCH_PATH, "w", encoding="utf-8") as f:
        json.dump(bench, f, ensure_ascii=False, indent=2)
    print("APPLIED — archives written as *.pre-adr0009.json")


if __name__ == "__main__":
    main()
