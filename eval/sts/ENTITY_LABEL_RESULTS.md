# Measurement — ADR 0009 Entity label in answers

> ผล eval gate หลัง implement ADR 0009 ครบ 4 ชั้น (prompt rule, corpus rewrite,
> gold correction, display collapsible) วัดเมื่อ 2026-09-22 บน branch
> `feature/er_han_and_JSDoc` · model `openai/gpt-4o-mini` · engine `agent` ·
> rag_top_k 3 · max_retries 2 · schema pruned — เงื่อนไขเดียวกับ baseline
> (`after_agent.json`, วัด 2026-09-16)

## การควบคุมตัวแปร

- Retrieval neighbors **ไม่เปลี่ยน** — store embed จาก question + tags เท่านั้น
  (SQL เป็น document ที่ไม่ถูก embed) การแก้ SQL ใน corpus จึงไม่กระทบตัวอย่าง
  ที่ถูกดึง และ carve ของ held-out เป็นแบบ id-based จึงเหมือนเดิมทุก id
- เปลี่ยนตัวแปรเดียว: กติกา Entity label (prompt + corpus + เฉลย 5 ข้อ)

## บทเรียนเรื่อง 429 (บันทึกไว้กันการตีความผิด)

- **RUN1/RUN2 (concurrency 3)** โดน OpenAI TPM limit หนัก (LLM_FAILED 4/6 ครั้ง,
  p50 24–32s เทียบ baseline 10.1s) — ตัวเลข accuracy ของสองรอบนี้**ใช้ตัดสินไม่ได้**
- **RUN3 (concurrency 1)** สะอาด: LLM_FAILED=0, p50 10.5s ≈ baseline →
  ตัวเลขตัดสินคือ RUN3 (`after_entity_label_run3.json`)

## ผลตัดสิน (RUN3 เทียบ baseline)

| Metric | Baseline | RUN3 (ADR 0009) | ตัดสิน |
|---|--:|--:|---|
| strict EX | 50.0% (14/28) | 46.4% (13/28) | −1 ข้อ = noise ระดับ n=28 |
| relaxed EX~ | 67.9% | **75.0%** | +2 ข้อ |
| grain correct | 89.3% | **92.9%** | +1 ข้อ |
| first-try success | 50.0% | 46.4% | −1 ข้อ (ตาม EX) |
| p50 / p95 latency | 10.1s / 16.8s | 10.5s / 21.2s | เท่าเดิม (sequential) |
| **คำตอบที่มี label column** | **14/26** | **18/26** | **เป้าหมายหลักของ ADR เพิ่ม +4** |
| **5 ข้อ id-ล้วนเดิมส่ง label กลับ** | 1/5 | **5/5** | **ผ่านเงื่อนไข ADR** |

## รายข้อที่ strict เปลี่ยน (ทั้ง 4 ตรวจกับ DB จริงแล้ว)

| ข้อ | คลาส | สาเหตุจริง (ไม่ใช่การเติมชื่อ) |
|---|---|---|
| attendance_absence_by_weekday | cols_only | ใช้ DOW (อา., ..., ศ.) แทน ISODOW (1–7) — ค่าต่าง ไม่ใช่คอลัมน์; EX~ ผ่าน |
| case_count_by_workflow_status | cols_only | ไม่ JOIN status table มาโชว์ `label_th` (โมเดลตัดสินใจเอง; รอบเก่าใส่, EX~ ผ่าน) |
| case_without_review_count_by_school | cols_only | ตัวเลข case_count ต่าง 6 รายการ (filter คนละทาง) — ทั้งเก่า/ใหม่ไม่เคย strict ตรงกันแบบนี้; **label มาครบทั้งคู่** |
| student_current_count_by_grade | wrong_result | จำนวนนักเรียนต่าง (snapshot filter คนละแบบ) — คอลัมน์มี label ครบทั้งคู่แล้ว |

ชดเชย: ได้กลับ 3 ข้อ (paraphrase_02, 11, 12) — สุทธิ −1 = noise

## สรุป gate

- เงื่อนไข ADR 0009 "strict EX ต้องไม่ตกเกิน noise" → **ผ่าน** (−1 ข้อ)
- เงื่อนไข "5 id-only live patterns ต้องคืน label" → **ผ่าน 5/5**
- Presentation layer: id คู่ชื่อถูก mark `collapsible` ทุก result แล้ว deterministic

## ไฟล์อ้างอิง

- ผลรอบตัดสิน: `eval/sts/after_entity_label_run3.json` (sequential)
- ผลที่โดน 429 (เก็บไว้เป็นหลักฐาน): `after_entity_label.json` (run1),
  `after_entity_label_run2.json`
- ของเดิมก่อน rewrite: `*.pre-adr0009.json` (corpus + benchmark archives)
