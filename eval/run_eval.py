"""
单轮评测：跑 turn=1 的题，对比参考 SQL 和系统结果。
用法：
    python -m eval.run_eval --mode columns
    python -m eval.run_eval --mode rag
"""

import argparse
import asyncio
import json
import sqlite3
from pathlib import Path
from datetime import datetime

from app.checkpointer import close_checkpointer
from app.graph import analyze
from eval.judge import rows_match

ROOT = Path(__file__).resolve().parents[1]
QUESTIONS = ROOT / "eval" / "questions.jsonl"
DB_PATH = ROOT / "data" / "retail.db"


def load_questions(turns: str, session: str | None = None) -> list[dict]:
    with QUESTIONS.open(encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    if turns == "first":
        rows = [row for row in rows if row["turn"] == 1]
    if session:
        rows = [row for row in rows if row["session_id"] == session]
    return sorted(rows, key=lambda row: (row["session_id"], row["turn"]))


def reference_rows(sql: str) -> list[list]:
    uri = f"file:{DB_PATH.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        return [list(row) for row in conn.execute(sql).fetchall()]
    finally:
        conn.close()


def summarize(mode: str, results: list[dict]) -> dict:
    total = len(results)
    correct = [r for r in results if r["correct"]]
    first = [r for r in correct if r["attempts"] == 1]
    multi = [r for r in results if r["turn"] > 1]
    multi_correct = [r for r in multi if r["correct"]]

    def rate(part: int, whole: int) -> float:
        return round(part / whole, 4) if whole else 0.0

    by_level = {}
    for level in ("easy", "medium", "hard"):
        rows = [r for r in results if r["level"] == level]
        hits = sum(1 for r in rows if r["correct"])
        by_level[level] = {"total": len(rows), "correct": hits, "rate": rate(hits, len(rows))}

    return {
        "mode": mode,
        "total": total,
        "first_success": len(first),
        "first_rate": rate(len(first), total),
        "final_success": len(correct),
        "final_rate": rate(len(correct), total),
        "avg_attempts": round(sum(r["attempts"] for r in correct) / len(correct), 2) if correct else 0,
        "coref_total": len(multi),
        "coref_correct": len(multi_correct),
        "coref_rate": rate(len(multi_correct), len(multi)),
        "by_level": by_level,
        "details": results,
    }


async def run(mode: str, turns: str, session: str | None = None) -> dict:
    questions = load_questions(turns, session)
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    results = []

    for item in questions:
        state = await analyze(
            item["question"],
            session_id=f"eval-{run_id}-{item['session_id']}",
            schema_mode=mode,
        )
        expected = reference_rows(item["reference_sql"])
        actual = state.get("rows") or []
        correct = rows_match(expected, actual, ordered=item.get("ordered", False))
        results.append(
            {
                "session_id": item["session_id"],
                "turn": item["turn"],
                "level": item["level"],
                "attempts": state.get("attempts", 0),
                "correct": correct,
                "sql": state.get("sql"),
                "error": state.get("error"),
            }
        )
        print(
            f"{item['session_id']} T{item['turn']} {item['level']:6}"
            f"attempts={state.get('attempts', 0)} correct = {correct}"
        )
    await close_checkpointer()
    return summarize(mode, results)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["columns", "rag"], required=True)
    parser.add_argument("--turns", choices=["first", "all"], default="all")
    parser.add_argument("--session", default=None, help="只跑某个会话，例如 E09")
    args = parser.parse_args()
    summary = asyncio.run(run(args.mode, args.turns, args.session))

    out = ROOT / "eval" / f"raw-{args.mode}-{args.turns}-{args.session or 'all'}.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "details"}, ensure_ascii=False, indent=2))
    print(f"明细已写入 {out}")


if __name__ == '__main__':
    main()
