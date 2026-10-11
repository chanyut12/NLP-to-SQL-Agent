# STS evaluation

## Golden set — `benchmark_sts.json` (30 questions)

Built by `scripts/build_sts_benchmark.py`, disjoint from `profiles/sts/examples.json`
so retrieval can never hand the model its own answer. Every gold SQL is verified
to execute and return ≥1 row on the dev database.

| `source_tag` | n | what it measures |
|---|--:|---|
| `held_out` | 10 | true generalisation — pulled out of the corpus, removed from retrieval |
| `paraphrase` | 12 | RAG-adaptation — reworded / abbreviated / code-switched; a sibling stays in the corpus |
| `novel` | 8 | compositional generalisation — metric/grain combos the corpus does not contain |

Regenerate: `python scripts/build_sts_profile.py && python scripts/build_sts_benchmark.py`

After changing the profile or `profiles/sts/schema_mappings.json`, wipe the
vector stores so they rebuild: `rm -rf rag_db schema_rag_db`

## Metrics (`run_eval_sts.py`)

Result-set equivalence against the gold SQL (order-insensitive, floats rounded to
2dp). Reported overall, by `source_tag`, and by category:

- **execution_accuracy** — exact result-set match (primary, strict)
- **execution_accuracy_relaxed** — same answer up to one added or dropped
  descriptive column (a name/label functionally dependent on the grouping key);
  row counts must still match. A wrong metric can slip through only if ≥2 other
  columns line up, so it is a loose upper bound, not the headline number.
- **first_try_success** — strict match with `retry_count == 0`
- **grain_correct** — same row count as gold (no duplicate amplification)
- **sql_validity / executability**
- **p50 / p95 latency**, **error_classes**: `no_sql`, `exec_fail`, `wrong_grain`,
  `cols_only` (relaxed-pass), `wrong_result`

## Models

Slugs live at the top of `eval/sweep_sts.py` — verify against openrouter.ai/models first.

| Model | via | role | status |
|---|---|---|---|
| gpt-4o-mini | OpenAI | anchor — RAG{0,3}×retry{0,2} ablation | active |
| z-ai/glm-5.2:free | OpenRouter | free-tier viability | commented out — needs OPENROUTER_API_KEY |
| deepseek/deepseek-v4-flash | OpenRouter | open-weight, code-strong | commented out — needs OpenRouter credit |
| qwen/qwen3-235b-a22b-2507 | OpenRouter | large open MoE | commented out — needs OpenRouter credit |

`:free` models still need `OPENROUTER_API_KEY`; they just don't draw credit.

## Running

```bash
rm -rf rag_db schema_rag_db                    # after any profile / schema-format change

# one config (30 questions, 8 in parallel, ~1 min)
python eval/run_eval_sts.py --model openai/gpt-4o-mini --rag-top-k 3 --max-retries 2

# matrix: gpt-4o-mini 4 configs × 5 repeats = 20 runs / ~600 calls / ~25 min. Resumable.
python eval/sweep_sts.py

# aggregate → eval/sts/COMPARISON.md
python eval/compare.py
```

Needs `OPENAI_API_KEY` (and `OPENROUTER_API_KEY` once those models are enabled) in
`.env`, and the dev DB reachable at `DATABASE_URL`. Most of the wall time is
sequential LLM latency; `--concurrency` (default 8) trades against the provider's
rate limit.
