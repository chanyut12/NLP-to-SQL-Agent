import os

class Settings:
    # Model Configuration
    MODEL_PROVIDER = os.getenv("MODEL_PROVIDER", "ollama").lower()
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    
    # Google Gemini Settings
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
    GOOGLE_MODEL = os.getenv("GOOGLE_MODEL", "gemini-2.0-flash-exp")
    
    # Ollama Settings
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
    # OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "a-kore/Arctic-Text2SQL-R1-7B") # If you have a lot of RAM , processing will be faster
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    # OpenRouter Settings (OpenAI-compatible, free tier available)
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-4-maverick:free")

    # Zhipu AI (GLM) Settings (OpenAI-compatible)
    ZHIPU_API_KEY = os.getenv("ZHIPU_API_KEY", "")
    ZHIPU_MODEL = os.getenv("ZHIPU_MODEL", "glm-4-flash")

    # ===========================================================================
    # RAG Configuration (การดึงตัวอย่าง SQL ที่ใกล้เคียง)
    # ===========================================================================
    RAG_DISTANCE_THRESHOLD = 10.0  # ค่า threshold สำหรับกรอง example ที่ไกลเกินไป (ยิ่งต่ำยิ่งเข้มงวด, ลดจาก 15.0 เพื่อลด latency)
    RAG_TOP_K = 3                  # จำนวนตัวอย่าง SQL ที่จะดึงมาช่วย LLM (Few-shot examples)
    
    # ===========================================================================
    # Schema RAG Configuration (การดึง Schema ที่เกี่ยวข้อง)
    # ===========================================================================
    SCHEMA_TOP_K = 5               # จำนวนตารางที่จะดึงมาให้ LLM พิจารณา (สำหรับ Ollama local model)
    
    # ===========================================================================
    # Embedding Model (โมเดลสำหรับ Semantic Search)
    # ===========================================================================
    # โมเดลนี้รองรับภาษาไทย ใช้สำหรับ RAG และ Schema search
    EMBEDDING_MODEL = "intfloat/multilingual-e5-small"
    EMBEDDING_DEVICE = os.getenv("EMBEDDING_DEVICE", "").strip()
    HF_TOKEN = os.getenv("HF_TOKEN", "").strip()
    
    # ===========================================================================
    # SQL Execution Configuration (การรัน SQL)
    # ===========================================================================
    MAX_SQL_LIMIT = 500            # จำนวนแถวสูงสุดที่อนุญาตให้ query ได้ (ป้องกัน DoS)
    MAX_RETRIES = 2                # จำนวนครั้งที่จะ retry เมื่อ SQL ผิดพลาด (Self-correction)
    
    # ===========================================================================
    # App Configuration (การตั้งค่าแอปพลิเคชัน)
    # ===========================================================================
    ENABLE_INTELLIGENT_VIZ = False  # Set to False to speed up response (disable extra LLM call)
    LOG_FILE_JSONL = "query_logs.jsonl"
    LOG_FILE_CSV = "query_logs.csv"

    # ===========================================================================
    # CORS Configuration (Frontend Origins)
    # ===========================================================================
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")

settings = Settings()
