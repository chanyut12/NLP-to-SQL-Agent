### Dialect: SQLite

This demo datasource is a local SQLite database. Use SQLite syntax only.

- Date parts: `strftime('%Y', date)` or `substr(date, 1, 4)`.
- String concatenation: `a || b`.
- Do not use PostgreSQL functions such as `date_trunc`, `FILTER`, or `::int`.
- `receipt.date` is stored as TEXT in `YYYY-MM-DD` format.
- `receipt.month` is stored as an English full month name (`January` ... `December`).

### Tables

**receipt** — one row per sales receipt.
- `receipt_id` (INTEGER, primary key)
- `date` (TEXT, `YYYY-MM-DD`)
- `month` (TEXT, English month name)
- `customer_name` (TEXT)
- `product_category` (TEXT)
- `items_count` (INTEGER)
- `total_price` (REAL)
- `payment_method` (TEXT: Cash, Credit Card, QR Code, TrueMoney)

**customers** — one row per customer.
- `customer_id` (INTEGER, primary key)
- `customer_name` (TEXT)
- `email` (TEXT) — personal data; never select it
- `phone` (TEXT) — personal data; never select it
- `membership_level` (TEXT: Bronze, Silver, Gold, Platinum)

**products** — one row per product.
- `product_id` (INTEGER, primary key)
- `product_name` (TEXT)
- `category` (TEXT)
- `unit_price` (REAL)
- `stock_quantity` (INTEGER)

### Joins

- `receipt.customer_name = customers.customer_name`
  This demo database has no declared foreign keys; the join is by name.
- `receipt.product_category = products.category`
  This is a category-level match only. Joining `products` directly to `receipt`
  multiplies each receipt by the number of products in that category. Aggregate
  `receipt` first, or avoid this join unless the question asks for product rows.

### Thai keyword hints

**Aggregation**
- "ยอดขาย" / "ยอดรวม" / "รายได้" -> `SUM(total_price)`
- "ค่าเฉลี่ย" / "เฉลี่ย" -> `AVG(...)`
- "จำนวน" / "กี่รายการ" / "นับ" -> `COUNT(...)`
- "มากที่สุด" / "สูงสุด" -> `ORDER BY ... DESC LIMIT`
- "น้อยที่สุด" / "ต่ำสุด" -> `ORDER BY ... ASC LIMIT`

**Grouping**
- "แต่ละเดือน" / "รายเดือน" -> `GROUP BY month`
- "แต่ละปี" / "รายปี" -> `GROUP BY substr(date, 1, 4)`
- "แต่ละหมวด" / "ตามหมวดหมู่" -> `GROUP BY product_category` on `receipt`,
  or `GROUP BY category` on `products`
- "แต่ละวิธีชำระเงิน" -> `GROUP BY payment_method`

**Ratio & average**
- "เฉลี่ยต่อลูกค้า" -> `SUM(total_price) / COUNT(DISTINCT customer_name)`
- "สัดส่วน" / "เปอร์เซ็นต์" -> divide by the overall total from a subquery
- "ที่มี...มากกว่า" -> filter after aggregation with `HAVING`

### Answer style

Return a SQL query that answers the question directly. Prefer explicit column
aliases in Thai-friendly English, and keep the result to the columns the user
asked for. Never select `customers.email` or `customers.phone`.
