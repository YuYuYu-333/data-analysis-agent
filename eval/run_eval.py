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

from app.graph import analyze
from eval.judge import rows_match

ROOT = Path(__file__).resolve().parents[1]
QUESTIONS = ROOT / "eval" / "questions.jsonl"
DB_PATH = ROOT / "data" / "retail.db"


def load_questions() -> list[dict]:
    with QUESTIONS.open(encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    return [row for row in rows if row["turn"] == 1]


def reference_rows(sql: str) -> list[list]:
    uri = f"file:{DB_PATH.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        return [list(row) for row in conn.execute(sql).fetchall()]
    finally:
        conn.close()


async def run(mode: str) -> dict:
    questions = load_questions()
    results = []

    for item in questions:
        state = await analyze(
            item["question"],
            session_id=f"eval-{item['session_id']}",
            schema_mode=mode,
        )
        expected = reference_rows(item["reference_sql"])
        actual = state.get("rows") or []
        correct = rows_match(expected, actual, ordered=item.get("ordered", False))
        results.append(
            {
                "session_id": item["session_id"],
                "level": item["level"],
                "attempts": state.get("attempts", 0),
                "correct": correct,
                "sql": state.get("sql"),
                "error": state.get("error"),
            }
        )
        print(
            f"{item['session_id']} {item['level']:6}"
            f"attempts={state.get('attempts', 0)} correct = {correct}"
        )

    total = len(results)
    first = sum(1 for r in results if r["correct"] and r["attempts"] == 1)
    final = sum(1 for r in results if r["correct"])
    successes = [r["attempts"] for r in results if r["correct"]]

    return {
        "mode": mode,
        "total": total,
        "first_success": first,
        "final_successes": final,
        "first_rate": round(first / total, 4) if total else 0,
        "final_rate": round(final / total, 4) if total else 0,
        "avg_attempts": round(sum(successes) / len(successes), 2) if successes else 0,
        "details": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["columns", "rag"], required=True)
    args = parser.parse_args()
    summary = asyncio.run(run(args.mode))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
