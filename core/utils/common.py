"""
Common Utilities Module for Thai NLP-to-SQL Agent.

This module provides shared utility functions to reduce code duplication
across the codebase.
"""

import hashlib
from typing import List, Any


def generate_stable_id(*args: Any) -> str:
    """
    Generate a stable MD5 hash ID from input arguments.
    
    This is used throughout the application for generating consistent IDs
    for RAG examples, schema entries, and other entities.
    
    Args:
        *args: Variable number of arguments to hash. They will be joined with '|'.
        
    Returns:
        MD5 hex digest string.
        
    Example:
        >>> generate_stable_id("question text", "SELECT * FROM users")
        'a1b2c3...'
    """
    content = "|".join(str(arg).strip() for arg in args)
    return hashlib.md5(content.encode()).hexdigest()


def truncate_text(text: str, max_length: int = 50, suffix: str = "...") -> str:
    """
    Truncate text with ellipsis if it exceeds max_length.
    
    Args:
        text: The text to truncate.
        max_length: Maximum length before truncation.
        suffix: String to append when truncated (default: "...").
        
    Returns:
        Truncated text with suffix, or original text if short enough.
        
    Example:
        >>> truncate_text("This is a very long text", 10)
        'This is...'
    """
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def format_timestamp(iso_timestamp: str) -> str:
    """
    Format ISO timestamp to readable format.
    
    Args:
        iso_timestamp: Timestamp string in ISO format.
        
    Returns:
        Formatted string "YYYY-MM-DD HH:MM" or original if parsing fails.
    """
    from datetime import datetime
    try:
        dt = datetime.fromisoformat(iso_timestamp)
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return iso_timestamp[:16] if len(iso_timestamp) >= 16 else iso_timestamp


def normalize_sql_code(raw_sql: str) -> str:
    """
    Clean and normalize SQL code by removing markdown blocks and extracting the query.

    Args:
        raw_sql: Raw SQL string potentially containing markdown or HTML tags.

    Returns:
        Cleaned SQL string.
    """
    import re

    if not raw_sql:
        return ""

    sql = raw_sql.strip()

    # 1. Extract SQL from <sql>...</sql> tags
    sql_tag_match = re.search(r'<sql>\s*(SELECT[^<]+)', sql, re.IGNORECASE | re.DOTALL)
    if sql_tag_match:
        return sql_tag_match.group(1).strip()

    # 2. Extract SQL from ```sql...``` markdown blocks
    sql_block_match = re.search(r'```sql\s*(SELECT[^`]+)', sql, re.IGNORECASE | re.DOTALL)
    if sql_block_match:
        return sql_block_match.group(1).strip()

    # 3. Simple Markdown cleanup if regex didn't match (e.g. valid SQL wrapped in backticks)
    sql = sql.replace("```sql", "").replace("```", "").strip()

    return sql


def clean_sql_response(response: str, dialect: str = None) -> str:
    """
    Clean and format SQL from LLM response.

    Handles various output formats including markdown blocks, XML tags,
    and explanatory text. Extracts and pretty-prints the SQL.

    Args:
        response: Raw LLM response containing SQL.
        dialect: Optional SQL dialect for formatting (e.g., 'sqlite', 'mysql').

    Returns:
        Cleaned and formatted SQL string.
    """
    import re

    # 1. Use common normalization (Extracts from <sql> or ```sql)
    sql = normalize_sql_code(response)

    # 2. If still contains explanatory text, find the last SELECT statement
    if not sql.upper().startswith('SELECT') and not sql.upper().startswith('WITH'):
        select_matches = list(re.finditer(r'(SELECT\s+.+?;)', sql, re.IGNORECASE | re.DOTALL))
        if select_matches:
            sql = select_matches[-1].group(1).strip()
        else:
            select_match = re.search(r'(SELECT\s+[^;]+)', sql, re.IGNORECASE | re.DOTALL)
            if select_match:
                sql = select_match.group(1).strip()

    # 3. Remove trailing explanation text after semicolon
    if ';' in sql:
        sql = sql.split(';')[0] + ';'

    # 4. Try to pretty print with sqlglot
    try:
        import sqlglot
        return sqlglot.transpile(sql, read=dialect, write=dialect, pretty=True)[0]
    except Exception:
        return sql
