"""
向量与 BM25 的混合检索，用 RRF 融合。
两种分数不可比：cos 在 -1~1，BM25 没有上限。
所以只看名次，不看分数。
"""

_RRF_K = 60


def rrf(ordered_lists: list[list[dict]], top_k: int) -> list[dict]:
    """每块得分 = sum(1 / (k + 名次))，出现在多路结果里的块自然得分更高。"""
    scores: dict[str, float] = {}
    chunks: dict[str, dict] = {}
    for ordered in ordered_lists:
        for position, chunk in enumerate(ordered, start=1):
            name = chunk["section"]
            chunks[name] = chunk
            scores[name] = scores.get(name, 0.0) + 1 / (_RRF_K + position)
    ranked = sorted(scores, key=lambda name: scores[name], reverse=True)
    return [chunks[name] for name in ranked[:top_k]]
