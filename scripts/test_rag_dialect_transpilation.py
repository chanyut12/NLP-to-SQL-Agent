"""
Test RAG Dialect Auto-Transpilation

ทดสอบว่า RAG Store แปลง SQL examples ระหว่าง dialects อัตโนมัติได้ไหม
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.data.rag_store import create_example_store


def test_rag_dialect_transpilation():
    """
    ทดสอบการดึง examples และแปลง dialect อัตโนมัติ
    """
    print("=" * 70)
    print("RAG Dialect Auto-Transpilation Test")
    print("=" * 70)

    # สร้าง RAG store
    store = create_example_store()

    # Test cases
    test_queries = [
        ("ยอดขายรวมทั้งหมด", "aggregation"),
        ("ยอดขายรวมปี 2004", "join with year function"),
        ("ยอดขายแยกตามเดือน", "groupby with month function"),
    ]

    dialects_to_test = ["sqlite", "mysql", "postgresql"]

    for question, description in test_queries:
        print(f"\n{'='*70}")
        print(f"📝 Question: {question}")
        print(f"   ({description})")
        print(f"{'='*70}\n")

        for dialect in dialects_to_test:
            print(f"🎯 Target Dialect: {dialect.upper()}")
            print(f"{'-'*70}")

            # ดึง examples พร้อมแปลง dialect
            examples = store.get_similar_examples(
                query=question,
                top_k=2,
                dialect=dialect,
                auto_transpile=True  # ✅ Enable auto-transpile
            )

            if examples:
                for idx, ex in enumerate(examples, 1):
                    print(f"\n📊 Example {idx}:")
                    print(f"   Question: {ex['question']}")
                    print(f"   Dialect: {ex['dialect']}")
                    print(f"   Distance: {ex['distance']:.4f}")
                    print(f"   SQL:")
                    # Format SQL for better readability
                    sql_lines = ex['sql'].strip().split('\n')
                    for line in sql_lines:
                        print(f"      {line}")
            else:
                print(f"   ⚠ No examples found")

            print()

    print("=" * 70)
    print("✅ Test completed!")
    print("=" * 70)


def test_manual_comparison():
    """
    เปรียบเทียบ SQL ที่แปลงแล้วกับต้นฉบับ
    """
    print("\n" + "=" * 70)
    print("Manual Comparison: MySQL → PostgreSQL")
    print("=" * 70)

    store = create_example_store()

    # ดึง example จาก MySQL
    mysql_examples = store.get_similar_examples(
        query="ยอดขายรวมปี 2004",
        top_k=1,
        dialect="mysql",
        auto_transpile=False  # ❌ ไม่แปลง
    )

    # ดึง example เดียวกันแต่แปลงเป็น PostgreSQL
    postgres_examples = store.get_similar_examples(
        query="ยอดขายรวมปี 2004",
        top_k=1,
        dialect="postgresql",
        auto_transpile=True  # ✅ แปลง
    )

    if mysql_examples and postgres_examples:
        print("\n📌 Original (MySQL):")
        print(mysql_examples[0]['sql'])

        print("\n📌 Transpiled (PostgreSQL):")
        print(postgres_examples[0]['sql'])

        print("\n✅ Differences:")
        print("   MySQL:      YEAR(orderDate)")
        print("   PostgreSQL: EXTRACT(YEAR FROM orderDate)")
    else:
        print("⚠ Examples not found")


def test_fallback_mechanism():
    """
    ทดสอบ fallback mechanism เมื่อไม่มี examples สำหรับ dialect นั้น
    """
    print("\n" + "=" * 70)
    print("Fallback Mechanism Test")
    print("=" * 70)

    store = create_example_store()

    # ทดสอบกับ PostgreSQL (ซึ่งไม่มี examples ใน thai_sql_examples.json)
    print("\n🔍 Querying for PostgreSQL (no native examples)...")

    examples = store.get_similar_examples(
        query="ยอดขายรวมทั้งหมด",
        top_k=3,
        dialect="postgresql",
        auto_transpile=True
    )

    print(f"\n✅ Found {len(examples)} examples")
    for idx, ex in enumerate(examples, 1):
        print(f"\n   Example {idx}:")
        print(f"   - Original dialect: {ex.get('dialect', 'unknown')}")
        print(f"   - SQL preview: {ex['sql'][:80]}...")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test RAG dialect transpilation")
    parser.add_argument(
        "--mode",
        choices=["full", "comparison", "fallback"],
        default="full",
        help="Test mode: full (all tests), comparison (manual comparison), fallback (fallback mechanism)"
    )

    args = parser.parse_args()

    if args.mode == "full":
        test_rag_dialect_transpilation()
        test_manual_comparison()
        test_fallback_mechanism()
    elif args.mode == "comparison":
        test_manual_comparison()
    elif args.mode == "fallback":
        test_fallback_mechanism()
