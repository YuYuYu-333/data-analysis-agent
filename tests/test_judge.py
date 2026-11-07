"""判定器：规范化与结果集比较。"""

from eval.judge import rows_match


def test_int_and_float_are_equal():
    assert rows_match([[1]], [[1.0]])


def test_float_tolerance():
    assert rows_match([[1.0000001]], [[1.0]])


def test_none_is_not_zero():
    assert not rows_match([[None]], [[0]])


def test_row_order_ignored_by_default():
    assert rows_match([[1], [2]], [[2], [1]])


def test_row_order_required_when_ordered():
    assert not rows_match([[1], [2]], [[2],
                                       [1]], ordered=True)


def test_column_order_ignored():
    assert rows_match([["华东", 100]], [[100,
                                         "华东"]])


def test_row_count_must_match():
    assert not rows_match([[1]], [[1], [2]])


def test_different_values_do_not_match():
    assert not rows_match([[1]], [[2]])


def test_money_rounding_matches_reference_precision():
    assert rows_match([[127.661251]], [[127.66]])


def test_rate_rounding_matches_reference_precision():
    assert rows_match([[0.09255079]], [[0.0926]])


def test_candidate_may_have_extra_columns():
    assert rows_match([["毛巾", 100]], [["P01", "毛巾", 100]])


def test_candidate_missing_a_value_fails():
    assert not rows_match([["P01", "毛巾", 100]], [["毛巾", 100]])


def test_wrong_value_in_second_column_fails():
    assert not rows_match([["毛巾", 100]], [["毛巾", 999999.0]])


def test_wrong_value_in_third_column_fails():
    assert not rows_match([["华东", 3, 100]], [["华东", 3, 999999.0]])


def test_missing_middle_value_fails():
    assert not rows_match([["华东", 3, 100]], [["华东", 0, 100]])


def test_duplicate_values_need_matching_counts():
    """行内同一个值出现两次，候选也得有两次"""
    assert not rows_match([[1, 1]], [[1, 2]])
