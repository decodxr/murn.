from __future__ import annotations

import ast
import math
import operator
from typing import Any, Callable


_BINARY: dict[type[ast.AST], Callable[[float, float], float]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY: dict[type[ast.AST], Callable[[float], float]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}
_FUNCTIONS: dict[str, Callable[..., Any]] = {
    "abs": abs,
    "round": round,
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "log": math.log,
    "log10": math.log10,
    "floor": math.floor,
    "ceil": math.ceil,
    "min": min,
    "max": max,
}
_CONSTANTS = {"pi": math.pi, "e": math.e, "tau": math.tau}


def _eval(node: ast.AST) -> float | int:
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.Name) and node.id in _CONSTANTS:
        return _CONSTANTS[node.id]
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
        left = _eval(node.left)
        right = _eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(float(right)) > 12:
            raise ValueError("Exponent is too large.")
        value = _BINARY[type(node.op)](left, right)
        if abs(float(value)) > 1e100:
            raise ValueError("Result is too large.")
        return value
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_eval(node.operand))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCTIONS:
        if node.keywords:
            raise ValueError("Keyword arguments are not supported.")
        args = [_eval(arg) for arg in node.args]
        if len(args) > 12:
            raise ValueError("Too many arguments.")
        return _FUNCTIONS[node.func.id](*args)
    raise ValueError("Unsupported expression.")


def calculate(expression: str) -> dict[str, Any]:
    text = str(expression or "").strip()
    if not text or len(text) > 500:
        raise ValueError("Expression is empty or too long.")
    tree = ast.parse(text, mode="eval")
    value = _eval(tree)
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return {"expression": text, "result": value}
