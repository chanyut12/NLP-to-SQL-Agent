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
