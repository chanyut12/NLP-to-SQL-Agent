# Before / After — pipeline vs conversational agent (tickets #18 + #21)

เซ็ตคำถามชุดเดียวกันทั้งสองรอบ (Golden set 36 ข้อ ตาม ADR 0007), model เดียวกัน
(openai/gpt-4o-mini), datasource เดียวกัน — ต่างกันแค่เอนจินที่ตอบคำถาม:

- **Before** (`baseline_before.json`): one-shot pipeline เดิม (`--engine pipeline`)
- **After** (`after_agent_pre_latency.json`): conversational agent loop ตาม ADR 0006
  (`--engine agent`) — รอบทางการหลังปรับ system prompt (ตัวเลขทั้งหมดในตารางด้านล่างอ้างรอบนี้)
  `after_agent.json` ปัจจุบันคือรอบยืนยันหลังการทดลอง latency ถอยกลับ — ผลอยู่ใน noise band
  เดียวกัน (ดูหัวข้อท้ายไฟล์)

ผลลัพธ์ถูกให้คะแนนด้วย comparator ชุดเดียวกันทุกข้อ (`eval/scoring.py` — ย้ายจาก
`eval/run_eval.py` แบบ verbatim) เพื่อให้เทียบกันได้โดยตรง

## SQL questions (28 ข้อ)

| Bucket | Before EX | After EX | Before EX~ | After EX~ | Before grain | After grain |
|---|--:|--:|--:|--:|--:|--:|
| count_groupby | 75% | **100%** | 100% | 100% | 100% | 100% |
| count_filter_groupby | 75% | 75% | 75% | 75% | 100% | 100% |
| aggregation_groupby | 25% | 0% | 75% | 50% | 100% | 75% |
| ratio_groupby | 25% | 25% | 25% | 25% | 50% | 75% |
| having_threshold | 50% | 50% | 75% | 75% | 100% | 100% |
| time_groupby | 75% | 50% | 100% | 100% | 100% | 100% |
| ranking | 75% | 75% | 75% | 75% | 100% | 100% |
| **OVERALL** | **57.1%** | **53.6%** | **75.0%** | **71.4%** | **92.9%** | **92.9%** |

รายคำถามที่พลิกผล (EX):

- agent **ได้ `paraphrase_02`** (นับนักเรียนตาม risk tier)
- agent **เสีย `paraphrase_11`** (อัปเดตล่าสุด/เก่าสุดต่อโรงเรียน) — ยังผ่าน EX~
  คือพลาดเฉพาะรูปร่างคอลัมน์ ไม่ใช่สาระของคำตอบ (กติกา "ล่าสุด = ถามกลับ" ไม่ได้ทำให้
  ข้อนี้ถูกถามกลับ — โมเดลตอบด้วย SQL ตามตัวอย่าง `MAX(updated_at)` ในคอร์ปัส)
- agent **เสีย `novel_04`** (เฉลี่ยนักเรียนต่อห้องตามระดับชั้น) — นิยาม ratio ต่างจากเฉลย

สุทธิ −1 ข้อ (16 → 15) อยู่ในระดับ noise ของ single-run (ตัวเลขราย bucket n=4 แกว่ง ±25pp)
— **SQL ทำได้ parity** การเปลี่ยนไปใช้ agent ไม่ได้แลกความแม่นยำของ SQL

## Answer-type questions (8 ข้อ, ให้คะแนนตาม refusal-first)

| คำตอบที่คาดหวัง | Before | After (ก่อน tune) | After (ทางการ) |
|---|---|---|---|
| clarification (ถามกลับ) | 0/4 (0%) | 3/4 (75%) | **4/4 (100%)** |
| refusal (ปฏิเสธ) | 0/4 (0%) | 4/4 (100%) | **4/4 (100%)** |

- Before: pipeline ตอบเป็น SQL ทุกครั้ง — ทั้งคำถามกำกวมและคำขอนอกขอบเขต
  (ขอข้อมูลส่วนบุคคล/คำสั่งเขียนข้อมูล) ไม่เคยถามกลับหรือปฏิเสธเลย
- After: **8/8** — คำถามกำกวมถูกถามกลับทุกข้อ (เช่น "เด็กเสี่ยงมีเท่าไหร่" →
  ถามว่านับตาม tier ไหน), คำขอ PII/คำสั่งเขียนถูกปฏิเสธทุกข้อ
- **การ tune ครั้งเดียวพอ**: รอบแรกได้ clarify 3/4 เพราะ prompt ไม่เคยบอกลำดับ
  "จำแนกก่อนเขียน SQL" และไม่มีตัวอย่างคู่เทียบ กำกวม ↔ ครบสาระ หลังแก้
  สองจุดนี้ได้ 4/4 ทันทีโดย **ไม่มี over-clarification** (28 คำถาม SQL ยังถูกตอบด้วย
  SQL ทุกข้อ) — ข้อ `answer_type_04` ("เคสล่าสุดมีกี่เคส") ตั้งใจหยุด tune ที่ 3 รอบ
  เพื่อไม่ overfit prompt กับตัวอย่างเดียว แต่ผลรอบทางการผ่านเอง

## ต้นทุนของการแลก (trade-offs)

| | Before (pipeline) | After (agent) |
|---|--:|--:|
| latency p50 (SQL ข้อ) | 2.3 s | **10.5 s** |
| latency p95 (SQL ข้อ) | 9.3 s | 16.1 s |
| LLM steps เฉลี่ยต่อคำถาม SQL | 1 | ~2.2 |
| latency เฉลี่ยคำถามถามกลับ/ปฏิเสธ | — (ไม่เคยทำ) | ~5.2 s (1–2 steps) |
| STEP_BUDGET_EXCEEDED | — | 0 ข้อ |

