# การแก้ไขปัญหา Uvicorn Reload Loop

## สรุปปัญหา

เมื่อรัน `uvicorn api.main:app --reload` เซิร์ฟเวอร์จะ **reload ไม่หยุด** วนเป็นลูปไม่สิ้นสุด

---

## อาการที่พบ

เมื่อรันคำสั่ง:
```bash
uvicorn api.main:app --reload
```

Terminal จะแสดงข้อความซ้ำๆ แบบนี้:

```
WARNING:  WatchFiles detected changes in 'venv/lib/python3.12/site-packages/torch/...'
INFO:     Started server process [36414]
INFO:     Application startup complete.
WARNING:  WatchFiles detected changes in 'venv/lib/python3.12/site-packages/torch/...'
INFO:     Started server process [36419]
INFO:     Application startup complete.
WARNING:  WatchFiles detected changes in 'venv/lib/python3.12/site-packages/torch/...'
...
(วนลูปไม่สิ้นสุด)
```

---

## สาเหตุของปัญหา

### 1. `--reload` flag ทำงานอย่างไร

เมื่อใช้ `--reload` uvicorn จะใช้ **WatchFiles** เพื่อตรวจสอบการเปลี่ยนแปลงของไฟล์ทุกไฟล์ในโปรเจค เมื่อพบว่าไฟล์มีการเปลี่ยนแปลง มันจะ restart เซิร์ฟเวอร์อัตโนมัติ

### 2. ปัญหาเกิดจาก PyTorch

โปรเจคนี้ใช้ `sentence-transformers` ซึ่งต้องพึ่งพา **PyTorch** (torch) ซึ่งเป็น library ขนาดใหญ่มาก (4+ GB) ที่มีไฟล์ Python หลายพันไฟล์

เมื่อ Python load PyTorch มันจะ:
1. เข้าถึงไฟล์ `.py` หลายร้อยไฟล์ใน `venv/lib/python3.12/site-packages/torch/`
2. สร้าง cache files (`.pyc`)
3. ทำให้ WatchFiles ตรวจพบ "การเปลี่ยนแปลง" ในไฟล์เหล่านั้น

### 3. วงจรอุบาทว์ (Infinite Loop)

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│   Uvicorn Start                                                 │
│        │                                                        │
│        ▼                                                        │
│   Load Application (api.main:app)                               │
│        │                                                        │
│        ▼                                                        │
│   Import sentence-transformers → Import PyTorch                 │
│        │                                                        │
│        ▼                                                        │
│   PyTorch accesses hundreds of .py files in venv/               │
│        │                                                        │
│        ▼                                                        │
│   WatchFiles detects "changes" in venv/...torch/...             │
│        │                                                        │
│        ▼                                                        │
│   Uvicorn triggers RELOAD ─────────────────────────┐            │
│        │                                           │            │
│        └───────────────────────────────────────────┘            │
│                    (วนซ้ำไม่สิ้นสุด)                              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## วิธีแก้ไขที่ลองแล้วไม่ได้ผล

### ❌ วิธีที่ 1: ใช้ `--reload-exclude`

```bash
uvicorn api.main:app --reload --reload-exclude "venv/*"
```

**ผลลัพธ์**: ไม่ได้ผล! WatchFiles ยังคงตรวจจับ venv อยู่

**เหตุผล**: `--reload-exclude` ใช้ glob pattern ที่ไม่ครอบคลุมไฟล์ทั้งหมดใน nested directories

---

## วิธีแก้ไขที่ได้ผล

### ✅ วิธีที่ถูกต้อง: ใช้ `--reload-dir`

แทนที่จะบอกว่า "อย่าดูอะไร" ให้บอกว่า **"ดูแค่อะไร"**

```bash
uvicorn api.main:app --reload --reload-dir api --reload-dir core
```

**คำอธิบาย**:
- `--reload-dir api` = ให้ดูเฉพาะโฟลเดอร์ `api/`
- `--reload-dir core` = ให้ดูเฉพาะโฟลเดอร์ `core/`
- ไม่ได้ระบุ `venv/` = **ไม่ดู venv เลย**

**ผลลัพธ์**:
```
INFO:     Will watch for changes in these directories: 
          ['.../api', '.../core']
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete.
(ไม่มี reload loop!)
```

---

## สิ่งสำคัญที่ต้องจำ

### 1. ต้อง Activate Virtual Environment ก่อนเสมอ

```bash
source venv/bin/activate
```

ถ้าไม่ทำ จะเกิด **Segmentation Fault** เพราะใช้ Python ผิดตัว

### 2. คำสั่งที่ถูกต้องสำหรับ Development

```bash
# ต้องทำทุกครั้ง
source venv/bin/activate

# คำสั่งที่ถูกต้อง
uvicorn api.main:app --reload --reload-dir api --reload-dir core --host 0.0.0.0 --port 8000
```

### 3. หรือใช้ Script ที่สร้างไว้

```bash
./start_server.sh
```

---

## ไฟล์ที่สร้างเพื่อแก้ปัญหา

| ไฟล์ | คำอธิบาย |
|------|----------|
| `start_server.sh` | Script สำหรับ Mac/Linux พร้อม reload-dir ที่ถูกต้อง |
| `start_server.bat` | Script สำหรับ Windows |
| `.env.example` | Template สำหรับ environment variables |
| `QUICK_START.md` | คู่มือการใช้งานฉบับย่อ |
| `docs/TROUBLESHOOTING_RELOAD_LOOP.md` | เอกสารนี้ |

---

## บทเรียนที่ได้

1. **`--reload-exclude` ไม่น่าเชื่อถือ** สำหรับ nested directories ที่ซับซ้อน
2. **`--reload-dir` เป็นวิธีที่ดีกว่า** เพราะเป็น whitelist แทน blacklist
3. **PyTorch เป็น library ที่ใหญ่มาก** และอาจทำให้เกิดปัญหากับ file watchers
4. **ตรวจสอบว่า venv ถูก activate ก่อนเสมอ**

---

## การตรวจสอบว่าแก้ไขสำเร็จ

### 1. เช็คว่าไม่มี reload loop

Terminal ควรแสดง:
```
INFO:     Application startup complete.
```
และ **ไม่มี** WARNING เกี่ยวกับ WatchFiles อีก

### 2. ทดสอบ Health Endpoint

```bash
curl http://localhost:8000/api/health
# ควรได้: {"status":"ok"}
```

### 3. ทดสอบเปลี่ยนโค้ด

แก้ไขไฟล์ใน `api/` หรือ `core/` และดูว่า server reload ได้ปกติ

---

## อ้างอิง

- [Uvicorn Documentation - Settings](https://www.uvicorn.org/settings/)
- [WatchFiles GitHub](https://github.com/samuelcolvin/watchfiles)
- [PyTorch Issue with File Watchers](https://github.com/pytorch/pytorch/issues)

---

**แก้ไขเมื่อ**: 5 กุมภาพันธ์ 2026
**ปัญหา**: Uvicorn Infinite Reload Loop  
**สาเหตุ**: WatchFiles ตรวจจับ PyTorch files ใน venv  
**วิธีแก้**: ใช้ `--reload-dir api --reload-dir core` แทน `--reload`
