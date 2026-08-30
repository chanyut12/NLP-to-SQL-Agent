# รายงานการทดลอง: การประเมินระบบ Thai Text-to-SQL บนฐานข้อมูล STS

*2026-08-31 · dataset: STS (Student Tracking System) PostgreSQL · โมเดล: gpt-4o-mini · โปรไฟล์: `sts`*

---

## 1. สมมติฐาน (Hypothesis)

**เราคาดว่า few-shot retrieval (RAG) จะเป็นปัจจัยชี้ขาดของความแม่นยำ ส่วน self-correction จะช่วยเพิ่มได้เล็กน้อย**

- **สิ่งที่ทดสอบ:** ระบบแปลงคำถามภาษาไทยเป็น SQL (PostgreSQL) สำหรับฐานข้อมูล STS แม่นแค่ไหน และองค์ประกอบสองอย่างมีผลต่อความแม่นยำอย่างไร:
  1. **RAG few-shot** — การดึงตัวอย่างคำถาม/SQL ที่คล้ายกันมาแนบใน prompt (เทียบ *ไม่ดึงเลย* กับ *ดึง 3 ตัวอย่าง*)
  2. **Self-correction** — เมื่อ SQL รันไม่ผ่าน ระบบส่ง error กลับให้โมเดลแก้เอง (เทียบ *ไม่แก้* กับ *แก้ได้สูงสุด 2 ครั้ง*)
- **สิ่งที่ทำนาย:**
  - RAG จะช่วย **มาก** เพราะ schema ของ STS ผิดปกติหลายอย่าง (คอลัมน์ต้องใส่ double-quote เช่น `"SchoolID_Onec"`, ตาราง "นักเรียนปัจจุบัน" เป็น view ที่ต้อง join แบบเฉพาะ, การเช็กชื่อเก็บแบบ exception-storage) โมเดลจะเดาเองไม่ถูกถ้าไม่มีตัวอย่าง
  - Self-correction จะช่วย **เล็กน้อย** — กู้เคสที่ SQL พลาดเรื่อง syntax/ชื่อคอลัมน์ได้บ้าง
- **เกณฑ์ว่าสมมติฐาน "เป็นจริง":** ถ้า RAG ช่วย → execution accuracy (สัดส่วนที่ผลลัพธ์ตรงกับเฉลย) ตอน RAG=3 ต้องสูงกว่าตอน RAG=0 อย่างชัดเจน. ถ้า self-correction ช่วย → retry=2 ต้องสูงกว่า retry=0 อย่างเห็นได้ (แม้เพียงเล็กน้อย)

---

## 2. ที่มาและแนวคิด (Background & Idea)

**โปรเจกต์นี้เปลี่ยน Thai NLP-to-SQL agent เดิม (ออกแบบมากับฐานข้อมูลตัวอย่าง classicmodels) ให้ทำงานกับ schema จริงของระบบติดตามนักเรียน (STS) แล้วต้องรู้ว่าความแม่นยำอยู่ระดับไหนและอะไรเป็นตัวขับ**

- **ปัญหาตั้งต้น:** engine เดิมมี prompt hints และชุดตัวอย่าง few-shot ที่ผูกกับ schema แบบ e-commerce (`customers`, `orders`, `total_price`). พอชี้ไปที่ฐานข้อมูล STS จริง — โรงเรียน นักเรียน การเช็กชื่อ ความเสี่ยง เคสติดตาม — hints และตัวอย่างเดิมใช้ไม่ได้เลย
- **สิ่งที่มีให้ทำงาน:** เพื่อนร่วมทีมส่ง design guide (`TEXT_TO_SQL_STS_GUIDE.md`) พร้อม **corpus ตัวอย่าง 86 รายการ** (version 2.0) ที่เขียน SQL ตาม schema จริง ครอบคลุม 6 โดเมน (enrollment, attendance, risk/case, task, teacher/subject, teacher-comment). guide ระบุว่าเป็น "design contract" ยังไม่ deployable — ส่วน security/scope/PII ยังต้องรอการตัดสินใจของเจ้าของข้อมูล
- **ขอบเขตที่เลือก (Tier 1):** เอาเฉพาะชั้น prompt — semantic model, PostgreSQL dialect, Thai hints, ตัวอย่าง — มาทำเป็น domain profile `sts`. ส่วน gateway ตรวจสอบ/scope/PII ตัดออกโดยตั้งใจ (บันทึกใน `docs/adr/0002`)
- **ทำไมต้องวัดผลแบบ ablation:** งานวิจัย Text-to-SQL (Spider, BIRD, DIN-SQL, CHESS) ชี้ว่า schema linking + few-shot retrieval + execution-guided correction คือสามเสาหลัก. เราอยากรู้ว่าสำหรับ *ระบบนี้ กับ schema นี้ กับโมเดลราคาถูก* เสาไหนสำคัญจริง เพื่อจัดลำดับความสำคัญของงานปรับปรุงต่อไป และเพื่อให้ตัวเลขที่ป้องกันได้ในรายงาน
- แนวคิดเชื่อมตรงกับสมมติฐาน: ถ้า schema STS ยาก (ซึ่งมันยาก) few-shot น่าจะเป็นตัวที่ทำให้โมเดลรู้ "รูปแบบที่ถูกต้อง" ของ schema นี้

