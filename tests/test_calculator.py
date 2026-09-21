"""Tests fuer den sicheren Rechner-Tool (AST-basiert)."""
import pytest

from tools.calculator import CalculatorTool


@pytest.fixture
def calc():
    return CalculatorTool()


def test_name():
    assert CalculatorTool.name == "calculator"


def test_add_subtract(calc):
    r = calc.run("2 + 3 * 4")
    assert r.success is True
    assert r.data == 14


def test_division(calc):
    r = calc.run("10 / 4")
    assert r.success is True
    assert r.data == 2.5


def test_float_and_power(calc):
    assert calc.run("2 ** 10").data == 1024
    assert calc.run("3.5 * 2").data == 7.0


def test_invalid_expression(calc):
    # Kein reines Mathematik-Ausdruck -> abgelehnt
    assert calc.run("__import__('os').system('id')").success is False
    assert calc.run("lambda: 1").success is False


def test_syntax_error(calc):
    assert calc.run("2 +").success is False


def test_empty(calc):
    assert calc.run("   ").success is False