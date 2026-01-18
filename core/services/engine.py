import pandas as pd
from langchain_community.utilities import SQLDatabase
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from sqlalchemy.engine import Engine
import logging

# Core Imports
from core.data.rag_store import create_example_store
from core.domain.sql_safety import validate_and_sanitize_sql
from core.domain.schema_utils import (
    get_database_schema, 
    filter_schema, 
    smart_filter_schema,
    format_schema_for_prompt,
    validate_sql_tables,
    get_join_hints
)
from core.data.schema_rag import create_schema_rag, SchemaRAG
from core.config import settings
from core.viz.viz_recommender import recommend_chart_with_series, get_chart_options

# Setup Logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class NLPEngine:
    def __init__(self):
        self._llm = None
        self._prompt = None
        self._example_store = None
        self._schema_rag: SchemaRAG = None
        self._current_engine: Engine = None  # Track for schema indexing
        self._schema_cache: dict = None  # Cache for database schema
        self._initialize_resources()

    def _initialize_resources(self):
        """Initialize LLM, Prompt, and RAG Store."""
        logger.info(f"Initializing NLPEngine with provider: {settings.MODEL_PROVIDER}")
        
        # 1. Setup RAG Store
        self._example_store = create_example_store(examples_path="thai_sql_examples.json")

        # 2. Setup LLM
        if settings.MODEL_PROVIDER == "openai":
            from langchain_openai import ChatOpenAI
            if not settings.OPENAI_API_KEY:
                raise ValueError("OPENAI_API_KEY not found in environment variables")
            
            self._llm = ChatOpenAI(
                model=settings.OPENAI_MODEL,
                temperature=0,
                api_key=settings.OPENAI_API_KEY
            )
        elif settings.MODEL_PROVIDER == "google":
            from langchain_google_genai import ChatGoogleGenerativeAI
            if not settings.GOOGLE_API_KEY:
                raise ValueError("GOOGLE_API_KEY not found in environment variables")
            
            self._llm = ChatGoogleGenerativeAI(
                model=settings.GOOGLE_MODEL,
                temperature=0,
                google_api_key=settings.GOOGLE_API_KEY,
                convert_system_message_to_human=True
            )
        else:
            from langchain_ollama import ChatOllama
            self._llm = ChatOllama(
                model=settings.OLLAMA_MODEL,
                temperature=0,
                base_url=settings.OLLAMA_BASE_URL
            )

        # 3. Setup Prompt Template
        self._prompt = self._create_prompt_template()

    def _create_prompt_template(self) -> PromptTemplate:
        template = """You are an expert SQL analyst specialized in Thai language understanding.
Given an input question (possibly in Thai), create a syntactically correct, read-only SQL query for the target database dialect.

### Target Dialect:
{dialect}

### Instructions:
4. Return ONLY a single statement (WITH ... SELECT is OK). Never generate multiple statements.
5. READ-ONLY ONLY: Never use INSERT/UPDATE/DELETE/DROP/ALTER/CREATE/TRUNCATE/PRAGMA/ATTACH.
6. Always include LIMIT {max_limit} unless the user explicitly requests fewer.
7. Return ONLY the SQL query without markdown or explanations.
8. DO NOT format percentages with '%' symbol in SQL (e.g., CONCAT(..., '%')). Return raw numbers. Frontend will handle formatting.
9. **IMPORTANT**: The "Similar Examples" below are automatically retrieved. If they rely on different tables or seem irrelevant to the current question, **IGNORE THEM** and rely on your own reasoning.

### Dialect-Specific Functions (Cheat Sheet):
- **Date extraction**: 
  - MySQL: YEAR(date_col), MONTH(date_col)
  - SQLite: strftime('%Y', date_col), strftime('%m', date_col)
- **String concat**: 
  - MySQL: CONCAT(a, b)
  - SQLite: a || b

### Thai-to-English Schema Mapping:
- "ยอดขาย" / "ยอดรวม" -> total_price (use SUM for aggregation)
- "จำนวนใบเสร็จ" / "กี่ใบ" -> COUNT(receipt_id)
- "ลูกค้า" / "คนซื้อ" -> customer_name
- "หมวดหมู่" / "ประเภทสินค้า" -> product_category
- "เดือน" -> month (values: 'January', 'February', ..., 'December')
- "การชำระเงิน" / "จ่ายเงิน" -> payment_method
- "ค่าเฉลี่ย" / "เฉลี่ย" -> AVG(...)
- "มากที่สุด" / "สูงสุด" -> ORDER BY ... DESC LIMIT
- "น้อยที่สุด" / "ต่ำสุด" -> ORDER BY ... ASC LIMIT

### Similar Examples (Retrieved dynamically):
{dynamic_examples}

### Current Database Schema:
{schema}

### Your Task (IMPORTANT: Use ONLY the tables and columns from the schema above):
Question: {question}

Think step by step:
1. Identify which tables match the entities in the question.
2. Check if tables need to be joined (look for common columns).
3. Use the correct dialect functions for dates/strings.
4. Write the SQL query.

SQL:"""
        return PromptTemplate.from_template(template)

    def clean_sql(self, response: str) -> str:
        """Cleans and formats SQL from various LLM output formats."""
        import sqlglot
        import re
        from core.utils.common import normalize_sql_code

        # 1. Use common normalization (Extracts from <sql> or ```sql)
        sql = normalize_sql_code(response)

        # 2. If still contains explanatory text (no clean block found), find the last SELECT statement
        # Note: normalize_sql_code returns stripped text if no tags found.
        if not sql.upper().startswith('SELECT') and not sql.upper().startswith('WITH'):
            # Find all SELECT statements
            select_matches = list(re.finditer(r'(SELECT\s+.+?;)', sql, re.IGNORECASE | re.DOTALL))
            if select_matches:
                sql = select_matches[-1].group(1).strip()
            else:
                # Try without semicolon
                select_match = re.search(r'(SELECT\s+[^;]+)', sql, re.IGNORECASE | re.DOTALL)
                if select_match:
                    sql = select_match.group(1).strip()

        # 3. Remove trailing explanation text after semicolon
        if ';' in sql:
            sql = sql.split(';')[0] + ';'

        try:
            # Pretty print SQL
            return sqlglot.transpile(sql, read=None, write=None, pretty=True)[0]
        except Exception:
            return sql

    def query_database(
        self,
        question: str,
        engine: Engine,
        dialect: str = "sqlite",
        max_limit: int = 500,
        max_retries: int = 2,
        preferred_chart_type: str = None
    ):
        """
        Main entry point to generate SQL and execute it against the DB.
        Returns: (sql, dataframe_dict, error_message, retry_count)
        """
        # 1. RAG Retrieval (ส่ง dialect เพื่อ filter examples ที่ตรงกับ database)
        dynamic_examples = self._example_store.format_examples_for_prompt(
            question, 
            top_k=3, 
            dialect=dialect,
            threshold=settings.RAG_DISTANCE_THRESHOLD
        )
        
        # 2. Schema Extraction with Caching
        # Check if we have cached schema for this engine
        engine_changed = (self._current_engine != engine)
        
        if not engine_changed and self._schema_cache is not None:
            raw_schema = self._schema_cache
        else:
            # Cache miss or engine changed - fetch and cache
            raw_schema = get_database_schema(engine)
            self._schema_cache = raw_schema
            self._current_engine = engine
        
        
        # Use smart filtering ONLY for local LLM (limited context window)
        # Cloud LLMs (OpenAI, Claude) can handle full schema, so skip optimization
        if settings.MODEL_PROVIDER == "ollama":
            # Initialize & index SchemaRAG if needed (lazy, once per DB)
            if self._schema_rag is None:
                # Share embedder from ExampleStore to save RAM
                shared_embedder = self._example_store.embedder
                self._schema_rag = create_schema_rag(embedder=shared_embedder)
            
            if engine_changed:
                self._schema_rag.index_schema_from_db(engine)
            
            # Use smart filtering (semantic + Thai mapping)
            filtered_schema = smart_filter_schema(
                raw_schema, 
                question, 
                schema_rag=self._schema_rag,
                llm=self._llm,  # Send LLM for Tier 3 Guessing
                top_k=5
            )
            
            # Add JOIN hints if multiple tables
            join_hints = get_join_hints(list(filtered_schema.keys()), filtered_schema)
            schema_text = format_schema_for_prompt(filtered_schema)
            if join_hints:
                schema_text += f"\n\n{join_hints}"
        else:
            # Cloud LLM: use full schema (no filtering needed)
            filtered_schema = raw_schema
            schema_text = format_schema_for_prompt(raw_schema)
        
        # 3. Chain Execution
        chain = (
            self._prompt.partial(
                dynamic_examples=dynamic_examples,
                schema=schema_text,
                dialect=dialect,
                max_limit=max_limit,
            )
            | self._llm
            | StrOutputParser()
        )
        
        # 4. First Attempt
        try:
            response = chain.invoke({"question": question})
            sql = self.clean_sql(response)
        except Exception as e:
            return None, None, f"LLM Generation Failed: {str(e)}", 0, None

        # 5. Retry Loop
        all_tables = list(raw_schema.keys())
        
        for attempt in range(max_retries + 1):
            try:
                # Validation
                safe_sql_obj = validate_and_sanitize_sql(
                    sql,
                    dialect=dialect,
                    max_limit=max_limit,
                    allowed_tables=all_tables
                )
                sql = safe_sql_obj.sql
                
                # Re-format for readability after validation (which may minify it)
                try:
                    import sqlglot
                    sql = sqlglot.transpile(sql, read=dialect, write=dialect, pretty=True)[0]
                except Exception:
                    pass # Keep as is if formatting fails

                # Execution
                df = pd.read_sql(sql, engine)
                
                # Convert DF to dict for JSON serialization
                # Using 'records' orientation: [{'col1': val, 'col2': val}, ...]
                result_data = df.to_dict(orient='records')

                # Visualization Recommendation
                # Priority 1: Use Intelligent Viz (if available)
                # Priority 2: Use Rule-based (fallback)
                viz_config = {}
                
                try:
                    if self._llm and settings.ENABLE_INTELLIGENT_VIZ:
                        from core.viz.viz_recommender import recommend_chart_intelligent
                        viz_config = recommend_chart_intelligent(df, question, self._llm)
                        
                        # Add options (helper)
                        viz_config["options"] = get_chart_options(viz_config.get("chart_type", "table"))
                    else:
                        # Fallback to Rule-based if LLM not available OR disabled by config
                        raise ValueError("Intelligent Viz disabled or no LLM")
                        
                except Exception as e:
                    # Fallback to Rule-based
                    chart_type, x_col, y_col, series_col = recommend_chart_with_series(df, question, preferred_chart_type)
                    viz_config = {
                        "chart_type": chart_type,
                        "x_col": x_col,
                        "y_col": y_col,
                        "series_col": series_col,  # NEW: Multi-series support
                        "options": get_chart_options(chart_type),
                        "title": "Visualization",
                        "reason": "Rule-based recommendation"
                    }
                    # DEBUG: Log the viz config
                    logger.info(f"VIZ_DEBUG: chart={chart_type}, x={x_col}, y={y_col}, series={series_col}")
                
                return sql, result_data, None, attempt, viz_config
                
            except Exception as e:
                error_msg = str(e)
                logger.warning(f"Attempt {attempt} failed: {error_msg}")
                
                if attempt < max_retries:
                    # Check if it's a "table not found" error
                    is_table_error = any(phrase in error_msg.lower() for phrase in [
                        "no such table", "table not found", "doesn't exist",
                        "unknown table", "relation.*does not exist"
                    ])
                    
                    # Enhanced correction with schema context
                    if is_table_error:
                        # Expand schema to include more tables
                        logger.info("Table error detected. Expanding schema context...")
                        expanded_schema = raw_schema  # Use full schema
                        expanded_text = format_schema_for_prompt(expanded_schema)
                        
                        correction_prompt = f"""The SQL query failed because it used a table that doesn't exist.

Target dialect: {dialect}
Error: {error_msg}
Failed SQL: {sql}

### Available Tables (FULL LIST - Use ONLY these):
{expanded_text}

Rewrite the query using ONLY the tables listed above.
Return ONLY the corrected SQL query without any explanation or markdown.
Corrected SQL:"""
                    else:
                        # Standard correction prompt
                        correction_prompt = f"""The following SQL query failed with an error OR violated safety constraints.

Target dialect: {dialect}
Error: {error_msg}
Failed SQL: {sql}

Please analyze the error and provide a corrected SQL query.
Return ONLY the corrected SQL query without any explanation or markdown.
Corrected SQL:"""
                    
                    corrected = self._llm.invoke(correction_prompt)
                    sql = self.clean_sql(corrected.content if hasattr(corrected, 'content') else str(corrected))
                else:
                    return sql, None, error_msg, attempt, None

        return sql, None, "Max retries exceeded", max_retries, None
