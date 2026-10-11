"""Deterministic Turn digest (ADR 0010, ticket #34).

The service is stateless: the Consumer replays prior Turns. Replaying only the SQL
leaves the model to guess what a Turn *meant* — which population it counted, what
it was filtered to — so a follow-up like "ช่วยกรองเฉพาะ X" can bind to the wrong
Turn. The digest is a small structured description of a Result Turn built purely
from its SQL and rows (no LLM, in the spirit of ADR 0004) that the Consumer stores
with the envelope and sends back inside `history`.

Pure function; never raises — a digest that cannot be built is simply absent.
"""

from typing import Any, List, Optional

import sqlglot
from sqlglot import exp

from core.services.data_knowledge import column_blocked

MAX_TABLES = 4
MAX_FILTERS = 5
MAX_GROUP_BY = 5
MAX_TOP_ROWS = 3
MAX_TEXT = 120


def _short(text: str, n: int = MAX_TEXT) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[: n - 1] + "…"


def _sql_parts(sql: str):
    tree = sqlglot.parse_one(sql, read="postgres")
    ctes = {c.alias_or_name for c in tree.find_all(exp.CTE)}
    tables = []
    for t in tree.find_all(exp.Table):
        if t.name and t.name not in ctes and t.name not in tables:
            tables.append(t.name)
    filters: List[str] = []
    for where in tree.find_all(exp.Where):
        for pred in where.this.flatten() if isinstance(where.this, exp.And) else [where.this]:
            text = _short(pred.sql(dialect="postgres"))
            if text not in filters:
                filters.append(text)
    group_by: List[str] = []
    for g in tree.find_all(exp.Group):
        for e in g.expressions:
            text = _short(e.sql(dialect="postgres"), 60)
            if text not in group_by:
                group_by.append(text)
    return tables, filters, group_by


def build_turn_digest(sql: Optional[str], rows: Optional[List[dict]],
                      columns: Optional[List[dict]], row_count: int,
                      table_notes: Optional[dict] = None) -> Optional[dict]:
    """Structured description of a Result Turn, or None when there is no query."""
    if not (sql and sql.strip()):
        return None
    try:
        tables, filters, group_by = _sql_parts(sql)
    except Exception:
        tables, filters, group_by = [], [], []

    notes = ((table_notes or {}).get("tables") or {})
    populations = {t: notes[t]["population"] for t in tables[:MAX_TABLES]
                   if t in notes and notes[t].get("population")}

    cols = [{"name": c.get("name"), "semantic_type": c.get("semantic_type")}
            for c in (columns or []) if c.get("name")]
    safe_names = [c["name"] for c in cols if not column_blocked(c["name"], table_notes)]
    top_rows: List[dict] = []
    for row in (rows or [])[:MAX_TOP_ROWS]:
        top_rows.append({k: (v if isinstance(v, (int, float)) and not isinstance(v, bool)
                             else _short(v, 60))
                         for k, v in row.items() if k in safe_names})

    return {
        "tables": tables[:MAX_TABLES],
        "populations": populations,
        "filters": filters[:MAX_FILTERS],
        "group_by": group_by[:MAX_GROUP_BY],
        "columns": cols,
        "top_rows": top_rows,
        "row_count": row_count,
    }


def digest_block(turn_digest: Optional[dict]) -> List[str]:
    """Indented lines describing a digest for the prompt's history block."""
    if not turn_digest:
        return []
    lines = []
    if turn_digest.get("tables"):
        lines.append("  tables: " + ", ".join(turn_digest["tables"]))
    for table, pop in (turn_digest.get("populations") or {}).items():
        lines.append(f"  population of {table}: {pop}")
    if turn_digest.get("filters"):
        lines.append("  filters: " + " AND ".join(turn_digest["filters"]))
    if turn_digest.get("group_by"):
        lines.append("  grouped by: " + ", ".join(turn_digest["group_by"]))
    if turn_digest.get("columns"):
        lines.append("  output columns: " + ", ".join(
            c["name"] + (f" ({c['semantic_type']})" if c.get("semantic_type") else "")
            for c in turn_digest["columns"]))
    for i, row in enumerate(turn_digest.get("top_rows") or [], 1):
        lines.append(f"  top row {i}: {row}")
    return lines