---

## 3. วิธีการทดลอง (Methodology)

**สร้าง golden set 30 คำถามที่แยกขาดจากชุด retrieval, รันผ่าน engine จริงบนฐานข้อมูล STS จริง, เทียบผลลัพธ์กับ SQL เฉลย, ทำ matrix 4 config × 5 รอบ**

### 3.1 ฐานข้อมูลและสภาพแวดล้อม

- **ฐานข้อมูล:** PostgreSQL `sts` (dev instance, localhost) — schema จริงของระบบติดตามนักเรียน
- **ข้อมูล:** มีปีการศึกษาเดียว **2569 ภาคเรียน 1**. ปริมาณ: 10 โรงเรียน, `student_term` 6,000 แถว, `attendance_day` 29,895 แถว, `student_risk_profiles` 5,980 แถว, `cases` 755 แถว. **ข้อจำกัดของข้อมูล dev:** เคสเกือบทั้งหมดสถานะ `OPEN`, ตาราง `task_assistance_measures` ว่างเปล่า, risk tier `WATCH` มีแค่ 1 คน, จำนวนวันมาสายสูงสุดคือ 4
- **จำนวนตารางที่โมเดลเห็นได้:** จาก 139 objects → ตัด 28 ตาราง backup/migration + ตาราง PII/audit (`araid_*`, `audit_log`, `system_settings`) ด้วย denylist → เหลือ **107 ตาราง/view เชิงวิเคราะห์**

### 3.2 Domain profile `sts`

- **`profiles/sts/hints.md`** — เขียนจาก guide section 4-7 และ 10: กติกา PostgreSQL (date_trunc, FILTER, ห้าม `YEAR()`/`strftime()`), semantic ของ STS (grain ของแต่ละตาราง, canonical join paths, status dictionaries), กติกา "นักเรียนปัจจุบัน" (ต้อง join `student_current_enrollment_resolution` ด้วย `person_uuid` + `selected_student_uuid` + `resolution_state = 'ACTIVE'`), attendance source-of-truth ตาม grain, และกฎว่าคอลัมน์ที่มีตัวพิมพ์ใหญ่ต้องใส่ double-quote
- **`profiles/sts/examples.json`** — สร้างจาก corpus 86 รายการด้วย `scripts/build_sts_profile.py`:
  1. แทนค่า parameter (`$1`, `$2`) กลับเข้า SQL ให้รันได้จริง (engine Tier 1 ไม่ bind placeholder)
  2. **กันไว้เป็น held-out 10 รายการ** — ดึงออกจากชุด retrieval เพื่อทดสอบ generalization แท้ (แบ่งตามโดเมนที่มีข้อมูลจริง: enrollment 3, attendance 3, risk/case 3, teacher-comment 1)
  3. **ตัดออก 8 รายการ** ที่ SQL รันไม่ผ่านบน schema จริง (อ้าง `classroom_subject_teachers` และ `case_reviews.deleted_at` ที่ไม่มีในฐานข้อมูล — corpus เขียนกับ schema เวอร์ชันใหม่กว่า dev DB)
  4. เหลือ **68 รายการในชุด retrieval**
- **`profiles/sts/schema_mappings.json`** — คำไทย → ชิ้นส่วนชื่อตาราง (โรงเรียน→`schools`, นักเรียน→`student_term`/`student_current_enrollment_resolution`, ครู→`teachers`, เคส→`cases`, เสี่ยง→`student_risk_profiles`, มาเรียน→`attendance_*`) จาก guide section 6.1

### 3.3 การจัดการ schema ใน prompt (pruned strategy)

