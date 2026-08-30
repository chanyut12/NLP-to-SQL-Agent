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

## Metrics (`run_eval_sts.py`)

Result-set equivalence against the gold SQL (order-insensitive, floats rounded).
Reported overall, by `source_tag`, and by category:

- **execution_accuracy** — result matches gold (primary)
- **first_try_success** — matched with `retry_count == 0`
- **grain_correct** — same row count as gold (no duplicate amplification)
- **sql_validity / executability**
- **p50 / p95 latency**, **error_classes** (`no_sql`, `exec_fail`, `wrong_grain`, `wrong_result`)

## Models

Slugs live at the top of `eval/sweep_sts.py` — verify against openrouter.ai/models first.

| Model | via | role |
|---|---|---|
| gpt-4o-mini | OpenAI | anchor — full RAG×retry ablation |
| deepseek/deepseek-chat (v3) | OpenRouter | open-weight, code-strong |
| qwen/qwen3-235b-a22b-2507 | OpenRouter | large open MoE |
| z-ai/glm-5.2:free | OpenRouter | free-tier viability |

## Running

```bash
# one config
python eval/run_eval_sts.py --model openai/gpt-4o-mini --rag-top-k 5 --max-retries 2

# full matrix (anchor: 8 configs × 5 repeats; others: best-config × 5). Resumable.
python eval/sweep_sts.py

# aggregate → eval/sts/COMPARISON.md
python eval/compare.py
```

Needs `OPENAI_API_KEY`, `OPENROUTER_API_KEY` in `.env`, and the dev DB reachable
at `DATABASE_URL`.
