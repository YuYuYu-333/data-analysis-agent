"""
图：SQL 抽取、路由和答案格式化（不调模型）。
"""

from app.graph import _extract_sql, build_answer, route


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


def test_build_answer_rows():
    result = build_answer({"columns": ["n"], "rows": [[12]]})
    assert result["answer"] == "n\n12"


def test_build_answer_empty():
    result = build_answer({"columns": ["n"], "rows": []})
    assert result["answer"] == "没有查到符合条件的数据。"


def test_build_answer_appends_history():
    result = build_answer(
        {
            "question": "q1",
            "sql": "SELECT 1",
            "columns": ["n"],
            "rows": [[1]],
            "history": [],
        }
    )
    assert result["history"] == [{"question": "q1", "sql": "SELECT 1"}]


def test_build_answer_keeps_last_two_history():
    result = build_answer(
        {
            "question": "q3",
            "sql": "SELECT 3",
            "columns": ["n"],
            "rows": [[3]],
            "history": [
                {"question": "q1", "sql": "s1"},
                {"question": "q2", "sql": "s2"},
            ],
        }
    )
    assert [item["question"] for item in result["history"]] == ["q2", "q3"]
