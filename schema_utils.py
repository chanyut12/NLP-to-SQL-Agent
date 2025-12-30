"""
Schema utilities for retrieving and formatting database schema.
Helps reduce prompt token usage by filtering relevant tables.
"""
from typing import Dict, List, Any, Optional
from sqlalchemy import Engine, inspect, text

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

