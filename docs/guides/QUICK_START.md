# 🚀 Quick Start Guide

คู่มือนี้พา service ขึ้นมาคุยกับ **STS Datasource** ได้ภายใน ~10 นาที

> Service หนึ่ง instance ตอบคำถามกับ **Datasource เดียว** ที่ fix จาก
> `DATABASE_URL` — ไม่มี `/connect` และ Consumer ไม่ส่ง credential ของ DB มา
> (ดู [ADR 0011](../adr/0011-one-datasource-per-deployment-profiles-as-seam.md))

---

## 📋 สิ่งที่ต้องมี

- **Python 3.10+** (repo นี้ใช้ 3.11) และ [uv](https://docs.astral.sh/uv/)
- **Read-only PostgreSQL connection ของ STS** — role `nl2sql_ro` พร้อม `SELECT`
  เท่านั้น วิธีสร้างและตรวจ RLS อยู่ใน [docs/DEPLOYMENT.md](../DEPLOYMENT.md)
- **LLM provider** อย่างน้อยหนึ่งตัว:
  - OpenAI / Google Gemini / OpenRouter / Zhipu (cloud)
  - หรือ [Ollama](https://ollama.com/) (local, RAM 8GB+)
- ไม่ต้องติดตั้ง Docker สำหรับ quick start นี้

---

## 🧪 Standalone demo (ไม่ต้องใช้ STS)

ถ้าต้องการลองหน้าเว็บและ API โดยไม่ต้องมี STS connection:

```bash
./start_demo.sh
# เปิด http://127.0.0.1:8001/
```

สคริปต์จะ:

- ใช้ `local_database.db` (SQLite sample) และ `profiles/demo`
- ตั้ง `APP_MODE=demo` ทำให้ UI อยู่ที่ `/` และ `/api` ไม่ต้องใช้ API key
- bind `127.0.0.1` เท่านั้น; เปลี่ยนได้ด้วย `DEMO_HOST=0.0.0.0` ถ้าตั้งใจเปิดในเครือข่าย
- สร้าง sample database ให้ถ้ายังไม่มีไฟล์

ตรวจว่า demo ต่อ datasource ได้:

```bash
curl http://127.0.0.1:8001/api/health
# {"status":"ok","datasource":true,...}
```

อยากลองกับฐานข้อมูลของตัวเอง ใช้แท็บ **🔌 Connect** ในหน้าเว็บ (เฉพาะโหมด demo):

- เลือกชนิดฐานข้อมูล กรอกฟิลด์ แล้วกด **Connect Database** — service จะสลับ
  datasource ให้ทันที และจำไว้จนกว่าจะปิด server (รีสตาร์ทแล้วกลับไปใช้ค่าเริ่มต้น)
- เลือก **Domain Profile** ให้ตรงกับฐานข้อมูลนั้น ไม่งั้นคำตอบจะอ้างคำศัพท์ผิดโดเมน
- ถ้าเชื่อมไม่สำเร็จ รายการเดิมยังตอบต่อได้ เพราะสลับเฉพาะเมื่อต่อสำเร็จเท่านั้น
- หรือชี้ตั้งแต่เริ่ม: `DEMO_DATABASE_URL="sqlite:///./other.db" DEMO_DOMAIN_PROFILE=demo ./start_demo.sh`

### 🧭 สร้าง Profile จากฐานข้อมูลของคุณ (Profile wizard)

ถ้าเชื่อมฐานข้อมูลของตัวเองแล้ว ยังไม่มี profile ที่รู้จักตารางและคำศัพท์ของมัน
ใช้ปุ่ม **🧭 สร้าง Profile จากฐานข้อมูลนี้** ในแท็บ Connect (หรือป้ายแนะนำที่ขึ้นเมื่อ
ฐานข้อมูลนั้นยังไม่มี profile) — ใช้เวลาประมาณ 5 นาทีใน 6 ขั้น (ขั้น 2 และ 4–6 ข้ามได้):

1. **ชื่อ profile** — ตัวพิมพ์เล็ก a-z, 0-9, `-`, `_` เท่านั้น (เช่น `my_school`)
2. **คำศัพท์ไทย** — คำที่ผู้ใช้พิมพ์ → ชื่อตาราง/คอลัมน์ (ข้ามได้)
3. **ตัวอย่างคำถาม** — พิมพ์คำถาม ระบบจะร่าง SQL แล้วรันกับฐานข้อมูลจริงให้ดู;
   ยอมรับ / แก้ SQL แล้วรันใหม่ / ข้ามได้ (ตัวอย่างที่ SQL รันไม่ผ่านจะไม่ถูกบันทึก)
4. **กฎธุรกิจและความกำกวม** — ข้อความนี้ถูกเก็บใน `hints.md` และใช้ทั้งสอง prompt
   (one-shot และ agent)
5. **ความหมายของตาราง** — ต่อตาราง: หนึ่งแถวคืออะไร และครอบคลุมกลุ่มไหน (เก็บใน
   `table_notes.json`) ตารางที่กรอกไม่ครบทั้งสองช่องจะไม่ถูกบันทึก
6. **ตัวอย่างคำตอบแบบถามกลับ/ปฏิเสธ** — คำถาม + ประเภทคำตอบ + ข้อความที่ควรตอบ
   (เห็น preview ข้อความก่อนบันทึก) เก็บเป็นตัวอย่างที่ไม่มี SQL

กด **บันทึก Profile** แล้วหน้าเว็บจะแสดง coverage (กฎธุรกิจ / จำนวนตัวอย่าง /
ตัวอย่างถามกลับ–ปฏิเสธ / จำนวนคำศัพท์ / จำนวนตารางที่มีบันทึก) และปุ่ม
**ใช้ profile นี้เลย** ซึ่งสลับให้ทันทีโดยไม่ต้อง restart

ไฟล์ถูกเขียนเป็น profile ธรรมดาใต้ `profiles/<ชื่อ>/` (`hints.md`,
`schema_mappings.json`, `table_notes.json`, `examples.json`) — ตรวจ diff และ commit เองได้ตามปกติ
wizard ใช้ได้เฉพาะโหมด demo (service mode ไม่มี endpoint เหล่านี้) และไม่ได้รัน
evaluation หรือ commit ให้อัตโนมัติ

> `APP_MODE=demo` ไม่มี authentication จึงห้ามใช้กับข้อมูลจริงหรือเปิดสู่อินเทอร์เน็ต
> production ใช้ `APP_MODE=service` + `API_KEY` ตามหัวข้อด้านล่าง

---

## ⚡ Quick start (macOS / Linux)

### 1. Clone และติดตั้ง dependencies

```bash
git clone https://github.com/chanyut12/NLP-to-SQL-Agent.git
cd NLP-to-SQL-Agent

# uv จะสร้าง .venv/ ให้เอง — ไม่ต้อง activate
uv sync
```

ถ้ายังไม่มี `uv`:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. ตั้งค่า `.env`

```bash
cp .env.example .env
nano .env   # หรือ open -e .env
```

ค่าที่ต้องมี:

```bash
# Deployment mode: auto (default) | demo | service
APP_MODE=auto

# Datasource — read-only connection, fix ตอน startup
DATABASE_URL=postgresql+psycopg2://nl2sql_ro:YOUR_PASSWORD@HOST:5432/postgres?sslmode=require
DOMAIN_PROFILE=sts

# Shared secret สำหรับ Consumer (เว้นว่าง = auto mode, demo UI mount ที่ /)
# API_KEY มาจาก .env หรือ shell; shell ที่ตั้งค่าจะชนะ .env
# ถ้าต้องการรันเป็น service ให้รัน: APP_MODE=service API_KEY=secret ./start_server.sh
API_KEY=

# LLM provider: openai | google | ollama | openrouter | zhipu
MODEL_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

- `DATABASE_URL` ต้องเป็นบัญชี **read-only** — อย่าใช้ connection string เดียวกับ
  backend ที่เขียนข้อมูลได้
- `DOMAIN_PROFILE=sts` คือ profile ที่รองรับ STS ในปัจจุบัน
- `APP_MODE=auto` (ค่าเริ่มต้น) เปิด demo UI เมื่อ `API_KEY` ว่าง และปิดเมื่อมี key
- `APP_MODE=service` เป็น Consumer-only: ต้องมี `API_KEY` และ UI/`/docs` จะถูกปิด
- `APP_MODE=demo` ใช้สำหรับ `./start_demo.sh` เท่านั้น; ต้องไม่มี `API_KEY`
- ถ้าตั้ง `API_KEY` เป็นค่าจริง: ต้องส่ง header `X-API-Key` ทุกครั้ง;
  shell ที่ตั้ง `API_KEY=secret ./start_server.sh` จะชนะค่าใน `.env`
- provider อื่นดูตัวอย่างใน [.env.example](../../.env.example)

### 3. Start และตรวจสอบ

```bash
./start_server.sh
```

สคริปต์จะเคลียร์ port 8000 ให้เองถ้าเป็น launchd service ของโปรเจกต์นี้ และรัน
uvicorn พร้อม auto-reload สำหรับ `api/` และ `core/`

ตรวจว่า service ต่อ Datasource ได้:

```bash
curl http://localhost:8000/api/health
# {"status":"ok","datasource":true,"schema_cached":true,"warming":false}
```

ลองถามคำถาม STS:

```bash
# ถ้าตั้ง API_KEY ไว้ ให้ export API_KEY=... ก่อน หรือแทนที่ด้วยค่าจริง
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{"question":"จำนวนนักเรียนปัจจุบันแยกตามโรงเรียน","history":[]}'
```

> `history: []` คือ Turn แรกของ Session และเลือกโหมด agent ถ้า **ไม่ส่ง**
> `history` เลย จะเป็น legacy one-shot (ไม่มีความสามารถถามกลับ/ปฏิเสธ)
> Response envelope ดูได้ที่ [docs/API.md](../API.md)

เปิด demo UI ที่ `http://localhost:8000` ได้เมื่อ `APP_MODE=demo` หรือ `auto` ที่
`API_KEY` ว่าง ถ้ารัน `APP_MODE=service` ให้ Consumer เรียก `/api/*` โดยตรง

> ครั้งแรกที่รัน ระบบจะ download embedding model (~500MB) จึงต้องใช้ internet
> และ request แรกอาจช้า

---

## 🪟 Windows

```bat
git clone https://github.com/chanyut12/NLP-to-SQL-Agent.git
cd NLP-to-SQL-Agent

:: ติดตั้ง uv (PowerShell): irm https://astral.sh/uv/install.ps1 | iex
uv sync

copy .env.example .env
notepad .env
:: ตั้ง DATABASE_URL, DOMAIN_PROFILE=sts และ LLM provider

start_server.bat
```

สำหรับ standalone demo บน Windows ให้ตั้ง `APP_MODE=demo`,
`DATABASE_URL=sqlite:///./local_database.db`, `DOMAIN_PROFILE=demo` และ `API_KEY=`
ใน `.env` แล้วรัน `start_server.bat` (UI จะอยู่ที่ port 8000)

ตรวจสอบด้วยคำสั่ง `curl` เดียวกับด้านบน (หรือใช้ Postman/Bruno)

---

## 🧪 ตรวจสอบเพิ่มเติม

```bash
# Unit tests
uv run --extra dev pytest tests/unit -q

# ตรวจ syntax
uv run python -m py_compile core/*.py api/*.py

# ดูตาราง/วิวที่โมเดลมองเห็น
curl -H "X-API-Key: $API_KEY" http://localhost:8000/api/schema
```

Evaluation (Golden set + metrics) ดูที่ [eval/STS_EVAL.md](../../eval/STS_EVAL.md)

---

## 🔧 Troubleshooting

### `503 Datasource unavailable`

- `DATABASE_URL` ว่าง หรือต่อ PostgreSQL ไม่ติด
- ตรวจ `curl http://localhost:8000/api/health` → `datasource` ต้องเป็น `true`
- ตรวจว่า role มี `SELECT` และ `CONNECT` ตาม [docs/DEPLOYMENT.md](../DEPLOYMENT.md)
- **ไม่มี `/connect`** — ต้องแก้ `.env` แล้ว restart service

### `401 invalid or missing API key`

- ตั้ง `API_KEY` ไว้ แต่ request ไม่มี header `X-API-Key` หรือค่าผิด
- ตรวจว่า shell ไม่ได้ตั้ง `API_KEY` ทับค่าที่ต้องการ (shell ชนะ `.env`)
- ถ้าเป็น dev ให้เว้น `API_KEY` ว่าง หรือใช้ `./start_demo.sh`

### เปิด `/` แล้ว 404

- แสดงว่า `APP_MODE=service` หรือ `API_KEY` ถูกตั้ง — demo UI ไม่ mount ตามดีไซน์
- ใช้ Consumer เรียก `/api/query` แทน, เปลี่ยนเป็น `APP_MODE=demo` หรือเว้น `API_KEY`
  สำหรับ local demo

### Ollama ไม่ตอบ

```bash
ollama list
ollama serve
ollama pull qwen2.5-coder:7b
# แล้วตั้ง MODEL_PROVIDER=ollama ใน .env
```

### `ModuleNotFoundError`

```bash
uv sync --reinstall
```

### Port 8000 ถูกใช้อยู่

- ถ้าเป็น launchd service ของโปรเจกต์ này `./start_server.sh` จะหยุดให้ก่อน
- ถ้าเป็น process อื่น สคริปต์จะบอก PID และหยุดเพื่อให้คุณจัดการเอง

### แก้ profile แล้วไม่เห็นผล

- `profiles/` ไม่ได้อยู่ใน `--reload-dir` — ต้อง restart service
- หลังแก้ `examples.json` / `schema_mappings.json` หรือ schema:
  ```bash
  rm -rf rag_db schema_rag_db
  ./start_server.sh
  ```
- หลัง STS migration เรียก `POST /api/admin/refresh-schema`
- รายละเอียด profile ทั้งหมดอยู่ที่ [PROFILES.md](PROFILES.md)

---

## 🤖 LLM providers

| Provider | ตั้งค่า | หมายเหตุ |
|---|---|---|
| OpenAI | `MODEL_PROVIDER=openai` + `OPENAI_API_KEY` | deployment ปัจจุบันใช้ `gpt-4o-mini` |
| Google Gemini | `MODEL_PROVIDER=google` + `GOOGLE_API_KEY` | ต้องมี key จาก Google AI Studio |
| Ollama | `MODEL_PROVIDER=ollama` + `OLLAMA_MODEL` | local/offline; ใช้ RAM มาก |
| OpenRouter | `MODEL_PROVIDER=openrouter` + `OPENROUTER_API_KEY` | มี free/paid models; ตรวจ latency ก่อนใช้ |
| Zhipu (GLM) | `MODEL_PROVIDER=zhipu` + `ZHIPU_API_KEY` | OpenAI-compatible endpoint |

ราคาและ quota เปลี่ยนได้ — ตรวจจากผู้ให้บริการก่อนเลือกใช้จริง

---

## 🐳 Docker (optional)

`Dockerfile` และ `docker-compose.yml` ยังอยู่ใน repo แต่ compose ปัจจุบันยังไม่ได้
forward `APP_MODE`, `DATABASE_URL`, `API_KEY` และ `DOMAIN_PROFILE` ให้ service — ถ้าจะใช้ Docker
ให้เพิ่ม environment เหล่านั้นเองหรือดูแนวทางใน [docs/DEPLOYMENT.md](../DEPLOYMENT.md)
สำหรับ quick start แนะนำใช้ `uv` ตามด้านบน

---

## 🎯 Next steps

- [API Reference](../API.md) — envelope, `answer_type`, `history`, SSE
- [Consumer Integration](../INTEGRATION.md) — ตัวอย่าง session และ NestJS relay
- [Domain Profiles](PROFILES.md) — เพิ่ม datasource/domain ใหม่
- [Deployment](../DEPLOYMENT.md) — read-only role และ Tailscale Funnel
- [README](../../README.md) — ภาพรวมและ scope ของโปรเจกต์

**Happy coding! 🎉**
