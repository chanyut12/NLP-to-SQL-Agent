# ==============================================================================
# Thai NLP-to-SQL Dockerfile
# ==============================================================================
# Builds the containerized microservice. Works for local `docker compose` AND for
# a Hugging Face Docker Space (see docs/DEPLOYMENT.md):
#   - runs as uid 1000 (HF Spaces runs containers as a non-root user)
#   - the embedding model is baked into the image so a cold boot needs no download
#     (HF free tier has an ephemeral filesystem — every restart would re-fetch it)
# Use a cloud LLM provider (OpenRouter / OpenAI / Google); Ollama needs a GPU.

FROM python:3.10-slim

# HF Spaces runs the container as uid 1000 — create a matching user up front.
RUN useradd -m -u 1000 user

# System deps: build-essential for wheels that need compiling, curl for the healthcheck.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Pin every model / HF cache inside the image so the baked download below is the
# one used at runtime (sentence-transformers 2.x reads SENTENCE_TRANSFORMERS_HOME,
# 3.x reads HF_HOME — set both).
ENV HF_HOME=/app/.cache/huggingface \
    SENTENCE_TRANSFORMERS_HOME=/app/.cache/sentence-transformers \
    PYTHONUNBUFFERED=1

# Install Python dependencies (own layer for caching).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code.
COPY . .

# Bake the embedding model into the image (≈470 MB). Runtime boot then does no
# network fetch for it — deterministic and offline-safe.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('intfloat/multilingual-e5-small')"

# ChromaDB writes these at runtime; hand the whole tree to the non-root user.
RUN mkdir -p rag_db schema_rag_db && chown -R user:user /app

USER user

# Expose 8000. On a HF Space, set `app_port: 8000` in the Space README frontmatter.
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
