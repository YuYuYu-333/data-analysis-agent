"""Schema MCP Server：切块、余弦与排序。"""

import types

from mcp_servers import schema_server
from mcp_servers.schema_server import SCHEMA_PATH, cosine, rank, split_sections


def test_split_sections_keeps_headers_and_body():
    text = (
        "# 标题\n\n"
        "## 1. 表清单\n内容 A\n\n"
        "### 1.1 门店\n内容 B\n\n"
        "## 2. 枚举\n内容 C\n"
    )
    chunks = split_sections(text)
    assert [c["section"] for c in chunks] == ["1. 表清单", "1.1 门店", "2. 枚举"]
    assert "内容 A" in chunks[0]["text"]
    assert "内容 B" in chunks[1]["text"]


def test_cosine():
    assert cosine([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert cosine([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_rank_orders_by_similarity():
    chunks = [{"section": "a"}, {"section": "b"}]
    vectors = [[1.0, 0.0], [0.0, 1.0]]
    result = rank([1.0, 0.0], vectors, chunks, 1)
    assert result[0]["section"] == "a"


def test_real_schema_has_sections():
    chunks = split_sections(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert len(chunks) >= 10
    assert any("指标口径" in c["section"] for c in chunks)


def _fake_client(vector):
    class _Embeddings:
        def create(self, **kwargs):
            return types.SimpleNamespace(
                data=[types.SimpleNamespace(embedding=vector)]
            )

    return types.SimpleNamespace(embeddings=_Embeddings())


def _prepare(monkeypatch, vector):
    chunks = [{"section": "a", "text": "A"},
              {"section": "b", "text": "B"}]
    vectors = [[1.0, 0.0], [0.0, 1.0]]
    monkeypatch.setattr(schema_server, "_chunks", chunks)
    monkeypatch.setattr(schema_server, "_vectors", vectors)
    monkeypatch.setattr(schema_server, "_ensure_index", lambda: None)
    monkeypatch.setattr(schema_server, "embed_client", _fake_client(vector))


def test_search_schema_uses_rerank_order(monkeypatch):
    _prepare(monkeypatch, [1.0, 0.0])
    monkeypatch.setattr(schema_server, "rerank", lambda query, docs: [0.1, 0.9])
    result = schema_server.search_schema("问题", top_k=2)
    assert [c["section"] for c in result["chunks"]] == ["b", "a"]


def test_search_schema_falls_back_when_rerank_fails(monkeypatch):
    _prepare(monkeypatch, [1.0, 0.0])

    def boom(query, docs):
        raise RuntimeError("rerank down")

    monkeypatch.setattr(schema_server, "rerank", boom)
    result = schema_server.search_schema("问题", top_k=2)
    assert [c["section"] for c in result["chunks"]] == ["a", "b"]
