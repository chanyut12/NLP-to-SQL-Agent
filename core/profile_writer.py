"""Writer for demo-authored Domain profiles (ADR 0014).

A wizard-created profile is an ordinary profile: the same files the loader reads,
under ``profiles/<name>/``. This module owns the file rules so the demo routes
stay a thin HTTP layer — it validates the slug, refuses to overwrite silently,
adds the fields a visitor should not have to know (dialect, category, id) and
always writes ``examples.json``, because that file is what makes a profile
selectable.

Only the demo may call this (ADR 0014); a service deployment has no endpoint that
reaches it.
"""

import json
import os
import re

import sqlglot
from sqlglot import exp

from core import profiles

# Lowercase letters, digits, dash and underscore. No dots, slashes or spaces, so
# a name can never traverse out of PROFILES_DIR.
PROFILE_NAME_RE = re.compile(r"^[a-z0-9_-]{1,64}$")

# sqlglot's dialect name -> the Example set contract's spelling (PROFILES.md).
_CONTRACT_DIALECT = {"postgres": "postgresql"}


def contract_dialect(sqlglot_name: str) -> str:
    """The dialect spelling an example file stores, from a sqlglot name."""
    return _CONTRACT_DIALECT.get(sqlglot_name, sqlglot_name)


def validate_profile_name(name: str) -> str:
    """Return the name if it is a safe profile slug; raise ValueError otherwise.

    The regex already excludes separators; the containment check is the explicit
    path-traversal guard the contract promises.
    """
    if not PROFILE_NAME_RE.fullmatch(name or ""):
        raise ValueError(
            "ชื่อ profile ใช้ได้เฉพาะ a-z, 0-9, - และ _ (ไม่เกิน 64 ตัว)"
        )
    root = os.path.realpath(profiles.PROFILES_DIR)
    target = os.path.realpath(os.path.join(root, name))
    if os.path.commonpath([root, target]) != root or target == root:
        raise ValueError("ชื่อ profile ไม่ถูกต้อง")
    return name


def categorize_sql(sql: str, dialect: str) -> str:
    """The SQL-shape bucket a drafted example belongs to, from its AST.

    Deterministic and independent of the question: the wizard cannot ask a
    visitor for a Golden-set category, so the shape of the SQL states it.
    """
    try:
        stmt = sqlglot.parse_one(sql, read=dialect)
    except Exception:
        return "general"

    has_group = bool(stmt.find(exp.Group))
    has_join = bool(next(stmt.find_all(exp.Join), None))
    has_count = bool(stmt.find(exp.Count))
    has_avg = bool(stmt.find(exp.Avg))
    has_sum = bool(stmt.find(exp.Sum))
    has_aggregate = has_count or has_avg or has_sum

    if has_group:
        if has_avg:
            return "average_groupby"
        if has_count:
            return "count_groupby"
        if has_sum:
            return "sum_groupby"
        return "groupby"
    if has_aggregate:
        if has_count:
            return "count"
        if has_avg:
            return "average"
        return "aggregation"
    if stmt.find(exp.Order) and stmt.find(exp.Limit):
        return "ranking"
    if stmt.find(exp.Distinct):
        return "filter_distinct"
    if has_join:
        return "join"
    return "filter"


_ANSWER_TYPE_LABELS = {"clarification": "ถามกลับ", "refusal": "ปฏิเสธ"}


