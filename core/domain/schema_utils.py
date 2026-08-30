"""
Schema utilities for retrieving and formatting database schema.
Helps reduce prompt token usage by filtering relevant tables.
"""
from typing import Dict, List, Any, Optional, Set, TYPE_CHECKING
from sqlalchemy import Engine, inspect, text
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
import re

if TYPE_CHECKING:
    from core.schema_rag import SchemaRAG

_SIMPLE_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")


def quote_ident(name: str) -> str:
    """Double-quote an identifier that PostgreSQL would otherwise fold to
    lower-case (mixed case, e.g. "SchoolID_Onec", "AttendanceStatus")."""
    return name if _SIMPLE_IDENT.match(name) else f'"{name}"'

# Objects that are never useful for analytical Text-to-SQL: migration/backfill
# snapshots, reconcile scratch tables, and identity/audit/config stores.
_DENYLIST_RE = re.compile(
    r"(backup|backfill|_bak\b|reconcile|remediation|demo_provenance|_seed_|"
    r"standardization|migration_20\d{2})",
    re.IGNORECASE,
)
_DENYLIST_EXACT = {
    "araid_identity_records", "araid_profiles", "audit_log", "system_settings",
    "schema_migrations", "_prisma_migrations",
}


def is_denylisted(name: str) -> bool:
    return name in _DENYLIST_EXACT or bool(_DENYLIST_RE.search(name))


def get_database_schema(engine: Engine) -> Dict[str, Any]:
    """
    Retrieve structured schema from the database INCLUDING foreign key relationships.

    Returns: {
        "tables": {table_name: [{"name", "type", "pk", "fk"}, ...]},
        "foreign_keys": [{"from_table", "from_column", "to_table", "to_column"}, ...]
    }

    FK info ช่วยให้ LLM เห็น JOIN path ที่ถูกต้อง โดยเฉพาะ cross-name FKs
    เช่น customers.salesRepEmployeeNumber → employees.employeeNumber
    """
    inspector = inspect(engine)
    tables_schema = {}
    all_foreign_keys = []

    # Views matter for STS: student_current_enrollment_resolution, attendance_day,
    # attendance_effective_records, ... are the sanctioned query surfaces.
    try:
        view_names = set(inspector.get_view_names())
    except Exception:
        view_names = set()
    table_names = [
        t for t in list(inspector.get_table_names()) + sorted(view_names)
        if not is_denylisted(t)
    ]
    for table in table_names:
        columns = []
        try:
            # Get column info
            cols_info = inspector.get_columns(table)

            # Get primary keys (views have none)
            try:
                pk_cols = set(inspector.get_pk_constraint(table).get("constrained_columns", []))
            except Exception:
                pk_cols = set()

            # Get foreign keys (views have none)
            try:
                fk_info = inspector.get_foreign_keys(table)
            except Exception:
                fk_info = []
            fk_lookup = {}  # {src_col: "referred_table.referred_col"}
            for fk in fk_info:
                for src_col, ref_col in zip(
                    fk["constrained_columns"],
                    fk["referred_columns"]
                ):
                    fk_lookup[src_col] = f"{fk['referred_table']}.{ref_col}"
                    all_foreign_keys.append({
                        "from_table": table,
                        "from_column": src_col,
                        "to_table": fk["referred_table"],
                        "to_column": ref_col,
                    })

            # Build column entries with PK/FK annotations
            for col in cols_info:
                columns.append({
                    "name": col["name"],
                    "type": str(col["type"]),
                    "pk": col["name"] in pk_cols,
                    "fk": fk_lookup.get(col["name"]),  # None if not FK
                })
            tables_schema[table] = columns
        except Exception:
            continue

    return {
        "tables": tables_schema,
        "foreign_keys": all_foreign_keys,
    }

