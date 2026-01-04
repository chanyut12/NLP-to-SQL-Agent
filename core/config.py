import os

class Settings:
    # Model Configuration
    MODEL_PROVIDER = os.getenv("MODEL_PROVIDER", "ollama").lower()
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    # App Configuration
    LOG_FILE_JSONL = "query_logs.jsonl"
    LOG_FILE_CSV = "query_logs.csv"

settings = Settings()
