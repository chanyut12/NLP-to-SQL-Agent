"""Run the STS benchmark across a model x RAG x retry matrix.

Edit MODELS / ABLATION below, then:  python eval/sweep_sts.py
Resumes automatically — a config whose result file already exists is skipped.

The full RAG x retry ablation runs only for ANCHOR_MODEL; every other model
runs at BEST_CONFIG only. Each cell is repeated REPEATS times.
"""

import itertools
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Verify slugs at https://openrouter.ai/models before a real run.
ANCHOR_MODEL = "openai/gpt-4o-mini"
MODELS = [
    ANCHOR_MODEL,
    # Enable once OPENROUTER_API_KEY is set / the account has credit:
    # "openrouter/z-ai/glm-5.2:free",
    # "openrouter/deepseek/deepseek-v4-flash",
    # "openrouter/qwen/qwen3-235b-a22b-2507",
]

ABLATION = list(itertools.product([0, 3], [0, 2]))   # (rag_top_k, max_retries)
BEST_CONFIG = (3, 2)
REPEATS = 5

DB_URL = os.getenv("DATABASE_URL",
                   "postgresql+psycopg2://postgres:stsLocalDev2026@localhost:5432/sts")


def result_path(model, rag, retry, run):
    slug = model.replace("/", "-")
    return os.path.join(ROOT, "eval", "sts",
                        f"results_{slug}_rag{rag}_re{retry}_run{run}.json")


def plan():
    for model in MODELS:
        configs = ABLATION if model == ANCHOR_MODEL else [BEST_CONFIG]
        for rag, retry in configs:
            for run in range(1, REPEATS + 1):
                yield model, rag, retry, run


def main():
    jobs = list(plan())
    todo = [j for j in jobs if not os.path.exists(result_path(*j))]
    print(f"{len(jobs)} cells, {len(todo)} to run ({len(jobs) - len(todo)} already done)")
    for i, (model, rag, retry, run) in enumerate(todo, 1):
        out = result_path(model, rag, retry, run)
        print(f"\n=== [{i}/{len(todo)}] {model} rag={rag} retry={retry} run={run} ===")
        cmd = [sys.executable, os.path.join(ROOT, "eval", "run_eval_sts.py"),
               "--model", model, "--rag-top-k", str(rag), "--max-retries", str(retry),
               "--db-url", DB_URL, "--output", os.path.relpath(out, ROOT)]
        r = subprocess.run(cmd, cwd=ROOT)
        if r.returncode != 0:
            print(f"  FAILED (exit {r.returncode}) — leaving for the next resume")


if __name__ == "__main__":
    main()
