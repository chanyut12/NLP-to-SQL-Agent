"""Grounding check for agent answers (ADR 0010, ticket #36).

A final_answer message may only state numbers that come from this Turn's result
rows, are trivially derived from them (count, sum, min/max/mean, share of a column
total), or were given by the user (question / prior-Turn text). Anything else is a
figure the model produced from memory — typically from a different table or
population (the Oct 2026 "Bangkok has the most signals" case) — and is flagged.

Pure functions, no LLM, no I/O.
"""

import re
from typing import Iterable, List, Sequence

_THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")
_NUM_RE = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?")
_THAI_MONTHS = ("มกราคม|กุมภาพันธ์|มีนาคม|เมษายน|พฤษภาคม|มิถุนายน|กรกฎาคม|สิงหาคม|"
                "กันยายน|ตุลาคม|พฤศจิกายน|ธันวาคม|ม\\.ค\\.|ก\\.พ\\.|มี\\.ค\\.|เม\\.ย\\.|"
                "พ\\.ค\\.|มิ\\.ย\\.|ก\\.ค\\.|ส\\.ค\\.|ก\\.ย\\.|ต\\.ค\\.|พ\\.ย\\.|ธ\\.ค\\.")
# "27 กันยายน 2569", "31 ส.ค. 2026", ISO dates/timestamps: calendar dates are
# presentation of the data's as-of stamp, not claims about the rows.
_DATE_RES = [
    re.compile(rf"\d{{1,2}}\s*(?:{_THAI_MONTHS})\s*\d{{2,4}}"),
    re.compile(rf"(?:{_THAI_MONTHS})\s*\d{{4}}"),
    re.compile(r"\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?)?"),
]
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+|(?<=ครับ)\s+|(?<=ค่ะ)\s+")


def _norm(text: str) -> str:
    return (text or "").translate(_THAI_DIGITS)


def _strip_dates(text: str) -> str:
    for r in _DATE_RES:
        text = r.sub(" ", text)
    return text


def extract_numbers(text: str) -> List[float]:
    """Numbers stated in prose, Thai digits and thousands separators normalised,
    calendar dates excluded."""
    out = []
    for m in _NUM_RE.finditer(_strip_dates(_norm(text))):
        whole = m.group(1).replace(",", "")
        out.append(float(f"{whole}.{m.group(2)}" if m.group(2) else whole))
    return out


def _decimals(token_text: str) -> int:
    m = re.search(r"\.(\d+)", token_text)
    return len(m.group(1)) if m else 0


def _cells(rows: Sequence[dict]) -> Iterable:
    for row in rows:
        for v in row.values():
            yield v


def allowed_numbers(rows_sets: Sequence[Sequence[dict]], context_text: str = "") -> set:
    """Every number the message may legitimately state."""
    allowed = set()
    for n in extract_numbers(context_text):
        allowed.add(round(n, 6))
    for rows in rows_sets:
        allowed.add(float(len(rows)))
        by_col = {}
        for row in rows:
            for k, v in row.items():
                if isinstance(v, bool):
                    continue
                if isinstance(v, (int, float)):
                    by_col.setdefault(k, []).append(float(v))
        for cell in _cells(rows):
            if isinstance(cell, str):
                for n in extract_numbers(cell):  # e.g. "ขาดสะสม 8 วัน (เกณฑ์ 7 วัน)"
                    allowed.add(round(n, 6))
        for vals in by_col.values():
            total = sum(vals)
            for v in vals:
                allowed.add(round(v, 6))
                if total:
                    allowed.add(round(v * 100.0 / total, 6))  # share of column total
            allowed.update(round(x, 6) for x in (total, min(vals), max(vals),
                                                  total / len(vals)))
    return allowed


def _matches(stated: float, text_form: str, allowed: set) -> bool:
    d = _decimals(text_form)
    tol = 0.5 * 10 ** (-d) + 1e-9
    return any(abs(stated - a) <= tol for a in allowed)


def ungrounded_numbers(message: str, rows_sets: Sequence[Sequence[dict]],
                       context_text: str = "") -> List[float]:
    """Numbers in `message` that no result row / derivation / user text explains."""
    allowed = allowed_numbers(rows_sets, context_text)
    bad = []
    body = _strip_dates(_norm(message))
    for m in _NUM_RE.finditer(body):
        whole = m.group(1).replace(",", "")
        stated = float(f"{whole}.{m.group(2)}" if m.group(2) else whole)
        form = f"{whole}.{m.group(2)}" if m.group(2) else whole
        if not _matches(stated, form, allowed):
            bad.append(stated)
    return bad


def drop_ungrounded_sentences(message: str, rows_sets: Sequence[Sequence[dict]],
                              context_text: str = "") -> str:
    """Message with every sentence containing an ungrounded number removed.
    Empty string when nothing survives."""
    keep = [s for s in _SENTENCE_SPLIT.split(message or "")
            if s.strip() and not ungrounded_numbers(s, rows_sets, context_text)]
    return " ".join(keep).strip()


def fallback_message(row_count: int) -> str:
    """Deterministic last resort — states only what the executed query returned."""
    if row_count == 0:
        return "ไม่พบข้อมูลที่ตรงกับเงื่อนไขที่ระบุ"
    return f"พบผลลัพธ์ {row_count} รายการ ดูรายละเอียดในตารางด้านล่าง"
