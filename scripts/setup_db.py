"""
Setup Script: สร้าง local_database.db สำหรับทดสอบระบบ

Usage:
    python scripts/setup_db.py

Output:
    local_database.db - SQLite database with sample data
"""

import sqlite3
import random
from datetime import datetime, timedelta
import os

# ชื่อไฟล์ Database
DB_NAME = "local_database.db"

def create_database():
    """สร้าง Database พร้อม Sample Data"""
    
    # ลบไฟล์เก่าถ้ามี
    if os.path.exists(DB_NAME):
        os.remove(DB_NAME)
        print(f"🗑️  ลบ database เก่า: {DB_NAME}")
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # ============================================
    # 1. สร้างตาราง receipt (ใบเสร็จ) - Main Table
    # ============================================
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
    print("📋 สร้างตาราง receipt สำเร็จ")
    
    # ============================================
    # 2. สร้างตาราง products (สินค้า) - Optional
    # ============================================
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS products (
        product_id INTEGER PRIMARY KEY,
        product_name TEXT,
        category TEXT,
        unit_price REAL,
        stock_quantity INTEGER
    )
    ''')
    print("📋 สร้างตาราง products สำเร็จ")
    
    # ============================================
    # 3. สร้างตาราง customers (ลูกค้า) - Optional
    # ============================================
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS customers (
        customer_id INTEGER PRIMARY KEY,
        customer_name TEXT,
        email TEXT,
        phone TEXT,
        membership_level TEXT
    )
    ''')
    print("📋 สร้างตาราง customers สำเร็จ")
    
    # ============================================
    # สร้างข้อมูลจำลอง (Mock Data)
    # ============================================
    
    # ข้อมูลพื้นฐาน
    categories = ['Electronics', 'Clothing', 'Groceries', 'Home & Garden', 'Toys']
    payment_methods = ['Cash', 'Credit Card', 'QR Code', 'TrueMoney']
    membership_levels = ['Bronze', 'Silver', 'Gold', 'Platinum']
    
    product_names = {
        'Electronics': ['iPhone', 'Samsung TV', 'MacBook', 'iPad', 'AirPods'],
        'Clothing': ['T-Shirt', 'Jeans', 'Jacket', 'Dress', 'Sneakers'],
        'Groceries': ['Rice', 'Milk', 'Eggs', 'Bread', 'Fruit'],
        'Home & Garden': ['Chair', 'Table', 'Lamp', 'Plant', 'Pillow'],
        'Toys': ['Lego', 'Doll', 'Car Toy', 'Puzzle', 'Board Game']
    }
    
    start_date = datetime(2024, 1, 1)
    
    # ----- Insert Products -----
    print("📦 กำลังสร้างข้อมูลสินค้า...")
    product_id = 1
    for category, names in product_names.items():
        for name in names:
            price = round(random.uniform(50, 5000), 2)
            stock = random.randint(10, 500)
            cursor.execute('''
                INSERT INTO products (product_id, product_name, category, unit_price, stock_quantity)
                VALUES (?, ?, ?, ?, ?)
            ''', (product_id, name, category, price, stock))
            product_id += 1
    
    # ----- Insert Customers -----
    print("👥 กำลังสร้างข้อมูลลูกค้า...")
    for i in range(1, 101):
        name = f"Customer_{i}"
        email = f"customer{i}@example.com"
        phone = f"08{random.randint(10000000, 99999999)}"
        level = random.choice(membership_levels)
        cursor.execute('''
            INSERT INTO customers (customer_id, customer_name, email, phone, membership_level)
            VALUES (?, ?, ?, ?, ?)
        ''', (i, name, email, phone, level))
    
    # ----- Insert Receipts -----
    print("🧾 กำลังสร้างข้อมูลใบเสร็จ 1,000 รายการ...")
    receipt_data = []
    
    for i in range(1, 1001):
        # สุ่มวันที่
        random_days = random.randint(0, 365)
        current_date = start_date + timedelta(days=random_days)
        date_str = current_date.strftime('%Y-%m-%d')
        month_str = current_date.strftime('%B')
        
        # สุ่มข้อมูลอื่นๆ
        category = random.choice(categories)
        payment = random.choice(payment_methods)
        items = random.randint(1, 10)
        price = round(random.uniform(100, 5000) * items, 2)
        customer = f"Customer_{random.randint(1, 100)}"
        
        receipt_data.append((i, date_str, month_str, customer, category, items, price, payment))
    
    cursor.executemany('''
        INSERT INTO receipt (receipt_id, date, month, customer_name, product_category, items_count, total_price, payment_method)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', receipt_data)
    
    conn.commit()
    
    # ============================================
    # แสดงสรุป
    # ============================================
    cursor.execute("SELECT COUNT(*) FROM receipt")
    receipt_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM products")
    product_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM customers")
    customer_count = cursor.fetchone()[0]
    
    conn.close()
    
    print("\n" + "=" * 50)
    print(f"✅ สร้าง Database '{DB_NAME}' สำเร็จ!")
    print("=" * 50)
    print(f"📊 สรุปข้อมูล:")
    print(f"   - receipt:   {receipt_count:,} รายการ")
    print(f"   - products:  {product_count:,} รายการ")
    print(f"   - customers: {customer_count:,} รายการ")
    print("=" * 50)
    print("\n🚀 พร้อมใช้งานกับ NLP-to-SQL Agent แล้ว!")
    print(f"   เชื่อมต่อโดยใช้ path: {os.path.abspath(DB_NAME)}")


if __name__ == "__main__":
    create_database()
