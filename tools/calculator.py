"""ODIN Agent - Calculator Tool.

Sicherer kleiner Mathematik-Interpreter ueber Python-AST.
Erlaubt NUR mathematische Ausdruecke, KEINE beliebige
Python-Ausfuehrung (kein Zugriff auf Name-/Attribute/Ressourcen).
"""
from __future__ import annotations

import ast
import operator

from tools.base import BaseTool, ToolResult


_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

_MAX_RESULT = 10**18  # Explosionsschutz gegen riesige Ergebnisse


def calculate(expression: str):
    """Sicherer Mathematik-Interpreter. Wirft ValueError bei illegalen Ausdruecken."""

    def evaluate(node):
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool):
                raise ValueError("Wahrheitswerte nicht erlaubt")
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError("Ungueltige Zahl")
        if isinstance(node, ast.BinOp):
            if type(node.op) not in _OPERATORS:
                raise ValueError("Operator nicht erlaubt")
            left = evaluate(node.left)
            right = evaluate(node.right)
            return _OPERATORS[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp):
            if type(node.op) not in _OPERATORS:
                raise ValueError("Operator nicht erlaubt")
            return _OPERATORS[type(node.op)](evaluate(node.operand))
        raise ValueError("Ausdruck nicht erlaubt")

    tree = ast.parse(expression, mode="eval")
    result = evaluate(tree.body)
    if isinstance(result, float) and abs(result) > _MAX_RESULT:
        raise ValueError("Ergebnis zu gross")
    return result


class CalculatorTool(BaseTool):
    name = "calculator"
    description = (
        "Berechnet einen mathematischen Ausdruck sicher. "
        "Unterstuetzt + - * / // % ** und Klammern. "
        'Beispiel: "1234 * 56", "(25 + 15) * 3".'
    )
    parameters = {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": (
                    "Mathematischer Ausdruck, z. B. '1234 * 56'."
                ),
            }
        },
        "required": ["expression"],
    }

    def run(self, expression: str) -> ToolResult:
        if not isinstance(expression, str) or not expression.strip():
            return ToolResult.fail(error="Bitte einen Ausdruck angeben.")
        try:
            result = calculate(expression)
        except (ValueError, SyntaxError, TypeError, ZeroDivisionError) as e:
            return ToolResult.fail(error=f"Ungueltiger Ausdruck: {e}")
        return ToolResult.ok(data=result)