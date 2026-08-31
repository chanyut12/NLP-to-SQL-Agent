"""Deterministic column typing and result summary for the query envelope.

No LLM involvement — see docs/adr/0004-deterministic-column-metadata.md. Everything
here is derived from the result's pandas dtypes and its column names, so it is cheap
and reproducible.

`describe_result(rows, truncated)` is the single entry point used by the API layer.
"""

from __future__ import annotations

import math
import re
from typing import Any

import pandas as pd

# Column-name fragments, checked in priority order. Matched case-insensitively
# against the lowercased column name.
_DATE_RE = re.compile(r"(date|datetime|timestamp|_at$|_on$|วันที่)", re.I)
_ID_RE = re.compile(r"(^id$|_id$|^uuid$|_uuid$|รหัส)", re.I)
_PERCENT_RE = re.compile(r"(rate|pct|percent|ratio|อัตรา|ร้อยละ|เปอร์เซ)", re.I)
_GPA_RE = re.compile(r"(gpax?|grade_point|เกรดเฉลี่ย)", re.I)
_COUNT_RE = re.compile(r"(count|_cnt$|^cnt|num_|_num$|total|จำนวน|ยอด|amount)", re.I)
_NAME_RE = re.compile(r"(^name$|_name$|fullname|full_name|title|ชื่อ)", re.I)

# semantic_type vocabulary (closed set, see ADR 0004):
#   count | number | percent | gpa | date | id | category | name | text
_CATEGORY_MAX_DISTINCT = 40


def _semantic_type(name: str, series: pd.Series) -> str:
    n = str(name).strip().lower()
    is_numeric = pd.api.types.is_numeric_dtype(series)
    is_datetime = pd.api.types.is_datetime64_any_dtype(series)

    if is_datetime or _DATE_RE.search(n):
        return "date"
    if _ID_RE.search(n):
        return "id"

    if is_numeric:
        if _PERCENT_RE.search(n):
            return "percent"
        if _GPA_RE.search(n):
            return "gpa"
        if _COUNT_RE.search(n):
            return "count"
        # Unlabelled numeric: integers read as counts, non-integers as plain numbers.
        non_null = series.dropna()
        if not non_null.empty and (non_null % 1 == 0).all():
            return "count"
        return "number"

    if _NAME_RE.search(n):
        return "name"
    distinct = int(series.nunique(dropna=True))
    return "category" if distinct <= _CATEGORY_MAX_DISTINCT else "text"


def _column_info(name: str, series: pd.Series) -> dict[str, Any]:
    sample = next((v for v in series if v is not None and not _is_nan(v)), None)
    return {
        "name": str(name),
        "type": type(sample).__name__ if sample is not None else "unknown",
        "numeric": bool(pd.api.types.is_numeric_dtype(series)),
        "semantic_type": _semantic_type(name, series),
    }


def _is_nan(v: Any) -> bool:
    return isinstance(v, float) and math.isnan(v)


def _finite(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _coerce_numeric_objects(df: pd.DataFrame) -> None:
    """In place: turn object columns that are entirely numeric into a numeric dtype.

    `pd.read_sql` hands back PostgreSQL NUMERIC/DECIMAL as object-dtype Decimals,
    which `is_numeric_dtype` would otherwise reject. Date strings stay untouched
    (they coerce to NaN, so the column isn't fully numeric).
    """
    for name in df.columns:
        if df[name].dtype != object:
            continue
        original_non_null = df[name].notna().sum()
        if original_non_null == 0:
            continue
        coerced = pd.to_numeric(df[name], errors="coerce")
        if coerced.notna().sum() == original_non_null:
            df[name] = coerced


def describe_result(
    rows: list[dict[str, Any]] | None, truncated: bool
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return (columns, summary) for a result set.

    columns: one {name, type, numeric, semantic_type} per column, in column order.
    summary: {row_count, truncated, numeric_aggregates, single_value}.
             numeric_aggregates maps each non-id numeric column to
             {sum, min, max, mean}; values that are not finite are dropped.
             single_value is True when the result is one row and one numeric column.
    """
    rows = rows or []
    df = pd.DataFrame(rows)
    _coerce_numeric_objects(df)

    if df.empty:
        return [], {
            "row_count": len(rows),
            "truncated": truncated,
            "numeric_aggregates": {},
            "single_value": False,
        }

    columns = [_column_info(c, df[c]) for c in df.columns]

    aggregates: dict[str, dict[str, float]] = {}
    for col in columns:
        if not col["numeric"] or col["semantic_type"] == "id":
            continue
        series = df[col["name"]].dropna()
        if series.empty:
            continue
        stats = {
            "sum": _finite(series.sum()),
            "min": _finite(series.min()),
            "max": _finite(series.max()),
            "mean": _finite(series.mean()),
        }
        aggregates[col["name"]] = {k: v for k, v in stats.items() if v is not None}

    single_value = len(df) == 1 and len(df.columns) == 1 and bool(columns[0]["numeric"])

    summary = {
        "row_count": len(df),
        "truncated": truncated,
        "numeric_aggregates": aggregates,
        "single_value": single_value,
    }
    return columns, summary
