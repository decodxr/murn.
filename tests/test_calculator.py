import math

import pytest

from murn.providers.calculator import calculate


def test_basic_arithmetic_is_exact():
    assert calculate("27 * 19")["result"] == 513


def test_common_math_functions_work():
    result = calculate("sqrt(81) + round(pi, 2)")["result"]
    assert math.isclose(result, 12.14, rel_tol=0, abs_tol=1e-9)


def test_unsafe_python_expression_is_rejected():
    with pytest.raises(ValueError):
        calculate("__import__('os').system('echo nope')")


def test_huge_exponent_is_rejected():
    with pytest.raises(ValueError):
        calculate("2 ** 999")
