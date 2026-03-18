# 🚀 Quick Start Guide

ถ้าคุณเพิ่ง clone project นี้มา คู่มือนี้จะช่วยให้คุณ run ได้ภายใน **5-10 นาที**

---

## 📋 ก่อนเริ่ม

เลือกวิธีติดตั้งตามความสะดวก:

| Method | Time | Difficulty | Requirements |
|--------|------|------------|--------------|
| **🐳 Docker** | 5 min | ⭐ Easy | Docker only |
| **☁️ Cloud LLM** | 5 min | ⭐ Easy | API key (free) |
| **💻 Local LLM** | 15 min | ⭐⭐⭐ Hard | GPU, 8GB+ RAM |

---

## 🐳 Option 1: Docker (แนะนำสำหรับคนที่ไม่อยากติดตั้งอะไรเยอะ)

### Prerequisites
- [Docker](https://www.docker.com/get-started) installed

### Steps

```bash
# 1. Clone project
git clone <your-repo-url>
cd nlp_sql_project

# 2. Create .env file
cp .env.example .env

# 3. Edit .env and add your API key
# For Google Gemini (Free):
MODEL_PROVIDER=google
GOOGLE_API_KEY=your-api-key-here

# 4. Run with Docker Compose
docker-compose up -d

# 5. Open browser
open http://localhost:8000
```

✅ **Done!** ใช้เวลาแค่ 5 นาที

---

## ☁️ Option 2: Cloud LLM (ไม่ต้องมี GPU)

### Prerequisites
- Python 3.10+
- API key from [Google AI Studio](https://makersuite.google.com/app/apikey) (ฟรี)

### Quick Setup (Automated)

**macOS/Linux:**
```bash
chmod +x setup.sh
./setup.sh
```

**Windows:**
```bash
setup.bat
```

### Manual Setup

```bash
# 1. Clone project
git clone <your-repo-url>
cd nlp_sql_project

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env and set:
#   MODEL_PROVIDER=google
#   GOOGLE_API_KEY=your-api-key-here

# 5. Create sample database
python scripts/setup_db.py

# 6. Start server
uvicorn api.main:app --reload

# 7. Open http://localhost:8000
```

✅ **Done!** ใช้เวลา 5-10 นาที

---

## 💻 Option 3: Local LLM with Ollama (สำหรับคนที่มี GPU และต้องการ privacy)

### Prerequisites
- Python 3.10+
- **8GB+ RAM** (16GB แนะนำ)
- [Ollama](https://ollama.com/) installed

### Steps

```bash
# 1-3. Same as Option 2
git clone <your-repo-url>
cd nlp_sql_project
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 4. Install and setup Ollama
# Download from: https://ollama.com/
ollama pull qwen2.5-coder:7b  # ~4.7GB, takes 5-15 min

# 5. Configure for Ollama
cp .env.example .env
# Edit .env and set:
#   MODEL_PROVIDER=ollama
#   OLLAMA_MODEL=qwen2.5-coder:7b

# 6. Create database and start
python scripts/setup_db.py
uvicorn api.main:app --reload
```

✅ **Done!** ใช้เวลา 15-20 นาที (รวม download model)

---

## 🧪 Testing

ทดสอบว่าระบบทำงานหรือไม่:

```bash
# 1. Check API health
curl http://localhost:8000/api/health

# 2. Test Thai query
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{
    "question": "มียอดขายทั้งหมดเท่าไหร่",
    "db_path": "local_database.db"
  }'
```

**Expected response:**
```json
{
  "sql": "SELECT SUM(total_price) FROM receipt",
  "results": [...],
  "chart_recommendation": {...}
}
```

---

## 🔧 Troubleshooting

### Error: "Ollama not responding"
```bash
# Check Ollama is running
ollama list

# Restart Ollama
ollama serve
```

### Error: "API key invalid"
- ตรวจสอบว่า API key ถูกต้อง
- Gemini: https://makersuite.google.com/app/apikey
- OpenAI: https://platform.openai.com/api-keys

### Error: "Module not found"
```bash
# Reinstall dependencies
pip install --upgrade -r requirements.txt
```

### Out of Memory (Ollama)
```bash
# Use smaller model
ollama pull qwen2.5-coder:3b  # ~2GB instead of 7GB

# Or switch to cloud
# Edit .env: MODEL_PROVIDER=google
```

---

## 📊 Cost Comparison

| Provider | Cost | Quota | Latency |
|----------|------|-------|---------|
| **Ollama (Local)** | $0 | Unlimited | 2-5s |
| **Google Gemini** | $0 | 1500/day | 1-2s |
| **OpenAI GPT-4o-mini** | ~$0.15/1M tokens | Unlimited | 1s |

---

## 🎯 Next Steps

1. ✅ ระบบทำงานแล้ว? ลองถามคำถามภาษาไทย
2. 📚 อ่าน [README.md](README.md) สำหรับ features ทั้งหมด
3. 🚀 อยาก deploy? ดู deployment guide ที่ README
4. 🐛 เจอ bug? เปิด [issue](https://github.com/your-repo/issues)

---

## 💡 Tips

**สำหรับ Development:**
- ใช้ `--reload` เพื่อ auto-restart เมื่อแก้ code
- ดู logs ที่ `query_logs.jsonl`
- Test API ด้วย [Bruno](https://www.usebruno.com/) หรือ Postman

**สำหรับ Production:**
- ใช้ cloud LLM (Google/OpenAI) แทน Ollama
- Setup HTTPS และ rate limiting
- Monitor ด้วย health check endpoint: `/api/health`

**ประหยัด Cost:**
- Google Gemini: 1500 requests/day ฟรี
- Together AI: $0.20/1M tokens (ถ้าต้องการ Qwen model)
- Modal: Pay-per-use serverless GPU

---

## 📞 Support

- 📖 Documentation: [README.md](README.md)
- 🐛 Bug reports: GitHub Issues
- 💬 Questions: GitHub Discussions

**Happy coding! 🎉**