def format_schema_for_prompt(schema_data: Dict[str, Any], max_tables: Optional[int] = None) -> str:
    """
    Format schema into a string compatible with the prompt.
    Supports both new format (with FK info) and legacy format (flat dict).

    New format produces:
      - [PK] / [FK -> table.col] annotations per column
      - Consolidated "Foreign Key Relationships" section at the bottom
    """
    if not schema_data:
        return ""

    # Detect new vs legacy format
    if "tables" in schema_data and "foreign_keys" in schema_data:
        tables = schema_data["tables"]
        fks = schema_data["foreign_keys"]
    else:
        # Legacy format — no FK info
        tables = schema_data
        fks = []

    lines = []
    table_names = list(tables.keys())
    if max_tables is not None:
        table_names = table_names[:max_tables]

    for table in table_names:
        lines.append(f"Table: {table}")
        lines.append("Columns:")
        for col in tables[table]:
            suffix = ""
            if col.get("pk"):
                suffix += " [PK]"
            if col.get("fk"):
                ref_t, _, ref_c = col["fk"].partition(".")
                suffix += f" [FK -> {ref_t}.{quote_ident(ref_c)}]" if ref_c else f" [FK -> {col['fk']}]"
            lines.append(f"  - {quote_ident(col['name'])} ({col['type']}){suffix}")
        lines.append("")  # Empty line between tables

    # Consolidated FK section — เฉพาะ FK ที่เกี่ยวกับ tables ที่แสดง
    table_set = set(table_names)
    relevant_fks = [
        fk for fk in fks
        if fk["from_table"] in table_set or fk["to_table"] in table_set
    ]
    if relevant_fks:
        lines.append("Foreign Key Relationships:")
        for fk in relevant_fks:
            lines.append(
                f"  - {fk['from_table']}.{quote_ident(fk['from_column'])} -> "
                f"{fk['to_table']}.{quote_ident(fk['to_column'])}"
            )
        lines.append("")

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

def _llm_guess_tables(question: str, all_tables: List[str], llm) -> Set[str]:
    """
    Tier 3: Ask LLM to guess relevant tables from the full list.
    Used when keyword matching fails.
    """
    if not llm:
        return set()
        
    print("🕵️ Keyword match failed. Asking AI to guess tables...")
    
    prompt = PromptTemplate(
        template="""You are an expert SQL assistant.
Given the user query: "{question}"
And the list of available tables: {all_tables}

Identify the top 3 most relevant tables needed to answer this query.
Return ONLY the table names separated by commas. Do not explain.
If you are unsure, return the most likely ones.

Relevant Tables:""",
        input_variables=["question", "all_tables"]
    )
    
    chain = prompt | llm | StrOutputParser()
    
    try:
        response = chain.invoke({
            "question": question,
            "all_tables": ", ".join(all_tables)
        })
        
        guessed = set()
        # Clean up response (handle commas, newlines, extra spaces)
        raw_names = [n.strip() for n in response.replace('\n', ',').split(',')]
        
        for name in raw_names:
            # Case-insensitive match against real table names
            for real_table in all_tables:
                if name.lower() == real_table.lower():
                    guessed.add(real_table)
                    break
                    
        print(f"🤖 AI Guessed: {guessed}")
        return guessed
        
    except Exception as e:
        print(f"⚠️ AI Guessing failed: {e}")
        return set()

