# Measurement — Latency & compute deepening (spec #27, ticket #32)

> หลักฐานการวัดจริง before/after ของงาน spec #27 (warm engine, free event loop,
> visible timing) วัดเมื่อ 2026-09-19 บน branch `feature/er_han_and_JSDoc`
> · commits: `880024f` + `a74024c` (after) เทียบ `3f07114` (before)

## วิธีวัด

- สร้าง git worktree 2 ตัวจาก commit จริง: **before = `3f07114`** (ก่อนงาน
  spec #27 ทั้งหมด) และ **after = `880024f`/`a74024c`** — ใช้ `.env`,
  `rag_db/`, `schema_rag_db/` ชุดเดียวกัน เพื่อให้ข้อมูล/โมเดล/index เหมือนกันทุกอย่าง
- สตาร์ทเซิร์ฟเวอร์ (uvicorn, port 8001/8002) → รอ port + รอ warm state ผ่าน
  `/api/health` → **ยิงคำถามแรกจริง** (ผ่าน agent loop, 2 steps, ต่อ STS จริง)
- ซีน 2–3 รัน live บน build หลัง (port 8899) โดยตั้ง
  `WARMUP_MAINTENANCE_INTERVAL_SECONDS=2` เพื่อพิสูจน์กลไกโดยไม่รอ 5 นาที
  (ค่า production คือ 300s)

## ซีน 1 — คำถามแรกหลังสตาร์ท (cold-start)

| รอบ | before (3f07114) | after (880024f+) |
|---|---|---|
| รอบ 1 | **9,349 ms** (2 steps, prep_ms: None) | **3,452 ms** (2 steps, **prep_ms: 429**) |
| รอบ 2 | **10,743 ms** (2 steps, prep_ms: None) | **3,747 ms** (2 steps, **prep_ms: 947**) |

- before: คำถามแรกจ่าย schema introspection (106 ตาราง) + schema-RAG เตรียม
  เองทั้งก้อน → แพงกว่าคำถาม warm ปกติชัดเจน
- after: งานหนักถูกย้ายไป background — warm เสร็จเองใน **17.9s / 20.9s**
  หลัง boot (`schema_cached:true, warming:false` บน `/api/health`) →
  **คำถามแรกเร็วขึ้น ~2.7–2.9 เท่า (ประหยัด ~6–7 วินาที)**
- `prep_ms` เห็นครั้งแรกบน after build — ตอนนี้แยก "งานเตรียมบริบท ~0.4–0.9s"
  ออกจาก "ราคา LLM 2 steps (~2.5–2.8s ที่เหลือ)" ได้เป็นตัวเลข

## ซีน 2 — TTL/refresh ไม่ตกกับผู้ใช้อีก (re-warm เบื้องหลัง)

```
POST /api/admin/refresh-schema  →  {"status":"ok"}
health ทันที:  schema_cached:false (stale ถูก mark ถูกต้อง)
3 วินาทีถัดมา:  schema_cached:true   ← maintenance loop สร้างใหม่เอง
                โดยไม่มีคำถามเข้ามาแม้แต่คำเดียว (ZERO questions sent)
```

- ก่อนหน้านี้: ผู้ใช้ที่ถามตรงช่วง TTL หมด (ทุกชั่วโมง) คือคนจ่าย rebuild
  หลายวินาทีตามรอบที่ 1
- แก้บั๊กที่จับได้ระหว่างวัด: maintenance loop เดิมรัน pass แรก**ทันทีตอน
  boot** แข่งกับ startup warmup (rebuild ซ้ำ) → แก้เป็น sleep-first
  (`a74024c`)

## ซีน 3 — endpoint เสริมไม่ block คำถาม/สตรีมอีกต่อไป

| การวัด | ผล |
|---|---|
| `/api/history` ตอน idle | 11–22 ms |
| `/api/history` 5 ครั้ง**ระหว่างสตรีมกำลังรัน** (กลาง LLM step) | **9–24 ms** |
| สตรีมที่ยิงพร้อมกัน | ครบ 4 progress events + envelope ปกติ |

- เท่ากับว่า I/O ของ history/feedback/favorites (to_thread ตาม #30) ไม่ทำให้
  request ของคนอื่นติดขัดอีกต่อไป — ตัวเลขระหว่างสตรีม = ตอน idle

## สรุป

ทั้งสามซีนยืนยัน spec #27 ตามเกณฑ์: cold-start หาย (9–11s → 3.5–3.7s),
staleness ถูกดูดซับในเบื้องหลัง, aux I/O ไม่แชร์ความทุกข์กับคำถาม
p50 ของคำถาม warm ปกติ (~10s = 2 LLM steps) ไม่เปลี่ยนตามการออกแบบ —
งานนี้ตัดค่าใช้จ่ายรอบนอก LLM ทั้งหมด และทำให้มองเห็นได้ (prep_ms)
