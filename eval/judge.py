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


def _sort_key(item: tuple) -> tuple:
    kind, value = item
    if kind == "num":
        return (0, value)
    if kind == "str":
        return (1, value)
    if kind == "null":
        return (2, "")
    return (3, value)


def _value_equal(left: tuple, right: tuple) -> bool:
    """比较两个已经规范化过的单值。"""
    if left[0] != right[0]:
        return False
    if left[0] == "num":
        return math.isclose(left[1], right[1], rel_tol=FLOAT_TOL, abs_tol=FLOAT_TOL)
    return left == right


def _row_equal(left: list[Any], right: list[Any]) -> bool:
    """行内列顺序不敏感：两行的值排序后逐项比较。"""
    if len(left) != len(right):
        return False
    a = sorted((_normalize_value(v) for v in left), key=_sort_key)
    b = sorted((_normalize_value(v) for v in right), key=_sort_key)
    return all(_value_equal(x, y) for x, y in zip(a, b))


def rows_match(reference: list[list[Any]], candidate: list[list[Any]], ordered: bool = False) -> bool:
    """
    比较两个结果集。
    ordered=True：行顺序必须一致（排名题）。
    ordered=False：行顺序不重要，按行做多重集匹配
    """
    if len(reference) != len(candidate):
        return False

    if ordered:
        return all(_row_equal(a, b) for a, b in zip(reference, candidate))

    remaining = list(candidate)
    for ref_row in reference:
        for index, cand_row in enumerate(remaining):
            if _row_equal(ref_row, cand_row):
                remaining.pop(index)
                break
        else:
            return False
    return True
