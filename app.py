import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
from langchain_community.utilities import SQLDatabase
from langchain_ollama import ChatOllama
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
import time
import os
import csv

# --- 1. ตั้งค่า Page ---
st.set_page_config(page_title="Thai NLP to SQL Agent", layout="wide")
st.title("🤖 AI Data Analyst (Thai Supported)")
st.caption("Powered by Qwen2.5-Coder & Streamlit")

# --- 2. Caching Resources (Performance Optimization) ---
# ใช้ @st.cache_resource เพื่อโหลด Model และ DB connection แค่ครั้งเดียว
# ไม่ต้อง connect ใหม่ทุกครั้งที่หน้าเว็บ refresh

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
    
    # 3. Setup Prompt
    template = """
    You are a SQLite expert. Given an input question, create a syntactically correct SQLite query to run.
    Unless the user specifies a specific number of examples, always limit your query to at most 100 results using LIMIT.
    Order the results by a relevant column to return the most interesting examples in the database.
    
    Important:
    - The input question might be in **Thai language**. You must interpret the intent and map it to the English schema.
    - Schema Mapping Examples:
      - "ยอดขาย" -> SUM(total_price)
      - "จำนวนใบเสร็จ" -> COUNT(receipt_id)
      - "ลูกค้า" -> customer_name
      - "หมวดหมู่" -> product_category
      - "เดือน" -> month (values are in English: 'January', 'February', etc.)
      - "การชำระเงิน" -> payment_method
      - "ค่าเฉลี่ย" -> AVG(...)
    
    Only return the SQL query. Do not return any markdown, explanations, or code blocks.
    
    Schema: {schema}
    Question: {question}
    SQL Query:
    """
    
    prompt = PromptTemplate.from_template(template)
    prompt = prompt.partial(schema=schema)
    
    # 4. Create Chain
    chain = prompt | llm | StrOutputParser()
    return chain

# --- 3. Logging Function (Metrics) ---
def log_query(question, sql, status, error_msg=""):
    """บันทึกข้อมูลการใช้งานลงไฟล์ CSV เพื่อวัดผล"""
    file_exists = os.path.isfile('query_logs.csv')
    with open('query_logs.csv', 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(['Timestamp', 'Question', 'SQL', 'Status', 'Error'])
        
        writer.writerow([pd.Timestamp.now(), question, sql, status, error_msg])

# Initialize Resources
try:
    engine = get_db_engine()
    generate_query = get_llm_chain()
except Exception as e:
    st.error(f"❌ Connection Error: {e}")
    st.stop()

# --- 4. User Interface (UI) ---

# Sidebar: Schema
with st.sidebar:
    st.header("📂 Database Schema")
    st.info("Table: receipt")
    st.markdown("""
    - **date**: วันที่
    - **month**: เดือน (January, ...)
    - **product_category**: หมวดสินค้า
    - **total_price**: ยอดขาย
    - **payment_method**: วิธีชำระเงิน
    """)
    st.markdown("---")
    st.write("💡 **ตัวอย่างคำถาม:**")
    st.code("ยอดขายรวมของเดือน December")
    st.code("แสดงยอดขายแยกตามหมวดหมู่สินค้า")
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

run_clicked = st.button("🚀 ค้นหาข้อมูล")

if run_clicked:
    st.session_state.last_error = None
    if not user_question:
        st.warning("กรุณาป้อนคำถามก่อนกดค้นหา")
    else:
        with st.spinner("🤖 AI กำลังเขียน SQL และดึงข้อมูล..."):
            try:
                # 1. Generate SQL
                start_time = time.time()
                response = generate_query.invoke({"question": user_question})
                
                # Clean SQL
                cleaned_sql = (
                    response.strip()
                    .replace("```sql", "")
                    .replace("```", "")
                    .strip()
                )
                
                # 2. Execute SQL
                df_result = pd.read_sql(cleaned_sql, engine)
                
                # Success Logic
                st.session_state.last_sql = cleaned_sql
                st.session_state.last_df = df_result
                
                # Log Success (Metric: 1)
                log_query(user_question, cleaned_sql, "Success")

            except Exception as e:
                # Error Logic
                st.session_state.last_error = str(e)
                st.session_state.last_sql = None
                st.session_state.last_df = None
                
                # Log Error (Metric: 0)
                log_query(user_question, response if 'response' in locals() else "", "Error", str(e))

# Display Logic
if st.session_state.last_error:
    st.error(f"❌ เกิดข้อผิดพลาด: {st.session_state.last_error}")
    st.warning("คำแนะนำ: ลองระบุชื่อคอลัมน์ให้ชัดเจนขึ้น หรือตรวจสอบคำสั่ง SQL")

df_result = st.session_state.last_df

if df_result is not None:
    st.success("✅ สร้าง SQL Query สำเร็จ!")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        st.code(st.session_state.last_sql or "", language="sql")
    with col2:
        # Feedback Loop (Simple Metric)
        st.caption("ผลลัพธ์ถูกต้องไหม?")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("👍"):
                st.toast("ขอบคุณสำหรับ Feedback!")
        with c2:
            if st.button("👎"):
                st.toast("เราจะนำไปปรับปรุงครับ")

    st.subheader("📊 ผลลัพธ์")
    if df_result.empty:
        st.warning("ไม่พบข้อมูลตามเงื่อนไขที่ค้นหา")
    else:
        st.dataframe(df_result, use_container_width=True)

        st.subheader("📈 Visualization")

        numeric_cols = df_result.select_dtypes(include=["float64", "int64"]).columns
        object_cols = df_result.select_dtypes(include=["object"]).columns

        if len(numeric_cols) > 0 and len(object_cols) > 0:
            x_axis = st.selectbox("เลือกแกน X (หมวดหมู่/เวลา)", object_cols, index=0, key="x_axis")
            y_axis = st.selectbox("เลือกแกน Y (ค่าตัวเลข)", numeric_cols, index=0, key="y_axis")

            chart_type = st.radio(
                "เลือกประเภทกราฟ",
                ["Bar Chart", "Line Chart", "Area Chart"],
                horizontal=True,
                key="chart_type",
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