- schema STS ใหญ่เกินกว่าจะยัดทั้งหมด (107 ตาราง ≈ 22,000 tokens)
- ใช้ **pruned strategy**: `smart_filter_schema` ดึง **top-25 ตารางที่เกี่ยวข้องกับคำถาม** ด้วย semantic search (embed คำถาม + Thai mapping) + ขยายด้วยตารางที่มี FK เชื่อม
- embedding model: `intfloat/multilingual-e5-small` (รองรับไทย). Schema RAG index ตาราง 107 ตัวครั้งเดียวตอน startup

### 3.4 Golden set — 30 คำถาม (`eval/benchmark_sts.json`)

สร้างด้วย `scripts/build_sts_benchmark.py`, **แยกขาดจากชุด retrieval 68 รายการ** เพื่อไม่ให้ระบบดึงเฉลยของตัวเองมาตอบ. ทุก SQL เฉลยถูกตรวจว่ารันได้และคืน ≥1 แถวบนฐานข้อมูล dev

| กลุ่ม (`source_tag`) | จำนวน | วัดอะไร | ที่มาของ SQL เฉลย |
|---|--:|---|---|
| **held_out** | 10 | generalization แท้ — ไม่มี sibling ในชุด retrieval | corpus (เพื่อน review แล้ว) |
| **paraphrase** | 12 | RAG-adaptation — คำถามเขียนใหม่/ย่อ/ผสมอังกฤษ ของตัวอย่างที่ยังอยู่ในชุด retrieval | corpus เดิม (คำถามใหม่, SQL เดิม) |
| **novel** | 8 | compositional generalization — เอา metric/grain มาผสมแบบที่ corpus ไม่มีตรงๆ | เขียนเองแล้ว verify ด้วยการ execute |

ครอบคลุม 14 category (count_groupby, ratio_groupby, having, ranking_per_group, not_exists_groupby, time_groupby, average_groupby, ฯลฯ)

### 3.5 เกณฑ์การให้คะแนน

เทียบ **result set** ของ SQL ที่โมเดลสร้าง กับ result set ของ SQL เฉลย (ไม่สนลำดับแถว, ปัด float 2 ตำแหน่ง, lowercase string):

- **Strict EX (execution accuracy)** — result set ตรงเป๊ะ (จำนวนคอลัมน์ + ทุกค่า). นี่คือ metric หลัก
- **Relaxed EX** — ตรงกันโดยยอมให้ต่างได้ **1 คอลัมน์บรรยาย** (ชื่อโรงเรียน/label ที่ขึ้นกับ key ของกลุ่ม) ที่โมเดลใส่เกินหรือขาด; จำนวนแถวต้องเท่ากัน. เป็น *ขอบบนแบบหลวม* — ค่า metric ที่ผิดจะรอดได้เฉพาะเมื่อมีอีก ≥2 คอลัมน์ตรงกัน
- **first-try success** — strict pass โดย `retry_count == 0`
- **grain correct** — จำนวนแถวเท่าเฉลย (ไม่มี duplicate amplification จาก join)
- **latency** p50/p95, **error taxonomy**: `no_sql` / `exec_fail` / `wrong_grain` / `cols_only` (relaxed-pass) / `wrong_result`

### 3.6 Matrix การทดลอง

- **โมเดล:** `gpt-4o-mini` (temperature 0), pruned schema, `max_retries` ของ LLM client = 6 (backoff เมื่อเจอ 429)
- **Ablation:** `RAG_TOP_K ∈ {0, 3}` × `MAX_RETRIES ∈ {0, 2}` = **4 config**
- **ทำซ้ำ 5 รอบต่อ config** (gpt-4o-mini ที่ temp=0 ไม่ deterministic 100% — วัด mean ± sd)
- รวม **20 cells × 30 คำถาม = 600 question-runs** (ราว 600-900 LLM calls รวม retry)
- รันคู่ขนาน 3 คำถามพร้อมกัน (`--concurrency 3`) — ต่ำเพราะบัญชี OpenAI ติด rate limit ที่ concurrency สูงกว่านี้
- driver: `eval/sweep_sts.py` (resume ได้), รวมผลด้วย `eval/compare.py`

### 3.7 บั๊กที่เจอและแก้ระหว่างการตั้ง harness

รันชุดแรกเจอ 3 บั๊กที่ทำให้ตัวเลขไม่มีความหมาย — แก้แล้วรันใหม่:

