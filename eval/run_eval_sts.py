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


def engine_call_for(mode, eng):
    """Pick the engine entrypoint that answers SQL questions (ticket #21).
    `pipeline` = one-shot chain (the #18 baseline path); `agent` = the ADR 0006
    conversational loop. Answer-type questions always use the agent entrypoint
    regardless of this switch."""
    if mode == "agent":
        return eng.agent_query_database
    return eng.query_database

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
    ap.add_argument("--concurrency", type=int, default=3, help="questions answered in parallel")
    ap.add_argument("--question-timeout", type=int, default=150,
                    help="hard cap per question; a stuck one is marked 'timeout' and the run continues")
    ap.add_argument("--engine", default="pipeline", choices=["pipeline", "agent"],
                    help="which engine answers SQL questions; answer-type "
                         "questions always go through the conversational agent")
    ap.add_argument("--skip-quota-gate", action="store_true",
                    help="override the ADR 0007 distribution gate (not recommended)")
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
    from eval.scoring import (
        relaxed_match, result_sets_match, score_sql_row, turn_result_fields,
    )

    bench = json.load(open(os.path.join(ROOT, args.benchmark), encoding="utf-8"))
    questions = bench["questions"][: args.limit] if args.limit else bench["questions"]

    # ADR 0007 quota gate (ticket #17): a drifted set refuses to run — balance
    # cannot silently decay. The FULL set is checked, so --limit smoke runs of a
    # balanced set stay legal.
    from eval.scoring import check_quota_gate, domain_of, score_answer_type
    from eval.distribution_audit import CATEGORY_BUCKETS, bucket_for
    if not args.skip_quota_gate:
        examples = json.load(open(os.path.join(ROOT, "TEXT_TO_SQL_STS_RAG_EXAMPLES.json"),
                                  encoding="utf-8"))["examples"]
        violations = check_quota_gate(bench["questions"], examples)
        if violations:
            print("QUOTA GATE REFUSED (ADR 0007): eval sets deviate from their distribution:")
            for v in violations:
                print("  -", v)
            print("Rebalance the sets (python eval/distribution_audit.py) "
                  "or pass --skip-quota-gate to override.")
            sys.exit(2)
    # Pool must cover concurrent gold + predicted-SQL executions.
    db = create_engine(args.db_url, pool_size=args.concurrency * 3, max_overflow=args.concurrency * 2)
    print(f"model={provider}/{model_id} engine={args.engine} "
          f"rag_top_k={settings.RAG_TOP_K} "
          f"max_retries={settings.MAX_RETRIES} schema={settings.SCHEMA_STRATEGY}")
    eng = NLPEngine()
    sql_call = engine_call_for(args.engine, eng)

    async def run_one(q):
        t0 = time.time()
        rec = {"id": q["id"], "source_tag": q["source_tag"], "category": q["category"],
               "question": q["question"], "pred_sql": None, "error": None,
               "sql_valid": False, "executable": False, "ex_pass": False,
               "ex_pass_relaxed": False, "grain_ok": False, "first_try": False, "retry_count": 0,
               "duration_sec": 0.0, "error_class": None,
               "expected_type": q.get("expected_answer_type"), "answer_type": None,
               "at_pass": None, "at_reason": None, "steps_used": None}
        if rec["expected_type"]:
            # Answer-type question (ADR 0007): no gold SQL — the agent answers
            # through the conversational Turn and we score the answer type.
            try:
                turn = await asyncio.wait_for(
                    eng.agent_query_database(q["question"], db, dialect="postgres"),
                    timeout=args.question_timeout,
                )
            except asyncio.TimeoutError:
                rec["duration_sec"] = round(time.time() - t0, 2)
                rec["at_pass"], rec["at_reason"] = False, f"timeout after {args.question_timeout}s"
                rec["error_class"] = "timeout"
                return rec
            except Exception as e:
                rec["duration_sec"] = round(time.time() - t0, 2)
                rec["at_pass"], rec["at_reason"] = False, f"exception: {e}"
                rec["error_class"] = "exception"
                return rec
            rec["duration_sec"] = round(time.time() - t0, 2)
            passed, reason = score_answer_type(
                rec["expected_type"],
                None if turn.error else turn.answer_type, error=turn.error)
            rec.update(answer_type=turn.answer_type, message=turn.message,
                       at_pass=passed, at_reason=reason, steps_used=turn.steps_used,
                       error=turn.error,
                       error_class=turn.error or (None if passed else "at_fail"))
            if args.verbose:
                print(f"  [{rec['id']}] {'AT-PASS' if passed else reason} "
                      f"steps={turn.steps_used} {rec['duration_sec']}s")
            return rec
        if args.engine == "agent":
            # Agent engine (ADR 0006): the SQL question is answered inside a
            # conversational Turn; the Turn's SQL is scored against gold exactly
            # like the pipeline path (ticket #21 — same comparator, same axes).
            try:
                turn = await asyncio.wait_for(
                    sql_call(q["question"], db, dialect="postgres"),
                    timeout=args.question_timeout,
                )
            except asyncio.TimeoutError:
                rec["duration_sec"] = round(time.time() - t0, 2)
                rec["error"] = f"question timed out after {args.question_timeout}s"
                rec["error_class"] = "timeout"
                return rec
            except Exception as e:
                rec["error"], rec["error_class"] = str(e), "exception"
                return rec
            rec["duration_sec"] = round(time.time() - t0, 2)
            rec["steps_used"] = getattr(turn, "steps_used", None)
            rec.update(turn_result_fields(turn))
            if not rec["pred_sql"]:
                rec["error"] = (getattr(turn, "error_message", None)
                                or rec["error_class"] or "no sql")
                return rec
            try:
                gold_df = await asyncio.to_thread(pd.read_sql, q["gold_sql"], db)
                pred_df = pd.DataFrame(turn.rows) if turn.rows else pd.DataFrame()
            except Exception as e:
                rec["error"], rec["error_class"] = f"gold error: {e}", "gold_error"
                return rec
            rec["executable"] = True
            score_sql_row(rec, gold_df, pred_df, retry=0)
            if args.verbose:
                print(f"  [{rec['id']}] {'PASS' if rec['ex_pass'] else rec['error_class']} "
                      f"gold={gold_df.shape[0]}r pred={pred_df.shape[0]}r "
                      f"steps={rec['steps_used']} {rec['duration_sec']}s")
            return rec
        try:
            sql, data, err, retry, _viz, _rag = await asyncio.wait_for(
                sql_call(q["question"], db, dialect="postgres"),
                timeout=args.question_timeout,
            )
        except asyncio.TimeoutError:
            rec["duration_sec"] = round(time.time() - t0, 2)
            rec["error"] = f"question timed out after {args.question_timeout}s"
            rec["error_class"] = "timeout"
            return rec
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
            if r.get("expected_type"):
                status = "AT-PASS" if r.get("at_pass") else (r.get("at_reason") or "at-fail")[:60]
            else:
                status = "PASS" if r["ex_pass"] else (r["error_class"] or "fail")
            print(f"[{done[0]:02d}/{len(questions)}] {q['id']} {status}")
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

    # ADR 0007: SQL-shaped and answer-type questions are scored on different
    # axes — SQL stats never mix answer-type rows into their rates.
    sql_rows = [r for r in results if not r.get("expected_type")]
    at_rows = [r for r in results if r.get("expected_type")]

    def at_block(rows):
        n = len(rows)
        passed = sum(1 for r in rows if r.get("at_pass"))
        return {"n": n, "pass": passed,
                "pass_rate": round(passed / n, 3) if n else 0.0}

    def bucket_of_rec(r):
        return bucket_for(r["category"]) or r["category"]

    domains = {}
    for q in bench["questions"]:
        domains[domain_of(q)] = domains.get(domain_of(q), 0) + 1

    report = {
        "model": f"{provider}/{model_id}",
        "engine": args.engine,
        "evaluated_at": datetime.now().isoformat(),
        "config": {"rag_top_k": settings.RAG_TOP_K, "max_retries": settings.MAX_RETRIES,
                   "schema_strategy": settings.SCHEMA_STRATEGY},
        "elapsed_sec": elapsed,
        "questions_total": len(results),
        "overall": block(sql_rows),
        "answer_type": {
            "expected_clarification": at_block([r for r in at_rows
                                                if r["expected_type"] == "clarification"]),
            "expected_refusal": at_block([r for r in at_rows
                                          if r["expected_type"] == "refusal"]),
        },
        "by_bucket": {b: block([r for r in sql_rows if bucket_of_rec(r) == b])
                      for b in CATEGORY_BUCKETS},
        "by_source_tag": {tag: block([r for r in sql_rows if r["source_tag"] == tag])
                          for tag in sorted({r["source_tag"] for r in sql_rows})},
        "by_category": {cat: block([r for r in sql_rows if r["category"] == cat])
                        for cat in sorted({r["category"] for r in sql_rows})},
        "domain_coverage": dict(sorted(domains.items())),
        "results": results,
    }

    o = report["overall"]
    print(f"\n{'':16}{'n':>4}{'EX':>8}{'EX~':>8}{'1st-try':>9}{'grain':>8}{'p50':>7}{'p95':>7}")
    for label, b in [("OVERALL(sql)", o), *report["by_bucket"].items()]:
        print(f"{label:16}{b['n']:>4}{b['execution_accuracy']:>8.1%}"
              f"{b['execution_accuracy_relaxed']:>8.1%}{b['first_try_success']:>9.1%}"
              f"{b['grain_correct']:>8.1%}{b['p50_latency']:>7}{b['p95_latency']:>7}")
    print("error classes:", o["error_classes"])
    for name, b in report["answer_type"].items():
        print(f"{name:24}{b['pass']:>3}/{b['n']:<3} pass ({b['pass_rate']:.1%})")
    print("domain coverage (reported):",
          ", ".join(f"{d}={n}" for d, n in report["domain_coverage"].items()))

    out_path = args.output or (
        f"eval/sts/results_{provider}_{model_id.replace('/', '-')}"
        f"_rag{settings.RAG_TOP_K}_re{settings.MAX_RETRIES}.json")
    out_abs = os.path.join(ROOT, out_path)
    os.makedirs(os.path.dirname(out_abs), exist_ok=True)
    json.dump(report, open(out_abs, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("\nsaved", out_path)


if __name__ == "__main__":
    main()
