"""
Schema MCP Server：把 data/schema.md
按小节切块、向量化，提供 search_schema。
只读本文件旁边的 schema.md；Agent 应用不参与。
"""

import logging
import math
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from app.llm import EMBED_MODEL, embed_client

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "data" / "schema.md"

# stdio 传输时 stdout 是协议通道，日志必须走 stderr
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr
)
logger = logging.getLogger("schema_server")

mcp = FastMCP("schema-server")

_chunks: list[dict] | None = None
_vectors: list[list[float]] | None = None


def split_sections(text: str) -> list[dict]:
    """按 ## / ### 标题切块，每块保留标题和正文"""
    chunks = []
    section = None
    lines: list[str] = []
    for line in text.splitlines():
        if line.startswith("## ") or line.startswith("### "):
            if section is not None:
                chunks.append({"section": section, "text": "\n".join(lines).strip()})
            section = line.lstrip("#").strip()
            lines = [line]
        elif section is not None:
            lines.append(line)
    if section is not None:
        chunks.append({"section": section, "text": "\n".join(lines).strip()})
    return chunks


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0
    return dot / (na * nb)


def rank(
        query_vector: list[float],
        vectors: list[list[float]],
        chunks: list[dict],
        top_k: int,
) -> list[dict]:
    scored = [
        (cosine(query_vector, vector), chunk)
        for vector, chunk in zip(vectors, chunks)
    ]
    scored.sort(key=lambda item: item[0], reverse=True)
    return [chunk for _, chunk in scored[:top_k]]


def _ensure_index() -> None:
    global _chunks, _vectors
    if _chunks is not None and _vectors is not None:
        return

    text = SCHEMA_PATH.read_text(encoding="utf-8")
    _chunks = split_sections(text)
    response = embed_client.embeddings.create(
        model=EMBED_MODEL,
        input=[chunk["text"] for chunk in _chunks],
    )
    _vectors = [item.embedding for item in response.data]
    logger.info("schema index ready: %d chunks", len(_chunks))


@mcp.tool()
def search_schema(query: str, top_k: int = 3) -> dict:
    """按语义检索 schema.md 的小节，返回最相关的 top_k 块。"""
    _ensure_index()
    if _chunks is None or _vectors is None:
        raise RuntimeError("schema index not ready")

    top_k = max(1, min(top_k, 5))
    response = embed_client.embeddings.create(
        model=EMBED_MODEL,
        input=[query]
    )
    query_vector = response.data[0].embedding
    return {"chunks": rank(query_vector, _vectors, _chunks, top_k)}


if __name__ == '__main__':
    mcp.run(transport="stdio")