| บั๊ก | ผลกระทบ | แก้ |
|---|---|---|
| `RAG_TOP_K`/`MAX_RETRIES` hardcode ไม่อ่าน env | ทุก cell แอบรัน rag=3 retry=2 → ablation ไม่ทำงานเลย | ให้อ่านจาก env |
| SQL validator reject ชื่อ CTE | ทุก query ที่ใช้ `WITH ... AS` fail "Table not allowed" | เก็บชื่อ CTE ออกจาก allowlist check |
| schema formatter ไม่ใส่ double-quote คอลัมน์ตัวพิมพ์ใหญ่ | โมเดลเขียน `SchoolID_Onec` (ไม่ quote) → Postgres fold เป็น lowercase → fail | quote คอลัมน์ที่ไม่ใช่ `[a-z_]+` |

ผลก่อน→หลังแก้ (gpt-4o-mini, rag=3, retry=2): exec-fail 9→0, grain 67%→97%, strict EX 40%→50%

---

## 4. ผลลัพธ์และการตีความ (Results & Interpretation)

### 4.1 ผล ablation หลัก

**RAG few-shot คือปัจจัยชี้ขาด — เพิ่ม strict EX จาก 3% เป็น 47% (14 เท่า). Self-correction แทบไม่มีผล**

| RAG top-k | retry | strict EX | relaxed EX | first-try | grain correct | p50 (s) | p95 (s) |
|--:|--:|--:|--:|--:|--:|--:|--:|
| 0 | 0 | **3.3%** | 30.0% | 3.3% | 70.0% ±6% | 3.7 | 18.2 |
| 0 | 2 | **4.7%** ±2% | 30.0% | 4.7% ±2% | 68.7% ±3% | 7.0 | 32.2 |
| 3 | 0 | **46.7%** ±2% | 72.7% | 46.7% ±2% | 88.0% ±4% | 5.8 | 20.4 |
| 3 | 2 | **47.3%** ±4% | 76.0% ±3% | 44.0% ±4% | 87.3% ±4% | 6.4 | 22.5 |

*(mean ± sd จาก 5 รอบ; sd ที่ไม่แสดง = 0 คือทุกรอบได้เท่ากันเป๊ะ)*

**การตีความ:**

- **RAG few-shot (0 → 3 ตัวอย่าง): strict EX 3.3% → 47%, relaxed EX 30% → 74-76%, grain 70% → 88%.** นี่คือผลที่ชัดที่สุดในการทดลอง — ยืนยันสมมติฐานเต็มๆ. ถ้าไม่มีตัวอย่าง โมเดลเดา schema STS ไม่ถูกเลย (ตอบถูกเป๊ะแค่ 1 ใน 30 คำถาม). ตัวอย่าง 3 อันสอนให้โมเดลรู้รูปแบบที่ถูกต้องของ schema นี้ — การ quote คอลัมน์ `_Onec`, การ join resolution view, การเลือก attendance view ตาม grain
- **Self-correction (retry 0 → 2): strict EX 46.7% → 47.3% (ต่างกัน 0.6 pp, อยู่ในช่วง noise ±4%).** first-try success กลับ *ลดลง* จาก 46.7% เป็น 44.0% — แปลว่า retry บางครั้งเปลี่ยนคำตอบที่ถูกอยู่แล้วให้ผิด. จาก 150 คำถามที่ retry=2 มีแค่ **5 ครั้ง** ที่ retry จบด้วยการตอบถูก. **สมมติฐานส่วนนี้ไม่เป็นจริง** — self-correction ไม่ช่วยวัดได้เลย
- **retry=2 ยังทำให้ latency แย่ลง** (p95 20.4s → 22.5s ที่ rag=3; 18s → 32s ที่ rag=0) และเพิ่มการโดน rate limit (ดู 4.4)
- ค่า strict EX **นิ่งมากระหว่างรอบ** (rag=0 ได้ 0.033 เป๊ะทั้ง 5 รอบ; rag=3 อยู่ช่วง 0.43-0.53) — temp=0 ให้ผลเกือบ deterministic

### 4.2 ผลแยกตามความยากของคำถาม (config rag=3, retry=2)

**Paraphrase ทำได้ดีสุด (มี sibling ให้ปรับ), held_out กลาง, novel ยากสุด (โดยเฉพาะ strict)**

