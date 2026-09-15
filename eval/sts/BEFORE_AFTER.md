# Before / After — pipeline vs conversational agent (ticket #21)

เซ็ตคำถามชุดเดียวกันทั้งสองรอบ (Golden set 36 ข้อ ตาม ADR 0007), model เดียวกัน
(openai/gpt-4o-mini), datasource เดียวกัน — ต่างกันแค่เอนจินที่ตอบคำถาม:

- **Before** (`baseline_before.json`): one-shot pipeline เดิม (`--engine pipeline`)
- **After** (`after_agent.json`): conversational agent loop ตาม ADR 0006 (`--engine agent`)

ผลลัพธ์ถูกให้คะแนนด้วย comparator ชุดเดียวกันทุกข้อ (`eval/scoring.py` — ย้ายจาก
`eval/run_eval.py` แบบ verbatim) เพื่อให้เทียบกันได้โดยตรง

## SQL questions (28 ข้อ)

| Bucket | Before EX | After EX | Before EX~ | After EX~ | Before grain | After grain |
|---|--:|--:|--:|--:|--:|--:|
| count_groupby | 75% | 75% | 100% | 100% | 100% | 100% |
| count_filter_groupby | 75% | 75% | 75% | 75% | 100% | 100% |
| aggregation_groupby | 25% | **0%** | 75% | 50% | 100% | 100% |
| ratio_groupby | 25% | 25% | 25% | 25% | 50% | 75% |
| having_threshold | 50% | 50% | 75% | 75% | 100% | 100% |
| time_groupby | 75% | 75% | 100% | 100% | 100% | 100% |
| ranking | 75% | 75% | 75% | 75% | 100% | 100% |
| **OVERALL** | **57.1%** | **53.6%** | **75.0%** | **71.4%** | **92.9%** | **96.4%** |

รายคำถามที่พลิกผล (EX): agent **เสีย `novel_04`** (aggregation_groupby) —
ไม่มีคำถามไหนที่ agent ทำได้แล้ว pipeline ทำไม่ได้ หรือกลับกัน นอกจากข้อเดียวนี้

## Answer-type questions (8 ข้อ, ให้คะแนนตาม refusal-first)

| คำตอบที่คาดหวัง | Before | After |
|---|---|---|
| clarification (ถามกลับ) | 0/4 (0%) | 0/4 (0%) |
| refusal (ปฏิเสธ) | 0/4 (0%) | **3/4 (75%)** |

- Before: pipeline ตอบเป็น SQL ทุกครั้ง — ทั้งคำถามกำกวมและคำถามนอกขอบเขต
  (ขอข้อมูลส่วนบุคคล/คำสั่งเขียนข้อมูล) ไม่เคยถามกลับหรือปฏิเสธเลย
- After: คำขอนอกขอบเขตถูกปฏิเสธ 3/4 ข้อ แต่คำถามกำกวมยังถูกตอบด้วย SQL
  แทนการถามกลับ (2 ข้อ) หรือปฏิเสธผิดประเภท (1 ข้อ) — เป็นโจทย์ tuning ต่อไป

## ต้นทุนของการแลก (trade-offs)

| | Before (pipeline) | After (agent) |
|---|--:|--:|
| latency p50 (SQL ข้อ) | 2.3 s | **10.1 s** |
| latency p95 (SQL ข้อ) | 15.7 s | 16.2 s |
| LLM calls โดยเฉลี่ยต่อคำถาม | 1 | ~2.1 steps |
| elapsed รวม 36 ข้อ (concurrency 1) | — | ~300 s |

Agent แพ้ latency เฉลี่ย ~4× เพราะ 1 คำถามใช้หลาย step (get_schema/run_sql/final_answer)
แต่ p95 ใกล้เคียงกัน — ความล่าช้ามาจากโครงสร้าง loop ไม่ใช่คำถามยาก ๆ ที่หมด budget

## ข้อจำกัดของการวัดครั้งนี้

- รันครั้งเดียวต่อเอนจิน (baseline เดิมของโปรเจกต์ก็รัน 5 ครั้ง; ตัวเลขราย bucket
  n=4 จึงมี noise ±25pp) — สรุประดับ OVERALL จึงน่าเชื่อถือกว่าระดับ bucket
- รอบ after รันด้วย concurrency 1 เพื่อเลี่ยง OpenAI 429 (รอบแรก concurrency 3
  เจอ LLM_FAILED 9 ข้อจาก rate limit และถูกทิ้ง) — before รอบด้วย concurrency 3
  แต่ใช้ 1 call ต่อคำถาม จึงไม่เจอ 429; ผลรวมความล่าช้าไม่ได้เทียบข้ามสองโหมดนี้โดยตรง
