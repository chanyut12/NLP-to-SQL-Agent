import os


VALID_APP_MODES = ("auto", "demo", "service")


def normalize_app_mode(value) -> str:
    """Normalize APP_MODE; an unset/blank value means the legacy auto mode."""
    return (value or "auto").strip().lower()


def validate_app_mode(mode, api_key) -> str:
    """Validate the deployment mode and its auth requirement.

    auto    — preserve the original behaviour: UI on iff API_KEY is empty.
    demo    — bundled UI on and auth off; API_KEY must be empty so the page
              cannot accidentally expose a protected datasource.
    service — Consumer-only: UI off and API_KEY required.
    """
    mode = normalize_app_mode(mode)
    if mode not in VALID_APP_MODES:
        raise ValueError(
            f"Invalid APP_MODE={mode!r}; expected one of {', '.join(VALID_APP_MODES)}."
        )
    if mode == "demo" and api_key:
        raise ValueError(
            "APP_MODE=demo serves an unauthenticated UI; unset API_KEY or use APP_MODE=service."
        )
    if mode == "service" and not api_key:
        raise ValueError(
            "APP_MODE=service requires API_KEY; use APP_MODE=demo for an unauthenticated local demo."
        )
    return mode


class Settings:
    # ===========================================================================
    # Deployment mode
    # ===========================================================================
    # auto (default) | demo | service. See validate_app_mode().
    APP_MODE = normalize_app_mode(os.getenv("APP_MODE", "auto"))
    # ===========================================================================
    # Datasource & Service (microservice deployment)
    # ===========================================================================
    # Single read-only PostgreSQL connection, fixed at deploy time.
    # e.g. postgresql+psycopg2://user:pass@host:5432/sts
    DATABASE_URL = os.getenv("DATABASE_URL", "")
    # Shared secret required in the X-API-Key header. Empty disables auth in
    # auto/demo mode; APP_MODE=service rejects an empty key at startup.
    API_KEY = os.getenv("API_KEY", "")
    # Domain profile: profiles/<name>/{hints.md,examples.json}
    DOMAIN_PROFILE = os.getenv("DOMAIN_PROFILE", "sts")

    # Model Configuration
    MODEL_PROVIDER = os.getenv("MODEL_PROVIDER", "openai").lower()
    LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "6"))  # backoff on 429 / transient errors
    LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "120"))  # abort a hung request (some OpenRouter providers stall)
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
    # General PaaS endpoint. The Coding Plan endpoint (api.z.ai/api/coding/paas/v4) is for
    # coding-plan keys only; set ZHIPU_BASE_URL to it if you switch back to a Coding Plan.
    ZHIPU_BASE_URL = os.getenv("ZHIPU_BASE_URL", "https://api.z.ai/api/paas/v4")
    # ===========================================================================
    # RAG Configuration (การดึงตัวอย่าง SQL ที่ใกล้เคียง)
    # ===========================================================================
    RAG_DISTANCE_THRESHOLD = 10.0  # ค่า threshold สำหรับกรอง example ที่ไกลเกินไป (ยิ่งต่ำยิ่งเข้มงวด, ลดจาก 15.0 เพื่อลด latency)
    RAG_TOP_K = int(os.getenv("RAG_TOP_K", "3"))  # จำนวนตัวอย่าง SQL few-shot (0 = ปิด RAG)
    
    # ===========================================================================
    # Schema RAG Configuration (การดึง Schema ที่เกี่ยวข้อง)
    # ===========================================================================
    # Schema handling for the generation prompt.
    #   pruned = semantic top-K relevant tables + FK neighbours (default)
    #   full   = every table that survives the denylist
    SCHEMA_STRATEGY = os.getenv("SCHEMA_STRATEGY", "pruned").lower()
    SCHEMA_TOP_K = int(os.getenv("SCHEMA_TOP_K", "25"))   # relevant tables in pruned mode
    SCHEMA_CACHE_TTL_SECONDS = int(os.getenv("SCHEMA_CACHE_TTL_SECONDS", "3600"))
    
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
    MAX_RETRIES = int(os.getenv("MAX_RETRIES", "2"))  # self-correction retries (0 = ปิด)
    
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

    def demo_ui_enabled(self) -> bool:
        """Whether the bundled web UI should be mounted at /."""
        mode = normalize_app_mode(self.APP_MODE)
        if mode == "demo":
            return True
        if mode == "service":
            return False
        return not self.API_KEY

    def api_key_enforced(self) -> bool:
        """Whether /api requests must carry X-API-Key."""
        return normalize_app_mode(self.APP_MODE) != "demo" and bool(self.API_KEY)


settings = Settings()
