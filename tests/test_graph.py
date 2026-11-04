"""
图：SQL 抽取、路由和答案格式化（不调模型）。
"""

from app.graph import _extract_sql, route, verify_citations


def test_extract_sql_plain():
    assert _extract_sql("SELECT 1") == "SELECT 1"


def test_extract_sql_code_fence():
    assert _extract_sql("```sql\nSELECT 1\n```") == "SELECT 1"


def test_extract_sql_with_explanation():
    assert _extract_sql("这是查询：\nSELECT 1;") == "SELECT 1;"


def test_route_retry():
    assert route({"error": "bad", "attempts": 1}) == "retry"


def test_route_give_up():
    assert route({"error": "bad", "attempts": 3}) == "give_up"


def test_route_answer():
    assert route({"error": None, "attempts": 1}) == "answer"


def test_verify_citations_ok():
    result = verify_citations({
        "columns": ["sales"],
        "rows": [[12345.67]],
        "answer": "销售额为 12345.67 元。",
        "question": "销售额是多少？",
    })
    assert result["degraded"] is False
    assert len(result["citations"]) == 1


def test_verify_citations_degrades_on_fake_number():
    result = verify_citations({
        "columns": ["sales"],
        "rows": [[12345.67]],
        "answer": "销售额为 999.00 元。",
        "question": "销售额是多少？",
    })
    assert result["degraded"] is True
    assert result["answer"].startswith("sales")


def test_verify_citations_skips_when_no_rows():
    result = verify_citations({"columns": ["n"], "rows": [], "answer": "没有查到符合条件的数据。"})
    assert result["degraded"] is False
