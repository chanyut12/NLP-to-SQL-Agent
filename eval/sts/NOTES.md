## Findings

**RAG few-shot is the whole game.** Going from `rag_top_k=0` to `rag_top_k=3`
takes gpt-4o-mini from **3% → 47%** strict EX (**30% → 76%** relaxed). Nothing else
in the sweep moves the number remotely as much. The three worked examples give the
model the STS join paths and the "current student" resolution rule that the schema
alone does not convey. deepseek-v4-flash shows the same jump (**13% → 50%**).

**Self-correction (retry) buys almost nothing.** `retry=0 → retry=2` is 47% → 47%
strict at `rag=3` for gpt-4o-mini (73% → 76% relaxed, within noise). The engine only
retries on an execution error, and at `rag=3` the SQL already executes ~88% of the
time — so there is little for the retry loop to fix, and its main effect is ~3× the
token cost and latency on the questions it touches. `retry=0` is the better default.

**The strict/relaxed gap is column selection, not arithmetic.** Relaxed EX minus
strict EX is ~29 points of `cols_only` for both models: the query returns the right
numbers grouped the right way, but with an extra or differently-named descriptive
column. Fine for a dashboard; fails exact-match scoring.

**By question source (gpt-4o-mini):** paraphrase **70%** > held_out **48%** >
novel **12%**. The model handles rewordings of corpus questions well and falls apart
on genuinely novel metric×grain combinations (novel also has the widest variance,
±11%, on only 8 questions). deepseek-v4-flash is the exception — its `novel` score
is **62%**, far above gpt-4o-mini, though on a single run.

**Latency & cost:** gpt-4o-mini p50 6.6 s at `rag=3, retry=2`; the full 20-cell
sweep cost **≈ $1.53**. deepseek-v4-flash is ~4× slower (p50 24.8 s) but ~3× cheaper
per token; its 2-cell run cost **≈ $0.07**.

**Bottom line:** ship at `rag=3, retry=0`. Invest further gains in the example set
(novel coverage) and in tightening column selection, not in the retry loop.

---

## deepseek/deepseek-v4-flash-0731 — single run, has timeouts

- One run per config (`rag=0` / `rag=3`, both `retry=2`) — **no ± yet**, treat as
  indicative, not a verdict. gpt-4o-mini has 5 runs per cell.
- **The OpenRouter provider for this model stalls mid-stream** on some questions.
  Runs only completed after a **per-question hard timeout (`--question-timeout 150`,
  added to `run_eval_sts.py`)** — a stuck question is marked `timeout` (counts as a
  miss) and the run continues. `rag=0` hit **8 timeouts / 30**, `rag=3` hit **1**.
- So `rag=0`'s 13% is a floor: some of the 8 timeouts might have passed given
  unlimited time. `rag=3` (1 timeout) is close to a clean number.

| config | EX | EX relaxed | first-try | grain | held_out | paraphrase | novel | p50 s | timeouts |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| rag=3, retry=2 | **50%** | 83% | 50% | 97% | 40% | 50% | **62%** | 24.8 | 1/30 |
| rag=0, retry=2 | 13% | 43% | 13% | 70% | 20% | 8% | 12% | 69.8 | 8/30 |

**vs gpt-4o-mini (rag=3, retry=2):** EX 50% vs 47% — effectively **tied** on the
headline number. deepseek wins clearly on `novel` (62% vs 12%) and `grain` (97% vs
87%), loses badly on speed (4× slower) and reliability (provider stalls). A real
comparison needs deepseek run 5× like the anchor, ideally via a stable provider
(DeepSeek's own API).
