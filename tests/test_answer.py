"""
溯源校验：抽数字、忽略规则、比对、拼表格。
"""

from app.answer import find_citations, format_table, numbers_in


def test_numbers_in_strips_thousands_separator():
    assert numbers_in("销售额 12,345.67 元") == [12345.67]


def test_citation_found_in_rows():
    citations, missing = find_citations("销售额为 12345.67 元。", ["sales"], [[12345.67]])
    assert missing == []
    assert citations == [{"value": 12345.67, "row": 0, "column": "sales"}]


def test_number_not_in_rows_is_missing():
    citations, missing = find_citations("销售额为 999.00 元。", ["sales"], [[12345.67]])
    assert citations == []
    assert missing == [999.0]


def test_percent_matches_ratio_cell():
    citations, missing = find_citations("占比 52.31 %。", ["share"], [[0.5231]])
    assert missing == []
    assert citations[0]["value"] == 0.5231


def test_numbers_from_question_are_ignored():
    citations, missing = find_citations(
        "2026 年 9 月销售额最高的 5 个商品共 12345.67 元。", ["sales"], [[12345.67]],
        question="2026 年 9 月销售额最高的 5 个商品？", )
    assert missing == []
    assert len(citations) == 1


def test_date_suffix_numbers_are_ignored():
    citations, missing = find_citations("2026 年 9 月共 12 家店。", ["store_count"], [[12]])
    assert missing == []
    assert len(citations) == 1


def test_format_table_marks_truncation():
    text = format_table(["a"], [[1], [2], [3]], limit=2)
    assert "共 3 行" in text


def test_format_table_without_truncation():
    assert format_table(["a"], [[1], [2]]) == "a\n1\n2"


def test_identifier_digits_are_not_numbers():
    assert numbers_in("订单 O000590") == []


def test_identifier_in_answer_does_not_break_citation():
    citations, missing = find_citations(
        "订单 O000590 的金额是 421.45 元。",
        ["order_id", "amount"],
        [["O000590", 421.45]],
    )
    assert missing == []
    assert len(citations) == 1


def test_sign_flip_still_counts_as_citation():
    citations, missing = find_citations(
        "比上月少了 2445.54。", ["diff"],
        [[-2445.54]], "9月比8月多了多少")
    assert not missing
    assert citations[0]["value"] == -2445.54
