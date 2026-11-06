"""
检索层评测：只评"该找的块排第几"，不评模型。
"""
import json
import logging
import time
from pathlib import Path

from app.bm25 import build_index as build_bm25_index, search as bm25_search
from app.hybrid import rrf
from app.llm import EMBED_MODEL, embed_client
from app.rerank import rerank
from mcp_servers.schema_server import rank, split_sections

logging.getLogger("httpx2").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "data" / "schema.md"
QUESTIONS_PATH = Path(__file__).with_name("retrieval_questions.jsonl")

# 旧生产方案基线：关键词强制插到 0 号位。已从生产移除，
# 保留在这里只为让对比表可复现。
METRIC_HINTS = {
    "销售额": "8.1",
    "订单数": "8.2",
    "客单价": "8.3",
    "退款率": "8.4",
    "环比": "8.5",
    "上月": "8.6",
    "本月": "8.6",
    "退款金额": "8.7",
    "退款订单": "8.7",
    "取消率": "8.7",
    "销售件数": "8.7",
    "占比": "8.7",
}


def apply_hints(query: str, ranked: list[dict], top_k: int, chunks: list[dict]) -> list[dict]:
    result = list(ranked[:top_k])
    present = {item["section"] for item in result}
    for keyword, prefix in METRIC_HINTS.items():
        if keyword not in query:
            continue
        for chunk in chunks:
            if chunk["section"].startswith(prefix) and chunk["section"] not in present:
                result.insert(0, chunk)
                present.add(chunk["section"])
                break
    return result[:top_k]


def load_questions() -> list[dict]:
    text = QUESTIONS_PATH.read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def build_index() -> tuple[list[dict], list[list[float]]]:
    # 和 schema_server._ensure_index 保持一致
    chunks = split_sections(SCHEMA_PATH.read_text(encoding="utf-8"))
    response = embed_client.embeddings.create(
        model=EMBED_MODEL,
        input=[chunk["text"] for chunk in chunks],
    )
    vectors = [item.embedding for item in response.data]
    return chunks, vectors


_vector_cache: dict[str, list[float]] = {}


def embed_query(text: str) -> list[float]:
    if text not in _vector_cache:
        response = embed_client.embeddings.create(
            model=EMBED_MODEL,
            input=[text]
        )
        _vector_cache[text] = response.data[0].embedding
    return _vector_cache[text]


def evaluate(questions: list[dict], rank_fn) -> tuple[list[int | None], list[str]]:
    ranks: list[int | None] = []
    tops: list[str] = []
    for question in questions:
        ordered = rank_fn(question["query"])
        tops.append(ordered[0]["section"] if ordered else " (无字面匹配) ")
        position = next((i for i, chunk in enumerate(ordered, start=1)
                         if chunk["section"] == question["gold"]),
                        None, )
        ranks.append(position)
    return ranks, tops


def print_row(label: str, ranks: list[int | None]) -> None:
    total = len(ranks)
    at1 = sum(1 for r in ranks if r == 1)
    at5 = sum(1 for r in ranks if r and r <= 5)
    mrr = sum(1 / r for r in ranks if r) / total
    print(f"{label:<6} {at1:>3}/{total:<3} {at5:>6} / {total:<3} {mrr:>7.3f}")


def report(label: str, questions: list[dict], ranks: list[int | None]) -> None:
    easy = [r for q, r in zip(questions, ranks) if q["difficulty"] == "easy"]
    hard = [r for q, r in zip(questions, ranks) if q["difficulty"] == "hard"]
    print_row(label, ranks)
    print_row("  easy", easy)
    print_row("  hard", hard)


def main() -> None:
    chunks, vectors = build_index()
    sections = {chunk["section"] for chunk in chunks}
    questions = load_questions()

    print(f"切块 {len(chunks)} 块，题目 {len(questions)} 道")

    missing = [q["id"] for q in questions if q["gold"] not in sections]
    if missing:
        print("gold 对不上切块标题：", ", ".join(missing))
        return

    bm25_index = build_bm25_index(chunks)

    vector_ranks, vector_tops = evaluate(questions,
                                         lambda query: rank(embed_query(query), vectors, chunks, len(chunks)))
    bm25_ranks, _ = evaluate(
        questions,
        lambda query: bm25_search(query, bm25_index, len(chunks)))

    def hybrid_order(query: str) -> list[dict]:
        return rrf([rank(embed_query(query), vectors, chunks, 10),
                    bm25_search(query, bm25_index, 10), ], len(chunks))

    hybrid_ranks, _ = evaluate(questions, hybrid_order)

    def rerank_order(query: str) -> list[dict]:
        candidates = rank(embed_query(query), vectors, chunks, 10)
        scores = rerank(query, [chunk["text"] for chunk in candidates])
        ordered = sorted(zip(scores, candidates), key=lambda item: item[0], reverse=True)
        return [chunk for _, chunk in ordered]

    started = time.perf_counter()
    rerank_ranks, _ = evaluate(questions, rerank_order)
    print(f"重排整行耗时 {time.perf_counter() - started:.1f}s（{len(questions)} 题）")

    def hybrid_rerank_order(query: str) -> list[dict]:
        candidates = rrf([rank(embed_query(query), vectors, chunks, 10), bm25_search(query, bm25_index, 10)], 10)
        scores = rerank(query, [chunk["text"] for chunk in candidates])
        ordered = sorted(zip(scores, candidates), key=lambda item: item[0], reverse=True)
        return [chunk for _, chunk in ordered]

    hybrid_rerank_ranks, _ = evaluate(questions, hybrid_rerank_order)

    def hint_order(query: str) -> list[dict]:
        ranked = rank(embed_query(query), vectors, chunks, 5)
        return apply_hints(query, ranked, 5, chunks)

    hint_ranks, _ = evaluate(questions, hint_order)

    print(f"\n{'方法':<6} {'recall@1':>9} {'recall@5':>10} {'MRR':>7}")
    report("向量", questions, vector_ranks)
    report("BM25", questions, bm25_ranks)
    report("混合", questions, hybrid_ranks)
    report("向量+重排", questions, rerank_ranks)
    report("混合+重排", questions, hybrid_rerank_ranks)
    report("向量+提示", questions, hint_ranks)

    print("\n向量没排第一的题：")
    for question, position, top in zip(questions, vector_ranks, vector_tops):
        if position != 1:
            print(f"  第{position or '?'}名 {question['id']} {question['query']}  →  {top}")


if __name__ == '__main__':
    main()