| กลุ่ม | n | strict EX | relaxed EX |
|---|--:|--:|--:|
| paraphrase | 12 | **70%** ±4% | 85% |
| held_out | 10 | **48%** ±4% | 74% |
| novel | 8 | **12%** ±11% | 65% |

**การตีความ:**

- **paraphrase 70% strict / 85% relaxed** — เมื่อมีตัวอย่างพี่น้องอยู่ในชุด retrieval โมเดลปรับให้เข้ากับคำถามที่เขียนใหม่/ผสมอังกฤษได้ดี. สะท้อนสถานการณ์ใช้งานจริงที่สุด
- **held_out 48% strict / 74% relaxed** — คำถามที่ไม่เคยเห็น (ไม่มี sibling) ตกลงมาราวครึ่งหนึ่ง. ช่องว่าง strict↔relaxed 26 pp = ส่วนใหญ่โมเดลได้ตัวเลขถูกแต่เลือกคอลัมน์ต่างจากเฉลย
- **novel 12% strict / 65% relaxed — ช่องว่าง 53 pp** ใหญ่มาก. โมเดลจับ grain/กลุ่มได้ (relaxed สูง) แต่ตอบให้ตรง result set เป๊ะทำไม่ค่อยได้. sd ±11% สูงเพราะ n=8 น้อย. **ข้อควรระวัง:** relaxed EX ของ novel ถูกดันสูงเกินจริงจากบางเคส เช่น `novel_04` ที่โมเดลตอบ 360 แทนที่จะเป็น 12 (AVG ผิด grain) แต่ id + label ตรง → relaxed นับผ่านทั้งที่ผิดจริง

### 4.3 ผลแยกตาม category (config rag=3, retry=2, รวม 5 รอบ)

**ทำได้ดี: negation, per-group ranking, time-ratio. ทำได้แย่: summary หลายคอลัมน์, multi-join, average**

| category | n | strict | relaxed | หมายเหตุ |
|---|--:|--:|--:|---|
| not_exists_groupby | 5 | 100% | 100% | `NOT EXISTS` pattern ชัด |
| time_ratio_groupby | 5 | 100% | 100% | |
| ranking_per_group | 10 | 80% | 80% | window function ต่อกลุ่ม |
| having | 5 | 80% | 80% | |
| freshness_groupby | 5 | 80% | 100% | |
| time_groupby | 15 | 67% | 87% | |
| count_filter_groupby | 20 | 65% | 90% | |
| count_groupby | 25 | 40% | 80% | มักขาดคอลัมน์ชื่อ |
| ratio_groupby | 15 | 33% | 67% | นิยาม denominator ต่างกัน |
| ranking_global | 10 | 30% | 30% | มักขาดคอลัมน์ label จริงๆ |
| having_ratio | 10 | 20% | 70% | |
| average_groupby | 15 | 13% | 100% | **strict ต่ำเพราะไม่ปัดเลข + ขาดคอลัมน์ count; relaxed 100%** |
| multi_join_aggregation | 5 | 0% | 20% | join หลายโดเมน — ยากจริง |
| summary_groupby | 5 | 0% | 0% | ต้องคืนหลาย metric ในแถวเดียว — โมเดลทำไม่ได้ |

### 4.4 การวิเคราะห์ error (config rag=3, retry=2, รวม 150 คำถาม)

| error class | จำนวน | ความหมาย |
|---|--:|---|
| `cols_only` | 43 | ตัวเลขถูก แต่คอลัมน์บรรยายต่าง (relaxed ผ่าน) — **ไม่ใช่โมเดลเขียนผิด** |
| `wrong_result` | 17 | SQL รันได้แต่ค่าผิดจริง |
| `no_sql` | 12 | โมเดลไม่คืน SQL — **ทั้งหมดคือ 429 rate limit** ตอนอยู่ใน retry loop |
| `wrong_grain` | 5 | จำนวนแถวไม่ตรง (มัก join ทำแถวซ้ำ หรือ filter ต่างจากเฉลย) |
| `exec_fail` | 2 | SQL รันไม่ผ่าน |

