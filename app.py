import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, inspect
from langchain_community.utilities import SQLDatabase
from langchain_ollama import ChatOllama
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
import time
import os
import csv
import uuid

# --- 1. ตั้งค่า Page ---
st.set_page_config(page_title="Thai NLP to SQL Agent", layout="wide")
st.title("🤖 AI Data Analyst (Thai Supported)")
st.caption("Powered by Qwen2.5-Coder & Streamlit")

# --- 2. Caching Resources (Performance Optimization) ---
@st.cache_resource
def get_db_engine():
    """สร้าง Connection ไปยัง Database และ cache ไว้"""
    db_path = "sqlite:///local_database.db"
    engine = create_engine(db_path)
    # ทดสอบการเชื่อมต่อ
    with engine.connect() as conn:
        pass
    return engine

@st.cache_resource
def get_llm_chain():
    """โหลด Model และสร้าง Prompt Chain เก็บไว้"""
    
    # 1. Setup DB Schema info
    engine = get_db_engine()
    db = SQLDatabase(engine)
    schema = db.get_table_info()
    
    # 2. Setup LLM
    llm = ChatOllama(model="qwen2.5-coder:7b", temperature=0)
    
    # 3. Setup Prompt with Few-shot Examples & Chain-of-Thought
    template = """You are a SQLite expert specialized in Thai language understanding.
Given an input question (possibly in Thai), create a syntactically correct SQLite query.

### Instructions:
1. Interpret Thai keywords and map them to English column names
2. Determine the appropriate SQL operation (SELECT, COUNT, SUM, AVG, etc.)
3. Apply filters (WHERE) and groupings (GROUP BY) as needed
4. Limit results to 100 unless specified otherwise
5. Return ONLY the SQL query without markdown or explanations

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

### Few-shot Examples (Thai -> SQL):

Question: ยอดขายรวมของเดือนธันวาคม
SQL: SELECT SUM(total_price) AS total_sales FROM receipt WHERE month = 'December';

Question: ลูกค้าคนไหนซื้อเยอะที่สุด 5 อันดับแรก
SQL: SELECT customer_name, SUM(total_price) AS total_spent FROM receipt GROUP BY customer_name ORDER BY total_spent DESC LIMIT 5;

Question: จำนวนใบเสร็จแยกตามวิธีชำระเงิน
SQL: SELECT payment_method, COUNT(receipt_id) AS receipt_count FROM receipt GROUP BY payment_method ORDER BY receipt_count DESC;

Question: ยอดขายเฉลี่ยต่อใบเสร็จของแต่ละหมวดสินค้า
SQL: SELECT product_category, AVG(total_price) AS avg_sale FROM receipt GROUP BY product_category ORDER BY avg_sale DESC;

Question: แสดงยอดขายรวมแยกตามเดือน
SQL: SELECT month, SUM(total_price) AS monthly_sales FROM receipt GROUP BY month ORDER BY monthly_sales DESC;

Question: หมวดสินค้าไหนขายดีที่สุด
SQL: SELECT product_category, SUM(total_price) AS total_sales FROM receipt GROUP BY product_category ORDER BY total_sales DESC LIMIT 1;

Question: มีลูกค้ากี่คนที่จ่ายด้วยบัตรเครดิต
SQL: SELECT COUNT(DISTINCT customer_name) AS customer_count FROM receipt WHERE payment_method = 'Credit Card';

### Current Database Schema:
{schema}

### Your Task:
Question: {question}
SQL:"""
    
    prompt = PromptTemplate.from_template(template)
    prompt = prompt.partial(schema=schema)
    
    # 4. Create Chain
    chain = prompt | llm | StrOutputParser()
    return chain, llm

def clean_sql(response: str) -> str:
    """Clean SQL response by removing markdown code fences and extra whitespace"""
    return (
        response.strip()
        .replace("```sql", "")
        .replace("```", "")
        .strip()
    )

