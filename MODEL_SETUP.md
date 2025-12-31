# 🤖 Model Provider Setup Guide

แอปนี้รองรับ **2 Model Providers** ที่สลับกันได้:
- **Ollama** (Local) - สำหรับ development ในเครื่อง (ฟรี)
- **OpenAI API** (Cloud) - สำหรับ deployment บน Streamlit Cloud (เสียค่าใช้จ่าย)

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

### 3. ตั้งค่าใน `.streamlit/secrets.toml`
```toml
MODEL_PROVIDER = "ollama"
OLLAMA_MODEL = "qwen2.5-coder:7b"
```

### 4. รันแอป
```bash
streamlit run app.py
```

**ข้อดี:**
- ✅ ฟรี ไม่มีค่าใช้จ่าย
- ✅ ไม่ต้องใช้อินเทอร์เน็ต
- ✅ ความเร็วขึ้นกับเครื่อง

**ข้อเสีย:**
- ⚠️ ต้องมี RAM อย่างน้อย 8GB (แนะนำ 16GB)
- ⚠️ ไม่สามารถ deploy บน Streamlit Cloud ได้

---

## ☁️ สำหรับ Cloud Deployment (OpenAI)

### 1. สมัคร OpenAI API Key
1. ไปที่ https://platform.openai.com/api-keys
2. สร้าง API Key ใหม่
3. เติมเงินเข้าบัญชี (ขั้นต่ำ $5)

### 2. ตั้งค่าใน `.streamlit/secrets.toml` (Local)
```toml
MODEL_PROVIDER = "openai"
OPENAI_API_KEY = "sk-proj-your-actual-key-here"
OPENAI_MODEL = "gpt-4o-mini"  # หรือ "gpt-4"
```

### 3. ตั้งค่าใน Streamlit Cloud (Deploy)
เมื่อ Deploy แล้ว ไปที่ **App Settings → Secrets** แล้วใส่:
```toml
MODEL_PROVIDER = "openai"
OPENAI_API_KEY = "sk-proj-your-actual-key-here"
OPENAI_MODEL = "gpt-4o-mini"
```

**ข้อดี:**
- ✅ Deploy ได้บน Cloud
- ✅ ประสิทธิภาพสูงและเสถียร
- ✅ ไม่ต้องมีเครื่องแรง

**ข้อเสีย:**
- 💰 มีค่าใช้จ่าย (~100-200 queries ต่อ $1 สำหรับ gpt-4o-mini)

---

## 🔄 การสลับระหว่าง Local และ Cloud

แค่เปลี่ยนค่า `MODEL_PROVIDER` ใน `.streamlit/secrets.toml`:

### Local (Ollama):
```toml
MODEL_PROVIDER = "ollama"
OLLAMA_MODEL = "qwen2.5-coder:7b"
```

### Cloud (OpenAI):
```toml
MODEL_PROVIDER = "openai"
OPENAI_API_KEY = "sk-proj-..."
OPENAI_MODEL = "gpt-4o-mini"
```

---

## 📊 เปรียบเทียบ Models

| Model | Provider | ความเร็ว | ความแม่นยำ | ราคา/Query |
|-------|----------|---------|-----------|------------|
| **qwen2.5-coder:7b** | Ollama | ⚡⚡⚡ | ⭐⭐⭐⭐ | ฟรี |
| **gpt-4o-mini** | OpenAI | ⚡⚡⚡⚡ | ⭐⭐⭐⭐⭐ | ~$0.005-0.01 |
| **gpt-4** | OpenAI | ⚡⚡ | ⭐⭐⭐⭐⭐⭐ | ~$0.03-0.06 |

---

## 🆘 Troubleshooting

### ❌ "Ollama connection failed"
```bash
# ตรวจสอบว่า Ollama ทำงานอยู่หรือไม่
ollama list

# ถ้าไม่มี ให้รัน
ollama serve
```

### ❌ "OpenAI Rate Limit Error"
- ตรวจสอบยอดเงินใน OpenAI Account
- ไปที่ https://platform.openai.com/usage

### ❌ "Model not found"
```bash
# ดาวน์โหลด model ใหม่
ollama pull qwen2.5-coder:7b
```

---

## 💡 คำแนะนำ

- 🏠 **ใช้ Ollama** เมื่อพัฒนาในเครื่อง (ฟรี และรวดเร็ว)
- ☁️ **ใช้ OpenAI** เมื่อต้องการ deploy ให้คนอื่นใช้ (เสถียรและใช้งานง่าย)
- 💰 เริ่มต้นด้วย **gpt-4o-mini** ก่อน (ถูก และเร็ว) ถ้าต้องการความแม่นยำสูงสุดค่อยเปลี่ยนเป็น **gpt-4**

