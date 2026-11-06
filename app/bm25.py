"""
BM25 检索：只看字面重合，不理解语义。
中文没有空格，用字符二元组当词："退款率" ->
"退款","款率"
不需要分词库，代价是词序信息丢失。
"""

import math
from collections import Counter

_K1 = 1.5
_B = 0.75


def tokenize(text: str) -> list[str]:
    """切成字符二元组，去掉所有空白"""
    text = "".join(ch for ch in text if not
    ch.isspace())
    if len(text) < 2:
        return [text] if text else []
    return [text[i:i + 2] for i in range(len(text) - 1)]


def build_index(chunks: list[dict]) -> dict:
    """把 22 块的字频和文档频率算好，查询时直接复用。"""
    docs = [Counter(tokenize(item["text"])) for item in chunks]
    df = Counter()
    for counts in docs:
        for term in counts:
            df[term] += 1
    total = sum(sum(counts.values()) for counts in docs)
    return {
        "chunks": chunks,
        "docs": docs,
        "df": df,
        "avg_len": total / len(docs) if docs else
        0.0,
    }


def search(query: str, index: dict, top_k: int = 5) -> list[dict]:
    """返回按得分降序的块；0 分的也保留，保证排名完整。"""
    chunks = index["chunks"]
    docs = index["docs"]
    df = index["df"]
    avg_len = index["avg_len"]
    n = len(docs)
    query_terms = Counter(tokenize(query))

    scored = []
    for chunk, counts in zip(chunks, docs):
        length = sum(counts.values())
        score = 0.0
        for term, query_count in query_terms.items():
            frequency = counts.get(term, 0)
            if not frequency:
                continue
            idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
            denominator = frequency + _K1 * (1 - _B + _B * length / avg_len)
            score += idf * frequency * (_K1 + 1) / denominator * query_count
        if score > 0:
            scored.append((score, chunk))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [chunk for _, chunk in scored[:top_k]]
