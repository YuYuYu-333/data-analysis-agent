"""
答案的溯源校验：回答里的每个数字，都必须能在查询结果里找到。
纯函数，不调模型、不碰数据库，所以可以直接写单测。
"""

import re

TOLERANCE = 1e-6
_TOKEN = re.compile(r"(?<![A-Za-z0-9])(-?\d[\d,]*(?:\.\d+)?)\s*(%?)")
_DATE_SUFFIX = "年月日号"
_DATE = re.compile(r"(?<!\d)\d{4}\s*[-/]\s*\d{1,2}(?:\s*[-/]\s*\d{1,2})?(?!\d)")


def _round_for_compare(value: float) -> float:
    """和 judge 用同一把尺子: 小于 1 的取 4 位, 其余取 2 位"""
    if abs(value) < 1:
        return round(value, 4)
    return round(value, 2)


def _same(left: float, right: float) -> bool:
    return abs(_round_for_compare(left) - _round_for_compare(right)) < TOLERANCE


def _tokens(text: str):
    """逐个吐出(数值,是否百分号,是否日期的一部分)"""
    body = text or ""
    date_spans = [(match.start(), match.end()) for match in _DATE.finditer(body)]
    for match in _TOKEN.finditer(body):
        if any(start <= match.start() < end for start, end in date_spans):
            continue
        after = body[match.end():match.end() + 3].lstrip()
        is_date = bool(after) and after[0] in _DATE_SUFFIX
        yield float(match.group(1).replace(",", "")), match.group(2) == "%", is_date


def numbers_in(text: str) -> list[float]:
    return [value for value, _, _ in _tokens(text)]


def format_table(columns: list[str], rows: list[list], limit: int = 20) -> str:
    lines = [" | ".join(columns)]
    for row in rows[:limit]:
        lines.append(" | ".join("" if value is None else str(value) for value in row))
    if len(rows) > limit:
        lines.append(f"...(共 {len(rows)} 行,仅显示前 {limit} 行)")
    return "\n".join(lines)


def find_citations(
        answer: str,
        columns: list[str],
        rows: list[list],
        question: str = "",
) -> tuple[list[dict], list[float]]:
    """返回 (命中的引用,找不到出处的数字)"""
    ignored = numbers_in(question)
    citations: list[dict] = []
    missing: list[float] = []

    for value, is_percent, is_date in _tokens(answer):
        if is_date or any(_same(value, item) for item in ignored):
            continue

        candidates = [value, -value]
        if is_percent:
            candidates += [value / 100.0, -value / 100.0]

        for row_index, row in enumerate(rows):
            hit = None
            for column_index, cell in enumerate(row):
                if isinstance(cell, bool) or not isinstance(cell, (int, float)):
                    continue
                if any(_same(candidate, float(cell)) for candidate in candidates):
                    name = columns[column_index] if column_index < len(columns) else str(column_index)
                    hit = {"value": float(cell), "row": row_index, "column": name}
                    break
            if hit:
                citations.append(hit)
                break
        else:
            missing.append(value)

    return citations, missing
