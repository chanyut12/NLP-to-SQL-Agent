import os

class Settings:
    # Model Configuration
    MODEL_PROVIDER = os.getenv("MODEL_PROVIDER", "ollama").lower()
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
    # OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "a-kore/Arctic-Text2SQL-R1-7B") # If you have a lot of RAM , processing will be faster
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    # RAG Configuration
    RAG_DISTANCE_THRESHOLD = 15.0

    # App Configuration
    LOG_FILE_JSONL = "query_logs.jsonl"
    LOG_FILE_CSV = "query_logs.csv"

settings = Settings()