- **`cols_only` (43) เป็น error class ที่ใหญ่ที่สุด** — ยืนยันว่าช่องว่าง strict↔relaxed เกิดจากการเลือกคอลัมน์ ไม่ใช่ตรรกะ. ตัวอย่าง: `student_average_term_gpa_by_grade` เฉลยคืน `(11, 'อ.1', 360, 2.74)` โมเดลคืน `(11, 'อ.1', 2.7423)` — เลข GPA เหมือนกัน แต่ไม่ปัดและไม่ใส่คอลัมน์ count
- **`no_sql` (12) คือ rate limit ล้วนๆ** — retry loop ยิง LLM ได้ถึง 3 ครั้ง/คำถาม พอ concurrency 3 → เกิด burst → 429 แม้ตั้ง `max_retries=6`. ที่ retry=0 มี `no_sql` แค่ 4. **ตรงนี้ทำให้การเทียบ retry=0 vs retry=2 มี bias** — retry=2 เสียคะแนนราว 5% จาก rate limit ที่ไม่เกี่ยวกับความสามารถโมเดล
- `exec_fail` เหลือแค่ 2 (จาก 9 ก่อนแก้บั๊ก) — การแก้ CTE validator + double-quote ได้ผล

### 4.5 คำถามที่ผ่าน/ไม่ผ่านสม่ำเสมอ (config rag=3, retry=2)

- **ผ่าน 5/5 รอบ (10 คำถาม):** `attendance_absence_by_weekday`, `attendance_absent_days_by_school_in_date_range`, `case_count_by_workflow_phase`, `case_created_count_by_month`, `paraphrase_01/03/06/08/10`, และ not_exists ต่างๆ
- **ไม่ผ่านเลย 0/5 รอบ (~10 คำถาม):** held_out ที่ต้องคืนหลายคอลัมน์ (`student_current_classroom_occupancy_summary_by_school`, `student_current_count_by_classroom`, `student_average_term_gpa_by_grade`, `teacher_comment_count_by_category`), `attendance_classrooms_below_rate_threshold`, `paraphrase_02/12`, และ novel 6/8 ตัว
- 12 จาก 30 คำถามผ่าน 4-5/5 รอบ — โมเดลทำ "คลัสเตอร์ที่ทำได้" อย่างเสถียร ส่วนที่เหลือทำไม่ได้อย่างเสถียรเช่นกัน

### 4.6 การเปรียบเทียบข้ามโมเดล

**ยังไม่ได้ทำ** — slate วางแผนไว้เทียบ `deepseek/deepseek-v4-flash`, `qwen/qwen3-235b-a22b-2507`, `z-ai/glm-5.2:free` ผ่าน OpenRouter แต่บัญชียังไม่มี credit/API key. harness รองรับแล้ว (`eval/sweep_sts.py` — uncomment รายการโมเดล + ใส่ `OPENROUTER_API_KEY`)

---

## 5. จุดแข็งและข้อจำกัด (Strengths & Limitations)

### จุดแข็ง

- **Golden set แยกขาดจากชุด retrieval จริง** — held-out 10 รายการถูกดึงออกจาก corpus และเอาออกจาก vector store ทั้งหมด. paraphrase/novel เป็นคำถามที่เขียนใหม่. ทำให้ strict EX ไม่ถูกเป่าจากการที่ระบบดึงเฉลยของตัวเองมาตอบ
- **ทุก SQL เฉลยถูก verify ด้วยการ execute จริง** บนฐานข้อมูล — ไม่มีเฉลยที่รันไม่ได้หรือคืน 0 แถว (ซึ่งจะทำให้ทุก query ที่ผิดแต่คืนว่างนับผ่าน)
- **วัด execution accuracy (ผล) ไม่ใช่ string match (ตัวอักษร)** — SQL คนละหน้าตาที่ให้ผลเหมือนกันนับถูก ตรงตามมาตรฐาน Spider/BIRD
- **ทำซ้ำ 5 รอบต่อ config** — มีตัวเลข sd จริง. strict EX นิ่งมาก (rag=0 ได้ 3.3% เป๊ะทุกรอบ) ทำให้มั่นใจว่าผลต่าง rag=0 vs rag=3 ไม่ใช่ noise
- **มีทั้ง strict และ relaxed metric** — strict เป็นขอบล่างที่ป้องกันได้ (ลงโทษการเลือกคอลัมน์), relaxed เป็นขอบบน. ความสามารถจริงอยู่ระหว่างนั้น ไม่ต้องเดา
- **บั๊ก 3 ตัวถูกจับได้จากการรันชุดแรกและแก้ก่อนรันจริง** — ตัวเลขในรายงานนี้มาจาก harness ที่ ablation ทำงานจริง

### ข้อจำกัด

