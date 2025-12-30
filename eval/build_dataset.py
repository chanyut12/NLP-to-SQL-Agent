"""
Script to build a golden dataset from approved query logs.
Reads query_logs.jsonl and filters for positive feedback or successful queries.
"""

import json
import argparse
import os

def build_dataset(log_file, output_file, min_feedback=None):
    if not os.path.exists(log_file):
        print(f"Log file not found: {log_file}")
        return

    dataset = []
    
    with open(log_file, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                entry = json.loads(line)
                
                # Criteria for inclusion:
                # 1. Has positive feedback OR
                # 2. Status is Success (and optionally no negative feedback)
                
                is_positive = entry.get("feedback") == "Positive"
                is_success = entry.get("status", "").startswith("Success")
                is_negative = entry.get("feedback") == "Negative"
                
                if is_positive or (is_success and not is_negative):
                    dataset.append({
                        "question": entry["question"],
                        "sql": entry["sql"],
                        "db_type": entry.get("dialect", "sqlite"), # fallback
                        "difficulty": "unknown"
                    })
                    
            except Exception as e:
                print(f"Skipping line: {e}")
                
    print(f"Collected {len(dataset)} examples.")
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({"version": "1.0", "examples": dataset}, f, indent=2, ensure_ascii=False)
    
    print(f"Saved dataset to {output_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--log-file", default="../query_logs.jsonl")
    parser.add_argument("--output", default="golden_dataset.json")
    args = parser.parse_args()
    
    build_dataset(args.log_file, args.output)

