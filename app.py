import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, inspect
from langchain_community.utilities import SQLDatabase
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
import time
import os
import csv
import json # added for jsonl logging
import uuid
import plotly.express as px

# RAG Store for dynamic few-shot examples
from rag_store import create_example_store

# SQL Safety (read-only, single statement, limit clamp)
from sql_safety import SQLSafetyError, validate_and_sanitize_sql

# Schema Utils
from schema_utils import get_database_schema, filter_schema, format_schema_for_prompt

# Viz Utils
from viz_recommender import recommend_chart, get_chart_options

# Query History & Favorites
from query_history import QueryHistoryManager, truncate_text, format_timestamp

# --- 1. ตั้งค่า Page ---
st.set_page_config(page_title="Thai NLP to SQL Agent", layout="wide")
st.title("🤖 AI Data Analyst (Thai Supported)")

# Detect model provider from secrets (default: ollama for local)
model_provider = st.secrets.get("MODEL_PROVIDER", "ollama").lower()
st.caption(f"Powered by {'OpenAI' if model_provider == 'openai' else 'Qwen2.5-Coder (Ollama)'} & Streamlit")

# --- 2. Caching Resources (Performance Optimization) ---
def get_db_engine(db_type, db_config):
    """สร้าง Connection ไปยัง Database และ cache ไว้"""
    try:
        if db_type == "SQLite":
            db_path = f"sqlite:///{db_config['database']}"
        elif db_type == "MySQL":
            db_path = f"mysql+pymysql://{db_config['user']}:{db_config['password']}@{db_config['host']}:{db_config['port']}/{db_config['database']}?charset=utf8mb4"
        elif db_type == "PostgreSQL":
            db_path = f"postgresql+psycopg2://{db_config['user']}:{db_config['password']}@{db_config['host']}:{db_config['port']}/{db_config['database']}"
        else:
            raise ValueError(f"Unsupported database type: {db_type}")
        
        engine = create_engine(db_path)
        # ทดสอบการเชื่อมต่อ
        with engine.connect() as conn:
            pass
        return engine, None  # Return engine and no error
    except Exception as e:
        return None, str(e)  # Return None and error message

@st.cache_resource
def get_example_store():
    """Initialize and cache the RAG example store."""
    return create_example_store(examples_path="thai_sql_examples.json")

