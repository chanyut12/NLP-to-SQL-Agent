# STS Text-to-SQL — model comparison

## Model comparison (best config: rag=3, retry=2)

| Model | runs | EX | EX relaxed | first-try | grain | held-out | paraphrase | novel | p50 s | p95 s |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| openai/gpt-4o-mini | 5 | 47% ±4% | 76% ±3% | 44% ±4% | 87% ±4% | 48% ±4% | 70% ±4% | 12% ±11% | 6.6 | 21.2 |

## Ablation — openai/gpt-4o-mini

| rag_top_k | retry | runs | EX | first-try | grain | p50 s |
|--:|--:|--:|--:|--:|--:|--:|
| 0 | 0 | 5 | 3% | 3% | 70% ±6% | 4.4 |
| 0 | 2 | 5 | 5% ±2% | 5% ±2% | 69% ±3% | 7.0 |
| 3 | 0 | 5 | 47% ±2% | 47% ±2% | 88% ±4% | 6.2 |
| 3 | 2 | 5 | 47% ±4% | 44% ±4% | 87% ±4% | 6.6 |