def build_examples(inputs: list, dialect: str) -> list:
    """Turn confirmed wizard examples into Example set records.

    ``inputs`` carry what the visitor supplied (question, optional sql, optional
    retrieval_tags and grain, and for an answer exemplar its
    expected_answer_type and expected_message); the service adds id, category
    and dialect. A clarification/refusal exemplar keeps the established shape:
    empty sql plus the two expected_* fields, and is never executed.
    """
    examples = []
    for index, item in enumerate(inputs, start=1):
        question = (item.get("question") or "").strip()
        sql = (item.get("sql") or "").strip()
        answer_type = (item.get("expected_answer_type") or "").strip()
        if not question:
            raise ValueError(f"ตัวอย่างที่ {index} ยังไม่มีคำถาม")

        example = {
            "id": f"wiz-{index:03d}",
            "question": question,
            "sql": sql,
            "dialect": dialect,
        }
        if answer_type:
            if answer_type not in _ANSWER_TYPE_LABELS:
                raise ValueError(
                    f"ตัวอย่างที่ {index} มีประเภทคำตอบไม่รองรับ: {answer_type!r}"
                )
            if sql:
                raise ValueError(
                    f"ตัวอย่างที่ {index} เป็นตัวอย่าง{_ANSWER_TYPE_LABELS[answer_type]}"
                    " ต้องไม่มี SQL"
                )
            message = (item.get("expected_message") or "").strip()
            if not message:
                raise ValueError(
                    f"ตัวอย่างที่ {index} ต้องมีข้อความที่ควรตอบ"
                )
            example["category"] = f"{answer_type}_exemplar"
            example["expected_answer_type"] = answer_type
            example["expected_message"] = message
        else:
            if not sql:
                raise ValueError(f"ตัวอย่างที่ {index} ยังไม่มี SQL")
            example["category"] = categorize_sql(sql, _sqlglot_dialect(dialect))

        tags = [str(tag).strip() for tag in (item.get("retrieval_tags") or [])]
        tags = [tag for tag in tags if tag]
        if tags:
            example["retrieval_tags"] = tags
        grain = (item.get("grain") or "").strip()
        if grain:
            example["grain"] = grain
        examples.append(example)
    return examples


def write_profile(
    name: str,
    *,
    hints: str = "",
    schema_mappings: dict = None,
    table_notes: dict = None,
    examples: list = None,
    overwrite: bool = False,
) -> dict:
    """Write a wizard profile and return its coverage.

    Writes the whole file set in one place: ``hints.md``, ``schema_mappings.json``,
    ``table_notes.json`` (only when the visitor filled it) and ``examples.json``
    (last — a profile becomes selectable only once that file exists). Every
    section is optional; an overwrite that leaves one empty removes the stale
    file rather than keeping the previous visitor's answer.
    """
    validate_profile_name(name)
    mappings = _validated_mappings(schema_mappings)
    notes = _validated_table_notes(table_notes)
    examples = examples or []
    body = (hints or "").strip()

    directory = profiles.profile_dir(name)
    notes_path = os.path.join(directory, "table_notes.json")
    exists = os.path.isdir(directory)
    if exists and not overwrite:
        raise FileExistsError(name)

    os.makedirs(directory, exist_ok=True)
    with open(os.path.join(directory, "hints.md"), "w", encoding="utf-8") as f:
        f.write(body + "\n" if body else "")
    _write_json(os.path.join(directory, "schema_mappings.json"), mappings)
    if notes:
        _write_json(notes_path, {"tables": notes})
    elif os.path.isfile(notes_path):
        os.remove(notes_path)
    _write_json(os.path.join(directory, "examples.json"), {"examples": examples})

    return {
        "hints": bool(body),
        "examples": sum(1 for ex in examples if not ex.get("expected_answer_type")),
        "exemplars": sum(1 for ex in examples if ex.get("expected_answer_type")),
        "schema_mappings": len(mappings),
        "table_notes": len(notes),
    }


def _validated_table_notes(table_notes: dict) -> dict:
    """Keep only entries with both halves filled — the file contract requires
    a meaning and a population for every table it names (PROFILES.md §5)."""
    cleaned = {}
    for table, entry in (table_notes or {}).items():
        name = str(table).strip()
        entry = entry or {}
        meaning = str(entry.get("meaning", "")).strip()
        population = str(entry.get("population", "")).strip()
        if not name:
            raise ValueError("ชื่อตารางใน table notes ต้องไม่ว่าง")
        if not meaning or not population:
            raise ValueError(
                f"ตาราง {name!r} ต้องมีทั้งความหมายและกลุ่มข้อมูล"
            )
        cleaned[name] = {"meaning": meaning, "population": population}
    return cleaned


def _validated_mappings(schema_mappings: dict) -> dict:
    """Keep only well-formed term -> [fragments] pairs (the file contract)."""
    cleaned = {}
    for term, fragments in (schema_mappings or {}).items():
        key = str(term).strip()
        values = [str(fragment).strip() for fragment in (fragments or [])]
        values = [value for value in values if value]
        if not key:
            raise ValueError("คำศัพท์ใน schema mappings ต้องไม่ว่าง")
        if not values:
            raise ValueError(f"คำศัพท์ {key!r} ยังไม่มีชื่อตารางหรือคอลัมน์")
        cleaned[key] = values
    return cleaned


def _sqlglot_dialect(dialect: str) -> str:
    return {"postgresql": "postgres"}.get(dialect, dialect)


def _write_json(path: str, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