@st.cache_resource
def get_llm_chain():
    """โหลด Model และสร้าง Prompt Chain เก็บไว้ (รองรับทั้ง Ollama และ OpenAI)"""
    
    # Note: Schema will be injected dynamically at runtime based on connected database
    
    # Detect model provider from secrets (default: ollama for local development)
    model_provider = st.secrets.get("MODEL_PROVIDER", "ollama").lower()
    
    # Setup LLM based on provider
    if model_provider == "openai":
        # OpenAI API (for cloud deployment)
        from langchain_openai import ChatOpenAI
        
        api_key = st.secrets.get("OPENAI_API_KEY")
        if not api_key:
            st.error("❌ OpenAI API Key not found! Please set OPENAI_API_KEY in secrets.")
            st.stop()
        
        llm = ChatOpenAI(
            model=st.secrets.get("OPENAI_MODEL", "gpt-4o-mini"),  # configurable model
            temperature=0,
            api_key=api_key
        )
        st.info("🤖 Using OpenAI API")
    
    else:  # default: ollama
        # Ollama (for local development)
        from langchain_ollama import ChatOllama
        
        llm = ChatOllama(
            model=st.secrets.get("OLLAMA_MODEL", "qwen2.5-coder:7b"),  # configurable model
            temperature=0
        )
        st.info("🤖 Using Ollama (Local)")
    
    # 3. Setup Prompt with Dynamic Few-shot Examples (RAG-based)
    # Note: {dynamic_examples} will be filled at runtime with semantically similar examples
    template = """You are an expert SQL analyst specialized in Thai language understanding.
Given an input question (possibly in Thai), create a syntactically correct, read-only SQL query for the target database dialect.

### Target Dialect:
{dialect}

### Instructions:
1. Interpret Thai keywords and map them to English column names
2. Determine the appropriate SQL operation (SELECT, COUNT, SUM, AVG, etc.)
3. Apply filters (WHERE) and groupings (GROUP BY) as needed
4. Return ONLY a single statement (WITH ... SELECT is OK). Never generate multiple statements.
5. READ-ONLY ONLY: Never use INSERT/UPDATE/DELETE/DROP/ALTER/CREATE/TRUNCATE/PRAGMA/ATTACH.
6. Always include LIMIT {max_limit} unless the user explicitly requests fewer.
7. Return ONLY the SQL query without markdown or explanations.

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
    
    prompt = PromptTemplate.from_template(template)
    
    # Note: schema and dynamic_examples will be filled at runtime
    return None, llm, prompt

def clean_sql(response: str) -> str:
    """Clean SQL response by removing markdown code fences and extra whitespace"""
    return (
        response.strip()
        .replace("```sql", "")
        .replace("```", "")
        .strip()
    )

def format_sql_for_display(sql: str, dialect: str = "sqlite") -> str:
    """Format SQL query for better readability with proper indentation and line breaks"""
    try:
        # Parse and format SQL using sqlglot with pretty printing
        import sqlglot
        parsed = sqlglot.parse_one(sql, read=dialect)
        formatted = parsed.sql(dialect=dialect, pretty=True)
        return formatted
    except Exception:
        # Fallback to original SQL if formatting fails
        return sql

def generate_sql_with_retry(
    question: str,
    prompt,
    llm,
    engine,
    example_store,
    dialect: str,
    max_limit: int = 500,
    allowed_tables=None,
    max_retries: int = 2,
):
    """
    Generate SQL with RAG-based few-shot and self-correction loop.
    
    Args:
        question: User's question (Thai or English)
        prompt: PromptTemplate with {dynamic_examples}, {schema}, {question} placeholders
        llm: Language model instance
        engine: SQLAlchemy engine
        example_store: RAG example store for dynamic few-shot
        max_retries: Maximum retry attempts for self-correction
    
    Returns:
        tuple: (final_sql, dataframe, error_message, retry_count)
    """
    # Get dynamic examples from RAG store
    dynamic_examples = example_store.format_examples_for_prompt(question, top_k=3)
    
    # Get and Filter Schema (Smart Schema Injection)
    raw_schema = get_database_schema(engine)
    filtered_schema = filter_schema(raw_schema, question)
    schema_text = format_schema_for_prompt(filtered_schema)
    
    # Prepare allowed tables for safety check
    # If filtered schema is used, we might restrict to those tables, 
    # BUT for safety, we should probably allow all tables existing in DB 
    # (or strictly what was passed to prompt? Strict is safer but might hallucinate tables not in prompt)
    # Let's start with allowing all tables in DB to avoid false positives if heuristic missed something
    all_tables = list(raw_schema.keys())
    
    # Create chain with dynamic examples and schema
    chain = (
        prompt.partial(
            dynamic_examples=dynamic_examples,
            schema=schema_text,
            dialect=dialect,
            max_limit=max_limit,
        )
        | llm
        | StrOutputParser()
    )
    
    # First attempt
    response = chain.invoke({"question": question})
    sql = clean_sql(response)
    
    for attempt in range(max_retries + 1):
        try:
            # Safety gate: read-only, single statement, enforce LIMIT, optional table allowlist
            safe = validate_and_sanitize_sql(
                sql,
                dialect=dialect,
                max_limit=max_limit,
                allowed_tables=all_tables,
            )
            sql = safe.sql

            # Try to execute SQL
            df = pd.read_sql(sql, engine)
            return sql, df, None, attempt  # Success
            
        except Exception as e:
            error_msg = str(e)
            
            if attempt < max_retries:
                # Create correction prompt
                correction_prompt = f"""The following SQL query failed with an error OR violated safety constraints.

Target dialect: {dialect}
Safety requirements:
- Single statement only (WITH ... SELECT allowed)
- Read-only only: SELECT queries only
- Never use INSERT/UPDATE/DELETE/DROP/ALTER/CREATE/TRUNCATE/PRAGMA/ATTACH
- Always include LIMIT {max_limit} unless the user explicitly requests fewer

Error: {error_msg}

Failed SQL: {sql}

Please analyze the error and provide a corrected SQL query.
Return ONLY the corrected SQL query without any explanation or markdown.

