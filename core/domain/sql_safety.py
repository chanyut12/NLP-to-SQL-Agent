"""
SQL Safety & Sanitization utilities.

Goals:
- Allow ONLY read-only queries (SELECT / WITH ... SELECT)
- Block multi-statement SQL and destructive statements
- Enforce a maximum LIMIT (and inject one if missing)
- (Optional) Restrict queries to an allowlist of tables
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

import sqlglot
from sqlglot import exp


from core.utils.common import normalize_sql_code


@dataclass(frozen=True)
class SafeSQL:
    sql: str
    dialect: str
    tables: tuple[str, ...]
    limit: Optional[int]


class SQLSafetyError(ValueError):
    pass


_DISALLOWED_NODE_TYPES: tuple[type[exp.Expression], ...] = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Alter,
    exp.Create,
    exp.Command,  # e.g. PRAGMA / SHOW / other commands
    exp.Transaction,
)


def _parse_single_statement(sql: str, dialect: str) -> exp.Expression:
    try:
        statements = sqlglot.parse(sql, read=dialect)
    except Exception as e:
        raise SQLSafetyError(f"SQL parse failed for dialect={dialect}: {e}") from e

    if not statements:
        raise SQLSafetyError("Empty SQL.")
    if len(statements) != 1:
        raise SQLSafetyError("Only a single SQL statement is allowed.")
    return statements[0]


def _root_query_expr(stmt: exp.Expression) -> exp.Expression:
    # WITH <ctes> SELECT ...  => root is exp.With, query is stmt.this
    if isinstance(stmt, exp.With):
        return stmt.this
    return stmt


def _extract_tables(stmt: exp.Expression) -> tuple[str, ...]:
    tables: list[str] = []
    for t in stmt.find_all(exp.Table):
        # sqlglot tables may have catalog/db; we keep only final name
        name = (t.name or "").strip()
        if name:
            tables.append(name)
    # de-dup stable order
    seen: set[str] = set()
    uniq: list[str] = []
    for n in tables:
        if n not in seen:
            seen.add(n)
            uniq.append(n)
    return tuple(uniq)


def _ensure_limit(stmt: exp.Expression, max_limit: int) -> tuple[exp.Expression, Optional[int]]:
    query = _root_query_expr(stmt)
    if not isinstance(query, exp.Expression):
        return stmt, None

    limit_exp = query.args.get("limit")
    if limit_exp is None:
        query.set("limit", exp.Limit(expression=exp.Literal.number(max_limit)))
        return stmt, max_limit

    # Clamp numeric limits if possible; if not numeric, keep it but do not exceed max by injecting is hard.
    try:
        limit_value = int(limit_exp.expression.name)  # type: ignore[union-attr]
    except Exception:
        return stmt, None

    if limit_value > max_limit:
        limit_exp.set("expression", exp.Literal.number(max_limit))
        return stmt, max_limit
    return stmt, limit_value


def validate_and_sanitize_sql(
    raw_sql: str,
    *,
    dialect: str,
    max_limit: int = 500,
    allowed_tables: Optional[Sequence[str]] = None,
) -> SafeSQL:
    """
    Validate SQL is safe (read-only) and return a sanitized SQL string.

    Args:
        raw_sql: SQL string from the model
        dialect: 'sqlite' | 'mysql' | 'postgres' (sqlglot dialect names)
        max_limit: maximum allowed LIMIT (injected if missing)
        allowed_tables: optional list of tables that query may reference
    """
    sql = normalize_sql_code(raw_sql)
    if not sql:
        raise SQLSafetyError("Empty SQL.")

    stmt = _parse_single_statement(sql, dialect=dialect)

    # Reject destructive nodes anywhere in the AST
    for node in stmt.walk():
        if isinstance(node, _DISALLOWED_NODE_TYPES):
            raise SQLSafetyError(f"Disallowed SQL operation: {node.__class__.__name__}")

    # Root must be SELECT/UNION or WITH wrapping a query
    root = _root_query_expr(stmt)
    if not isinstance(root, (exp.Select, exp.Union, exp.Intersect, exp.Except)):
        raise SQLSafetyError("Only read-only SELECT queries are allowed.")

    # Optional allowlist of tables
    tables = _extract_tables(stmt)
    if allowed_tables is not None:
        allowed_set = {t.lower() for t in allowed_tables}
        for t in tables:
            if t.lower() not in allowed_set:
                raise SQLSafetyError(f"Table not allowed: {t}")

    # Enforce LIMIT
    stmt, limit_value = _ensure_limit(stmt, max_limit=max_limit)

    try:
        sanitized_sql = stmt.sql(dialect=dialect)
    except Exception:
        # Fallback to original if serialization fails (still safe by checks)
        sanitized_sql = sql

    return SafeSQL(sql=sanitized_sql, dialect=dialect, tables=tables, limit=limit_value)


