"""Schema MCP Server：切块、余弦与排序。"""

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
