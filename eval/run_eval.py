"""
Evaluation script: Execution Accuracy (EX) for Thai NLP-to-SQL Agent
======================================================================
วัด Execution Accuracy โดยเปรียบเทียบ result set ของ predicted SQL กับ gold SQL
บน classicmodels.db (SQLite) โดยไม่ต้องการ ground-truth SQL ที่ตรงกันเป๊ะ

Usage:
    python eval/run_eval.py [--benchmark eval/benchmark_classicmodels.json]
                            [--db classicmodels.db]
                            [--output eval/results.json]
                            [--verbose]

Metrics:
    - SQL Validity Rate: % ที่ engine generate SQL ได้ (ไม่ crash ก่อน execute)
    - Executability Rate: % ที่ SQL รันผ่านโดยไม่เกิด runtime error
    - Execution Accuracy (EX): % ที่ result set ตรงกับ gold SQL
    - ทั้งหมดแยกตาม category: simple / aggregation / join / complex
"""

import sys
import os
import json
import asyncio
import argparse
import time
from datetime import datetime

# ── path setup ────────────────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Load .env BEFORE importing core modules (config.py reads os.getenv at import time)
from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, ".env"))

import pandas as pd
from sqlalchemy import create_engine as sa_create_engine

from core.services.engine import NLPEngine
from core.config import settings


# ── result comparison ─────────────────────────────────────────────────────────

def _to_comparable(df: pd.DataFrame) -> frozenset:
    """
    Convert DataFrame to a frozenset of tuples for order-insensitive comparison.
    - Rounds floats to 2 decimal places
    - Lowercases strings
    - Drops column names (compare values only)
    """
    rows = []
    for row in df.itertuples(index=False):
        normalized = []
        for v in row:
            if isinstance(v, float):
                normalized.append(round(v, 2))
            elif isinstance(v, str):
                normalized.append(v.strip().lower())
            elif v is None:
                normalized.append(None)
            else:
                normalized.append(v)
        rows.append(tuple(normalized))
    return frozenset(rows)


def result_sets_match(gold_df: pd.DataFrame, pred_df: pd.DataFrame) -> bool:
    """Return True if both DataFrames contain equivalent result sets."""
    if gold_df.shape[1] != pred_df.shape[1]:
        return False
    gold_set = _to_comparable(gold_df)
    pred_set = _to_comparable(pred_df)
    return gold_set == pred_set


# ── evaluation core ───────────────────────────────────────────────────────────

async def evaluate_one(
    example: dict,
    nlp_engine: NLPEngine,
    db_engine,
    verbose: bool = False,
) -> dict:
    """Run one benchmark example; return a result dict."""
    qid = example["id"]
    question = example["question"]
    gold_sql = example["gold_sql"]
    category = example["category"]

    result = {
        "id": qid,
        "question": question,
        "category": category,
        "gold_sql": gold_sql,
        "pred_sql": None,
        "sql_valid": False,       # engine returned a non-empty SQL
        "executable": False,      # pred SQL ran without error
        "ex_pass": False,         # result set matches gold
        "error": None,
        "duration_sec": 0.0,
        "retry_count": 0,
        "rag_count": 0,
    }

    t0 = time.time()
    try:
        # Call NLP engine (dialect=sqlite to match the benchmark DB)
        pred_sql, pred_data, error_msg, retry_count, viz_config, rag_count = \
            await nlp_engine.query_database(
                question=question,
                engine=db_engine,
                dialect="sqlite",
            )

        result["duration_sec"] = round(time.time() - t0, 2)
        result["retry_count"] = retry_count
        result["rag_count"] = rag_count

        if not pred_sql or not pred_sql.strip():
            result["error"] = error_msg or "No SQL generated"
            if verbose:
                print(f"  [{qid}] NO SQL — {result['error']}")
            return result

        result["pred_sql"] = pred_sql
        result["sql_valid"] = True

        if error_msg:
            result["error"] = error_msg
            if verbose:
                print(f"  [{qid}] EXECUTE FAIL — {error_msg[:120]}")
            return result

        result["executable"] = True

        # Compare result sets
        gold_df = pd.read_sql(gold_sql, db_engine)
        pred_df = pd.DataFrame(pred_data) if pred_data else pd.DataFrame()

        match = result_sets_match(gold_df, pred_df)
        result["ex_pass"] = match

        if verbose:
            status = "PASS ✓" if match else "FAIL ✗"
            print(f"  [{qid}] {status} | gold={len(gold_df)}r pred={len(pred_df)}r retry={retry_count}")
            if not match:
                print(f"    gold sample: {gold_df.head(2).to_dict('records')}")
                print(f"    pred sample: {pred_df.head(2).to_dict('records')}")

    except Exception as e:
        result["duration_sec"] = round(time.time() - t0, 2)
        result["error"] = str(e)
        if verbose:
            print(f"  [{qid}] EXCEPTION — {e}")

    return result


# ── reporting ─────────────────────────────────────────────────────────────────