Corrected SQL:"""
                
                # Ask LLM to fix the SQL
                corrected_response = llm.invoke(correction_prompt)
                
                # Handle AIMessage object
                if hasattr(corrected_response, 'content'):
                    sql = clean_sql(corrected_response.content)
                else:
                    sql = clean_sql(str(corrected_response))
            else:
                # Max retries exceeded
                return sql, None, error_msg, attempt
    
    return sql, None, "Max retries exceeded", max_retries

# --- 3. Logging & Feedback Functions (Metrics) ---
LOG_FILE_CSV = 'query_logs.csv'
LOG_FILE_JSONL = 'query_logs.jsonl'

def log_query(question, sql, status, error_msg="", duration=0, **kwargs):
    """
    Log query execution details to both CSV (legacy) and JSONL (rich data).
    kwargs allows passing extra fields like dialect, db_type, retry_count, etc.
    """
    log_id = str(uuid.uuid4())
    timestamp = pd.Timestamp.now().isoformat()
    
    # 1. Write to JSONL (Preferred for structured data)
    log_entry = {
        "log_id": log_id,
        "timestamp": timestamp,
        "question": question,
        "sql": sql,
        "status": status,
        "error_msg": error_msg,
        "duration_sec": duration,
        "feedback": "",
        **kwargs # store extra metadata
    }
    
    try:
        with open(LOG_FILE_JSONL, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"Error writing JSONL log: {e}")

    # 2. Write to CSV (Legacy support)
    file_exists = os.path.isfile(LOG_FILE_CSV)
    try:
        with open(LOG_FILE_CSV, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(['LogID', 'Timestamp', 'Question', 'SQL', 'Status', 'Error', 'Duration_Sec', 'Feedback'])
                
            writer.writerow([log_id, timestamp, question, sql, status, error_msg, f"{duration:.2f}", ""])
    except Exception as e:
        print(f"Error writing CSV log: {e}")
        
    return log_id

def update_feedback(log_id, feedback_value):
    """Update feedback in both CSV and JSONL."""
    
    # Update CSV
    if os.path.isfile(LOG_FILE_CSV):
        rows = []
        updated = False
        with open(LOG_FILE_CSV, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            try:
                header = next(reader)
                rows.append(header)
                for row in reader:
                    if row and row[0] == log_id:
                        while len(row) < 8: row.append("")
                        row[7] = feedback_value
                        updated = True
                    rows.append(row)
            except StopIteration:
                pass
        
        if updated:
            with open(LOG_FILE_CSV, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerows(rows)

    # Update JSONL
    if os.path.isfile(LOG_FILE_JSONL):
        logs = []
        with open(LOG_FILE_JSONL, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    if entry.get("log_id") == log_id:
                        entry["feedback"] = feedback_value
                    logs.append(entry)
                except:
                    continue
        
        with open(LOG_FILE_JSONL, 'w', encoding='utf-8') as f:
            for entry in logs:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

# --- 4. User Interface (UI) ---

# Sidebar: Database Connection Settings
with st.sidebar:
    st.header("🔌 Database Connection")
    
    # Database Type Selector
    db_type = st.selectbox(
        "Database Type",
        ["SQLite", "MySQL", "PostgreSQL"],
        index=0,
        help="เลือกประเภท Database ที่ต้องการเชื่อมต่อ"
    )
    
    # Configuration based on database type
    if db_type == "SQLite":
        db_config = {
            "database": st.text_input("Database File", value="local_database.db", help="ชื่อไฟล์ SQLite (เช่น data.db)")
        }
    else:  # MySQL or PostgreSQL
        with st.expander("⚙️ Connection Settings", expanded=True):
            col1, col2 = st.columns(2)
            with col1:
                db_config = {
                    "host": st.text_input("Host", value="localhost"),
                    "port": st.text_input("Port", value="3306" if db_type == "MySQL" else "5432")
                }
            with col2:
                db_config.update({
                    "user": st.text_input("Username", value="root" if db_type == "MySQL" else "postgres"),
                    "password": st.text_input("Password", type="password", value="")
                })
            
            db_config["database"] = st.text_input(
                "Database Name",
                value="classicmodels" if db_type == "MySQL" else "mydb",
                help="ชื่อ Database ที่ต้องการเชื่อมต่อ"
            )
    
    # Connect Button
    connect_clicked = st.button("🔗 Connect to Database", use_container_width=True)
    
    # Initialize session state for connection
    if "db_connected" not in st.session_state:
        st.session_state.db_connected = False
        st.session_state.engine = None
        st.session_state.connection_error = None
    
    # Handle connection
    if connect_clicked or st.session_state.db_connected:
        if connect_clicked:
            with st.spinner("กำลังเชื่อมต่อ Database..."):
                engine, error = get_db_engine(db_type, db_config)
                
                if engine:
                    st.session_state.engine = engine
                    st.session_state.db_connected = True
                    st.session_state.connection_error = None
                    st.success("✅ เชื่อมต่อสำเร็จ!")
                else:
                    st.session_state.db_connected = False
                    st.session_state.connection_error = error
                    st.error(f"❌ เชื่อมต่อไม่สำเร็จ: {error}")
        
        # Show connection status
        if st.session_state.db_connected:
            st.info(f"📊 Connected to: **{db_type}** - `{db_config.get('database', 'N/A')}`")
    else:
        st.warning("⚠️ กรุณาเชื่อมต่อ Database ก่อนใช้งาน")
        st.stop()
    
    st.markdown("---")
    st.header("📂 Database Schema")
    
    # Use Inspector to get dynamic schema
    engine = st.session_state.engine
    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    
    if not table_names:
        st.warning("ไม่พบตารางใน Database")
    
    for table in table_names:
        with st.expander(f"Table: {table}", expanded=True):
            columns = inspector.get_columns(table)
            for col in columns:
                col_name = col['name']
                col_type = col['type']
                st.markdown(f"- **{col_name}** (`{col_type}`)")
                
    st.markdown("---")
    st.write("💡 **ตัวอย่างคำถาม:**")
    st.code("ยอดขายรวมของเดือน December")
    st.code("ลูกค้าคนไหนมียอดซื้อเยอะที่สุด 5 อันดับแรก")

# Input Form (Prevents reset on submit)
with st.form(key="query_form"):
    user_question = st.text_input("💬 ถามข้อมูลของคุณ (ภาษาไทยได้เลย):", placeholder="เช่น ยอดขายรวมทั้งหมดของปีนี้แบ่งตามเดือน")
    run_clicked = st.form_submit_button("🚀 ค้นหาข้อมูล")

# Initialize Session State
if "last_sql" not in st.session_state:
    st.session_state.last_sql = None
if "last_df" not in st.session_state:
    st.session_state.last_df = None
if "last_error" not in st.session_state:
    st.session_state.last_error = None
if "last_log_id" not in st.session_state:
    st.session_state.last_log_id = None

# Query History & Favorites Session State
if "history_manager" not in st.session_state:
    st.session_state.history_manager = QueryHistoryManager()
if "rerun_query" not in st.session_state:
    st.session_state.rerun_query = None

if run_clicked:
    st.session_state.last_error = None
    st.session_state.last_log_id = None  # Reset Log ID
    st.session_state.last_retry_count = 0  # Track retry attempts
    
    if not user_question:
        st.warning("กรุณาป้อนคำถามก่อนกดค้นหา")
    else:
        # Initialize LLM resources on first query
        if "llm_initialized" not in st.session_state:
            with st.spinner("กำลังโหลด AI Model..."):
                try:
                    generate_query, llm, prompt_template = get_llm_chain()
                    example_store = get_example_store()
                    st.session_state.llm = llm
                    st.session_state.prompt_template = prompt_template
                    st.session_state.example_store = example_store
                    st.session_state.llm_initialized = True
                except Exception as e:
                    st.error(f"❌ Error loading AI Model: {e}")
                    st.stop()
        
        llm = st.session_state.llm
        prompt_template = st.session_state.prompt_template
        example_store = st.session_state.example_store
        engine = st.session_state.engine

        # Map UI db_type to sqlglot dialect names
        dialect_map = {"SQLite": "sqlite", "MySQL": "mysql", "PostgreSQL": "postgres"}
        dialect = dialect_map.get(db_type, "sqlite")
        # Hard cap for safety; can be made configurable later
        max_limit = 500
        
        with st.spinner("🤖 AI กำลังเขียน SQL และดึงข้อมูล..."):
            start_time = time.time()
            
            # Use RAG-based few-shot with self-correction loop (max 2 retries)
            final_sql, df_result, error_msg, retry_count = generate_sql_with_retry(
                question=user_question,
                prompt=prompt_template,
                llm=llm,
                engine=engine,
                example_store=example_store,
                dialect=dialect,
                max_limit=max_limit,
                allowed_tables=None,
                max_retries=2
            )
            
            duration = time.time() - start_time
            st.session_state.last_retry_count = retry_count
            
            if df_result is not None:
                # Success
                st.session_state.last_sql = final_sql
                st.session_state.last_df = df_result
                st.session_state.last_error = None
                st.session_state.last_dialect = dialect  # Store dialect for formatting
                
                # Log with retry info
                status = "Success" if retry_count == 0 else f"Success (Retry {retry_count})"
                log_id = log_query(
                    question=user_question, 
                    sql=final_sql, 
                    status=status, 
                    duration=duration,
                    dialect=dialect,
                    retry_count=retry_count
                )
                st.session_state.last_log_id = log_id
            else:
                # Error after all retries
                st.session_state.last_error = error_msg
                st.session_state.last_sql = final_sql  # Keep last attempted SQL for debugging
                st.session_state.last_df = None
                st.session_state.last_dialect = dialect  # Store dialect for formatting
                
                # Log Error
                log_id = log_query(
                    question=user_question, 
                    sql=final_sql, 
                    status="Error", 
                    error_msg=error_msg, 
                    duration=duration,
                    dialect=dialect,
                    retry_count=retry_count
                )
                st.session_state.last_log_id = log_id

# Display Logic
if st.session_state.last_error:
    st.error(f"❌ เกิดข้อผิดพลาด: {st.session_state.last_error}")
    st.warning("คำแนะนำ: ลองระบุชื่อคอลัมน์ให้ชัดเจนขึ้น หรือตรวจสอบคำสั่ง SQL")

df_result = st.session_state.last_df

if df_result is not None:
    # Show success message with retry info if applicable
    retry_count = st.session_state.get("last_retry_count", 0)
    if retry_count > 0:
        st.success(f"✅ สร้าง SQL Query สำเร็จ! (Self-corrected after {retry_count} retry)")
    else:
        st.success("✅ สร้าง SQL Query สำเร็จ!")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        # Format SQL for better readability
        raw_sql = st.session_state.last_sql or ""
        dialect = st.session_state.get("last_dialect", "sqlite")
        formatted_sql = format_sql_for_display(raw_sql, dialect=dialect)
        st.code(formatted_sql, language="sql")
    with col2:
        # Feedback Loop (Real Metrics)
        st.caption("ผลลัพธ์ถูกต้องไหม?")
        c1, c2 = st.columns(2)
        
        # ใช้ callback เพื่อ update feedback โดยไม่ต้อง rerun logic หลัก
        def on_feedback_click(rating):
            if st.session_state.last_log_id:
                update_feedback(st.session_state.last_log_id, rating)
                st.toast(f"บันทึก Feedback: {rating}")

        with c1:
            if st.button("👍"):
                on_feedback_click("Positive")
        with c2:
            if st.button("👎"):
                on_feedback_click("Negative")

    st.subheader("📊 ผลลัพธ์")
    if df_result.empty:
        st.warning("ไม่พบข้อมูลตามเงื่อนไขที่ค้นหา")
    else:
        # Auto-Viz Logic
        rec_type, rec_x, rec_y = recommend_chart(df_result)
        
        st.dataframe(df_result, use_container_width=True)

        st.subheader("📈 Visualization")
        
        if rec_type != "none" and rec_type != "table":
            # Controls
            with st.expander("⚙️ ตั้งค่ากราฟ", expanded=False):
                col1, col2, col3 = st.columns(3)
                with col1:
                    chart_type = st.selectbox(
                        "ประเภทกราฟ", 
                        ["Bar Chart", "Line Chart", "Area Chart", "Pie Chart", "Scatter Plot"],
                        index=0 if rec_type == "bar" else 1 if rec_type == "line" else 0
                    )
                with col2:
                    numeric_cols = df_result.select_dtypes(include=['number']).columns.tolist()
                    object_cols = df_result.columns.tolist()
                    x_axis = st.selectbox("แกน X", object_cols, index=object_cols.index(rec_x) if rec_x in object_cols else 0)
                with col3:
                    y_axis = st.selectbox("แกน Y", numeric_cols, index=numeric_cols.index(rec_y) if rec_y in numeric_cols else 0)
            
            # Plot
            try:
                if chart_type == "Bar Chart":
                    fig = px.bar(df_result, x=x_axis, y=y_axis, title=f"{y_axis} by {x_axis}", text_auto=True)
                elif chart_type == "Line Chart":
                    fig = px.line(df_result, x=x_axis, y=y_axis, markers=True, title=f"{y_axis} over {x_axis}")
                elif chart_type == "Area Chart":
                    fig = px.area(df_result, x=x_axis, y=y_axis, title=f"{y_axis} over {x_axis}")
                elif chart_type == "Pie Chart":
                    fig = px.pie(df_result, names=x_axis, values=y_axis, title=f"{y_axis} distribution")
                elif chart_type == "Scatter Plot":
                    fig = px.scatter(df_result, x=x_axis, y=y_axis, title=f"{y_axis} vs {x_axis}")
                
                st.plotly_chart(fig, use_container_width=True)
            except Exception as e:
                st.error(f"ไม่สามารถสร้างกราฟได้: {e}")
                
        elif len(df_result) > 0 and len(df_result.columns) >= 2:
             st.info("💡 ข้อมูลนี้แสดงเป็นตารางเหมาะสมที่สุด (หรือลองปรับแกนในตั้งค่า)")
