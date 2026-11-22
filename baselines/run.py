"""Run a baseline over eval/questions.jsonl and save answers to eval/results/<system>.jsonl (resumable).

Usage:
  python -m baselines.run --system a
  python -m baselines.run --system b
  python -m baselines.run --system b --limit 3
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from generation.llm import DEFAULT_MODEL, is_abstention

ROOT = Path(__file__).resolve().parent.parent
QUESTIONS = ROOT / "eval" / "questions.jsonl"
RESULTS_DIR = ROOT / "eval" / "results"
NAMES = {"a": "a_llm_only", "b": "b_text_rag"}


def summary(rows: list[dict]) -> None:
    ans = [r for r in rows if r["answerable"]]
    una = [r for r in rows if not r["answerable"]]
    pct = lambda xs: f"{100 * sum(xs) / max(len(xs), 1):.0f}%"
    print(f"\nQuestions: {len(rows)} ({len(ans)} answerable, {len(una)} unanswerable/advice)")
    print(f"  abstained on answerable:   {pct([r['abstained'] for r in ans])}  (should be low)")
    print(f"  abstained on unanswerable: {pct([r['abstained'] for r in una])}  (should be high)")
    if any(r["contexts"] for r in rows):
        hits = [any(c["url"] in r["source_url"] for c in r["contexts"]) for r in ans]
        print(f"  right page in top 5:       {pct(hits)}  (retrieval recall@5)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--system", required=True, choices=sorted(NAMES))
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--split", default="test")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    questions = [json.loads(l) for l in QUESTIONS.open(encoding="utf-8") if l.strip()]
    questions = [q for q in questions if q["split"] == args.split][: args.limit]
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / f"{NAMES[args.system]}.jsonl"
    done = {json.loads(l)["id"] for l in out_path.open(encoding="utf-8")} if out_path.exists() else set()
    todo = [q for q in questions if q["id"] not in done]

    passages = {}
    if args.system == "b" and todo:
        from retrieval.text_index import TextIndex, embed
        from .text_rag import K
        hits = TextIndex().search_vectors(embed([q["question"] for q in todo]), K)
        passages = {q["id"]: h for q, h in zip(todo, hits)}

    with out_path.open("a", encoding="utf-8") as out:
        for n, q in enumerate(todo, 1):
            t0 = time.time()
            if args.system == "a":
                from .llm_only import answer
                res = answer(q["question"], args.model)
            else:
                from .text_rag import answer
                res = answer(q["question"], args.model, passages[q["id"]])
            row = {"id": q["id"], "type": q["type"], "answerable": q["answerable"], "question": q["question"],
                   "gold_answer": q["gold_answer"], "source_url": q["source_url"], "system": NAMES[args.system],
                   "model": args.model, **res, "abstained": is_abstention(res["answer"]),
                   "seconds": round(time.time() - t0, 1)}
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            out.flush()
            print(f"[{n}/{len(todo)}] {q['id']} ({row['seconds']}s) {res['answer'][:90]!r}", flush=True)

    summary([json.loads(l) for l in out_path.open(encoding="utf-8")])


if __name__ == "__main__":
    main()