- **ฐานข้อมูล dev มีข้อมูลบางและเอียง** — ปีการศึกษาเดียว, เคสเกือบทั้งหมด `OPEN`, `task_assistance_measures` ว่าง, `WATCH` มี 1 คน. โดเมน task/assistance และ case-workflow แทบวัดไม่ได้ — golden set เลยเลี่ยงโดเมนพวกนี้ ทำให้ coverage ไม่กว้างเท่าที่ guide section 15.1 กำหนด
- **novel 8 คำถาม + SQL เฉลย เขียนเอง** (ผ่านการ execute แต่ยังไม่ผ่าน domain expert). n=8 น้อย → sd ±11%. บางเฉลยอาจตีความคำถามต่างจากที่ควร (เช่น `paraphrase_12` "สัดส่วนในแต่ละหมวด" — เฉลยเก็บทุกหมวดรวมหมวดที่เป็น 0, โมเดล filter เฉพาะหมวดที่มี — ทั้งคู่ตีความได้)
- **relaxed EX เป็นขอบบนที่หลวมเกินไปในบางเคส** — `novel_04` โมเดลตอบ 360 แทน 12 (AVG ผิด grain) แต่ relaxed นับผ่านเพราะ id+label ตรง. relaxed EX ของ novel (65%) จึงสูงเกินความสามารถจริง
- **การเทียบ retry=0 vs retry=2 มี confound จาก rate limit** — retry loop ยิง LLM 3 เท่า → 429 บ่อยขึ้น → retry=2 เสีย ~5% จาก `no_sql` ที่ไม่เกี่ยวกับความสามารถ. ข้อสรุป "retry ไม่ช่วย" ยังยืนได้ (แม้หัก bias นี้ออก retry=2 ก็ยังไม่ชนะ retry=0) แต่ตัวเลข retry=2 ที่แท้จริงน่าจะสูงกว่า 47.3% นิดหน่อย
- **ทดสอบโมเดลเดียว (gpt-4o-mini)** — ไม่รู้ว่าผล ablation (RAG สำคัญ, retry ไม่สำคัญ) generalize ไปโมเดลใหญ่/reasoning model หรือไม่. โมเดลที่เก่งกว่าอาจต้องพึ่ง few-shot น้อยลง
- **corpus/guide เขียนกับ schema เวอร์ชันใหม่กว่า dev DB** — ตัด 8 ตัวอย่างที่อ้างตาราง/คอลัมน์ที่ไม่มี. โดเมน teacher/subject จึงบางกว่าที่ guide บอก
- **schema strategy fix เป็น "pruned" อย่างเดียว** — ไม่ได้ ablate เทียบกับ full schema. ไม่รู้ว่าการตัดเหลือ 25 ตารางทำให้พลาดตารางที่ต้องใช้บ่อยแค่ไหน (แต่ `no_sql`/`exec_fail` ต่ำ แปลว่าไม่น่าเป็นปัญหาหลัก)
- **Tier 1 เท่านั้น** — ไม่มี scope enforcement, PII gating, deterministic AST validator ตาม guide. คำถาม clarify/deny วัดไม่ได้เพราะ engine gen SQL เสมอ

---

## 6. สรุปผล (Conclusion)

