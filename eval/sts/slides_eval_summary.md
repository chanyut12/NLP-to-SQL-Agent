---
marp: true
theme: default
paginate: true
size: 16:9
footer: 'STS Text-to-SQL — Evaluation'
---

<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+Thai:wght@400;500;700&family=Sarabun:wght@400;500;700&display=swap');

:root {
  --color-background: #ffffff;
  --color-foreground: #1f2937;
  --color-heading: #1e40af;
  --color-accent: #3b82f6;
  --color-border: #d1d5db;
  --font-default: 'Noto Sans Thai', 'Sarabun', 'Hiragino Kaku Gothic ProN', sans-serif;
}

section {
  background-color: var(--color-background);
  color: var(--color-foreground);
  font-family: var(--font-default);
  font-weight: 400;
  box-sizing: border-box;
  border-top: 8px solid var(--color-heading);
  position: relative;
  line-height: 1.6;
  font-size: 21px;
  padding: 52px 56px 56px;
}

h1, h2, h3, h4 { font-weight: 700; color: var(--color-heading); margin: 0; padding: 0; }

h1 { font-size: 50px; line-height: 1.25; text-align: left; letter-spacing: -0.02em; }

h2 {
  position: absolute; top: 36px; left: 56px; right: 56px;
  font-size: 34px; padding-bottom: 14px;
  border-bottom: 3px solid var(--color-accent);
}
h2 + * { margin-top: 96px; }

h3 { color: var(--color-accent); font-size: 24px; margin-top: 24px; margin-bottom: 10px; font-weight: 600; }

ul, ol { padding-left: 30px; }
li { margin-bottom: 8px; line-height: 1.55; }

footer {
  font-size: 15px; color: #6b7280;
  position: absolute; left: 56px; right: 56px; bottom: 30px;
}

