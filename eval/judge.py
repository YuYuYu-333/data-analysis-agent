"""
评测判定：比较参考 SQL 和系统 SQL 的结果集。
只做规范化与比较，不执行 SQL。
"""

import math
from typing import Any

FLOAT_TOL = 1e-6


def _round_for_compare(value: float) -> float:
    """参考 SQL 金额保留 2 位、比率保留 4 位；比较时按同样精度归一化。"""
    if abs(value) < 1:
        return round(value, 4)
    return round(value, 2)


def _normalize_value(value: Any) -> tuple:
    """int / float 统一成 float；字符串去首尾空白；NULL 单独标记。"""
    if value is None:
        return ("null", None)
    if isinstance(value, bool):
        return ("num", _round_for_compare(float(value)))
    if isinstance(value, (int, float)):
        return ("num", _round_for_compare(float(value)))
    if isinstance(value, str):
        return ("str", value.strip())
    return ("other", repr(value))


def _row_contains(reference_row: list[Any], candidate_row: list[Any]) -> bool:
    """候选行必须包含参考行里的每个值；候选允许有多余的列"""
    remaining = [_normalize_value(v) for v in candidate_row]
    for ref_value in (_normalize_value(v) for v in reference_row):
        for index, cand_value in enumerate(remaining):
            if _value_equal(ref_value, cand_value):
                remaining.pop(index)
                break
        else:
            return False
    return True


def _value_equal(left: tuple, right: tuple) -> bool:
    """比较两个已经规范化过的单值。"""
    if left[0] != right[0]:
        return False
    if left[0] == "num":
        return math.isclose(left[1], right[1], rel_tol=FLOAT_TOL, abs_tol=FLOAT_TOL)
    return left == right


def rows_match(reference: list[list[Any]], candidate: list[list[Any]], ordered: bool = False) -> bool:
    """
    比较两个结果集。
    ordered=True：行顺序必须一致（排名题）。
    ordered=False：行顺序不重要，按行做多重集匹配
    """
    if len(reference) != len(candidate):
        return False

    if ordered:
        return all(_row_contains(a, b) for a, b in zip(reference, candidate))

    remaining = list(candidate)
    for ref_row in reference:
        for index, cand_row in enumerate(remaining):
            if _row_contains(ref_row, cand_row):
                remaining.pop(index)
                break
        else:
            return False
    return True
