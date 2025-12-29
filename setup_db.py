import sqlite3
import pandas as pd
import random
from datetime import datetime, timedelta

# ชื่อไฟล์ Database
db_name = "local_database.db"

# สร้าง Connection
conn = sqlite3.connect(db_name)
cursor = conn.cursor()

# 1. สร้างตาราง receipt (ใบเสร็จ)
cursor.execute('''
CREATE TABLE IF NOT EXISTS receipt (
    receipt_id INTEGER PRIMARY KEY,
    date DATE,
    month TEXT,
    customer_name TEXT,
    product_category TEXT,
    items_count INTEGER,
    total_price REAL,
    payment_method TEXT
)
''')

# 2. สร้างข้อมูลจำลอง (Mock Data)
categories = ['Electronics', 'Clothing', 'Groceries', 'Home & Garden', 'Toys']
payment_methods = ['Cash', 'Credit Card', 'QR Code', 'TrueMoney']
months = ['January', 'February', 'March', 'April', 'May', 'June', 
          'July', 'August', 'September', 'October', 'November', 'December']

data = []
start_date = datetime(2024, 1, 1)

print("กำลังสร้างข้อมูลจำลอง 1,000 รายการ...")

for i in range(1000):
    # สุ่มวันที่
    random_days = random.randint(0, 365)
    current_date = start_date + timedelta(days=random_days)
    date_str = current_date.strftime('%Y-%m-%d')
    month_str = current_date.strftime('%B')
    
    # สุ่มข้อมูลอื่นๆ
    category = random.choice(categories)
    payment = random.choice(payment_methods)
    items = random.randint(1, 10)
    price = round(random.uniform(100, 5000) * items, 2)  # ราคาตามจำนวนชิ้น
    customer = f"Customer_{i}"

    data.append((i, date_str, month_str, customer, category, items, price, payment))

# 3. Insert ข้อมูลลง Database
cursor.executemany('''
INSERT OR REPLACE INTO receipt (receipt_id, date, month, customer_name, product_category, items_count, total_price, payment_method)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
''', data)

conn.commit()
conn.close()

print(f"✅ สร้าง Database '{db_name}' สำเร็จเรียบร้อย!")
