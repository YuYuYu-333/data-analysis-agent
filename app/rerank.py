"""
用 cross-encoder 重排候选块。
向量检索分别编码问题和文档，重排模型把两者拼在一起
读，
能理解条件和否定，代价是每对都要单独算一次。
"""

import httpx

from app.config import SILICONFLOW_API_KEY

RERANK_MODEL = "BAAI/bge-reranker-v2-m3"
_URL = "https://api.siliconflow.cn/v1/rerank"
_TIMEOUT = 5.0


def rerank(query: str, documents: list[str]) -> list[float]:
    """返回与 documents 等长的分数列表，顺序和输入一致。"""
    response = httpx.post(
        _URL,
        headers={"Authorization": f"Bearer {SILICONFLOW_API_KEY}"},
        json={"model": RERANK_MODEL, "query": query, "documents": documents},
        timeout=_TIMEOUT,
    )
    response.raise_for_status()

    scores = [0.0] * len(documents)
    for item in response.json()["results"]:
        scores[item["index"]] = item["relevance_score"]
    return scores