def generate_sql_with_retry(question: str, chain, llm, engine, max_retries: int = 2):
    """
    Generate SQL with self-correction loop.
    If SQL execution fails, send error back to LLM for correction.
    
    Returns:
        tuple: (final_sql, dataframe, error_message, retry_count)
    """
    # First attempt
    response = chain.invoke({"question": question})
    sql = clean_sql(response)
    
    for attempt in range(max_retries + 1):
        try:
            # Try to execute SQL
            df = pd.read_sql(sql, engine)
            return sql, df, None, attempt  # Success
            
        except Exception as e:
            error_msg = str(e)
            
            if attempt < max_retries:
                # Create correction prompt
                correction_prompt = f"""The following SQL query failed with an error.

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
LOG_FILE = 'query_logs.csv'

def log_query(question, sql, status, error_msg="", duration=0):
    """บันทึกข้อมูลการใช้งานลงไฟล์ CSV เพื่อวัดผล"""
    file_exists = os.path.isfile(LOG_FILE)
    
    # สร้าง ID สำหรับ Log นี้เพื่อให้ update feedback ทีหลังได้
    log_id = str(uuid.uuid4())
    
    with open(LOG_FILE, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        # Check header mismatch (migration)
        if not file_exists:
            writer.writerow(['LogID', 'Timestamp', 'Question', 'SQL', 'Status', 'Error', 'Duration_Sec', 'Feedback'])
            
        writer.writerow([log_id, pd.Timestamp.now(), question, sql, status, error_msg, f"{duration:.2f}", ""])
        
    return log_id

def update_feedback(log_id, feedback_value):
    """อัปเดตค่า Feedback ในไฟล์ CSV ตาม LogID"""
    if not os.path.isfile(LOG_FILE):
        return

    # อ่านข้อมูลทั้งหมดมาก่อน (สำหรับ Local App ไฟล์ไม่ใหญ่มากใช้วิธีนี้ง่ายสุด)
    rows = []
    updated = False
    with open(LOG_FILE, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader)
        rows.append(header)
        
        for row in reader:
            if row[0] == log_id:  # เจอ LogID ที่ตรงกัน (Column 0)
                # Column Index: 7 is Feedback
                # ถ้าไฟล์เก่า column ไม่ครบ ต้องระวัง index error แต่ assume ว่าไฟล์ใหม่ถูกสร้างแล้ว
                while len(row) < 8: row.append("")
                row[7] = feedback_value
                updated = True
            rows.append(row)
    
    if updated:
        with open(LOG_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerows(rows)

# Initialize Resources
try:
    engine = get_db_engine()
    generate_query, llm = get_llm_chain()
except Exception as e:
    st.error(f"❌ Connection Error: {e}")
    st.stop()

# --- 4. User Interface (UI) ---

# Sidebar: Dynamic Schema Display
with st.sidebar:
    st.header("📂 Database Schema")
    
    # Use Inspector to get dynamic schema
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

# Input Box
user_question = st.text_input("💬 ถามข้อมูลของคุณ (ภาษาไทยได้เลย):", placeholder="เช่น ยอดขายรวมทั้งหมดของปีนี้แบ่งตามเดือน")

# Initialize Session State
if "last_sql" not in st.session_state:
    st.session_state.last_sql = None
if "last_df" not in st.session_state:
    st.session_state.last_df = None
if "last_error" not in st.session_state:
    st.session_state.last_error = None
if "last_log_id" not in st.session_state:
    st.session_state.last_log_id = None

run_clicked = st.button("🚀 ค้นหาข้อมูล")

if run_clicked:
    st.session_state.last_error = None
    st.session_state.last_log_id = None  # Reset Log ID
    st.session_state.last_retry_count = 0  # Track retry attempts
    
    if not user_question:
        st.warning("กรุณาป้อนคำถามก่อนกดค้นหา")
    else:
        with st.spinner("🤖 AI กำลังเขียน SQL และดึงข้อมูล..."):
            start_time = time.time()
            
            # Use self-correction loop (max 2 retries)
            final_sql, df_result, error_msg, retry_count = generate_sql_with_retry(
                question=user_question,
                chain=generate_query,
                llm=llm,
                engine=engine,
                max_retries=2
            )
            
            duration = time.time() - start_time
            st.session_state.last_retry_count = retry_count
            
            if df_result is not None:
                # Success
                st.session_state.last_sql = final_sql
                st.session_state.last_df = df_result
                st.session_state.last_error = None
                
                # Log with retry info
                status = "Success" if retry_count == 0 else f"Success (Retry {retry_count})"
                log_id = log_query(user_question, final_sql, status, duration=duration)
                st.session_state.last_log_id = log_id
            else:
                # Error after all retries
                st.session_state.last_error = error_msg
                st.session_state.last_sql = final_sql  # Keep last attempted SQL for debugging
                st.session_state.last_df = None
                
                # Log Error
                log_id = log_query(user_question, final_sql, "Error", error_msg, duration)
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
        st.code(st.session_state.last_sql or "", language="sql")
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
        st.dataframe(df_result, use_container_width=True)

        st.subheader("📈 Visualization")

        numeric_cols = df_result.select_dtypes(include=["float64", "int64"]).columns
        object_cols = df_result.select_dtypes(include=["object"]).columns

        if len(numeric_cols) > 0 and len(object_cols) > 0:
            # ใช้ unique key เพื่อป้องกัน Duplicate Widget ID error
            x_axis = st.selectbox("เลือกแกน X (หมวดหมู่/เวลา)", object_cols, index=0, key="x_axis_v2")
            y_axis = st.selectbox("เลือกแกน Y (ค่าตัวเลข)", numeric_cols, index=0, key="y_axis_v2")

            chart_type = st.radio(
                "เลือกประเภทกราฟ",
                ["Bar Chart", "Line Chart", "Area Chart"],
                horizontal=True,
                key="chart_type_v2",
            )

            series = df_result.set_index(x_axis)[y_axis]
            if chart_type == "Bar Chart":
                st.bar_chart(series)
            elif chart_type == "Line Chart":
                st.line_chart(series)
            elif chart_type == "Area Chart":
                st.area_chart(series)
        elif len(numeric_cols) >= 2:
            st.scatter_chart(df_result)
        else:
            st.info("ข้อมูลไม่เพียงพอสำหรับการสร้างกราฟ (ต้องการอย่างน้อย 1 คอลัมน์ตัวเลข และ 1 คอลัมน์หมวดหมู่)")
