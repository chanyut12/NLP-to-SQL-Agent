import pandas as pd
from langchain_community.utilities import SQLDatabase
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from sqlalchemy.engine import Engine
import logging

# Core Imports
from core.rag_store import create_example_store
from core.sql_safety import validate_and_sanitize_sql
from core.schema_utils import get_database_schema, filter_schema, format_schema_for_prompt
from core.config import settings
from core.viz_recommender import recommend_chart, get_chart_options

# Setup Logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class NLPEngine:
    def __init__(self):
        self._llm = None
        self._prompt = None
        self._example_store = None
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
SQL:"""
        return PromptTemplate.from_template(template)

    def clean_sql(self, response: str) -> str:
        """Cleans and formats SQL."""
        import sqlglot
        
        sql = (
            response.strip()
            .replace("```sql", "")
            .replace("```", "")
            .strip()
        )
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
        max_retries: int = 2
    ):
        """
        Main entry point to generate SQL and execute it against the DB.
        Returns: (sql, dataframe_dict, error_message, retry_count)
        """
        # 1. RAG Retrieval
        dynamic_examples = self._example_store.format_examples_for_prompt(question, top_k=3)
        
        # 2. Schema Extraction
        raw_schema = get_database_schema(engine)
        filtered_schema = filter_schema(raw_schema, question)
        schema_text = format_schema_for_prompt(filtered_schema)
        
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
                chart_type, x_col, y_col = recommend_chart(df, question)
                viz_config = {
                    "chart_type": chart_type,
                    "x_col": x_col,
                    "y_col": y_col,
                    "options": get_chart_options(chart_type)
                }
                
                return sql, result_data, None, attempt, viz_config
                
            except Exception as e:
                error_msg = str(e)
                logger.warning(f"Attempt {attempt} failed: {error_msg}")
                
                if attempt < max_retries:
                    # Self-Correction
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
