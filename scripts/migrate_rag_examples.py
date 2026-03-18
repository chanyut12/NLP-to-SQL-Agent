"""
RAG Example Migration Script - แปลง SQL examples เมื่อเปลี่ยน database engine

เมื่อย้ายจาก dialect หนึ่งไปอีก dialect ตัวอย่าง SQL ใน thai_sql_examples.json
ต้องถูกแปลงให้ตรงกับ dialect ใหม่
"""
import json
import sys
import os
from typing import List, Dict

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.utils.dialect_transpiler import DialectTranspiler


def migrate_rag_examples(
    input_file: str,
    output_file: str,
    from_dialect: str,
    to_dialect: str
) -> Dict:
    """
    แปลง SQL examples จาก dialect หนึ่งไปอีก dialect

    Args:
        input_file: ไฟล์ JSON ต้นฉบับ (เช่น thai_sql_examples.json)
        output_file: ไฟล์ JSON ที่แปลงแล้ว
        from_dialect: dialect ต้นทาง (SQLite, MySQL, PostgreSQL)
        to_dialect: dialect ปลายทาง (SQLite, MySQL, PostgreSQL)

    Returns:
        {
            "total": int,
            "success": int,
            "failed": int,
            "errors": [list of error messages]
        }
    """
    print(f"🔄 Migrating RAG examples: {from_dialect} → {to_dialect}")
    print(f"📖 Input: {input_file}")
    print(f"📝 Output: {output_file}")

    # อ่านไฟล์ต้นฉบับ
    with open(input_file, 'r', encoding='utf-8') as f:
        examples = json.load(f)

    stats = {
        "total": len(examples),
        "success": 0,
        "failed": 0,
        "errors": []
    }

    migrated_examples = []

    for idx, example in enumerate(examples):
        try:
            # แปลง SQL
            original_sql = example.get("sql", "")
            if not original_sql:
                migrated_examples.append(example)
                stats["success"] += 1
                continue

            # ใช้ DialectTranspiler แปลง
            transpiled_sql = DialectTranspiler.transpile(
                original_sql,
                from_dialect,
                to_dialect,
                pretty=True
            )

            if transpiled_sql:
                # สร้าง example ใหม่ที่แปลงแล้ว
                new_example = example.copy()
                new_example["sql"] = transpiled_sql
                new_example["dialect"] = to_dialect  # เพิ่ม metadata

                # เก็บ SQL เดิมไว้ใน metadata (สำหรับ reference)
                if "metadata" not in new_example:
                    new_example["metadata"] = {}
                new_example["metadata"]["original_sql"] = original_sql
                new_example["metadata"]["original_dialect"] = from_dialect

                migrated_examples.append(new_example)
                stats["success"] += 1

                print(f"✓ [{idx+1}/{stats['total']}] Migrated: {example.get('question', 'N/A')[:50]}...")
            else:
                # แปลงไม่สำเร็จ - ใช้ SQL เดิม
                migrated_examples.append(example)
                stats["failed"] += 1
                error_msg = f"Example {idx+1}: Transpilation returned None"
                stats["errors"].append(error_msg)
                print(f"⚠ [{idx+1}/{stats['total']}] {error_msg}")

        except Exception as e:
            # Error - ใช้ example เดิม
            migrated_examples.append(example)
            stats["failed"] += 1
            error_msg = f"Example {idx+1}: {str(e)}"
            stats["errors"].append(error_msg)
            print(f"✗ [{idx+1}/{stats['total']}] {error_msg}")

    # บันทึกไฟล์ใหม่
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(migrated_examples, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Migration completed!")
    print(f"   Total: {stats['total']}")
    print(f"   Success: {stats['success']}")
    print(f"   Failed: {stats['failed']}")

    if stats['errors']:
        print(f"\n⚠ Errors:")
        for error in stats['errors'][:5]:  # แสดงแค่ 5 errors แรก
            print(f"   - {error}")

    return stats


def validate_migrated_examples(file_path: str, target_dialect: str) -> Dict:
    """
    ตรวจสอบว่า SQL examples ที่แปลงแล้วใช้ได้กับ dialect ใหม่ไหม

    Args:
        file_path: ไฟล์ JSON ที่แปลงแล้ว
        target_dialect: dialect ที่ต้องการตรวจสอบ

    Returns:
        {
            "total": int,
            "valid": int,
            "invalid": int,
            "issues": [list of validation issues]
        }
    """
    print(f"\n🔍 Validating migrated examples for {target_dialect}...")

    with open(file_path, 'r', encoding='utf-8') as f:
        examples = json.load(f)

    stats = {
        "total": len(examples),
        "valid": 0,
        "invalid": 0,
        "issues": []
    }

    for idx, example in enumerate(examples):
        sql = example.get("sql", "")
        if not sql:
            continue

        # ตรวจสอบด้วย DialectTranspiler
        validation = DialectTranspiler.validate_compatibility(sql, target_dialect)

        if validation["compatible"]:
            stats["valid"] += 1
            print(f"✓ [{idx+1}/{stats['total']}] Valid")
        else:
            stats["invalid"] += 1
            issue = {
                "example_id": idx + 1,
                "question": example.get("question", "N/A")[:50],
                "issues": validation["issues"],
                "suggestions": validation["suggestions"]
            }
            stats["issues"].append(issue)
            print(f"✗ [{idx+1}/{stats['total']}] Invalid: {validation['issues']}")

    print(f"\n✅ Validation completed!")
    print(f"   Total: {stats['total']}")
    print(f"   Valid: {stats['valid']}")
    print(f"   Invalid: {stats['invalid']}")

    return stats


# =============================================================================
# CLI Interface
# =============================================================================
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Migrate RAG examples between database dialects"
    )
    parser.add_argument(
        "--input",
        default="thai_sql_examples.json",
        help="Input JSON file with examples"
    )
    parser.add_argument(
        "--output",
        help="Output JSON file (default: <input>_<to_dialect>.json)"
    )
    parser.add_argument(
        "--from-dialect",
        required=True,
        choices=["SQLite", "MySQL", "PostgreSQL"],
        help="Source database dialect"
    )
    parser.add_argument(
        "--to-dialect",
        required=True,
        choices=["SQLite", "MySQL", "PostgreSQL"],
        help="Target database dialect"
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate migrated examples after conversion"
    )

    args = parser.parse_args()

    # ตั้งค่า output file
    if not args.output:
        base_name = args.input.replace('.json', '')
        args.output = f"{base_name}_{args.to_dialect.lower()}.json"

    # Migration
    stats = migrate_rag_examples(
        args.input,
        args.output,
        args.from_dialect,
        args.to_dialect
    )

    # Validation (optional)
    if args.validate:
        validate_migrated_examples(args.output, args.to_dialect)

    # Exit code
    exit(0 if stats["failed"] == 0 else 1)
