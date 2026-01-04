# 🤖 Model Provider Setup Guide

แอปนี้รองรับ **2 Model Providers** ที่สลับกันได้:
- **Ollama** (Local) - สำหรับ development ในเครื่อง (ฟรี)
- **OpenAI API** (Cloud) - สำหรับ production deployment (เสียค่าใช้จ่าย)

---

## 🏠 สำหรับ Local Development (Ollama)

### 1. ติดตั้ง Ollama
```bash
# macOS/Linux
curl -fsSL https://ollama.ai/install.sh | sh

# หรือดาวน์โหลดจาก https://ollama.ai
```

### 2. ดาวน์โหลด Model
```bash
ollama pull qwen2.5-coder:7b
```

### 3. ตั้งค่าใน `.env` (Optional)

สร้างไฟล์ `.env` ในโปรเจกต์:

```bash
MODEL_PROVIDER=ollama
OLLAMA_MODEL=qwen2.5-coder:7b
OLLAMA_BASE_URL=http://localhost:11434
```

**หมายเหตุ:** ถ้าไม่ตั้งค่า ระบบจะใช้ค่า default ใน `core/config.py`

### 4. รัน Ollama Server
```bash
ollama serve
```

### 5. รัน FastAPI Backend
```bash
uvicorn api.main:app --reload
```

### 6. เปิด Frontend
เปิดไฟล์ `web/index.html` ในเบราว์เซอร์ (หรือใช้ Live Server)

**ข้อดี:**
- ✅ ฟรี ไม่มีค่าใช้จ่าย
- ✅ ไม่ต้องใช้อินเทอร์เน็ต
- ✅ ไม่ต้องกังวลเรื่องความเป็นส่วนตัว

**ข้อเสีย:**
- ⚠️ ต้องมี RAM อย่างน้อย 8GB (แนะนำ 16GB)
- ⚠️ ความแม่นยำต่ำกว่า GPT-4 (แต่พอใช้ได้สำหรับงานทั่วไป)

---

## ☁️ สำหรับ Cloud Deployment (OpenAI)

### 1. สมัคร OpenAI API Key
1. ไปที่ https://platform.openai.com/api-keys
2. สร้าง API Key ใหม่
3. เติมเงินเข้าบัญชี (ขั้นต่ำ $5)

### 2. ตั้งค่าใน Environment Variables

#### Local Development:
สร้างไฟล์ `.env`:
```bash
MODEL_PROVIDER=openai
OPENAI_API_KEY=sk-proj-your-actual-key-here
OPENAI_MODEL=gpt-4o-mini  # หรือ "gpt-4" สำหรับความแม่นยำสูงสุด
```

#### Production Deployment (e.g., Docker, Cloud):
Set environment variables:
```bash
export MODEL_PROVIDER=openai
export OPENAI_API_KEY=sk-proj-...
export OPENAI_MODEL=gpt-4o-mini
```

### 3. รัน Backend
```bash
uvicorn api.main:app --reload
```

**ข้อดี:**
- ✅ ประสิทธิภาพสูงและเสถียร
- ✅ ไม่ต้องมีเครื่องแรง
- ✅ ความแม่นยำสูงสุด (โดยเฉพาะ GPT-4)

**ข้อเสีย:**
- 💰 มีค่าใช้จ่าย (~100-200 queries ต่อ $1 สำหรับ gpt-4o-mini)
- 🌐 ต้องการอินเทอร์เน็ต
- 🔐 ข้อมูลถูกส่งไป OpenAI (ถ้ากังวลเรื่องความเป็นส่วนตัว)

---

## 🔄 การสลับระหว่าง Local และ Cloud

แค่เปลี่ยนค่า `MODEL_PROVIDER` ในไฟล์ `.env` หรือ environment variables:

### Local (Ollama):
```bash
MODEL_PROVIDER=ollama
OLLAMA_MODEL=qwen2.5-coder:7b
```

### Cloud (OpenAI):
```bash
MODEL_PROVIDER=openai
OPENAI_API_KEY=sk-proj-...
OPENAI_MODEL=gpt-4o-mini
```

จากนั้น restart FastAPI server:
```bash
# กด Ctrl+C แล้วรันใหม่
uvicorn api.main:app --reload
```

---

## 📊 เปรียบเทียบ Models

| Model | Provider | ความเร็ว | ความแม่นยำ | ราคา/Query | Use Case |
|-------|----------|---------|-----------|------------|----------|
| **qwen2.5-coder:7b** | Ollama | ⚡⚡⚡ | ⭐⭐⭐⭐ | ฟรี | Development, Testing |
| **gpt-4o-mini** | OpenAI | ⚡⚡⚡⚡ | ⭐⭐⭐⭐⭐ | ~$0.005-0.01 | Production (balanced) |
| **gpt-4** | OpenAI | ⚡⚡ | ⭐⭐⭐⭐⭐⭐ | ~$0.03-0.06 | Critical accuracy needs |

---

## 🆘 Troubleshooting

### ❌ "Ollama connection failed"
```bash
# ตรวจสอบว่า Ollama ทำงานอยู่หรือไม่
ollama list

# ถ้าไม่มี ให้รัน
ollama serve

# ตรวจสอบว่า server ตอบสนอง
curl http://localhost:11434/api/tags
```

### ❌ "OpenAI Rate Limit Error"
- ตรวจสอบยอดเงินใน OpenAI Account
- ไปที่ https://platform.openai.com/usage
- ตรวจสอบ API Key ว่าใช้งานได้

### ❌ "Model not found"
```bash
# ดาวน์โหลด model ใหม่
ollama pull qwen2.5-coder:7b

# ตรวจสอบว่าโหลดสำเร็จ
ollama list
```

### ❌ "Connection refused on port 8000"
```bash
# ตรวจสอบว่า FastAPI กำลังรันอยู่
lsof -i :8000

# ถ้าไม่มี ให้รัน
uvicorn api.main:app --reload
```

---

## 💡 คำแนะนำ

### สำหรับ Development
- 🏠 **ใช้ Ollama** - ฟรี รวดเร็ว และไม่ต้องกังวลเรื่อง API quota
- 📊 **เพิ่มตัวอย่างใน RAG** - ช่วยให้ Local model แม่นยำขึ้น
- 🧪 **ทดสอบบน Ollama ก่อน** - debug ได้ง่ายกว่า

### สำหรับ Production
- ☁️ **ใช้ OpenAI** - เสถียร ความแม่นยำสูง และไม่ต้องบำรุงรักษา server
- 💰 **เริ่มด้วย gpt-4o-mini** - ราคาถูกและเร็ว (เหมาะกับ 80% use cases)
- 🔄 **Monitor usage** - ตรวจสอบค่าใช้จ่าย API ผ่าน OpenAI dashboard

### การปรับแต่งเพิ่มเติม
- 📈 **ถ้าความแม่นยำต่ำ:** เพิ่มตัวอย่างใน `thai_sql_examples.json`
- 🚀 **ถ้าต้องการความเร็ว:** ใช้ Ollama + เครื่องที่มี GPU
- 🎯 **ถ้าต้องการความแม่นยำสูงสุด:** ใช้ GPT-4 (แพงกว่าแต่แม่นมาก)

---

## 🔧 Configuration File Reference

ตั้งค่าทั้งหมดอยู่ใน `core/config.py`:

```python
class Settings:
    # Model Configuration
    MODEL_PROVIDER = os.getenv("MODEL_PROVIDER", "ollama").lower()
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
```

สามารถ override ค่าใดก็ได้ผ่าน `.env` file หรือ environment variables
