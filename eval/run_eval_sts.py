"""STS evaluation runner.

Answers every question in eval/benchmark_sts.json and scores it by result-set
equivalence against the gold SQL, broken down by source_tag (held_out /
paraphrase / novel) and by category.

Usage:
    python eval/run_eval_sts.py --model openai/gpt-4o-mini
    python eval/run_eval_sts.py --model openrouter/deepseek/deepseek-chat --rag-top-k 5 --max-retries 2

Model spec is "<provider>/<model-id>"; provider is one of openai, google,
openrouter, ollama, zhipu.
"""

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _apply_model_env(spec: str):
    provider, _, model_id = spec.partition("/")
    provider = provider.lower()
    os.environ["MODEL_PROVIDER"] = provider
    os.environ[{
        "openai": "OPENAI_MODEL", "google": "GOOGLE_MODEL",
        "openrouter": "OPENROUTER_MODEL", "ollama": "OLLAMA_MODEL",
        "zhipu": "ZHIPU_MODEL",
    }.get(provider, "OPENAI_MODEL")] = model_id
    return provider, model_id


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="<provider>/<model-id>")
    ap.add_argument("--benchmark", default="eval/benchmark_sts.json")
    ap.add_argument("--db-url", default=os.getenv("DATABASE_URL",
                    "postgresql+psycopg2://postgres:stsLocalDev2026@localhost:5432/sts"))
    ap.add_argument("--rag-top-k", type=int, default=None)
    ap.add_argument("--max-retries", type=int, default=None)
    ap.add_argument("--schema-strategy", default=None, choices=["pruned", "full"])
    ap.add_argument("--output", default=None)
    ap.add_argument("--limit", type=int, default=None, help="only the first N questions (smoke)")
    ap.add_argument("--concurrency", type=int, default=8, help="questions answered in parallel")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    provider, model_id = _apply_model_env(args.model)
    if args.rag_top_k is not None:
        os.environ["RAG_TOP_K"] = str(args.rag_top_k)
    if args.max_retries is not None:
        os.environ["MAX_RETRIES"] = str(args.max_retries)
    if args.schema_strategy:
        os.environ["SCHEMA_STRATEGY"] = args.schema_strategy
    os.environ["DATABASE_URL"] = args.db_url

    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"), override=False)

    import pandas as pd
    from sqlalchemy import create_engine
    from core.services.engine import NLPEngine
    from core.config import settings
    from eval.run_eval import result_sets_match, _to_comparable

    def _col_vectors(df):
        """Each column as an order-normalised tuple of its (rounded/lowercased) values."""
        s = df.sort_values(list(df.columns), kind="stable").reset_index(drop=True)
        out = set()
        for col in s.columns:
            vec = []
            for v in s[col]:
                if isinstance(v, float):
                    vec.append(round(v, 2))
                elif isinstance(v, str):
                    vec.append(v.strip().lower())
                else:
                    vec.append(v)
            out.add(tuple(vec))
        return out

    def relaxed_match(gold_df, pred_df):
        """Same answer up to one added or dropped descriptive column (a name/label
        that is functionally dependent on the grouping key). Row counts must match.
        Looser than strict EX; a wrong metric can slip through only if >=2 other
        columns still line up."""
        if gold_df.empty or pred_df.empty:
            return gold_df.empty and pred_df.empty
        if len(gold_df) != len(pred_df):
            return False
        gv, pv = _col_vectors(gold_df), _col_vectors(pred_df)
        shared = len(gv & pv)
        return shared >= len(gv) - 1 and shared >= len(pv) - 1

    bench = json.load(open(os.path.join(ROOT, args.benchmark), encoding="utf-8"))
    questions = bench["questions"][: args.limit] if args.limit else bench["questions"]
    # Pool must cover concurrent gold + predicted-SQL executions.
    db = create_engine(args.db_url, pool_size=args.concurrency * 3, max_overflow=args.concurrency * 2)
    print(f"model={provider}/{model_id} rag_top_k={settings.RAG_TOP_K} "
          f"max_retries={settings.MAX_RETRIES} schema={settings.SCHEMA_STRATEGY}")
    eng = NLPEngine()

    async def run_one(q):
        t0 = time.time()
        rec = {"id": q["id"], "source_tag": q["source_tag"], "category": q["category"],
               "question": q["question"], "pred_sql": None, "error": None,
               "sql_valid": False, "executable": False, "ex_pass": False,
               "ex_pass_relaxed": False, "grain_ok": False, "first_try": False, "retry_count": 0,
               "duration_sec": 0.0, "error_class": None}
        try:
            sql, data, err, retry, _viz, _rag = await eng.query_database(
                q["question"], db, dialect="postgres")
        except Exception as e:
            rec["duration_sec"] = round(time.time() - t0, 2)
            rec["error"], rec["error_class"] = str(e), "exception"
            return rec
        rec["duration_sec"] = round(time.time() - t0, 2)
        rec["retry_count"] = retry
        if not sql:
            rec["error"], rec["error_class"] = err or "no sql", "no_sql"
            return rec
        rec["pred_sql"], rec["sql_valid"] = sql, True
        if err:
            rec["error"] = err
            rec["error_class"] = "exec_fail"
            return rec
        rec["executable"] = True
        try:
            gold_df = await asyncio.to_thread(pd.read_sql, q["gold_sql"], db)
            pred_df = pd.DataFrame(data) if data else pd.DataFrame()
        except Exception as e:
            rec["error"], rec["error_class"] = f"gold error: {e}", "gold_error"
            return rec
        rec["ex_pass"] = result_sets_match(gold_df, pred_df)
        rec["ex_pass_relaxed"] = rec["ex_pass"] or relaxed_match(gold_df, pred_df)
        rec["grain_ok"] = rec["ex_pass"] or (pred_df.shape[0] == gold_df.shape[0])
        rec["first_try"] = rec["ex_pass"] and retry == 0
        if not rec["ex_pass"]:
            rec["error_class"] = "wrong_grain" if not rec["grain_ok"] else (
                "cols_only" if rec["ex_pass_relaxed"] else "wrong_result")
        if args.verbose:
            print(f"  [{rec['id']}] {'PASS' if rec['ex_pass'] else rec['error_class']} "
                  f"gold={gold_df.shape[0]}r pred={pred_df.shape[0]}r {rec['duration_sec']}s")
        return rec

    async def run_all():
        sem = asyncio.Semaphore(max(1, args.concurrency))
        done = [0]

        async def guarded(q):
            async with sem:
                r = await run_one(q)
            done[0] += 1
            print(f"[{done[0]:02d}/{len(questions)}] {q['id']} "
                  f"{'PASS' if r['ex_pass'] else (r['error_class'] or 'fail')}")
            return r

        # First question alone: builds the schema cache / RAG index once (under the
        # engine's lock) before the rest fan out.
        first = await guarded(questions[0])
        rest = await asyncio.gather(*(guarded(q) for q in questions[1:]))
        return [first, *rest]

    t_start = time.time()
    results = asyncio.run(run_all())
    elapsed = round(time.time() - t_start, 1)

    def rate(rows, key):
        return round(sum(1 for r in rows if r[key]) / len(rows), 3) if rows else 0.0

    def block(rows):
        durs = [r["duration_sec"] for r in rows]
        errs = {}
        for r in rows:
            if r["error_class"]:
                errs[r["error_class"]] = errs.get(r["error_class"], 0) + 1
        return {
            "n": len(rows),
            "sql_validity": rate(rows, "sql_valid"),
            "executability": rate(rows, "executable"),
            "execution_accuracy": rate(rows, "ex_pass"),
            "execution_accuracy_relaxed": rate(rows, "ex_pass_relaxed"),
            "first_try_success": rate(rows, "first_try"),
            "grain_correct": rate(rows, "grain_ok"),
            "p50_latency": round(statistics.median(durs), 2) if durs else 0,
            "p95_latency": round(sorted(durs)[max(0, round(len(durs) * 0.95) - 1)], 2) if durs else 0,
            "error_classes": errs,
        }

    report = {
        "model": f"{provider}/{model_id}",
        "evaluated_at": datetime.now().isoformat(),
        "config": {"rag_top_k": settings.RAG_TOP_K, "max_retries": settings.MAX_RETRIES,
                   "schema_strategy": settings.SCHEMA_STRATEGY},
        "elapsed_sec": elapsed,
        "overall": block(results),
        "by_source_tag": {tag: block([r for r in results if r["source_tag"] == tag])
                          for tag in ("held_out", "paraphrase", "novel")},
        "by_category": {cat: block([r for r in results if r["category"] == cat])
                        for cat in sorted({r["category"] for r in results})},
        "results": results,
    }

    o = report["overall"]
    print(f"\n{'':16}{'n':>4}{'EX':>8}{'EX~':>8}{'1st-try':>9}{'grain':>8}{'p50':>7}{'p95':>7}")
    for label, b in [("OVERALL", o), *report["by_source_tag"].items()]:
        print(f"{label:16}{b['n']:>4}{b['execution_accuracy']:>8.1%}"
              f"{b['execution_accuracy_relaxed']:>8.1%}{b['first_try_success']:>9.1%}"
              f"{b['grain_correct']:>8.1%}{b['p50_latency']:>7}{b['p95_latency']:>7}")
    print("error classes:", o["error_classes"])

    out_path = args.output or (
        f"eval/sts/results_{provider}_{model_id.replace('/', '-')}"
        f"_rag{settings.RAG_TOP_K}_re{settings.MAX_RETRIES}.json")
    out_abs = os.path.join(ROOT, out_path)
    os.makedirs(os.path.dirname(out_abs), exist_ok=True)
    json.dump(report, open(out_abs, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("\nsaved", out_path)


if __name__ == "__main__":
    main()
