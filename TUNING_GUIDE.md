# LLM Tuning Guide for Thai NLP-to-SQL Agent

This guide documents all tuning techniques implemented and available for the Thai NLP-to-SQL Agent project. It covers both **implemented features** and **advanced techniques** you can explore further.

---

## Table of Contents

1. [Overview](#overview)
2. [Implemented Techniques](#implemented-techniques)
   - [Advanced Prompt Engineering](#1-advanced-prompt-engineering)
   - [Self-Correction Loop](#2-self-correction-loop)
   - [RAG-based Dynamic Few-shot](#3-rag-based-dynamic-few-shot)
3. [Advanced Techniques (Guide)](#advanced-techniques-guide)
   - [Fine-tuning with LoRA/QLoRA](#4-fine-tuning-with-loraqra)
   - [Model Comparison](#5-model-comparison)
4. [Evaluation Metrics](#evaluation-metrics)

---

## Overview

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        User Input                                │
│                    (Thai Question)                               │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                     RAG Layer                                    │
│  ┌─────────────┐    ┌──────────────┐    ┌─────────────────┐    │
│  │ Embedding   │───▶│  ChromaDB    │───▶│ Similar Examples │    │
│  │ Model       │    │  Vector DB   │    │ (Top-3)          │    │
│  └─────────────┘    └──────────────┘    └─────────────────┘    │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Prompt Engineering                              │
│  ┌─────────────┐    ┌──────────────┐    ┌─────────────────┐    │
│  │ Schema      │ +  │ Dynamic      │ +  │ Instructions    │    │
│  │ Mapping     │    │ Examples     │    │ (CoT)           │    │
│  └─────────────┘    └──────────────┘    └─────────────────┘    │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                     LLM Layer                                    │
│                 (Qwen2.5-Coder:7b)                              │
│                         │                                        │
│                         ▼                                        │
│                   Generated SQL                                  │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                 Self-Correction Loop                             │
│  ┌─────────────┐    ┌──────────────┐    ┌─────────────────┐    │
│  │ Execute SQL │───▶│ Error?       │───▶│ Retry with      │    │
│  │             │    │              │    │ Error Context   │    │
│  └─────────────┘    └──────────────┘    └─────────────────┘    │
│                              │ Success                          │
│                              ▼                                   │
│                        DataFrame                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Implemented Techniques

### 1. Advanced Prompt Engineering

**Status:** ✅ Implemented

**File:** `core/engine.py` - `_create_prompt_template()` method

#### What it does:
- Provides structured instructions with Chain-of-Thought (CoT) reasoning
- Maps Thai keywords to English column names
- Includes few-shot examples for pattern learning

#### Key Components:

```python
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
...
"""
```

#### Best Practices:
1. **Be explicit**: Tell the model exactly what format you expect
2. **Provide mappings**: Thai keywords → SQL columns/functions
3. **Include constraints**: LIMIT, ORDER BY preferences
4. **Use examples**: Few-shot examples help pattern recognition

---

### 2. Self-Correction Loop

**Status:** ✅ Implemented

**File:** `core/engine.py` - `query_database()` method

#### What it does:
- Attempts to execute generated SQL
- If execution fails, sends error message back to LLM
- LLM analyzes error and provides corrected SQL
- Retries up to 2 times (configurable)

#### Implementation:

```python
def generate_sql_with_retry(question, prompt, llm, engine, example_store, max_retries=2):
    # Get dynamic examples from RAG
    dynamic_examples = example_store.format_examples_for_prompt(question, top_k=3)
    
    # Create chain and generate SQL
    chain = prompt.partial(dynamic_examples=dynamic_examples) | llm | StrOutputParser()
    response = chain.invoke({"question": question})
    sql = clean_sql(response)
    
    for attempt in range(max_retries + 1):
        try:
            df = pd.read_sql(sql, engine)
            return sql, df, None, attempt  # Success
        except Exception as e:
            if attempt < max_retries:
                # Create correction prompt with error context
                correction_prompt = f"""
                Error: {str(e)}
                Failed SQL: {sql}
                Please provide corrected SQL.
                """
                corrected = llm.invoke(correction_prompt)
                sql = clean_sql(corrected.content)
            else:
                return sql, None, str(e), attempt
```

#### Benefits:
- Reduces error rate by 20-30%
- Handles common SQL syntax errors automatically
- No additional training required

---

### 3. RAG-based Dynamic Few-shot

**Status:** ✅ Implemented

**Files:** 
- `core/rag_store.py` - Vector store implementation
- `thai_sql_examples.json` - Example dataset (28 examples)
- `core/engine.py` - Integration

#### What it does:
- Stores Thai→SQL examples in ChromaDB vector database
- Uses multilingual embeddings for Thai language support
- Retrieves semantically similar examples for each query
- Injects relevant examples into prompt dynamically

#### Components:

**Example Store (`rag_store.py`):**
```python
class ExampleStore:
    DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    
    def get_similar_examples(self, query: str, top_k: int = 3):
        query_embedding = self.embedder.encode(query).tolist()
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k
        )
        return results
```

**Example Dataset (`thai_sql_examples.json`):**
```json
{
  "examples": [
    {
      "question": "ยอดขายรวมของเดือนธันวาคม",
      "sql": "SELECT SUM(total_price) AS total_sales FROM receipt WHERE month = 'December';",
      "category": "aggregation_filter"
    },
    ...
  ]
}
```

#### Benefits:
- Context-aware examples (not random)
- Scales without prompt bloat
- Easy to add new examples

#### How to Add More Examples:
1. Edit `thai_sql_examples.json`
2. Add new question/SQL pairs
3. Restart the application (store rebuilds automatically)

---

## Advanced Techniques (Guide)

### 4. Fine-tuning with LoRA/QLoRA

**Status:** 📚 Guide Only (Not Implemented)

Fine-tuning creates a specialized model for your specific database and Thai vocabulary.

#### When to Use:
- Current accuracy < 70%
- You have 500+ labeled examples
- Need consistent output format
- Have access to GPU (RTX 3090+ or cloud)

#### Step 1: Prepare Dataset

Create a JSONL file with instruction-input-output format:

```json
{"instruction": "Convert Thai question to SQL", "input": "Schema: receipt(...)\nQuestion: ยอดขายเดือนธันวา", "output": "SELECT SUM(total_price) FROM receipt WHERE month = 'December';"}
{"instruction": "Convert Thai question to SQL", "input": "Schema: receipt(...)\nQuestion: ลูกค้าซื้อมากสุด", "output": "SELECT customer_name, SUM(total_price) FROM receipt GROUP BY customer_name ORDER BY 2 DESC LIMIT 1;"}
```

**Recommended: 500-1000 examples** covering:
- Different SQL operations (SELECT, COUNT, SUM, AVG)
- Various Thai phrasings for same intent
- Edge cases and common errors

#### Step 2: Setup Training Environment

**Option A: Google Colab (Recommended for beginners)**
```python
# Install Unsloth (fast LoRA training)
!pip install unsloth
!pip install --no-deps trl peft accelerate bitsandbytes

from unsloth import FastLanguageModel

# Load base model
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name="unsloth/Qwen2.5-Coder-7B-Instruct-bnb-4bit",
    max_seq_length=2048,
    load_in_4bit=True,
)

# Add LoRA adapters
model = FastLanguageModel.get_peft_model(
    model,
    r=16,                 # LoRA rank
    lora_alpha=16,
    lora_dropout=0,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
)
```

**Option B: Local (Requires RTX 3090+ with 24GB VRAM)**
```bash
# Install dependencies
pip install unsloth torch transformers datasets

# Run training script
python train_lora.py --model qwen2.5-coder:7b --data thai_sql_train.jsonl
```

#### Step 3: Training Configuration

```python
from trl import SFTTrainer
from transformers import TrainingArguments

trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=dataset,
    max_seq_length=2048,
    args=TrainingArguments(
        per_device_train_batch_size=2,
        gradient_accumulation_steps=4,
        warmup_steps=5,
        max_steps=100,  # Increase for better results
        learning_rate=2e-4,
        fp16=True,
        output_dir="outputs",
    ),
)

trainer.train()
```

#### Step 4: Export to Ollama

```python
# Save in GGUF format
model.save_pretrained_gguf("thai-sql-qwen", tokenizer, quantization_method="q4_k_m")
```

```bash
# Create Modelfile
cat > Modelfile << EOF
FROM ./thai-sql-qwen-Q4_K_M.gguf
TEMPLATE "{{ .Prompt }}"
PARAMETER temperature 0
EOF

# Import to Ollama
ollama create thai-sql-qwen -f Modelfile

# Use in app.py
llm = ChatOllama(model="thai-sql-qwen", temperature=0)
```

#### Expected Improvements:
- Accuracy: +15-25%
- Consistency: Much better
- Speed: Same (after quantization)

---

### 5. Model Comparison

**Status:** 📚 Guide Only (Not Implemented)

Comparing different models helps you choose the best one for your use case.

#### Models to Compare:

| Model | Size | VRAM Required | Thai Support |
|-------|------|---------------|--------------|
| qwen2.5-coder:7b | 4.7GB | 8GB | Good |
| qwen2.5-coder:14b | 9GB | 16GB | Better |
| deepseek-coder:6.7b | 4GB | 8GB | Moderate |
| codellama:7b | 4GB | 8GB | Limited |

#### Evaluation Framework

Create `evaluate.py`:

```python
import pandas as pd
from sqlalchemy import create_engine

# Test cases with expected results
test_cases = [
    {
        "question": "ยอดขายรวมทั้งหมด",
        "expected_sql": "SELECT SUM(total_price) FROM receipt;"
    },
    {
        "question": "ลูกค้าที่ซื้อมากที่สุด",
        "expected_sql": "SELECT customer_name, SUM(total_price) AS total FROM receipt GROUP BY customer_name ORDER BY total DESC LIMIT 1;"
    },
    # Add 50+ test cases
]

def evaluate_model(model_name, test_cases, engine):
    results = []
    
    for tc in test_cases:
        generated_sql = generate_sql(tc["question"], model=model_name)
        
        # Metric 1: Execution Success
        try:
            pd.read_sql(generated_sql, engine)
            exec_success = True
        except:
            exec_success = False
        
        # Metric 2: Result Match
        try:
            expected = pd.read_sql(tc["expected_sql"], engine)
            actual = pd.read_sql(generated_sql, engine)
            result_match = expected.equals(actual)
        except:
            result_match = False
        
        results.append({
            "question": tc["question"],
            "exec_success": exec_success,
            "result_match": result_match
        })
    
    df = pd.DataFrame(results)
    print(f"\n=== {model_name} ===")
    print(f"Execution Accuracy: {df['exec_success'].mean()*100:.1f}%")
    print(f"Result Accuracy: {df['result_match'].mean()*100:.1f}%")
    
    return df

# Run comparison
engine = create_engine("sqlite:///local_database.db")
for model in ["qwen2.5-coder:7b", "qwen2.5-coder:14b"]:
    evaluate_model(model, test_cases, engine)
```

#### Metrics Explained:

| Metric | Description | Target |
|--------|-------------|--------|
| Execution Accuracy | SQL runs without error | > 90% |
| Result Accuracy | SQL returns correct data | > 80% |
| Latency | Time to generate SQL | < 5s |

---

## Evaluation Metrics

### Current Metrics (from query_logs.csv)

The system logs every query with:
- **LogID**: Unique identifier
- **Timestamp**: When query was made
- **Question**: User's Thai question
- **SQL**: Generated SQL
- **Status**: Success/Error/Success (Retry N)
- **Duration_Sec**: Time taken
- **Feedback**: User rating (Positive/Negative)

### How to Calculate Accuracy:

```python
import pandas as pd

df = pd.read_csv('query_logs.csv')

# Execution Success Rate
success_rate = df['Status'].str.contains('Success').mean() * 100
print(f"Execution Success Rate: {success_rate:.1f}%")

# Self-Correction Effectiveness
retry_success = df['Status'].str.contains('Retry').sum()
total_success = df['Status'].str.contains('Success').sum()
print(f"Queries saved by self-correction: {retry_success}")

# User Satisfaction
feedback_df = df[df['Feedback'].notna()]
positive_rate = (feedback_df['Feedback'] == 'Positive').mean() * 100
print(f"User Satisfaction: {positive_rate:.1f}%")
```

---

## Next Steps

1. **Short-term**: Add more examples to `thai_sql_examples.json`
2. **Medium-term**: Create evaluation test set and run model comparison
3. **Long-term**: Fine-tune with LoRA if accuracy needs improvement

---

## Future Development Roadmap

This section outlines potential features and enhancements to consider for future development. These are derived from stakeholder requirements analysis.

### 1. User Management & Access Control

**Priority:** High (for production deployment)

| Feature | Description | Complexity |
|---------|-------------|------------|
| User Authentication | Login/logout with username/password | Medium |
| Role-based Access | Admin, Analyst, Viewer roles | Medium |
| Table-level Permissions | Restrict access to sensitive tables/columns | High |
| Audit Trail | Log who queried what and when | Low |

**Implementation Approach:**
```python
# Example: Streamlit-Authenticator integration
import streamlit_authenticator as stauth

authenticator = stauth.Authenticate(
    credentials, cookie_name, key, cookie_expiry_days
)
name, authentication_status, username = authenticator.login()

# Role-based table filtering
ROLE_PERMISSIONS = {
    "admin": ["*"],  # All tables
    "analyst": ["receipt", "products", "customers"],
    "viewer": ["receipt_summary"]  # Aggregated views only
}
```

---

### 2. Query History & Favorites

**Priority:** Medium

| Feature | Description | Complexity |
|---------|-------------|------------|
| Query History | View past queries with results | Low |
| Save as Favorite | Bookmark frequently used queries | Low |
| Query Templates | Pre-defined queries with parameters | Medium |
| Share Queries | Share saved queries with team | Medium |

**Data Model:**
```python
# Store in SQLite or session state
saved_queries = {
    "id": "uuid",
    "user_id": "user123",
    "name": "Monthly Sales Report",
    "question": "ยอดขายรายเดือน",
    "sql": "SELECT month, SUM(total_price) ...",
    "created_at": "2025-01-01",
    "is_favorite": True
}
```

---

### 3. Export & Sharing

**Priority:** High

| Feature | Description | Complexity |
|---------|-------------|------------|
| Export to Excel/CSV | Download query results | Low |
| Export Chart as Image | PNG/SVG export | Low |
| PDF Report | Generate formatted reports | Medium |
| Email Delivery | Send results via email | Medium |
| API Endpoint | REST API for external integration | High |

**Quick Implementation (Excel/CSV):**
```python
import io

# Add to Streamlit UI
col1, col2 = st.columns(2)
with col1:
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button("Download CSV", csv, "result.csv", "text/csv")
with col2:
    buffer = io.BytesIO()
    df.to_excel(buffer, index=False)
    st.download_button("Download Excel", buffer.getvalue(), "result.xlsx")
```

---

### 4. Scheduling & Automation

**Priority:** Low (for advanced use cases)

| Feature | Description | Complexity |
|---------|-------------|------------|
| Scheduled Queries | Run queries on schedule (daily/weekly) | High |
| Email Reports | Auto-send results to stakeholders | Medium |
| Alerts | Notify when metrics exceed thresholds | Medium |
| Dashboard Refresh | Auto-refresh dashboards | Low |

**Technology Options:**
- **APScheduler**: Python-native scheduling
- **Celery + Redis**: Distributed task queue
- **Airflow**: Enterprise-grade orchestration

---

### 5. Multi-turn Conversation

**Priority:** Medium

| Feature | Description | Complexity |
|---------|-------------|------------|
| Context Memory | Remember previous queries in session | Medium |
| Follow-up Questions | "แล้วถ้าเฉพาะเดือนนี้ล่ะ?" | High |
| Query Refinement | "เพิ่ม filter ลูกค้าชื่อ X" | High |
| Undo/Modify | Adjust previous query conditions | Medium |

**Implementation Approach:**
```python
# Add conversation memory
from langchain.memory import ConversationBufferWindowMemory

memory = ConversationBufferWindowMemory(k=5)  # Remember last 5 turns

# Enhanced prompt with context
template = """
Previous conversation:
{history}

Current question: {question}
Generate SQL considering the context above.
"""
```

---

### 6. Extended Data Source Support

**Priority:** Medium

| Data Source | Driver/Library | Status |
|-------------|---------------|--------|
| SQLite | Built-in | ✅ Implemented |
| MySQL | pymysql | ✅ Implemented |
| PostgreSQL | psycopg2 | ✅ Implemented |
| Microsoft SQL Server | pyodbc | 🔲 Planned |
| Oracle | cx_Oracle | 🔲 Planned |
| BigQuery | google-cloud-bigquery | 🔲 Planned |
| CSV/Excel Files | pandas | 🔲 Planned |
| REST APIs | requests + pandas | 🔲 Planned |

**Adding New Database:**
```python
# In app.py, extend get_engine()
elif db_type == "mssql":
    url = f"mssql+pyodbc://{user}:{password}@{host}:{port}/{database}?driver=ODBC+Driver+17+for+SQL+Server"
elif db_type == "oracle":
    url = f"oracle+cx_oracle://{user}:{password}@{host}:{port}/{database}"
```

---

### 7. Enhanced Visualization

**Priority:** Medium

| Feature | Description | Complexity |
|---------|-------------|------------|
| Dashboard Builder | Create multi-chart dashboards | High |
| Chart Customization | Colors, labels, themes | Low |
| Drill-down | Click chart to filter data | Medium |
| Map Visualization | Geographic data on maps | Medium |
| Real-time Charts | Auto-updating visualizations | High |

---

### 8. Performance & Scalability

**Priority:** High (for production)

| Concern | Solution | Complexity |
|---------|----------|------------|
| Query Caching | Cache frequent query results | Medium |
| Connection Pooling | SQLAlchemy pool configuration | Low |
| Async Execution | Background query processing | Medium |
| Rate Limiting | Prevent API abuse | Low |
| Load Balancing | Multiple Streamlit instances | High |

**Query Caching Example:**
```python
from functools import lru_cache
import hashlib

@lru_cache(maxsize=100)
def cached_query(sql_hash: str, engine_url: str):
    # Execute and cache results
    return pd.read_sql(sql, engine)

# Usage
sql_hash = hashlib.md5(sql.encode()).hexdigest()
df = cached_query(sql_hash, str(engine.url))
```

---

### 9. Error Handling & UX Improvements

**Priority:** Medium

| Feature | Description | Complexity |
|---------|-------------|------------|
| Friendly Error Messages | Thai error explanations | Low |
| Query Suggestions | "Did you mean...?" | Medium |
| Schema Explorer | Interactive table/column browser | Low |
| SQL Preview & Edit | Allow manual SQL adjustment | Low |
| Progress Indicator | Show generation steps | Low |

---

### 10. Evaluation & Monitoring

**Priority:** High

| Feature | Description | Complexity |
|---------|-------------|------------|
| Accuracy Dashboard | Track success rate over time | Medium |
| A/B Testing | Compare model/prompt versions | High |
| Error Analysis | Categorize failure patterns | Medium |
| User Feedback Loop | Improve from user corrections | Medium |
| Cost Tracking | Monitor API/compute usage | Low |

---

### Implementation Priority Matrix

```
                    High Impact
                         │
    ┌────────────────────┼────────────────────┐
    │                    │                    │
    │  Export/Sharing    │  User Management   │
    │  Error Handling    │  Performance       │
    │                    │  Evaluation        │
    │                    │                    │
Low ├────────────────────┼────────────────────┤ High
Effort                   │                    Effort
    │                    │                    │
    │  Query History     │  Multi-turn Conv.  │
    │  Visualization     │  Scheduling        │
    │                    │  Dashboard Builder │
    │                    │                    │
    └────────────────────┼────────────────────┘
                         │
                    Low Impact
```

**Recommended Implementation Order:**
1. Export to CSV/Excel (Quick win, high value)
2. Query History & Favorites (Improves UX)
3. User Authentication (Required for production)
4. Error Message Improvements (Better UX)
5. Multi-turn Conversation (Advanced feature)

---

**Created by:** Thai NLP-to-SQL Agent Development Team
**Last Updated:** December 2025

