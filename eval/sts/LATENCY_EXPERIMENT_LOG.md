# Experiment log — การทดลองลด latency ของ agent engine

> **จุดประสงค์ของไฟล์นี้:** บันทึกว่าอะไร work อะไรไม่ work จากการทดลองจริงบน benchmark
> **ใครก็พยายามลด latency รอบหน้า ให้อ่านไฟล์นี้ก่อน** — ห้ามรายการในหัวข้อ
> "ไม่ work" จะถูกทำซ้ำถ้าไม่มีเหตุผลใหม่ที่ลบล้างหลักฐานเดิม
>
> งานนี้ถูกบันทึกด้วยกระบวนการ grilling (skill `grill-with-docs`): เป้าหมาย เกณฑ์ผ่าน
> และข้อจำกัดถูกตกลงร่วมกันก่อนลงมือ — ดูสรุปการตัดสินใจใน `eval/sts/BEFORE_AFTER.md`
> หัวข้อ "การทดลองลด latency" และ commit `1a3f746`

## บริบทและเป้าหมายที่ตกลงไว้

- **เป้า:** ลด p50 ของคำถาม SQL จาก ~10.5s ให้เหลือ ~5s (ถามกลับ/ปฏิเสธอยู่ที่ ~5s แล้ว)
- **เงื่อนไขผ่าน (gate):** ทุกครั้งที่แก้ prompt ต้องรัน eval เต็ม 36 ข้อ แล้วต้องได้
  answer-type **8/8** + SQL ไม่ต่ำกว่าเดิมเกิน **noise band ±1 ข้อ** (จาก 28) จึง commit
- **ข้อจำกัดที่ยอมรับ:** ไม่คว่ำ ADR 0006 (LLM เป็นผู้ควบคุม, refusal-first),
  ไม่เปลี่ยนโมเดล (before/after จะเทียบกันไม่ได้), แก้ที่ prompt/โครงสร้างเท่านั้น

## สรุปผู้บริหาร

| ทางลด latency | ผล | รายละเอียด |
|---|---|---|
| ตัด Tier-3 LLM fallback ออกจาก context prep ของ agent | ✅ **work — เก็บไว้** | ถูกต้องเชิงสถาปัตยกรรม ไม่แตะพฤติกรรมที่วัดผลได้ |
| ย้ายเนื้อหา dynamic ออกจาก system prompt (เพื่อ prefix caching) | ❌ **ไม่ work** | ทำ recency ของกติกาหาย — capability ทรุด 2 รอบติด |
| Same-step batching (`run_sql` + `final_answer` พร้อมกัน) กับคำถาม SQL | ❌ **ไม่ work** | โมเดลปฏิเสธ 24/28 แม้สั่งสองจุดสองบล็อก |
| Reminder block ท้าย user message (กู้ recency) | ❌ **ไม่เสถียรพอ** | refusal กลับมา แต่ clarification ยัง 3/4 สองรอบติด |
| ตัด schema pruning เพื่อให้ cache ข้ามคำถามติด | ❌ **ตั้งแต่ยังไม่ลอง** | premise เป็นเท็จ — prefix หนักเปลี่ยนทุกคำถามอยู่แล้ว |

**ข้อสรุป:** p50 ~10s ต่อคำถาม SQL คือ**ราคาโครงสร้างของสถาปัตยกรรม ADR 0006** —
ได้รับการพิสูจน์ด้วย gate เต็ม 3 รอบ ไม่ใช่ความเห็น

---

## ✅ สิ่งที่ WORK

### W1 — `agent_mode`: ตัด Tier-3 LLM table-guessing ออกจาก context prep ของ agent
- **อาการเดิม:** `_prepare_context` ส่ง `_llm` เข้า `smart_filter_schema` ทุก Turn ของ agent
  ด้วย — Tier-3 fallback ถูกออกแบบไว้ให้ pipeline one-shot (กู้คืนไม่ได้เมื่อกรองตารางพลาด)
  แต่ agent มีทางกู้คืนของตัวเองคือ `get_schema` tool อยู่แล้ว จึงเป็น LLM call ซ้ำซ้อน
  ที่ไม่มีใครขอและไม่อยู่ใน step budget
- **การแก้:** flag `agent_mode=True` จาก `run_agent_turn` → engine ส่ง `llm=None`
- **ทำไม work:** ตรงตามหลัก "แต่ละกลไกกู้คืนของตัวเอง" และไม่เปลี่ยนพฤติกรรมที่วัดได้
  (fallback เกิดยากมาก) — gate-confirmation run ผ่าน 8/8 พร้อม parity