def print_report(results: list[dict], elapsed: float):
    categories = ["simple", "aggregation", "join", "complex"]

    print("\n" + "=" * 62)
    print("  Thai NLP-to-SQL — Execution Accuracy Evaluation Report")
    print("=" * 62)

    total = len(results)
    valid = sum(1 for r in results if r["sql_valid"])
    executable = sum(1 for r in results if r["executable"])
    ex_pass = sum(1 for r in results if r["ex_pass"])

    print(f"\n{'Metric':<30} {'Count':>6}  {'Rate':>7}")
    print("-" * 46)
    print(f"{'Total examples':<30} {total:>6}")
    print(f"{'SQL Validity Rate':<30} {valid:>6}  {valid/total:>7.1%}")
    print(f"{'Executability Rate':<30} {executable:>6}  {executable/total:>7.1%}")
    print(f"{'Execution Accuracy (EX)':<30} {ex_pass:>6}  {ex_pass/total:>7.1%}")
    print(f"\n  Total time: {elapsed:.1f}s  |  Avg/query: {elapsed/total:.1f}s")

    print("\n── By Category ─────────────────────────────────────────────")
    print(f"  {'Category':<14} {'N':>3}  {'Valid':>6}  {'Exec':>6}  {'EX':>6}")
    print("  " + "-" * 42)
    for cat in categories:
        cat_results = [r for r in results if r["category"] == cat]
        n = len(cat_results)
        if n == 0:
            continue
        v = sum(1 for r in cat_results if r["sql_valid"])
        e = sum(1 for r in cat_results if r["executable"])
        x = sum(1 for r in cat_results if r["ex_pass"])
        print(f"  {cat:<14} {n:>3}  {v/n:>6.1%}  {e/n:>6.1%}  {x/n:>6.1%}")

    failed = [r for r in results if not r["ex_pass"]]
    if failed:
        print(f"\n── Failed Questions ({len(failed)}) ───────────────────────────────")
        for r in failed:
            status = "no-sql" if not r["sql_valid"] else ("no-exec" if not r["executable"] else "wrong-result")
            print(f"  [{r['id']}] ({status}) {r['question']}")
            if r["error"]:
                print(f"    error: {r['error'][:100]}")
            if r["pred_sql"]:
                print(f"    pred:  {r['pred_sql'][:100].strip()}")

    print("\n" + "=" * 62 + "\n")


# ── main ──────────────────────────────────────────────────────────────────────

async def run_eval(benchmark_path: str, db_path: str, output_path: str, verbose: bool):
    # Load benchmark
    with open(benchmark_path, "r", encoding="utf-8") as f:
        benchmark = json.load(f)
    examples = benchmark["examples"]
    print(f"Loaded {len(examples)} examples from {benchmark_path}")
    print(f"Database: {db_path}  |  Dialect: {benchmark['dialect']}")

    # Setup DB
    abs_db = os.path.join(ROOT, db_path) if not os.path.isabs(db_path) else db_path
    db_engine = sa_create_engine(f"sqlite:///{abs_db}")

    # Setup NLP engine
    print("\nInitializing NLP engine...")
    nlp_engine = NLPEngine()

    # Run evaluation
    print(f"\nRunning evaluation ({len(examples)} questions)...\n")
    t_start = time.time()
    results = []
    for i, ex in enumerate(examples, 1):
        print(f"[{i:02d}/{len(examples)}] {ex['id']} — {ex['question']}")
        r = await evaluate_one(ex, nlp_engine, db_engine, verbose=verbose)
        results.append(r)

    elapsed = time.time() - t_start

    # Print report
    print_report(results, elapsed)

    # Save results JSON
    model_name = {
        "openai": settings.OPENAI_MODEL,
        "google": settings.GOOGLE_MODEL,
        "ollama": settings.OLLAMA_MODEL,
        "openrouter": settings.OPENROUTER_MODEL,
        "zhipu": settings.ZHIPU_MODEL,
    }.get(settings.MODEL_PROVIDER, settings.OLLAMA_MODEL)

    output = {
        "benchmark": benchmark_path,
        "database": db_path,
        "evaluated_at": datetime.now().isoformat(),
        "model": f"{settings.MODEL_PROVIDER}/{model_name}",
        "config": {
            "rag_top_k": settings.RAG_TOP_K,
            "max_retries": settings.MAX_RETRIES,
            "rag_distance_threshold": settings.RAG_DISTANCE_THRESHOLD,
        },
        "summary": {
            "total": len(results),
            "sql_valid": sum(1 for r in results if r["sql_valid"]),
            "executable": sum(1 for r in results if r["executable"]),
            "ex_pass": sum(1 for r in results if r["ex_pass"]),
            "sql_validity_rate": sum(1 for r in results if r["sql_valid"]) / len(results),
            "executability_rate": sum(1 for r in results if r["executable"]) / len(results),
            "execution_accuracy": sum(1 for r in results if r["ex_pass"]) / len(results),
            "elapsed_sec": round(elapsed, 1),
        },
        "by_category": {},
        "results": results,
    }
    for cat in ["simple", "aggregation", "join", "complex"]:
        cat_r = [r for r in results if r["category"] == cat]
        n = len(cat_r)
        output["by_category"][cat] = {
            "n": n,
            "ex_pass": sum(1 for r in cat_r if r["ex_pass"]),
            "execution_accuracy": sum(1 for r in cat_r if r["ex_pass"]) / n if n else 0,
        }

    abs_output = os.path.join(ROOT, output_path) if not os.path.isabs(output_path) else output_path
    os.makedirs(os.path.dirname(abs_output), exist_ok=True)
    with open(abs_output, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"Results saved → {abs_output}")


def main():
    parser = argparse.ArgumentParser(description="Thai NLP-to-SQL Execution Accuracy Evaluation")
    parser.add_argument("--benchmark", default="eval/benchmark_classicmodels.json",
                        help="Path to benchmark JSON file")
    parser.add_argument("--db", default="classicmodels.db",
                        help="Path to SQLite database file")
    parser.add_argument("--output", default="eval/results.json",
                        help="Path to save evaluation results JSON")
    parser.add_argument("--verbose", action="store_true",
                        help="Print per-question details during evaluation")
    args = parser.parse_args()

    asyncio.run(run_eval(args.benchmark, args.db, args.output, args.verbose))


if __name__ == "__main__":
    main()
