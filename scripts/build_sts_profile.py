"""Build profiles/sts/examples.json + heldout_ids.json from the STS RAG corpus.

- Holds out 10 examples (stratified by primary schema pack) for evaluation; these
  are removed from the retrieval corpus so eval cannot retrieve its own answer.
- Inlines the corpus's parameter values into the SQL so the remaining examples are
  directly executable few-shot (the Tier-1 engine does not bind $n placeholders).
"""

import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "TEXT_TO_SQL_STS_RAG_EXAMPLES.json")
OUT_DIR = os.path.join(ROOT, "profiles", "sts")
DB_URL = os.getenv("STS_DB_URL", "postgresql://postgres:stsLocalDev2026@localhost:5432/sts")

# primary pack -> how many to hold out. Skewed toward the domains that actually
# have data in the dev DB (task_assistance measures are empty; cases are ~all OPEN).
HELDOUT_PER_PACK = {
    "student_enrollment": 3,
    "attendance": 3,
    "risk_case": 3,
    "teacher_comment_analytics": 1,
    "task_assistance": 0,
    "teacher_subject": 0,
}


def primary_pack(ex: dict) -> str:
    """The most specific pack — bridge packs (student_enrollment) come first in the list."""
    packs = ex.get("schema_packs", [])
    return packs[-1] if packs else "student_enrollment"


def inline_params(sql: str, params: list) -> str:
    if not params:
        return sql
    by_pos = {p["position"]: p for p in params}

    def repl(m):
        p = by_pos.get(int(m.group(1)))
        if p is None:
            return m.group(0)
        v = p["value"]
        if p["type"] in ("integer", "numeric"):
            return str(v)
        return "'" + str(v).replace("'", "''") + "'"

    return re.sub(r"\$(\d+)", repl, sql)


def executable_ids(examples: list) -> set:
    """ids whose (param-inlined) SQL passes EXPLAIN on the live DB. Empty set if no DB."""
    try:
        import psycopg2
        conn = psycopg2.connect(DB_URL, connect_timeout=3)
    except Exception as e:
        print(f"WARN: no DB ({e}); skipping executability filter")
        return {e["id"] for e in examples}
    ok = set()
    for ex in examples:
        cur = conn.cursor()
        try:
            cur.execute("EXPLAIN " + inline_params(ex["sql"], ex.get("parameters", [])))
            ok.add(ex["id"])
        except Exception as err:
            print(f"  drop {ex['id']}: {str(err).splitlines()[0][:80]}")
        finally:
            conn.rollback()
    conn.close()
    return ok


def main():
    corpus = json.load(open(SRC, encoding="utf-8"))
    examples = corpus["examples"]

    runnable = executable_ids(examples)
    examples = [e for e in examples if e["id"] in runnable]

    # deterministic stratified hold-out
    by_pack: dict = {}
    for ex in sorted(examples, key=lambda e: e["id"]):
        by_pack.setdefault(primary_pack(ex), []).append(ex)

    heldout_ids = set()
    for pack, n in HELDOUT_PER_PACK.items():
        pool = by_pack.get(pack, [])
        seen_cats: set = set()
        picked = []
        for ex in pool:
            if len(picked) >= n:
                break
            if ex["category"] not in seen_cats or len(pool) - pool.index(ex) <= n - len(picked):
                picked.append(ex)
                seen_cats.add(ex["category"])
        heldout_ids.update(e["id"] for e in picked)

    kept = []
    for ex in examples:
        if ex["id"] in heldout_ids:
            continue
        kept.append({
            "id": ex["id"],
            "question": ex["question"],
            "sql": inline_params(ex["sql"], ex.get("parameters", [])),
            "category": ex["category"],
            "dialect": "postgresql",
            "grain": ex.get("grain", ""),
            "schema_packs": ex.get("schema_packs", []),
            "retrieval_tags": ex.get("retrieval_tags", []),
        })

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "examples.json"), "w", encoding="utf-8") as f:
        json.dump({
            "description": "STS few-shot Example set (parameters inlined, eval hold-out removed)",
            "version": corpus["version"],
            "source": "TEXT_TO_SQL_STS_RAG_EXAMPLES.json",
            "examples": kept,
        }, f, ensure_ascii=False, indent=2)

    with open(os.path.join(OUT_DIR, "heldout_ids.json"), "w", encoding="utf-8") as f:
        json.dump(sorted(heldout_ids), f, ensure_ascii=False, indent=2)

    print(f"corpus {len(examples)} -> kept {len(kept)}, held out {len(heldout_ids)}")
    print("held out:", sorted(heldout_ids))


if __name__ == "__main__":
    main()