- **หลักฐาน:** commit `1a3f746`, `core/services/engine.py` (`_prepare_context`),
  เทส `TestAgentModeContext` ใน `tests/unit/test_agent_loop.py`

### W2 — โครง prompt เดิม (กติกาใน system prompt) คือ configuration ที่ดีที่สุดที่รู้จัก
- รอบทางการก่อนการทดลอง (`after_agent_pre_latency.json`): **8/8**, SQL parity, p50 ~10.5s
- รอบยืนยันหลัง revert (`after_agent.json`): **8/8**, SQL ใน band, p50 ~10.1s
- **ข้อสรุป:** ถ้าจะแก้ prompt ต่อ ให้เริ่มจาก state นี้ และจำไว้ว่าการย้ายกติกาออกจาก
  system prompt เคยทำลายมัน (ดู F1)

### W3 — กระบวนการ gate เต็ม + noise band
- จับ capability regression ได้ 2 ครั้ง **ก่อน commit** — unit test ผ่านหมดทั้งสองครั้ง
  (บั๊ก bind_tools เคยหลุดผ่าน mock มาแล้ว — ห้ามเชื่อ mock อย่างเดียว)
- noise band ±1 ข้อที่ตกลงร่วมกัน ป้องกันการวนจูนตามตัวสุ่มของ gpt-4o-mini ได้จริง

### W4 — same-step batching กับคำถาม clarify/refusal (ไม่ต้องแก้อะไรเพิ่ม)
- คำถาม answer-type จบใน **1 step (~5s)** ตามธรรมชาติของโครงเดิมอยู่แล้ว —
  ไม่ต้องมีกติกาพิเศษ อย่าเสียเวลาเพิ่มกลไกตรงนี้

---

## ❌ สิ่งที่ ไม่ WORK — ห้ามทำซ้ำโดยไม่มีเหตุผลใหม่

### F1 — ย้ายเนื้อหา dynamic ออกจาก system prompt (static-first)
- **สิ่งที่ทำ:** system prompt เหลือแต่ invariant (dialect, tool spec, กติกา, ชื่อ section);
  คำถาม/history/examples/schema ย้ายไป user message เพื่อให้ prefix cache ของ OpenAI ติด
- **ผล:** gate ล้ม — clarification **1/4**, refusal 3/4, EX~ 60.7%, p50 ไม่ลด
- **กลไกที่พิสูจน์แล้ว:** กติกา classification/PII เดิมเป็น*สิ่งสุดท้ายที่โมเดลอ่านก่อนตัดสินใจ*
  เมื่อย้ายออก สิ่งสุดท้ายกลายเป็น schema summary โมเดลเลย (a) เห็นคำถามก่อนกติกา →
  ตอบคำถามกำกวมด้วย SQL, (b) เห็นตารางท้ายสุด → ออกล่าข้อมูล PII จนหมด budget
- **บทเรียน:** กับโมเดลขนาดนี้ **ตำแหน่งของกติกาสำคัญกว่าประสิทธิภาพของ cache** —
  อย่าย้ายกติกา classification/PII ออกจาก system prompt

### F2 — บังคับ same-step กับคำถาม SQL
- **สิ่งที่ทำ:** สั่งใน system prompt (rule 4) และซ้ำใน reminder — "เมื่อ run_sql สำเร็จ
  ให้ยิง final_answer ใน step เดียวกัน โดย message ไม่อ้างตัวเลข"
- **ผล:** **24/28 คำถาม SQL ยังใช้ 2 steps** — p50 รวมไม่ขยับ (10.98 → 11.1s)
- **กลไก:** โมเดล**รอเห็นแถวผลก่อนเขียนข้อความสรุป** — เป็นพฤติกรรมที่สั่งด้วย prompt
  ไม่เปลี่ยน; ทางเดียวที่บังคับได้คือ auto-finalize ฝั่ง service ซึ่งคว่ำหลัก
  LLM-as-controller ของ ADR 0006 (ถูกตัดตั้งแต่ต้น)
- **บทเรียน:** อย่าเสีย gate อีกไปกับการจูน same-step สำหรับ SQL — มันคือ 2 steps
  เชิงโครงสร้าง ไม่ใช่ปัญหา prompt

### F3 — Reminder block ท้าย user message เป็นกลไกกู้ recency
- **ผล:** กู้ refusal ได้ (4/4) แต่ clarification ยัง **3/4 สองรอบติด** — และตัวที่พลาด
  สลับไปมาระหว่างรอบ (สุ่ม) แปลว่าไม่มีจุดหยุดนิ่งที่ไว้ใจได้
- **บทเรียน:** reminder ช่วยได้บางส่วนแต่ไม่เทียบกับกติกาที่อยู่ใน system prompt —
  ถ้าจะใช้ reminder จริง ต้องมี benchmark ambiguous set ที่ใหญ่กว่า 4 ข้อเพื่อวัดเสถียรภาพ