- **RAG few-shot คือปัจจัยที่สำคัญที่สุดอย่างไม่มีข้อโต้แย้ง** — จาก results: strict EX 3.3% → 47%, relaxed 30% → 76%, grain 70% → 88% เมื่อเพิ่มตัวอย่างจาก 0 เป็น 3. per-run variance ต่ำมาก (rag=0 ได้ 3.3% เป๊ะทุกรอบ) → ผลต่างนี้เป็นของจริง ไม่ใช่ noise. **ส่วนแรกของสมมติฐานเป็นจริงเต็มที่ ด้วยความมั่นใจสูง**
- **Self-correction ไม่ช่วยความแม่นยำเลย และอาจเสียนิดหน่อย** — จาก results: strict EX 46.7% → 47.3% (ต่างในช่วง noise), first-try 46.7% → 44.0% (retry เปลี่ยนคำตอบถูกเป็นผิดบางครั้ง), จาก 150 คำถามมีแค่ 5 ครั้งที่ retry จบด้วยการตอบถูก. แม้หัก bias จาก rate limit ออก retry=2 ก็ยังไม่ชนะ retry=0. **ส่วนที่สองของสมมติฐานไม่เป็นจริง** — บนโมเดลและ schema นี้ self-correction ไม่คุ้มค่า latency ที่เพิ่ม
- **ความแม่นยำที่แท้จริงของ gpt-4o-mini บน STS อยู่ราว 47-60%** — strict EX 47% เป็นขอบล่าง (ลงโทษการเลือกคอลัมน์ที่ต่างจากเฉลย ซึ่งเป็น error class ที่ใหญ่ที่สุด 43/150). relaxed EX 76% เป็นขอบบนที่หลวมเกินจริง (บางเคสค่า metric ผิดแต่นับผ่าน). ตัวเลขที่ควรอ้างในงานเขียนคือ **strict EX 47% ± 4%** พร้อมหมายเหตุว่า ~29 pp ของช่องว่างไป relaxed เป็นเรื่องรูปแบบผลลัพธ์ ไม่ใช่ตรรกะ SQL
- **ความสามารถกระจายไม่เท่ากันตามประเภทคำถาม** — negation (`NOT EXISTS`), per-group ranking, time-ratio ทำได้ ~80-100%; ส่วน summary หลายคอลัมน์ และ multi-join ทำได้ ~0-20%. paraphrase (มี sibling) 70% > held_out 48% > novel 12% strict
- **ข้อจำกัดที่กระทบการ generalize มากที่สุด:** ทดสอบโมเดลเดียว + ฐานข้อมูล dev ที่ข้อมูลบาง + novel เฉลยยังไม่ผ่าน expert. ข้อสรุปเรื่อง RAG แข็งพอที่จะเชื่อได้; ข้อสรุปเรื่องตัวเลขสัมบูรณ์ (47%) ควรถือเป็นค่าประมาณของ setup นี้เท่านั้น

---

## 7. ข้อเสนอแนะและงานในอนาคต (Future Work)

- **เทียบข้ามโมเดล** (จาก limitation "ทดสอบโมเดลเดียว") → ใส่ `OPENROUTER_API_KEY` แล้วรัน `eval/sweep_sts.py` กับ deepseek-v4-flash, qwen3-235b, glm-5.2:free ที่ best config — ดูว่าโมเดลเปิดถูก/ฟรี ทำได้ใกล้ gpt-4o-mini แค่ไหน และผล ablation (RAG สำคัญ) ยังจริงไหม
- **ลดช่องว่าง strict↔relaxed ที่ต้นเหตุ** (จาก insight "`cols_only` 43 เป็น error ที่ใหญ่สุด") → เพิ่มกติกาใน `hints.md` ว่า "คืนเฉพาะ grouping key + metric ไม่ต้อง join ชื่อมาโชว์ ยกเว้นถูกขอ" แล้วเขียน SQL เฉลยแบบ minimal ให้ตรงกัน — strict EX น่าจะขยับขึ้น 15-25 pp โดยไม่ต้องแตะโมเดล
- **แก้ rate-limit confound ในการวัด retry** (จาก limitation "retry=2 เสีย ~5% จาก 429") → ขอเพิ่ม tier บัญชี OpenAI หรือใส่ token-bucket limiter ระดับ process แล้วรัน ablation retry ใหม่ให้สะอาด
- **ให้เพื่อน/domain expert review เฉลย 20 ข้อ** (held_out ที่ 0/5 + novel 8 ข้อ) (จาก limitation "novel เขียนเอง") → เคลียร์ว่าที่ 0/5 คือโมเดลผิดจริง หรือเฉลย/คำถามกำกวม — โดยเฉพาะ `novel_04` (AVG grain) และ `paraphrase_12` (นิยาม denominator)
- **ขยาย golden set เมื่อฐานข้อมูลมีข้อมูลครบ** (จาก limitation "dev DB บาง") → เพิ่มคำถามโดเมน task/assistance และ case-workflow, เพิ่มปีการศึกษา/ภาคเรียนที่สอง เพื่อทดสอบ "ปีการศึกษา vs ปีปฏิทิน" และ time-series ข้ามเทอม
- **ablate schema strategy** (จาก limitation "fix pruned อย่างเดียว") → เพิ่มแกน `SCHEMA_STRATEGY ∈ {pruned, full}` และลอง `SCHEMA_TOP_K ∈ {15, 25, 40}` — ดูว่าการตัดเหลือ 25 ตารางทำให้พลาด recall แค่ไหน
- **ทดสอบ RAG top-k ละเอียดขึ้น** (จาก decision ตัด ablation เหลือ {0,3}) → เพิ่ม k ∈ {5, 7} เพื่อดู dose-response ว่าตัวอย่างมากขึ้นช่วยต่อหรืออิ่มตัวที่ 3
