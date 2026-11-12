"""calculator：安全求值数学表达式。

不使用 eval：用 ast 白名单遍历，只允许数字、算术运算符与括号。
"""

from __future__ import annotations

import ast
import operator

from app.common.errors import ToolError
from app.tools.registry import Tool, registry

MAX_EXPR_LENGTH = 200
MAX_POWER = 100

_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def _eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ToolError("表达式只能包含数字")
        return node.value
    if isinstance(node, ast.BinOp):
        op = _BIN_OPS.get(type(node.op))
        if op is None:
            raise ToolError("只支持 + - * / // % ** 运算")
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > MAX_POWER:
            raise ToolError("指数过大，拒绝计算")
        return op(left, right)
    if isinstance(node, ast.UnaryOp):
        op = _UNARY_OPS.get(type(node.op))
        if op is None:
            raise ToolError("只支持正负号")
        return op(_eval_node(node.operand))
    raise ToolError("表达式包含不支持的语法（仅允许数字、运算符与括号）")


def calculate(session, args: dict) -> dict:
    expression = str(args["expression"]).strip()
    if not expression:
        raise ToolError("expression 不能为空")
    if len(expression) > MAX_EXPR_LENGTH:
        raise ToolError(f"表达式过长（上限 {MAX_EXPR_LENGTH} 字符）")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ToolError(f"无法解析表达式：{expression}") from exc

    try:
        value = _eval_node(tree.body)
    except ZeroDivisionError as exc:
        raise ToolError("除数不能为 0") from exc

    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ToolError("计算结果不是一个有效数字")
        value = int(value) if value.is_integer() else round(value, 10)
    return {"expression": expression, "result": value}


registry.register(
    Tool(
        name="calculator",
        description="计算数学表达式，支持 + - * / // % ** 与括号，表达式只能包含数字和运算符。",
        parameters={
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "要计算的表达式，例如 (23*4+7)/5",
                }
            },
            "required": ["expression"],
        },
        handler=calculate,
    )
)
