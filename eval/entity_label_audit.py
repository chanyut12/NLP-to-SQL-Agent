"""Entity-label audit (ADR 0009).

The Entity label contract: a result grouped by or filtered to one non-person
entity must carry that entity's readable label column, never its id alone.
The id alone cannot be parsed by a human reader, and the presentation layer
cannot invent the label after the fact — generation must provide it.

This audit checks both sources of that behaviour:

- the Example set (TEXT_TO_SQL_STS_RAG_EXAMPLES.json) — what retrieval teaches,
- the Golden set (eval/benchmark_sts.json) — what the eval defines as right.

A SQL statement violates the contract when its outermost SELECT list outputs an
id-typed column and no name-typed column for the same entity. Pure date
group-bys (month buckets) carry no entity id and never violate. Passes with no
output when both sets comply; prints violations and exits 1 otherwise.

Usage:
    python eval/entity_label_audit.py
"""

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

EXAMPLE_SET_PATH = os.path.join(ROOT, "TEXT_TO_SQL_STS_RAG_EXAMPLES.json")
GOLDEN_SET_PATH = os.path.join(ROOT, "eval", "benchmark_sts.json")

# Output-column classification (mirrors core.viz.column_meta semantics).
_ID_PAT = re.compile(r"(?i)(^|_)id$|รหัส|^uuid")
# `_th` / `_en` suffixes are language tags (subject_name_th), not a different
# column kind.
_NAME_PAT = re.compile(r"(?i)name(_th|_en)?$|label|ชื่อ|title")
# Columns that LOOK like ids but are not bookkeeping: readable codes and label
# columns (subject_code / grade_label next to a name), time buckets, ordinals
# and provenance. Only excluded from the id class — a label/anything matching
# _NAME_PAT always counts as a label.
_ID_NEUTRAL_PAT = re.compile(
    r"(?i)(code|label|month|year|day|week|quarter|date|term|semester|"
    r"rank|_as_of|count|_num)"
)


def _outer_select_list(sql: str) -> list[str]:
    """Output column names of the outermost SELECT, CTE-aware."""
    sql = re.sub(r"\s+", " ", sql.strip())
    if not sql.upper().startswith("SELECT"):
        m = re.match(r"(?is)^WITH\b(.*)$", sql)
        if not m:
            return []
        depth = 0
        i = m.start(1)
        while i < len(sql):
            if sql[i] == "(":
                depth += 1
            elif sql[i] == ")":
                depth -= 1
            elif depth == 0 and re.match(r"(?i)\bSELECT\b", sql[i:]):
                break
            i += 1
        body = sql[i:]
    else:
        body = sql

    depth = 0
    end = len(body)
    for tok in re.finditer(r"\(|\)|\bFROM\b", body, re.I):
        if tok.group(0) == "(":
            depth += 1
        elif tok.group(0) == ")":
            depth -= 1
        elif depth == 0:
            end = tok.start()
            break
    sel = body[6:end]

    parts, cur, depth = [], "", 0
    for ch in sel:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)

    cols = []
    for p in parts:
        p = p.strip()
        m = re.search(r"(?is)\bAS\s+([A-Za-z_]\w*)\s*$", p)
        if m:
            cols.append(m.group(1))
            continue
        m = re.search(r"(?i)([A-Za-z_]\w*)\s*$", re.sub(r"\s+", " ", p.split("::")[0]))
        cols.append(m.group(1) if m else p[:30])
    return cols


def _violating_columns(sql: str) -> bool:
    """True when the outermost SELECT outputs ids but no label column."""
    cols = _outer_select_list(sql)
    ids = [c for c in cols if _ID_PAT.search(c) and not _ID_NEUTRAL_PAT.search(c)]
    names = [c for c in cols if _NAME_PAT.search(c)]
    return bool(ids) and not bool(names)


def audit_example_set() -> list[str]:
    """Return human-readable violations for the Example set."""
    data = json.load(open(EXAMPLE_SET_PATH, encoding="utf-8"))
    offenders = []
    for ex in data["examples"]:
        sql = ex.get("sql", "")
        if sql.strip() and _violating_columns(sql):
            offenders.append(f"{ex['id']}: SELECT outputs ids without a label")
    return offenders


def audit_golden_set() -> list[str]:
    """Return human-readable violations for the Golden set."""
    bench = json.load(open(GOLDEN_SET_PATH, encoding="utf-8"))
    offenders = []
    for q in bench["questions"]:
        sql = q.get("gold_sql") or ""
        if sql.strip() and _violating_columns(sql):
            offenders.append(f"{q['id']}: gold SQL outputs ids without a label")
    return offenders


if __name__ == "__main__":
    problems = audit_example_set() + audit_golden_set()
    if problems:
        print("ADR 0009 Entity-label violations:")
        for p in problems:
            print("  -", p)
        sys.exit(1)
    print("ADR 0009: Example set and Golden set comply with the Entity label contract.")
