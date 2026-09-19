# ผลกระทบของกติกาแกน (ADR 0008) ต่อผล eval — รายงานตาม ticket #26

**วิธีวัด (โปร่งใสเต็มรูปแบบ):** นำ `pred_sql` ของรอบทางการล่าสุด (`after_agent.json`, 36 ข้อ ที่
executable จริง 26 ข้อ) ไปรันกับ Postgres จริง (`sts` @ localhost:5432) แล้วป้อน DataFrame ที่ได้เข้า
recommender สองตัว: **โค้ดเก่าจริง** (โหลดจาก git HEAD) เทียบกับ **โค้ดใหม่** (กติกา ADR 0008) —
ไม่ใช้การจำลองพฤติกรรม ไม่ใช้ LLM

## ตัวเลขรวม

| กลุ่ม | จำนวน |
|---|--:|
| รัน SQL สำเร็จ (จาก 36 ข้อของ benchmark, ที่เหลือเป็นคำถามถามกลับ/ปฏิเสธไม่มี SQL) | 26 |
| **เปลี่ยนการนำเสนอ** รวม | **17** |
| ↳ สลับแกน id → คอลัมน์ชื่อ (chart type คงเดิม) | 12 |
| ↳ กราฟ → ตาราง (id เป็นมิติเดียวของผล = not chartable) | 5 |
| ตอนนี้แสดงเป็นตาราง (รวมเคสที่เคยเป็นตารางอยู่แล้ว) | 7 |
| คงเดิมทุกอย่าง | 9 |

## กลุ่มที่ 1 — สลับแกน id → ชื่อ (12 ข้อ: จุดหมายหลักของ ADR 0008)

เดิมกราฟเหล่านี้มีแกนเป็นรหัส (`school_id`, `classroom_id`, `grade_level_id`) ทั้งที่คอลัมน์ชื่อ
อยู่ในผลเดียวกัน — เป็นสิ่งที่อาจารย์วิจารณ์โดยตรง:

| ข้อ | เดิม | ใหม่ |
|---|---|---|
| attendance_classrooms_below_rate_threshold | pie / classroom_id | pie / room_name |
| attendance_late_days_by_school_in_date_range | bar / school_id | bar / school_name |
| student_current_classroom_occupancy_summary_by_school | bar / school_id | bar / school_name |
| student_current_count_by_grade | bar / grade_level_id | bar / grade_label |
| paraphrase_03 | bar / school_id | bar / school_name |
| paraphrase_04 | bar / classroom_id | bar / room_name |
| paraphrase_05 | bar / school_id | bar / school_name |
| paraphrase_08 | bar / classroom_id | bar / room_name |
| novel_02 | pie / school_id | pie / school_name |
| novel_04 | bar / grade_level_id | bar / grade_label |
| novel_05 | pie / school_id | pie / school_name |
| novel_06 | bar / school_id | bar / school_name |

## กลุ่มที่ 2 — กราฟ → ตาราง (5 ข้อ: "not chartable" ตาม ADR 0008 ข้อ 3)

ผลของข้อเหล่านี้มี id เป็นมิติแบ่งเดียว (ไม่มี name/category/text เลย) เดิมจึงวาดกราฟแกนรหัส
ซึ่งอ่านไม่ออก — ตอนนี้แสดงตารางพร้อม reason ว่า "ไม่มีคอลัมน์ชื่อสำหรับเป็นแกน":

| ข้อ | เดิม | ใหม่ |
|---|---|---|
| case_without_review_count_by_school | line / school_id | table |
| paraphrase_06 | bar / school_id | table |
| paraphrase_09 | bar / school_id | table |
| novel_08 | bar / grade_level_id | table |
| novel_09 | bar / school_id | table |

## ข้อสังเกตสำหรับผู้ประเมิน

- การเปลี่ยนทั้ง 17 ข้อ**ไม่กระทบความถูกต้องของ SQL/ตัวเลขเลย** — เปลี่ยนเฉพาะวิธีนำเสนอ
  (คอลัมน์แกน หรือ กราฟ→ตาราง) ตัวเลข EX/EX~/grain ใน before/after ยังอ่านได้เหมือนเดิม
- กราฟ 5 ข้อที่หายไปเป็น**การถอยแบบตั้งใจสู่ความจริง**: เดิมระบบ "โชว์กราฟได้" โดยแลกกับแกน
  รหัสไร้ความหมาย — ตาม ADR 0008 ผลที่ไม่มีคอลัมน์ชื่อถือว่า not chartable ผู้ใช้เห็นตาราง
  ครบข้อมูล + คำอธิบาย และ agent สามารถถูกถามต่อให้ JOIN ชื่อมาได้
- 9 ข้อที่คงเดิมยืนยันว่ากติกาไม่ over-แก้ — กราฟที่ถูกต้องอยู่แล้ว (แกนเป็นชื่อ/หมวด/เวลา)
  ไม่ถูกแตะ