### F4 — หวังพึ่ง prompt caching ข้ามคำถาม (premise เป็นเท็จตั้งแต่ต้น)
- **ทำไมไม่เป็นทางออกเลย:** `SCHEMA_STRATEGY = pruned` ทำให้ schema ตัดตามคำถามแต่ละข้อ
  และ few-shot examples ก็ retrieve ตามคำถาม — prefix หนัก (สิ่งที่ cache แล้วคุ้ม)
  **เปลี่ยนทุกคำถาม** จึงไม่มีทาง cache ข้ามคำถามได้; ส่วนที่ cache ข้ามได้จริงคือ
  system prompt ซึ่งเทียบกันไม่เห็นความต่างที่วัดได้
- **บทเรียน:** ก่อนออกแบบ prompt รอบ caching ให้ถามก่อนว่า "prefix หนักตัวไหนเปลี่ยน
  ต่อ request" — ถ้าคำตอบคือทุกตัว อย่าเริ่ม

### F5 — อ่าน latency จากรอบที่โดน 429 รัว ๆ
- รอบทดลองเจอ OpenAI 429 + retry แทรกหลายจุดแม้ concurrency 1 — ตัวเลข latency
  รอบนั้นฟุ่มเฟือย อย่าใช้ตัดสินจูน
- **บทเรียน:** วัด latency จริงจังต้องมี retry-budget ต่ำหรือเลือกรอบที่ log สะอาด
  (ไฟล์ `after_agent.json` รอบ gate-confirmation สะอาดกว่ารอบทดลอง)

---

## ข้อเท็จจริงพื้นฐานที่วัดแล้ว (ใช้คำนวณต่อได้เลย)

- **latency บัญญัติโดยจำนวน step: ~5s/step** — 1 step = 5.4s, 2 = 10.3s, 3 = 16.1s,
  4 = 21.7s, 5 = 29.6s (จาก `after_agent_pre_latency.json`, 36 ข้อ)
- คำถาม SQL = 2 steps เชิงโครงสร้าง (run_sql → อ่านแถว → final_answer)
- คำถาม clarification/refusal = 1 step (~5s)
- noise ของ single-run eval: ตัวเลข SQL รวมแกว่ง **±1–2 ข้อ** (จาก 28) —
  ราย bucket (n=4) แกว่งถึง ±25pp อย่าอ่านระดับ bucket เป็นสัญญาณ
- ต้นทุน eval รอบเต็ม: ~6–7 นาที (concurrency 1, agent engine)

## ทางที่ยังไม่ได้ลอง (เรียงตามความคุ้มที่คาดไว้)

1. **Streaming response** — ไม่ลดเวลาจริงแต่ลด perceived latency ฝั่ง UI/Consumer,
   ไม่แตะ ADR 0006 (ถูกตัดจากเป้าหมาย p50 แต่เป็นทาง UX ที่ยังเปิด)
2. **ขยายชุด ambiguous ใน golden set** ก่อนจูน prompt รอบใดอีก — 4 ข้อไม่พอวัดเสถียรภาพ
   และเสี่ยง overfit ทุกครั้งที่แก้
3. **Auto-finalize เมื่อ SQL สำเร็จ** — ทางเดียวที่จะได้ p50 ~5.5s จริง แต่**ต้องเขียน
   ADR คว่ำ ADR 0006 ก่อน** (LLM ไม่ใช่ผู้ควบคุมเต็มรูปแบบ) — เป็นการตัดสินใจเชิง
   สถาปัตยกรรม ไม่ใช่การจูน prompt
4. **เปลี่ยนโมเดลทั้งสองฝั่ง before/after** — ได้ latency ดีขึ้นได้ แต่ตัวเลขเทียบเดิม
   ต้องรันใหม่ทั้งชุด

## ไฟล์หลักฐานทั้งหมด

| ไฟล์/หลักฐาน | คืออะไร |
|---|---|
| `eval/sts/after_agent_pre_latency.json` | รอบทางการก่อนทดลอง — state อ้างอิง 8/8 |
| `eval/sts/after_agent.json` | รอบ gate-confirmation หลัง revert — 8/8 + band |
| `eval/sts/BEFORE_AFTER.md` | ตาราง before/after + หัวข้อ "การทดลองลด latency" |
| commit `1a3f746` | โค้ดสุดท้าย: revert + `agent_mode` + เทส + เอกสาร |
| `tests/unit/test_agent_loop.py::TestAgentModeContext` | เทสประกันของสิ่งที่เก็บไว้ |