def _get_tables_dict(schema_data: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """Helper: extract tables dict from new or legacy schema format."""
    if "tables" in schema_data and "foreign_keys" in schema_data:
        return schema_data["tables"]
    return schema_data


def _build_filtered_schema(
    schema_data: Dict[str, Any],
    relevant_tables: Set[str]
) -> Dict[str, Any]:
    """Helper: build filtered schema preserving FK info if available."""
    if "tables" in schema_data and "foreign_keys" in schema_data:
        filtered_tables = {
            t: schema_data["tables"][t]
            for t in relevant_tables if t in schema_data["tables"]
        }
        # Keep only FKs where both tables are in filtered set
        filtered_fks = [
            fk for fk in schema_data["foreign_keys"]
            if fk["from_table"] in relevant_tables or fk["to_table"] in relevant_tables
        ]
        return {"tables": filtered_tables, "foreign_keys": filtered_fks}
    else:
        return {t: schema_data[t] for t in relevant_tables if t in schema_data}


def smart_filter_schema(
    schema_data: Dict[str, Any],
    question: str,
    schema_rag: Optional["SchemaRAG"] = None,
    llm: Optional[Any] = None,
    top_k: int = 5
) -> Dict[str, Any]:
    """
    Smart schema filtering using semantic search + Thai mapping + keyword matching + LLM guessing.
    Supports both new format (with FK info) and legacy format.

    Args:
        schema_data: Full database schema (new or legacy format)
        question: User's question (Thai or English)
        schema_rag: Optional SchemaRAG instance for semantic search
        llm: Optional LangChain LLM object for fallback guessing
        top_k: Maximum number of tables to return

    Returns:
        Filtered schema (same format as input)
    """
    tables = _get_tables_dict(schema_data)

    if not tables:
        return schema_data

    # If schema is small, return everything
    if len(tables) <= 5:
        return schema_data

    relevant_tables: Set[str] = set()

    # 1. Use SchemaRAG if available (Tier 1 - Semantic + Thai mapping)
    if schema_rag is not None:
        try:
            rag_tables = schema_rag.get_relevant_tables(question, top_k=top_k)
            relevant_tables.update(rag_tables)
        except Exception as e:
            print(f"Warning: SchemaRAG search failed: {e}")

    # 2. Keyword matching (Tier 2)
    question_lower = question.lower()
    for table, columns in tables.items():
        if table.lower() in question_lower:
            relevant_tables.add(table)
            continue
        for col in columns:
            if col['name'].lower() in question_lower:
                relevant_tables.add(table)
                break

    # 3. LLM Guessing (Tier 3 - Fallback)
    if not relevant_tables and llm:
        guessed_tables = _llm_guess_tables(question, list(tables.keys()), llm)
        relevant_tables.update(guessed_tables)

    # 4. If we found some tables, include their related tables for JOINs
    if schema_rag is not None and relevant_tables:
        try:
            from core.data.schema_rag import expand_tables_with_relationships
            relationships = schema_rag.get_table_relationships()
            expanded = expand_tables_with_relationships(
                list(relevant_tables),
                relationships,
                max_total=top_k + 3
            )
            relevant_tables.update(expanded)
        except Exception as e:
            print(f"Warning: Could not expand related tables: {e}")

    # 5. Fallback: If still nothing found, return all
    if not relevant_tables:
        return schema_data

    # 6. Build filtered schema (preserving FK info)
    filtered = _build_filtered_schema(schema_data, relevant_tables)
    return filtered if (_get_tables_dict(filtered)) else schema_data


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
    schema_data: Dict[str, Any]
) -> str:
    """
    Generate JOIN hints using actual FK relationships when available.
    Falls back to column name matching for legacy schema format.

    Args:
        tables: List of table names to generate hints for
        schema_data: Database schema (new format with FK or legacy flat dict)

    Returns:
        String with JOIN hints for the prompt
    """
    if len(tables) < 2:
        return ""

    # Use FK-based hints if available (new format)
    if "foreign_keys" in schema_data:
        return _join_hints_from_fks(tables, schema_data["foreign_keys"])

    # Legacy fallback: column name intersection
    return _join_hints_from_names(tables, schema_data)


def _join_hints_from_fks(tables: List[str], foreign_keys: List[Dict[str, str]]) -> str:
    """Generate JOIN hints from actual FK constraint data — ไม่พลาด cross-name FKs."""
    table_set = set(tables)
    hints = []

    for fk in foreign_keys:
        from_t = fk["from_table"]
        to_t = fk["to_table"]
        # แสดงเฉพาะ FK ที่ทั้ง 2 tables อยู่ใน filtered set
        if from_t in table_set and to_t in table_set:
            hints.append(
                f"- {from_t}.{fk['from_column']} = {to_t}.{fk['to_column']}"
            )

    if hints:
        return "JOIN Conditions (from Foreign Keys):\n" + "\n".join(hints)
    return ""


def _join_hints_from_names(tables: List[str], schema: Dict[str, List[Dict[str, Any]]]) -> str:
    """Legacy: Generate JOIN hints from column name intersection."""
    table_columns: Dict[str, Set[str]] = {}
    for table in tables:
        if table in schema:
            table_columns[table] = {col['name'].lower() for col in schema[table]}

    hints = []
    checked_pairs = set()

    for t1 in tables:
        for t2 in tables:
            if t1 >= t2:
                continue
            pair = (t1, t2)
            if pair in checked_pairs:
                continue
            checked_pairs.add(pair)

            if t1 in table_columns and t2 in table_columns:
                common = table_columns[t1] & table_columns[t2]
                if common:
                    for col in list(common)[:2]:
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
