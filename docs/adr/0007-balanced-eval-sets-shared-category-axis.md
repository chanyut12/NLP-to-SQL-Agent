# Balanced evaluation sets on a shared category axis

The professor's requirement — evaluation questions and few-shot examples should be
evenly distributed so eval results are meaningful — collides with two measured facts:
the golden set's 30 questions scatter across 14 category tags (one tag holds ~9 of 30),
and the 86-example corpus is a ~38% count monoculture while the hardest shapes
(having-threshold, ranking) have the least few-shot fuel (6 and 2 examples). Per-bucket
eval numbers were partly measuring retrieval starvation, not model ability.

We consolidated the 14 tags into **7 shared category buckets** (count_groupby,
count_filter_groupby, aggregation_groupby, ratio_groupby, having_threshold, time_groupby,
ranking) — the single primary distribution axis for **both** sets. Domain area is a
reported coverage axis only. Quotas: golden set = 4 questions × 7 buckets + 4 ambiguous +
4 deny (36 total, surplus count questions retired); example set = ~8 per bucket (~56
total, surplus demoted to an on-disk archive never loaded by retrieval) plus a 3 clarify +
3 refusal exemplar block outside the quotas. The eval harness refuses to run when a set
deviates from its quota, so balance cannot silently decay. Sequencing: rebalance corpus →
carve new held_out questions from it → freeze both sets → re-baseline once.

Why demote instead of add-only: keeping all 33 count examples while adding ranking
examples preserves the monoculture inside top-k retrieval — balance on paper, bias in
practice. The archive (not deletion) keeps the change reversible. Deny-before-clarify
scoring follows ADR 0006: a deny question answered with a Clarification fails.

Consequences: one re-baseline breaks comparability with pre-balance numbers (kept as
the "before" figure); balancing slightly thins count-shaped few-shot depth even though
real traffic skews count — accepted because retrieval top-k, not corpus mass, is what
reaches the prompt.

## Amendment (Oct 2026): regression block outside the bucket quotas

The frozen Golden set (36 questions) says nothing about examples added after the
freeze, so a later corpus edit could silently break them. We add a third block to the
Golden set, alongside ambiguous and deny: **9 regression questions** (8 at the amendment, 1 added with the province concern ranking) (`source_tag:
"regression"`), each a paraphrase of a post-freeze example whose gold SQL is that
example's SQL, so it is checked by result equivalence like any other question.

- The block sits **outside the 4 × 7 bucket quotas**, the same way the clarify/refusal
  exemplars sit outside the Example set's quotas. Regression items never count toward a
  bucket, so the bucket balance this ADR protects is untouched.
- `REGRESSION_QUOTA = 9`; the eval harness refuses to run when the block deviates, like
  every other quota. Golden set total: 36 + 9 = 45.
- Growing the block later means changing `REGRESSION_QUOTA` in the same commit, so the
  size stays a deliberate decision.
- They cover the STS cause chain: province concern ranking, risk factors, why cases were opened, case counts per
  school and province, home-visit absence reasons / root causes / parental status, and
  referrals by agency kind.

Known gap, not decided here: the quota gate audits `data/corpus/
TEXT_TO_SQL_STS_RAG_EXAMPLES.json` (62 examples), while the engine retrieves from
`profiles/sts/examples.json` (69). Post-freeze examples live only in the latter, so the
Example-set quota does not cover them.