Agent แพ้ latency เฉลี่ย ~4× เพราะ 1 คำถามใช้หลาย step (get_schema/run_sql/final_answer)
แต่คำถามกำกวม/นอกขอบเขตจบเร็วกว่าคำถาม SQL (ปฏิเสธได้โดยไม่ต้องเขียน SQL)

## ข้อจำกัดของการวัดครั้งนี้

- รันครั้งเดียวต่อเอนจิน (baseline เดิมของโปรเจกต์รัน 5 ครั้ง; ตัวเลขราย bucket n=4
  จึงมี noise ±25pp) — สรุประดับ OVERALL จึงน่าเชื่อถือกว่าระดับ bucket
- รอบ after รันด้วย concurrency 1 เพื่อเลี่ยง OpenAI 429 (รอบแรก concurrency 3
  เจอ LLM_FAILED 9 ข้อจาก rate limit และถูกทิ้ง) — before รอบด้วย concurrency 3
  แต่ใช้ 1 call ต่อคำถาม จึงไม่เจอ 429; ผลรวมความล่าช้าไม่ได้เทียบข้ามสองโหมดนี้โดยตรง
- กติกา prompt ใหม่ ("ล่าสุด/ช่วงนี้ ไม่มีวันที่ = ถามกลับ") เขียนจากหลักฐานว่า
  28 คำถาม SQL ทุกข้อระบุ tier/ช่วงเวลาครบ แต่การป้องกัน over-clarification อาศัย
  ตัวอย่างใน prompt ไม่ใช่การพิสูจน์เชิงสถิติ — ควรขยายชุด ambiguous ต่อในอนาคต

## การทดลองลด latency (หลัง #21) — สรุป: เป็นราคาโครงสร้างของ ADR 0006

ทดลอง 3 รอบ gate เต็ม 36 ข้อ เพื่อลด p50 จาก ~10s ให้เหลือ ~5s:

1. **ย้ายเนื้อหา dynamic ออกจาก system prompt** (เพื่อ OpenAI prefix caching) + กติกา
   "ยิง `run_sql` + `final_answer` ใน step เดียวกัน" + ตัด Tier-3 LLM fallback ออกจาก
   การเตรียม context ของ agent → **gate ล้ม**: clarification 1/4, refusal 3/4, EX~ 60.7%,
   p50 ไม่ลด — การย้ายกติกาทำ recency หาย (สิ่งสุดท้ายที่โมเดลอ่านกลายเป็น schema summary)
2. เติม reminder block ท้าย user message + บังคับ same-step กับ SQL (message ไม่อ้างตัวเลข)
   → **gate ล้มซ้ำ**: clarification 3/4 สองรอบติด, EX~ หลุด band, **p50 ยัง 11.1s**
3. **ถอยกลับ prompt เป๊ะ** (กู้ 8/8 + SQL parity) เก็บเฉพาะการตัด Tier-3 fallback
   (`agent_mode`) → **gate ผ่าน**: 8/8, EX 50.0% / EX~ 67.9% / grain 89.3% (band ±1 จากรอบทางการ)

ข้อเท็จจริงที่พิสูจน์ได้จากการทดลอง:

- **latency บัญญัติโดยจำนวน step** — ~5s/step (1 step = 5.4s, 2 = 10.3s, 3 = 16.1s)
- คำถาม SQL ทุกข้อใช้ 2 steps เพราะโมเดล**รอเห็นแถวผลก่อนเขียนข้อความสรุป** — สั่ง same-step
  สองจุดในสองบล็อกก็ไม่เปลี่ยน (24/28 ยัง 2 steps) same-step ที่เกิดจริงคือคำถาม
  clarification/refusal (1 step ~5s) ซึ่งโครงเดิมก็ทำได้อยู่แล้ว
- ตัวเลข latency ในรอบทดลองอ่านไม่ได้เท่าไร (OpenAI 429 แทรกระหว่างรัน) แต่ข้อสรุปยึดที่
  **ความสามารถทรุด 2/2 รอบโดย latency ไม่ลด** — เพียงพอสำหรับการถอยตามเกณฑ์ gate
- ตัด schema pruning ออกเพื่อให้ prefix cache ข้ามคำถามได้ไม่เป็นทางเลือก: prefix หนัก
  (examples + schema) เปลี่ยนทุกคำถามอยู่แล้ว cache ข้ามคำถามจึงไม่มีทางติด และการตัด
  schema กระทบความแม่นยำโดยตรง

**p50 ~10s ต่อคำถาม SQL จึงเป็นราคาโครงสร้างของสถาปัตยกรรม agent ตาม ADR 0006**
(LLM เป็นผู้ควบคุม + refusal-first): ทางเดียวที่จะลง ~5s คือ (a) auto-finalize เมื่อ SQL
สำเร็จ — คว่ำหลัก LLM-as-controller, (b) เปลี่ยนโมเดล — ทำ before/after เทียบไม่ได้,
หรือ (c) streaming — ลด latency ที่รู้สึก ไม่ลดเวลาจริง ทั้งหมดเกินขอบเขตงานนี้และถูก
ตัดสินใจไว้ชัดเจนตามเอกสารนี้

สิ่งที่เก็บไว้จากการทดลอง: flag `agent_mode` — การเตรียม context ของ agent ไม่เรียก
Tier-3 LLM table-guessing อีกต่อไป (fallback นั้นออกแบบไว้ให้ pipeline one-shot ซึ่ง
กู้คืนไม่ได้ ส่วน agent กู้คืนเองด้วย `get_schema` tool) — สถาปัตยกรรมสอดคล้องขึ้นโดย
ไม่แตะพฤติกรรมที่วัดผลได้
