"""SQL structural metrics extraction using sqlglot AST parsing."""

from dataclasses import dataclass
from typing import List

import sqlglot
from sqlglot import exp


@dataclass(frozen=True)
class SQLMetrics:
    tables_used: List[str]
    join_count: int
    has_aggregation: bool
    has_subquery: bool
    has_group_by: bool


def parse_sql_metrics(sql: str, dialect: str = "sqlite") -> SQLMetrics:
    """Parse structural metrics from SQL using sqlglot AST. Never raises."""
    try:
        if not sql or not sql.strip():
            raise ValueError("empty")
        statements = sqlglot.parse(sql, dialect=dialect)
        stmt = statements[0] if statements else None
        if stmt is None:
            raise ValueError("no statement")

        tables = list(dict.fromkeys(
            t.name.lower()
            for t in stmt.find_all(exp.Table)
            if t.name
        ))
        joins = list(stmt.find_all(exp.Join))
        aggs = bool(stmt.find(exp.Sum, exp.Count, exp.Avg, exp.Max, exp.Min))
        subqueries = bool(stmt.find(exp.Subquery)) or isinstance(stmt, exp.With)
        group_by = bool(stmt.find(exp.Group))

        return SQLMetrics(
            tables_used=tables,
            join_count=len(joins),
            has_aggregation=aggs,
            has_subquery=subqueries,
            has_group_by=group_by,
        )
    except Exception:
        return SQLMetrics(
            tables_used=[], join_count=0, has_aggregation=False,
            has_subquery=False, has_group_by=False
        )
