"""
Schema utilities for retrieving and formatting database schema.
Helps reduce prompt token usage by filtering relevant tables.
"""
from typing import Dict, List, Any, Optional, Set, TYPE_CHECKING
from sqlalchemy import Engine, inspect, text
import re

if TYPE_CHECKING:
    from core.schema_rag import SchemaRAG

def get_database_schema(engine: Engine) -> Dict[str, List[Dict[str, Any]]]:
    """
    Retrieve structured schema from the database.
    Returns: {table_name: [{name, type, ...}, ...]}
    """
    inspector = inspect(engine)
    schema = {}
    
    table_names = inspector.get_table_names()
    for table in table_names:
        columns = []
        try:
            cols_info = inspector.get_columns(table)
            for col in cols_info:
                columns.append({
                    "name": col["name"],
                    "type": str(col["type"]),
                    # "comment": col.get("comment", "") # Optional if driver supports
                })
            schema[table] = columns
        except Exception:
            continue
            
    return schema

def format_schema_for_prompt(schema: Dict[str, List[Dict[str, Any]]], max_tables: int = 10) -> str:
    """
    Format schema into a string compatible with the prompt.
    Mimics CREATE TABLE syntax for clarity.
    """
    if not schema:
        return ""
        
    lines = []
    tables = list(schema.keys())[:max_tables]  # Limit tables if too many
    
    for table in tables:
        lines.append(f"Table: {table}")
        lines.append("Columns:")
        for col in schema[table]:
            lines.append(f" - {col['name']} ({col['type']})")
        lines.append("") # Empty line between tables
        
    return "\n".join(lines)