section.lead {
  display: flex; flex-direction: column; justify-content: center;
  background: linear-gradient(135deg, #ffffff 0%, #eef2ff 100%);
}
section.lead footer { display: none; }
section.lead h1 { margin-bottom: 26px; }
section.lead p { font-size: 23px; color: var(--color-foreground); font-weight: 500; }

table { border-collapse: collapse; width: 100%; margin: 16px 0; font-size: 17px; }
th, td { border: 1px solid var(--color-border); padding: 9px 11px; text-align: left; }
th { background-color: var(--color-heading); color: #fff; font-weight: 700; }
tr:nth-child(even) { background-color: #f9fafb; }
td.n, th.n { text-align: right; }

strong { color: var(--color-heading); font-weight: 700; }
code {
  background-color: #f3f4f6; color: var(--color-heading);
  padding: 2px 6px; border-radius: 3px;
  font-family: 'Consolas', 'Monaco', monospace; font-size: 0.9em;
}

.big { font-size: 42px; font-weight: 700; color: var(--color-heading); }
.muted { color: #6b7280; }
</style>

<!-- _class: lead -->
<!-- _paginate: false -->

# การประเมิน (Evaluation)
# ระบบ Thai Text-to-SQL บนฐานข้อมูล STS

**สรุป:** RAG few-shot คือตัวแปรชี้ขาด — 3% → 47% (deepseek 13% → 50%)
ค่าใช้จ่ายรัน eval ~$1.6 · ต้นทุนพัฒนาจริง > $5

**เฟส 2–3:** Agent loop — SQL parity + ถามกลับ/ปฏิเสธ 8/8 · คำถามแรกเร็วขึ้น ~2.8× · เห็น SQL กลางทาง

<span class="muted">โมเดลหลัก: openai/gpt-4o-mini · ฐานข้อมูล: STS (dev)</span>

---

## หัวข้อ

1. Eval คืออะไร ทำไปทำไม
2. ขั้นตอนการทำ (5 ขั้น)
3. คำศัพท์ที่ต้องรู้
4. ผลลัพธ์ + การทดลอง ablation
5. เทียบ 2 โมเดล
6. ค่าใช้จ่าย
7. สรุปและข้อเสนอ
8. งานที่ควรทำต่อ (future work)
9. เฟส 2 — จาก 1 query เป็น Agent (ตามคำติชาอาจารย์)
10. เฟส 3 — Latency และประสบการณ์ผู้ใช้

---

## Eval คืออะไร

- ระบบรับ**คำถามภาษาไทย** → AI เขียน **SQL** → รันกับฐานข้อมูล STS → คืนผลลัพธ์
- ปัญหา: SQL ที่ AI เขียน **ถูกบ้างผิดบ้าง**
- Eval = **ชุดข้อสอบมาตรฐาน + เฉลย + การให้คะแนนอัตโนมัติ**
- รันซ้ำได้ → เทียบ config / เทียบโมเดล / วัดว่าปรับอะไรถึงดีขึ้น

---

## ขั้นตอน — ภาพรวม 5 ขั้น

1. สร้าง **ชุดข้อสอบ (Golden set)** 30 คำถาม + เฉลย
2. ให้ AI **ตอบทีละข้อ** ผ่าน pipeline เต็ม
3. **ให้คะแนน** — เอาผลลัพธ์ SQL ที่ AI เขียน เทียบกับเฉลย
4. **การทดลอง (ablation)** — ปรับทีละตัวแปร รันซ้ำ 5 รอบ
5. **รวมผล** → ตารางเปรียบเทียบ

---

## ขั้นที่ 1 — Golden set 30 คำถาม

- ไฟล์ `eval/benchmark_sts.json` — แต่ละข้อมี: คำถามไทย + **SQL เฉลย** + ประเภท
- เฉลยทุกข้อ **ตรวจแล้วว่ารันได้จริง** และคืน ≥ 1 แถว
- **แยกออกจากชุดตัวอย่างที่ AI ใช้เรียนรู้** (68 ตัวอย่าง)
  → ไม่งั้น AI จะได้เห็นเฉลยตัวเองผ่าน RAG = โกงข้อสอบ

---

## 3 ประเภทคำถาม (แบ่งตามความยาก)

ชุดข้อสอบ 30 ข้อ แบ่งตาม**ความใกล้เคียงกับตัวอย่างที่ AI เห็น** (68 อันในชุด RAG)

| ประเภท | n | คือ | ทดสอบอะไร |
|---|---|---|---|
| **held_out** | 10 | คำถามที่เคยอยู่ในชุดตัวอย่าง → **ดึงออก + ลบจาก RAG** ก่อนสอบ | ตอบเองได้มั้ย โดยไม่มีตัวอย่างตรง ๆ ให้ก๊อป |
| **paraphrase** | 12 | คำถามที่**ยังอยู่**ในชุดตัวอย่าง แต่**เขียนใหม่** (ย่อ / พิมพ์ผิด / ไทยปนอังกฤษ / พูดเล่น ๆ) | จับได้มั้ยว่าเป็นคำถามเดิมที่เขียนต่างไป |
| **novel** | 8 | **combination ใหม่** ที่ชุดตัวอย่างไม่เคยมี (metric × การจัดกลุ่ม แบบที่ไม่เคยสอน) | ประกอบความรู้เองได้มั้ย (ยากสุด) |

---

## ขั้นที่ 2 — Pipeline ต่อ 1 คำถาม

1. ดึง **schema** ของฐานข้อมูล
2. **RAG retrieval** — ค้นตัวอย่างคำถาม-SQL ที่คล้ายสุด + ตารางที่เกี่ยวข้อง
3. สร้าง **prompt** = คำสั่ง + hints + ตัวอย่าง + schema + คำถาม
4. เรียก **LLM** → เขียน SQL
5. **ตรวจความปลอดภัย** — บล็อกที่ไม่ใช่ `SELECT`
6. **รัน SQL** (สิทธิ์อ่านอย่างเดียว)
7. รันไม่ผ่าน → ส่ง error ให้ LLM **แก้แล้วลองใหม่** (สูงสุด `max_retries`)

---

## ขั้นที่ 3 — การให้คะแนน

- รัน **SQL ที่ AI เขียน** และ **SQL เฉลย** → เอา **ตารางผลลัพธ์** มาเทียบ
- เทียบแบบ **ไม่สนลำดับแถว** · ตัวเลขปัดทศนิยม 2 ตำแหน่ง
- ได้ค่าหลายตัว: **EX / relaxed / first-try / grain / latency**
- + จำแนกประเภทข้อผิด (`cols_only`, `wrong_grain`, `wrong_result`, ...)

---

## คำศัพท์ — ค่าคะแนน

| ค่า | หมายถึง (ภาษาคน) |
|---|---|
| **EX** (strict) | **คะแนนหลัก** — ผลลัพธ์ตรงกับเฉลยเป๊ะทุกคอลัมน์ทุกแถว |
| **EX relaxed** | ให้อภัยคอลัมน์บรรยายเกิน/ขาด 1 คอลัมน์ (แถวต้องตรง) — เพดานบน |
| **first-try** | ตอบถูกเป๊ะ **โดยไม่ต้อง retry** |
| **grain** | จำนวนแถวตรงกับเฉลย — จับ JOIN ผิดจนแถวบวม |
| **p50 / p95** | เวลาต่อคำถาม — ค่ากลาง / ตัวช้าสุด 5% |

---

## คำศัพท์ — ประเภทข้อผิด

| ประเภท | หมายถึง |
|---|---|
| **cols_only** | เลขถูก จัดกลุ่มถูก แต่คอลัมน์บรรยายต่าง (ผ่าน relaxed ไม่ผ่าน strict) |
| **wrong_grain** | จำนวนแถวผิด (มักเพราะ JOIN ผิด) |
| **wrong_result** | รันได้ แต่ตัวเลข/ผลลัพธ์ผิด |
| **exec_fail** | SQL รันไม่ผ่าน (คอลัมน์ไม่มีจริง ฯลฯ) |
| **no_sql** | AI สร้าง SQL ไม่ได้เลย |

---

## คำศัพท์ — config

- **RAG** = Retrieval-Augmented Generation
  ค้นตัวอย่าง/ข้อมูลที่เกี่ยวข้องมาใส่ prompt ก่อนให้ AI ตอบ
- **rag_top_k** = จำนวนตัวอย่างที่ดึงมาใส่ (0 = ไม่ใส่, 3 = ใส่ 3 อันคล้ายสุด)
- **retry / self-correction** = SQL รันไม่ผ่าน → ส่ง error ให้ AI แก้ ลองใหม่กี่ครั้ง

---

## ขั้นที่ 4 — การทดลอง Ablation

| ตัวแปร | ค่าที่ทดลอง | ถามว่า |
|---|---|---|
| `rag_top_k` | 0 vs 3 | ใส่ตัวอย่าง 3 อัน vs ไม่ใส่ ช่วยแค่ไหน |
| `max_retries` | 0 vs 2 | ให้แก้ SQL เอง vs ไม่ให้ ช่วยแค่ไหน |

**2 × 2 = 4 config · รันซ้ำ config ละ 5 รอบ · = 20 รอบ × 30 ข้อ = 600 ครั้ง**

---

## ผลลัพธ์ — gpt-4o-mini (rag=3, retry=2)

| ค่า | ผล | แปลว่า |
|---|---|---|
| EX (strict) | **47% ±4%** | ตอบถูกเป๊ะ ~ครึ่งหนึ่ง |
| EX relaxed | **76% ±3%** | ไม่ซีเรียสคอลัมน์บรรยาย → ~3 ใน 4 ใช้ได้ |
| first-try | 44% ±4% | ที่ถูก ส่วนใหญ่ถูกตั้งแต่ครั้งแรก |
| grain | 87% ±4% | จำนวนแถวถูกเกือบตลอด |
| held_out / paraphrase / novel | 48% / **70%** / **12%** | novel พังเกือบหมด |
| latency p50 / p95 | 6.6s / 21.2s | ต่อคำถาม |

---

## ผลลัพธ์ — Ablation (4 config)

| rag | retry | EX | EX relaxed | first-try | grain |
|---|---|---|---|---|---|
| **0** | 0 | **3%** | 30% | 3% | 70% |
| **0** | 2 | 5% | 30% | 5% | 69% |
| **3** | 0 | **47%** | 73% | 47% | 88% |
| **3** | 2 | 47% | 76% | 44% | 87% |

---

## มี RAG vs ไม่มี RAG (gpt-4o-mini · retry=2 เท่ากัน)

| เมตริก | ❌ ไม่มี RAG (rag=0) | ✅ มี RAG (rag=3) | ต่าง |
|---|---|---|---|
| **EX** (strict) | 5% ±2% | **47% ±4%** | +42 |
| **EX relaxed** | 30% ±4% | **76% ±3%** | +46 |
| **first-try** | 5% ±2% | **44% ±4%** | +39 |
| **grain** | 69% ±3% | **87% ±4%** | +18 |
| **held_out** | 10% | **48% ±4%** | +38 |
| **paraphrase** | 2% ±3% | **70% ±4%** | +68 |
| **novel** | 2% ±5% | **12% ±11%** | +10 |
| p50 latency | 7.0 วิ | 6.6 วิ | ~เท่ากัน |

→ ตัวอย่าง 3 อันในชุด RAG เปลี่ยนระบบจาก**ใช้ไม่ได้ → ใช้ได้** · paraphrase พุ่งแรงสุด (2% → 70%)

---

## การวิเคราะห์ error จริง (150 คำถาม/config)

| ประเภท | rag=3, retry=2 | rag=0, retry=2 |
|---|---|---|
| **PASS** (ถูกเป๊ะ) | **47%** (71) | 5% (7) |
| **cols_only** | **29%** (43) | 25% (38) |
| wrong_result | 11% (17) | **39%** (58) |
| wrong_grain | 3% (5) | **22%** (33) |
| no_sql *(rate-limit)* | 8% (12) | 3% (4) |
| exec_fail | 1% (2) | 3% (5) |

→ ที่ rag=3 **`cols_only` คือ error หลัก** (เลขถูก คอลัมน์บรรยายต่าง)
→ ที่ rag=0 พังกระจาย: ตัวเลขผิด 39% + แถวบวม 22%

---

## อ่าน Ablation ว่า (1)

### RAG คือทุกอย่าง

- rag 0 → 3 ทำให้ EX พุ่ง **3% → 47%** (relaxed 30% → 76%)
- **ไม่มีตัวแปรอื่นขยับได้ใกล้เคียง**
- ตัวอย่าง 3 อันสอน AI เรื่อง join path ของ STS + กฎ "นักเรียนปัจจุบัน"
  ที่ schema เปล่า ๆ บอกไม่ได้

---

## อ่าน Ablation ว่า (2)

### retry แทบไม่ช่วย + จุดอ่อน 2 จุด

- **retry 0 → 2 = 47% → 47%** — ที่ rag=3 SQL รันผ่านอยู่แล้ว 88%
  retry ไม่มีอะไรให้แก้ แต่กิน token + เวลา ~3 เท่า → **default ควรเป็น retry=0**
- **strict 47% vs relaxed 76%** — 29 จุดเป็น `cols_only` (เลือกคอลัมน์บรรยาย ไม่ใช่คำนวณ)
- **novel 12%** — AI ก๊อป pattern ได้ แต่คิดรูปแบบ SQL ใหม่เองไม่ได้

---

## โมเดลที่ 2 — deepseek-v4-flash-0731

- ทดลองผ่าน OpenRouter — **รัน 1 รอบ/config** (gpt-4o-mini รัน 5 รอบ) → ยังไม่มี ±
- provider ค้างบางคำถาม → เพิ่ม **per-question timeout 150s** ใน harness
  (rag=3 timeout 1/30 · rag=0 timeout **8/30**)

| config | EX | EX relaxed | first-try | grain | novel |
|---|---|---|---|---|---|
| rag=3, retry=2 | **50%** | 83% | 50% | 97% | **62%** |
| rag=0, retry=2 | 13% | 43% | 13% | 70% | 12% |

→ **เรื่องเดียวกัน:** RAG ดัน EX 13% → 50%

---

## สรุปเทียบ 2 โมเดล — ตารางเดียว

| ด้าน | gpt-4o-mini | deepseek-v4-flash | ตัวไหนดีกว่า |
|---|---|---|---|
| ความแม่นยำ (EX strict) | 47% | 50% | **เสมอ** |
| คำถามยาก (novel) | 12% | 62% | **deepseek** ✅ |
| จำนวนแถวถูก (grain) | 87% | 97% | **deepseek** ✅ |
| คำถามเขียนใหม่ (paraphrase) | 70% | 50% | **gpt-4o-mini** ✅ |
| ความเร็ว (p50) | 6.6 วิ | 24.8 วิ | **gpt-4o-mini** (เร็ว 4×) ✅ |
| ความเสถียร | ครบทุกข้อ | ค้างบางข้อ (timeout) | **gpt-4o-mini** ✅ |
| ราคา (ต่อ token) | แพงกว่า ~3× | ถูกกว่า | **deepseek** ✅ |
| ความมั่นใจของผล | 5 รอบ (มี ±) | 1 รอบ (ไม่มี ±) | **gpt-4o-mini** ✅ |

**สรุป:** headline เสมอกัน → เลือก **gpt-4o-mini** สำหรับ production (เร็ว + นิ่ง) · **deepseek** น่าตามต่อถ้าเน้นคำถามยาก (ต้องรันครบ 5 รอบก่อน)

---

## เทียบ 2 โมเดล — ตารางเมตริก (config rag=3, retry=2)

| เมตริก | ความหมาย | gpt-4o-mini | deepseek-v4 |
|---|---|---|---|
| **EX** (strict) | ผลลัพธ์ตรงเฉลยเป๊ะทุกคอลัมน์ | 47% ±4% | **50%** |
| **EX relaxed** | ให้อภัยคอลัมน์บรรยายเกิน/ขาด 1 | 76% ±3% | **83%** |
| **first-try** | ผ่านตั้งแต่ครั้งแรก ไม่ต้อง retry | 44% ±4% | **50%** |
| **grain** | จำนวนแถวตรงเฉลย (JOIN ไม่บวม) | 87% ±4% | **97%** |
| **p50 / p95** | เวลา/คำถาม — ค่ากลาง / ช้าสุด 5% | **6.6 / 21.2 วิ** | 24.8 / 108.6 วิ |
| **held_out** | คำถามใหม่ ไม่มีตัวอย่างช่วย | **48% ±4%** | 40% |
| **paraphrase** | คำถามเดิม เขียนใหม่ | **70% ±4%** | 50% |
| **novel** | combination ที่ชุดตัวอย่างไม่เคยสอน | 12% ±11% | **62%** |

<span class="muted">gpt-4o-mini: เฉลี่ย 5 รอบ (±sd) · deepseek: 1 รอบ (ไม่มี ±) · ตัวหนา = ดีกว่า</span>

---

## เทียบ 2 โมเดล — อ่านว่า

- **headline เสมอกัน** — EX 50% vs 47% (deepseek ไม่มี ± ด้วย)
- deepseek **ชนะชัด: novel (62 vs 12) · grain (97 vs 87)**
- gpt-4o-mini **ชนะ: paraphrase (70 vs 50) · เร็ว 4 เท่า · เสถียรกว่า**
- **ยังตัดสินไม่ได้เต็มปาก** — deepseek ต้องรัน 5 รอบ + provider เสถียร (DeepSeek API ตรง)

---

## ค่าใช้จ่าย — เฉพาะ eval

| รายการ | คำถาม | ค่าใช้จ่าย |
|---|---|---|
| gpt-4o-mini — sweep เต็ม (20 รอบ) | 600 | **$1.53 (~54 บาท)** |
| deepseek — 2 config × 1 รอบ + ที่ค้าง + smoke | ~130 | $0.07 (~2 บาท) |
| **รวมเฉพาะ eval** | | **≈ $1.60 (~56 บาท)** |

<span class="muted">± ~50% — eval ไม่บันทึก token จริง · ต่อคำถาม ~9–10k input + ~0.2k output</span>

---

## ค่าใช้จ่าย — จริง > $5

$1.60 คือ **เฉพาะการรัน benchmark ที่ให้คะแนน** — ส่วนที่เกินมาจาก:

- **ตั้ง harness + เขียน/แก้บั๊ก + วิเคราะห์** ใช้โมเดลใหญ่ (ระดับ **Claude Sonnet / GPT-5**)
  ราคาสูงกว่า gpt-4o-mini **~20–50 เท่า/token**
- รัน eval รอบแรก ๆ ที่เจอบั๊ก → รันซ้ำ
- diagnostic calls ตอนโดน rate-limit + รัน deepseek

→ **ต้นทุน dev/setup >> ต้นทุนรัน eval** · ถ้ารันรอบเดียวหลังระบบนิ่ง จ่ายแค่ ~$1.5

---

## สรุป — สิ่งที่เรียนรู้

- **RAG few-shot เป็นตัวแปรชี้ขาด** — gpt-4o-mini 3% → 47% · deepseek 13% → 50%
- **self-correction (retry) ไม่คุ้ม** — ไม่เพิ่มคะแนน เพิ่มเวลา/เงิน ~3 เท่า
- **จุดอ่อน 2 จุด:** การเลือกคอลัมน์ (strict 47% vs relaxed 76%) · คำถาม novel (12%)

---

## สรุป — ข้อเสนอ

| ทำอะไร | เพราะ |
|---|---|
| ตั้ง default `rag=3, retry=0` | retry ไม่ช่วย ประหยัด 2–3 เท่า |
| เพิ่มตัวอย่างในชุด RAG โดยเฉพาะ **novel** | จุดที่พังชัดสุด และ RAG แก้ได้ |
| ปรับ prompt เรื่องการเลือกคอลัมน์ | ปิดช่องว่าง strict/relaxed 29 จุด |
| เทียบโมเดลที่ 2 ใช้ **provider ตรง** | OpenRouter route ไป provider ถูก ๆ ที่ค้าง |

---

## งานที่ควรทำต่อ (1) — ด้านการวัดผล

| งาน | ทำไม (โยงกับข้อจำกัด) |
|---|---|
| รัน **deepseek 5 รอบ** ผ่าน **DeepSeek API ตรง** | ตอนนี้ 1 รอบ ไม่มี ± + provider ค้าง → ยังตัดสินไม่ได้ |
| เพิ่ม **Gemini** เป็นโมเดลที่ 3 | มีแค่ 2 โมเดล · ต้องมี Google API key |
| **ขยาย golden set** — เพิ่ม `novel` (มีแค่ 8) และรวมทั้งชุด > 30 | ± ของ novel สูง ±11% ตีความยาก |
| ทดลอง **rag_top_k เพิ่ม** (1 / 5 / 8) | ทดลองแค่ 0 vs 3 · ยังไม่รู้จุดอิ่มตัว |
| **human eval** เคส `cols_only` | เช็กว่าคอลัมน์บรรยายต่าง = รับได้จริงมั้ย (relaxed เป็นเพดานที่ใช้ได้จริงหรือเปล่า) |

---

## งานที่ควรทำต่อ (2) — ด้านการพัฒนาระบบ

| งาน | ทำไม |
|---|---|
| **เพิ่มตัวอย่าง novel** ในชุด RAG (metric × การจัดกลุ่ม ที่ยังไม่เคยสอน) | novel 12% คือจุดพังชัดสุด · RAG เป็นตัวแก้ที่ได้ผล |
| ปรับ prompt / เพิ่มกฎ **การเลือกคอลัมน์** (ห้าม `SELECT *`, เลือกเฉพาะที่ถาม) | ปิดช่องว่าง strict 47% vs relaxed 76% (29 จุด = `cols_only`) |
| ตั้ง default **`rag=3, retry=0`** แล้ว **เก็บคำถามจริงจากผู้ใช้** ป้อนกลับเข้า RAG | retry ไม่คุ้ม · คำถามจริงคือแหล่งตัวอย่าง novel ที่ดีที่สุด |
| ทดสอบซ้ำบน **ข้อมูลระดับ production** (หลายภาคเรียน / หลายโรงเรียน) | dev มี 1 ภาคเรียน · 10 โรงเรียน → ตัวเลขอาจเลื่อน |
| ทำ **PDPA / การกันข้อมูลส่วนบุคคล** ก่อนขึ้น production | STS มีชื่อ–เลขบัตร ปชช. · ผู้เรียนเป็นผู้เยาว์ |

---

## ข้อจำกัดของการทดลอง

- ฐานข้อมูล dev มีข้อมูลน้อย (1 ภาคเรียน · 10 โรงเรียน · 6,000 การลงทะเบียน)
  → ตัวเลขอาจไม่ตรงกับ production
- `novel` มีแค่ 8 ข้อ → ส่วนเบี่ยงเบน ±11% สูง ตีความอย่างระวัง
- gpt-4o-mini รัน 5 รอบ (มี ±) · deepseek รัน 1 รอบ (ไม่มี ±) + timeout
- ค่าใช้จ่ายเป็นการประมาณ

---

<!-- _class: lead -->

# เฟส 2 — จาก 1 Query เป็น Agent

**คำติชาอาจารย์:** ระบบเดิม "1 คำถาม 1 SQL" ยังไม่ใช่ agent

→ ออกแบบใหม่เป็น agent loop แบบ ChatGPT/Gemini — โมเดลเลือกเครื่องมือเองจนได้คำตอบ

<span class="muted">เฟส 1 วัดพฤติกรรม pipeline เดิม · เฟส 2 วัดด้วย benchmark ใหม่ที่สมดุล</span>

---

## สถาปัตยกรรม Agent (ADR 0006)

- 1 Turn = โมเดลวน**เลือกเครื่องมือเอง** — ไม่มี script บังคับลำดับ
- Tools: `get_schema` ดูโครงสร้างตาราง · `run_sql` รัน SQL (**อ่านอย่างเดียว**) · `final_answer` ส่งคำตอบ
- `final_answer` เลือกได้ **3 แบบ: result / clarification / refusal** ← pipeline เดิมมีแค่ result
- เซิร์ฟเวอร์ไม่เก็บความจำ — ผู้เรียกส่ง**ประวัติสนทนา**มาเอง · เพดาน **8 steps** กัน loop ไม่รู้จบ

---

## Benchmark ใหม่ที่สมดุล 36 ข้อ (ADR 0007)

ชุดเดิม 30 ข้อกระจุกคำถามนับ/กรอง และไม่มีโจทย์วัดการถามกลับ/ปฏิเสธเลย

| กลุ่ม | n | วัดอะไร |
|---|--:|---|
| SQL: 4 ข้อ × 7 buckets (นับ/กรอง/รวม/สัดส่วน/HAVING/ช่วงเวลา/อันดับ) | 28 | ความแม่น SQL **กระจายสม่ำเสมอ** |
| คำถามกำกวม (เช่น "เด็กเสี่ยงมีเท่าไหร่" ไม่ระบุ tier) | 4 | ต้อง**ถามกลับ** ไม่เดา |
| ขอข้อมูลส่วนบุคคล / สั่งเขียนข้อมูล | 4 | ต้อง**ปฏิเสธ** |

ตัวอย่างคลัง RAG ปรับสมดุล ≤ 8 ตัวอย่าง/bucket → ตอบคำติชา "ตัวอย่างควรกระจายเท่ากัน"

---

## ผล Before / After — SQL ไม่แพ้ แต่ได้ความสามารถใหม่ 8/8

| Metric | Pipeline | Agent | อ่านว่า |
|---|--:|--:|---|
| strict EX (SQL 28 ข้อ) | 57.1% | 53.6% | ต่าง 1 ข้อ = noise ของ single-run |
| grain (จำนวนแถวถูก) | 92.9% | 92.9% | เท่ากันเป๊ะ |
| **ถามกลับเมื่อกำกวม** | 0/4 | **4/4** | pipeline ไม่เคยถามกลับเลย |
| **ปฏิเสธ PII / เขียนข้อมูล** | 0/4 | **4/4** | รวมปิด PII leak |
| latency p50 | 2.3 วิ | 10.5 วิ | ~2.2 steps × ~5 วิ/step |

---

## ผลราย bucket — Agent ชนะ/เสียตรงไหน

| Bucket (4 ข้อ/bucket) | Pipeline เดิม — EX เข้ม | Agent — EX เข้ม | Agent — EX~ ผ่อน | Agent — grain |
|---|--:|--:|--:|--:|
| count_groupby | 75% | **100%** | 100% | 100% |
| count_filter_groupby | 75% | 75% | 75% | 100% |
| aggregation_groupby | 25% | **0%** | 50% | 75% |
| ratio_groupby | 25% | 25% | 25% | 75% |
| having_threshold | 50% | 50% | 75% | 100% |
| time_groupby | 75% | 50% | 100% | 100% |
| ranking | 75% | 75% | 75% | 100% |
| **OVERALL** | **57.1%** | **53.6%** | **71.4%** | **92.9%** |

- **EX เข้ม** = ตรงเฉลยเป๊ะทุกแถวทุกคอลัมน์ · **EX~ ผ่อน** = สาระถูก ยืดหยุ่นคอลัมน์บรรยาย · **grain** = จำนวนแถวตรงเฉลย
- ชนะ: `count_groupby` 100% · เสีย: `aggregation_groupby` (นิยาม ratio/รูปร่างคอลัมน์ต่างจากเฉลย)
- รายข้อที่พลิก: ได้ `paraphrase_02` · เสีย `paraphrase_11` (เฉพาะรูปร่างคอลัมน์ ผ่าน EX~) · เสีย `novel_04` (นิยาม ratio)
- ⚠ n=4 ต่อ bucket แกว่ง ±25pp จากข้อเดียวพลิก — สรุปที่ระดับ OVERALL แน่นกว่า

---

## Eval จับบั๊กที่ unit test มองไม่เห็น

- **Tool spec ไม่เคยถูก bind ให้โมเดล** — mock หลอกว่ามี tools เทสผ่านหมด แต่โมเดลจริงพิมพ์ยาวจนตายด้วย STEP_BUDGET_EXCEEDED (จับจาก smoke run จริง)
- **Turn แรกหลุดไป pipeline เก่า** — route เช็ค `if history:` จึงไม่เข้า agent → แก้เป็นเช็คว่า field ถูกส่งมาหรือไม่ (backward compatible)
- จูนถึง 8/8 ด้วย**ลำดับกติกา**ใน prompt ("จำแนกก่อนเขียน SQL เสมอ" ขึ้นหัว) + คู่เทียบตัวอย่าง — หยุดหลัง 3 รอบเพื่อกัน overfit

---

<!-- _class: lead -->

# เฟส 3 — Latency และประสบการณ์ผู้ใช้

คำถาม: "ทำไม ChatGPT/Claude ดูเร็วกว่า?"

วิธี: **วัดก่อนแก้** → ตั้งเป้าที่ perceived latency และตัดต้นทุนรอบนอก LLM

---

## ทำไม AI อื่น "ดู" เร็ว — แยก 3 ชั้น

| ชั้น | ของเขา | ของเรา (ก่อนแก้) |
|---|---|---|
| **Streaming** | โชว์ทุก token ทันที มี indicator | จ้อง spinner นิ่ง 10 วิ |
| **รูปแบบงาน** | แชท = 1 LLM call | agent loop = 2+ calls + SQL (~5 วิ/step) |
| **Infrastructure** | inference เองบน GPU | ผ่าน API มี network hop (แตะไม่ได้) |

→ เวลาจริงของ LLM steps = ราคาโครงสร้าง (ทดลองแก้ 3 รอบไม่ผ่าน) — งานเฟส 3 จึงอยู่**รอบนอก** และทำให้**เห็น**ความคืบหน้า

---

## แก้ชั้น Streaming — Progress events ผ่าน SSE

- endpoint ใหม่ `POST /api/query/stream` — event ระหว่าง Turn ตัวสุดท้าย = **envelope เดิมทุก field** (legacy ไม่เปลี่ยน)
- `turn_started` → **`sql_planned` (โชว์ SQL จริงทันทีที่เขียนเสร็จ)** → `sql_ok` (N แถว) → `turn_done`
- ทดสอบ live: SQL โผล่ตั้งแต่ **~7.5 วิ** (เดิมรอ 19 วิแบบไม่เห็นอะไรเลย) และเห็นโมเดล**ล้ม 2 รอบแล้วแก้ตัวเอง** — หลักฐานพฤติกรรม agent
- กติกา: progress ไม่เข้า history ไม่เป็นคำตอบ · NestJS/React อ่านตาม INTEGRATION.md

---

## แก้ต้นทุนรอบนอก LLM — วัดจริงด้วย git worktree 2 ตัว

| สิ่งที่แก้ | ก่อน | หลัง |
|---|---|---|
| **Warm engine ตอนสตาร์ท** (ย้ายอ่าน 106 ตาราง + สร้าง schema-RAG ไปเบื้องหลัง) | คำถามแรก **9.3–10.7 วิ** | **3.5–3.7 วิ** (เร็ว ~2.8×) |
| **Re-warm อัตโนมัติ** เมื่อ schema เก่า | ผู้ใช้ที่ถามตรง TTL หมด (ทุก ชม.) จ่ายเอง | สร้างใหม่เองใน **3 วิ** โดยไม่มีคำถามเข้า |
| **Endpoint เสริมไม่ block event loop** | อ่านไฟล์ประวัติเบรกคำถามคนอื่น | 9–24 ms ระหว่างสตรีม = เท่า idle |
| **`prep_ms` ใน envelope** | ประมาณไม่ได้ว่าเวลาไปไหน | เห็นตรง: เตรียมบริบท 0.4–0.9 วิ ที่เหลือ = ราคา LLM |

---

## กราฟแกน "ชื่อ" ไม่ใช่ "รหัส" (ADR 0008)

เดโม่เคยโชว์กราฟแกนเป็น `school_id` ทั้งที่ชื่อโรงเรียนอยู่ในผลเดียวกัน

**กติกาใหม่:** id ไม่มีสิทธิ์ขึ้นแกน — ใช้ชื่อ → หมวด → ข้อความ · ไม่มีคอลัมน์ชื่อ = ตาราง + คำอธิบาย

| ผล (รัน SQL จริง 26 ข้อจากผล eval เทียบโค้ดเก่าจาก git) | จำนวน |
|---|--:|
| สลับแกน id → ชื่อ (เช่น `school_id` → `school_name`) | **12** |
| กราฟ → ตาราง + reason (id เป็นมิติเดียว = not chartable) | **5** |
| คงเดิม (ไม่ over-แก้) | 9 |

→ **EX / ตัวเลขไม่กระทบเลย** — เปลี่ยนเฉพาะการนำเสนอ

---

## สรุปรวม 3 เฟส

| เฟส | ทำอะไร | หลักฐาน |
|---|---|---|
| **1 · Eval** | RAG ชี้ขาด 3% → 47% · retry ไม่คุ้ม | sweep 20 รอบ · $1.6 |
| **2 · Agent** | SQL parity + ถามกลับ/ปฏิเสธ **8/8** | benchmark สมดุล 36 ข้อ |
| **3 · Latency** | เห็นความคืบหน้า + เร็วขึ้น 2.8× + กราฟอ่านออก | วัด before/after ด้วย worktree 2 ตัว |

---

<!-- _class: lead -->
<!-- _paginate: false -->

# ขอบคุณครับ

<span class="muted">รายละเอียดเต็ม: `eval/sts/EVAL_SUMMARY_TH.md` · `eval/sts/COMPARISON.md`</span>
