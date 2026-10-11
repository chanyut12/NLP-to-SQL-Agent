"""Data-knowledge helpers for the agent's describe_table / sample_values tools
(ADR 0010, ticket #37). Pure functions: formatting and the PII/identifier guards.
"""

import re
from typing import Optional

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Always applied, independent of the profile — sample_values must never leak these
# even when a profile ships no table_notes.json.
DEFAULT_BLOCKED_COLUMN_PATTERN = (
    r"(first|middle|last|full|student|teacher)_?name|citizen|national_?id|passport|"
    r"phone|mobile|email|line_?id|address|photo|password|pin_|_pin$|token|hash|"
    r"secret|guardian|birth"
)

SAMPLE_LIMIT = 20
MAX_VALUE_CHARS = 80


def is_identifier(name: str) -> bool:
    return bool(name and _IDENT.match(name))


def column_blocked(column: str, notes: Optional[dict]) -> bool:
    """True when the column name looks like personal data or a credential."""
    patterns = [DEFAULT_BLOCKED_COLUMN_PATTERN]
    extra = ((notes or {}).get("_global") or {}).get("blocked_column_pattern")
    if extra:
        patterns.append(extra)
    return any(re.search(p, column or "", re.IGNORECASE) for p in patterns)


def format_table_notes(table: str, notes: Optional[dict], raw_columns: Optional[str]) -> str:
    """Human/LLM-readable description: curated notes (if any) + the column list."""
    entry = ((notes or {}).get("tables") or {}).get(table)
    lines = [f"Table {table}:"]
    if entry:
        lines.append(f"- Meaning: {entry.get('meaning', '')}")
        lines.append(f"- Population (who/what is in it): {entry.get('population', '')}")
        if entry.get("key_columns"):
            lines.append("- Key columns: " + ", ".join(entry["key_columns"]))
        for j in entry.get("joins", []):
            lines.append(f"- Join: {j}")
        for n in entry.get("notes", []):
            lines.append(f"- Note: {n}")
    else:
        lines.append("- (no curated notes for this table)")
    if raw_columns:
        lines.append(f"- All columns: {raw_columns}")
    return "\n".join(lines)