def filter_schema(schema: Dict[str, List[Dict[str, Any]]], question: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    Heuristic filtering: Keep tables where table name or column names appear in question.
    If no match found, return all schema (fallback).
    """
    if not schema:
        return {}
        
    question_lower = question.lower()
    relevant_schema = {}
    
    for table, columns in schema.items():
        # Check table name match
        if table.lower() in question_lower:
            relevant_schema[table] = columns
            continue
            
        # Check column match
        for col in columns:
            if col['name'].lower() in question_lower:
                relevant_schema[table] = columns
                break
    
    # If heuristic found nothing, return everything (safer than returning empty)
    # Or if schema is small (< 5 tables), just return all
    if not relevant_schema or len(schema) < 5:
        return schema
        
    return relevant_schema


# =============================================================================
# Smart Schema Filtering (New)
# =============================================================================

def smart_filter_schema(
    schema: Dict[str, List[Dict[str, Any]]],
    question: str,
    schema_rag: Optional["SchemaRAG"] = None,
    top_k: int = 5
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Smart schema filtering using semantic search + Thai mapping + keyword matching.
    
    Args:
        schema: Full database schema
        question: User's question (Thai or English)
        schema_rag: Optional SchemaRAG instance for semantic search
        top_k: Maximum number of tables to return
        
    Returns:
        Filtered schema with only relevant tables
    """
    if not schema:
        return {}
    
    # If schema is small, return everything
    if len(schema) <= 5:
        return schema
    
    relevant_tables: Set[str] = set()
    
    # 1. Use SchemaRAG if available (semantic + Thai mapping)
    if schema_rag is not None:
        try:
            rag_tables = schema_rag.get_relevant_tables(question, top_k=top_k)
            relevant_tables.update(rag_tables)
        except Exception as e:
            print(f"Warning: SchemaRAG search failed: {e}")
    
    # 2. Fallback: Use keyword matching
    question_lower = question.lower()
    for table, columns in schema.items():
        # Check table name in question
        if table.lower() in question_lower:
            relevant_tables.add(table)
            continue
        
        # Check column names in question
        for col in columns:
            if col['name'].lower() in question_lower:
                relevant_tables.add(table)
                break
    
    # 3. If we found some tables, include their related tables for JOINs
    if schema_rag is not None and relevant_tables:
        try:
            from core.schema_rag import expand_tables_with_relationships
            relationships = schema_rag.get_table_relationships()
            expanded = expand_tables_with_relationships(
                list(relevant_tables), 
                relationships, 
                max_total=top_k + 3  # Allow a few extra for JOINs
            )
            relevant_tables.update(expanded)
        except Exception:
            pass
    
    # 4. If still nothing found, return all (safer fallback)
    if not relevant_tables:
        return schema
    
    # 5. Build filtered schema
    filtered = {t: schema[t] for t in relevant_tables if t in schema}
    
    return filtered if filtered else schema


def validate_sql_tables(sql: str, available_tables: List[str]) -> Dict[str, Any]:
    """
    Validate that SQL only uses available tables.
    
    Args:
        sql: SQL query string
        available_tables: List of valid table names
        
    Returns:
        {
            "valid": bool,
            "missing_tables": list of tables not in schema,
            "used_tables": list of tables used in SQL
        }
    """
    # Normalize table names for comparison
    available_lower = {t.lower(): t for t in available_tables}
    
    # Extract table names from SQL using regex
    # Matches: FROM table, JOIN table, INTO table, UPDATE table
    patterns = [
        r'\bFROM\s+(\w+)',
        r'\bJOIN\s+(\w+)',
        r'\bINTO\s+(\w+)',
        r'\bUPDATE\s+(\w+)',
    ]
    
    used_tables: Set[str] = set()
    sql_upper = sql.upper()
    
    for pattern in patterns:
        matches = re.findall(pattern, sql_upper, re.IGNORECASE)
        used_tables.update(m.lower() for m in matches)
    
    # Find missing tables
    missing = []
    matched = []
    
    for table in used_tables:
        if table in available_lower:
            matched.append(available_lower[table])
        else:
            missing.append(table)
    
    return {
        "valid": len(missing) == 0,
        "missing_tables": missing,
        "used_tables": matched
    }


def get_join_hints(
    tables: List[str], 
    schema: Dict[str, List[Dict[str, Any]]]
) -> str:
    """
    Generate JOIN hints for given tables based on common column names.
    
    Args:
        tables: List of table names
        schema: Database schema
        
    Returns:
        String with JOIN hints for the prompt
    """
    if len(tables) < 2:
        return ""
    
    # Find common columns between tables
    table_columns: Dict[str, Set[str]] = {}
    for table in tables:
        if table in schema:
            table_columns[table] = {col['name'].lower() for col in schema[table]}
    
    hints = []
    checked_pairs = set()
    
    for t1 in tables:
        for t2 in tables:
            if t1 >= t2:  # Avoid duplicates
                continue
            
            pair = (t1, t2)
            if pair in checked_pairs:
                continue
            checked_pairs.add(pair)
            
            if t1 in table_columns and t2 in table_columns:
                common = table_columns[t1] & table_columns[t2]
                if common:
                    for col in list(common)[:2]:  # Limit to 2 columns
                        hints.append(f"- {t1}.{col} = {t2}.{col}")
    
    if hints:
        return "Possible JOINs:\n" + "\n".join(hints)
    
    return ""


def find_missing_tables(
    missing_tables: List[str],
    full_schema: Dict[str, List[Dict[str, Any]]],
    schema_rag: Optional["SchemaRAG"] = None
) -> List[str]:
    """
    Try to find the correct table names for missing tables.
    Useful for error recovery when LLM generates wrong table names.
    
    Args:
        missing_tables: Table names that were not found
        full_schema: Full database schema
        schema_rag: Optional SchemaRAG for semantic matching
        
    Returns:
        List of suggested corrections
    """
    suggestions = []
    all_tables = list(full_schema.keys())
    
    for missing in missing_tables:
        missing_lower = missing.lower()
        
        # 1. Try fuzzy match on table names
        for table in all_tables:
            table_lower = table.lower()
            # Substring match
            if missing_lower in table_lower or table_lower in missing_lower:
                suggestions.append(f"'{missing}' → maybe '{table}'?")
                break
        else:
            # 2. Try semantic search if available
            if schema_rag:
                try:
                    related = schema_rag.get_relevant_tables(missing, top_k=1)
                    if related:
                        suggestions.append(f"'{missing}' → maybe '{related[0]}'?")
                except Exception:
                    pass
    
    return suggestions

