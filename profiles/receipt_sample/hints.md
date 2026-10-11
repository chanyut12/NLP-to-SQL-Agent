### Dialect-Specific Functions:
- Date: MySQL: YEAR(col), MONTH(col) | SQLite: strftime('%Y', col)
- String: MySQL: CONCAT(a, b) | SQLite: a || b

### Thai Keyword Hints:
**Aggregation:**
- "ยอดขาย" / "ยอดรวม" -> SUM(sales_column)
- "ค่าเฉลี่ย" / "เฉลี่ย" -> AVG(...)
- "มากที่สุด" / "สูงสุด" -> ORDER BY ... DESC LIMIT
- "น้อยที่สุด" / "ต่ำสุด" -> ORDER BY ... ASC LIMIT
- "จำนวน" / "กี่รายการ" / "นับ" -> COUNT(...)

**Schema Column Mapping (receipt table):**
- "ลูกค้า" / "คนซื้อ" -> customer_name
- "ยอดขาย" / "ยอดรวม" -> total_price (use SUM for aggregation)
- "จำนวนใบเสร็จ" / "กี่ใบ" -> COUNT(receipt_id)
- "หมวดหมู่" / "ประเภทสินค้า" -> product_category
- "การชำระเงิน" / "จ่ายเงิน" -> payment_method
- "เดือน" -> month column (IMPORTANT: stored as TEXT e.g. 'January', 'February', ..., 'December' — do NOT use date functions on this column, use GROUP BY month directly)
- "ปี" -> year column (stored as INTEGER)

**Ratio & Rate:**
- "อัตราส่วน" / "สัดส่วน" / "เปอร์เซ็นต์" -> SUM(A) / SUM(B) * 100 (aggregate BOTH numerator AND denominator)
- "อัตราการแปลง" / "conversion" -> COUNT(condition) / COUNT(*) * 100
- "เทียบกับ" / "เปรียบเทียบ" -> use ratio or difference between two aggregated values
- "ต่อ" (per, e.g. "ยอดขายต่อคน") -> SUM(value) / COUNT(DISTINCT entity)
- "เติบโต" / "growth" -> (current - previous) / previous * 100

**Time Grouping:**
- "รายเดือน" / "แต่ละเดือน" -> GROUP BY year, month (use actual column names from schema, not date functions unless column is a date type)
- "รายปี" / "แต่ละปี" -> GROUP BY year
- "รายไตรมาส" / "quarter" -> GROUP BY YEAR, QUARTER
- "ล่าสุด" / "ใหม่สุด" -> ORDER BY date DESC LIMIT
- "ระหว่าง" / "ช่วง" -> WHERE date BETWEEN ... AND ...
- "กี่วัน" / "ระยะเวลา" -> DATEDIFF or julianday difference
- "ลูกค้าใหม่" / "เพิ่มขึ้น" -> COUNT customers whose MIN(date/receipt) falls in that period (use subquery or MIN to find first purchase)

**Negation & NULL:**
- "ไม่เคย" / "ยังไม่" -> LEFT JOIN ... WHERE right.id IS NULL or NOT EXISTS
- "ไม่มี" / "ว่างเปล่า" -> IS NULL or = ''

**Advanced:**
- "แต่ละ" / "ของแต่ละ" / "ตาม" -> GROUP BY the entity mentioned
- "ที่มี...มากกว่า" / "เฉพาะที่" -> HAVING aggregate > value (filter AFTER GROUP BY)
