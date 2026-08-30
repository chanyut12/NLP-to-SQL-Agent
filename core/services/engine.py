import time
import pandas as pd
import asyncio
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
    smart_filter_schema,
    format_schema_for_prompt,
    get_join_hints
)
from core.data.schema_rag import create_schema_rag, SchemaRAG
from core.config import settings
from core.profiles import load_hints as load_profile_hints, examples_path as profile_examples_path
from core.viz.viz_recommender import create_viz_service, VizService
from core.utils.common import clean_sql_response

# Setup Logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class NLPEngine:
    def __init__(self):
        self._llm = None
        self._prompt = None
        self._example_store = None
        self._schema_rag: SchemaRAG = None
        self._viz_service: VizService = None
        self._current_engine: Engine = None  # Track for schema indexing
        self._schema_cache: dict = None  # Cache for database schema
        self._schema_cache_ts: float = 0.0  # When _schema_cache was fetched
        self._schema_text_cache: str = None  # Cache for formatted schema text
        self._join_hints_cache: str = None   # Cache for join hints
        self._all_tables_cache: list = None  # Cache for table list
        self._full_schema_text_cache: str = None  # Cache for full schema (retry path)
        self._schema_reindex: bool = False  # set by refresh_schema(), consumed under the lock
        self._schema_lock = asyncio.Lock()  # serialize schema fetch / RAG (re)index
        self._initialize_resources()

    def _initialize_resources(self):
        """Initialize LLM, Prompt, and RAG Store."""
        logger.info(f"Initializing NLPEngine with provider: {settings.MODEL_PROVIDER}")
        
        # 1. Setup RAG Store (few-shot examples for the active domain profile)
        self._example_store = create_example_store(
            examples_path=profile_examples_path(settings.DOMAIN_PROFILE),
            profile=settings.DOMAIN_PROFILE,
        )

        # 2. Setup LLM
        if settings.MODEL_PROVIDER == "openai":
            from langchain_openai import ChatOpenAI
            if not settings.OPENAI_API_KEY:
                raise ValueError("OPENAI_API_KEY not found in environment variables")
            
            self._llm = ChatOpenAI(
                model=settings.OPENAI_MODEL,
                temperature=0,
                api_key=settings.OPENAI_API_KEY,
                max_retries=settings.LLM_MAX_RETRIES,
            )
        elif settings.MODEL_PROVIDER == "google":
            from langchain_google_genai import ChatGoogleGenerativeAI
            if not settings.GOOGLE_API_KEY:
                raise ValueError("GOOGLE_API_KEY not found in environment variables")
            
            self._llm = ChatGoogleGenerativeAI(
                model=settings.GOOGLE_MODEL,
                temperature=0,
                google_api_key=settings.GOOGLE_API_KEY,
                convert_system_message_to_human=True,
                max_retries=settings.LLM_MAX_RETRIES,
            )
        elif settings.MODEL_PROVIDER == "zhipu":
            from langchain_openai import ChatOpenAI
            if not settings.ZHIPU_API_KEY:
                raise ValueError("ZHIPU_API_KEY not found in environment variables")
            self._llm = ChatOpenAI(
                model=settings.ZHIPU_MODEL,
                temperature=0,
                api_key=settings.ZHIPU_API_KEY,
                base_url="https://api.z.ai/api/coding/paas/v4",
                max_retries=settings.LLM_MAX_RETRIES,
            )
        elif settings.MODEL_PROVIDER == "openrouter":
            from langchain_openai import ChatOpenAI
            if not settings.OPENROUTER_API_KEY:
                raise ValueError("OPENROUTER_API_KEY not found in environment variables")
            self._llm = ChatOpenAI(
                model=settings.OPENROUTER_MODEL,
                temperature=0,
                api_key=settings.OPENROUTER_API_KEY,
                base_url="https://openrouter.ai/api/v1",
                max_retries=settings.LLM_MAX_RETRIES,
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

        # 4. Setup Visualization Service
        self._viz_service = create_viz_service(
            llm=self._llm,
            enable_intelligent=settings.ENABLE_INTELLIGENT_VIZ
        )

    def refresh_schema(self) -> None:
        """Ask the next query to re-introspect the datasource and re-index the
        schema RAG. Safe to call while queries are in flight — the actual work
        happens under the schema lock, not here."""
        self._schema_cache_ts = 0.0
        self._schema_reindex = True
        logger.info("Schema marked stale; next query will re-introspect and re-index.")

    def _create_prompt_template(self) -> PromptTemplate:
        template = """You are an expert SQL analyst specialized in Thai language understanding.
Given an input question (possibly in Thai), create a syntactically correct, read-only SQL query for the target database dialect.

### Target Dialect:
{dialect}

### Rules:
1. Return ONLY a single SELECT statement (WITH ... SELECT is OK). Never generate multiple statements.
2. READ-ONLY ONLY: Never use INSERT/UPDATE/DELETE/DROP/ALTER/CREATE/TRUNCATE/PRAGMA/ATTACH.
3. Always include LIMIT {max_limit} unless the user explicitly requests fewer.
4. Return ONLY the SQL query without markdown or explanations.
5. DO NOT format percentages with '%' symbol in SQL. Return raw numbers.
6. The "Similar Examples" below are automatically retrieved. If they use different tables, ignore them.

{hints}

### Similar Examples (Retrieved dynamically):
{dynamic_examples}

### Current Database Schema:
{schema}

### Your Task:
Question: {question}

Think step by step:
1. Identify which tables match the entities in the question.
2. **Check the Foreign Key Relationships / [FK -> ...] annotations in the schema above to determine correct JOIN conditions.** Do NOT guess JOIN columns — use the FK info provided.
3. Use the correct dialect functions for dates/strings.
4. Write the SQL query using ONLY tables and columns from the schema above.

SQL:"""
        return PromptTemplate.from_template(template).partial(
            hints=load_profile_hints(settings.DOMAIN_PROFILE)
        )

    def clean_sql(self, response: str, dialect: str = None) -> str:
        """Cleans and formats SQL from various LLM output formats."""
        return clean_sql_response(response, dialect)

    async def query_database(
        self,
        question: str,
        engine: Engine,
        dialect: str = "sqlite",
        max_limit: int = None,
        max_retries: int = None,
        preferred_chart_type: str = None
    ):
        """
        Main entry point to generate SQL and execute it against the DB.
        Returns: (sql, dataframe_dict, error_message, retry_count, viz_config)
        
        This method is async and uses parallel RAG retrieval for better performance.
        """
        # Use settings if not explicitly provided
        if max_limit is None:
            max_limit = settings.MAX_SQL_LIMIT
        if max_retries is None:
            max_retries = settings.MAX_RETRIES
        
        pruned = settings.SCHEMA_STRATEGY == "pruned"

        # Schema fetch + RAG (re)index run under one lock so concurrent queries
        # (and a concurrent /admin/refresh-schema) never double-index or race a
        # half-built _schema_rag.
        async with self._schema_lock:
            engine_changed = (self._current_engine != engine)
            cache_fresh = (
                self._schema_cache is not None
                and not engine_changed
                and (time.time() - self._schema_cache_ts) < settings.SCHEMA_CACHE_TTL_SECONDS
            )
            schema_refetched = not cache_fresh
            if cache_fresh:
                raw_schema = self._schema_cache
            else:
                raw_schema = await asyncio.to_thread(get_database_schema, engine)
                self._schema_cache = raw_schema
                self._schema_cache_ts = time.time()
                self._current_engine = engine
                self._schema_text_cache = None
                self._join_hints_cache = None
                self._all_tables_cache = None
                self._full_schema_text_cache = None

            if pruned and self._schema_rag is None:
                self._schema_rag = create_schema_rag(
                    embedder=self._example_store.embedder,
                    embedding_cache=self._example_store._embedding_cache,
                    embedding_lock=self._example_store._embedding_cache_lock,
                    profile=settings.DOMAIN_PROFILE,
                )
            if pruned and (schema_refetched or self._schema_reindex):
                await asyncio.to_thread(
                    self._schema_rag.index_schema_from_db, engine,
                    force_reindex=self._schema_reindex,
                )
                self._schema_reindex = False

            if self._all_tables_cache is None:
                tables_dict = raw_schema.get("tables", raw_schema) if isinstance(raw_schema, dict) and "tables" in raw_schema else raw_schema
                self._all_tables_cache = list(tables_dict.keys())
        
        # Cache the full formatted schema (used by the "full" strategy and by retries)
        if self._schema_text_cache is None:
            schema_text = format_schema_for_prompt(raw_schema)
            join_hints = get_join_hints(self._all_tables_cache, raw_schema)
            if join_hints:
                schema_text += f"\n\n{join_hints}"
            self._schema_text_cache = schema_text
        
        # =============================================================
        # PARALLEL RAG RETRIEVAL - Key Performance Optimization
        # =============================================================
        # Execute Example RAG and Schema processing concurrently
        
        async def get_examples():
            """Async task: Get similar examples from RAG store (returns (text, count))."""
            return await self._example_store.async_format_examples_for_prompt_with_count(
                question,
                top_k=settings.RAG_TOP_K,
                dialect=dialect,
                threshold=settings.RAG_DISTANCE_THRESHOLD
            )
        
        async def get_schema_text():
            """Per-query pruned schema, or the cached full schema."""
            if not pruned:
                return self._schema_text_cache

            # Semantic + Thai-mapping filter to the tables this question needs.
            filtered_schema = await asyncio.to_thread(
                smart_filter_schema,
                raw_schema,
                question,
                self._schema_rag,
                self._llm,
                settings.SCHEMA_TOP_K,
            )
            schema_text = format_schema_for_prompt(filtered_schema)
            tables_dict = filtered_schema.get("tables", filtered_schema) if isinstance(filtered_schema, dict) and "tables" in filtered_schema else filtered_schema
            join_hints = get_join_hints(list(tables_dict.keys()), filtered_schema)
            if join_hints:
                schema_text += f"\n\n{join_hints}"
            return schema_text
        
        # Run both tasks in parallel
        (dynamic_examples, rag_count), schema_text = await asyncio.gather(
            get_examples(),
            get_schema_text()
        )
        
        # =============================================================
        # LLM Chain Execution
        # =============================================================
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
        
        # First Attempt - Use native async invoke
        try:
            response = await chain.ainvoke({"question": question})
            sql = self.clean_sql(response, dialect)
        except Exception as e:
            return None, None, f"LLM Generation Failed: {str(e)}", 0, None, 0

        # Use cached table list
        all_tables = self._all_tables_cache

        # Lazy: full_schema_text only computed if a retry actually needs it
        full_schema_text = self._full_schema_text_cache if self._full_schema_text_cache else None

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

                # Execution - wrap in thread to not block event loop
                df = await asyncio.to_thread(pd.read_sql, sql, engine)

                # Convert DF to dict for JSON serialization
                result_data = df.to_dict(orient='records')

                # Visualization Recommendation (delegated to VizService)
                viz_config = self._viz_service.recommend(df, question, preferred_chart_type)
                logger.info(f"VIZ_DEBUG: chart={viz_config.get('chart_type')}, x={viz_config.get('x_col')}, y={viz_config.get('y_col')}, series={viz_config.get('series_col')}")

                return sql, result_data, None, attempt, viz_config, rag_count

            except Exception as e:
                error_msg = str(e)
                logger.warning(f"Attempt {attempt} failed: {error_msg}")

                if attempt < max_retries:
                    # Lazy compute full schema text (only on first retry)
                    if full_schema_text is None:
                        full_schema_text = format_schema_for_prompt(raw_schema)
                        self._full_schema_text_cache = full_schema_text

                    msg = error_msg.lower()
                    # PostgreSQL: 'column "x" does not exist' / 'relation "x" does not exist'
                    is_column_error = any(p in msg for p in [
                        "unknown column", "no such column", "column not found", "ambiguous column",
                    ]) or ("column" in msg and "does not exist" in msg)
                    is_table_error = any(p in msg for p in [
                        "no such table", "table not found", "doesn't exist", "unknown table",
                    ]) or ("relation" in msg and "does not exist" in msg)

                    # ทั้ง table error และ column error ให้ส่ง full schema + FK info
                    if is_table_error or is_column_error:
                        error_type = "table" if is_table_error else "column"
                        logger.info(f"{error_type.title()} error detected. Sending full schema with FK info...")

                        correction_prompt = f"""The SQL query failed because it referenced a wrong {error_type}.

Target dialect: {dialect}
Error: {error_msg}
Failed SQL: {sql}

### Database Schema (with Foreign Key relationships):
{full_schema_text}

IMPORTANT: Check the [FK -> ...] annotations and "Foreign Key Relationships" section above.
Use those FK paths to determine the correct JOIN conditions — do NOT guess column names.
If two tables are not directly related, find the intermediate table that connects them via FK.

Rewrite the query using ONLY the tables and columns listed above.
Return ONLY the corrected SQL query without any explanation or markdown.
Corrected SQL:"""
                    else:
                        # Standard correction prompt
                        correction_prompt = f"""The following SQL query failed with an error OR violated safety constraints.

Target dialect: {dialect}
Error: {error_msg}
Failed SQL: {sql}

### Database Schema (for reference):
{full_schema_text}

Please analyze the error and provide a corrected SQL query.
Return ONLY the corrected SQL query without any explanation or markdown.
Corrected SQL:"""
                    
                    corrected = await self._llm.ainvoke(correction_prompt)
                    sql = self.clean_sql(corrected.content if hasattr(corrected, 'content') else str(corrected), dialect)
                else:
                    return sql, None, error_msg, attempt, None, rag_count

        return sql, None, "Max retries exceeded", max_retries, None, rag_count
