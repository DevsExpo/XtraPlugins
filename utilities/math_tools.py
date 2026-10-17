# Copyright (C) 2021-present by FridaySoftware@Github, < https://github.com/FridaySoftware >.
#
# This file is part of < https://github.com/FridaySoftware/Friday > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/Altriux/Friday/blob/main/LICENSE >
#
# All rights reserved.

import ast
import math
import operator
from typing import Any
from Main import Friday
from Main.core.types.client import FridayTelegramClient as Client
from Main.core.types.message import Message

# Supported operators mapping
OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

# Supported mathematical functions and constants
MATH_FUNCTIONS = {
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "log": math.log,
    "log10": math.log10,
    "log2": math.log2,
    "exp": math.exp,
    "abs": abs,
    "round": round,
    "floor": math.floor,
    "ceil": math.ceil,
    "factorial": math.factorial,
    "degrees": math.degrees,
    "radians": math.radians,
}

MATH_CONSTANTS = {
    "pi": math.pi,
    "e": math.e,
    "tau": math.tau,
}


def _safe_eval(node: ast.AST) -> Any:
    """Safely evaluate AST node without arbitrary code execution."""
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    elif isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"Unsupported constant type: {type(node.value)}")
    elif isinstance(node, ast.Name):
        if node.id.lower() in MATH_CONSTANTS:
            return MATH_CONSTANTS[node.id.lower()]
        raise ValueError(f"Unknown variable: {node.id}")
    elif isinstance(node, ast.BinOp):
        left = _safe_eval(node.left)
        right = _safe_eval(node.right)
        op_type = type(node.op)
        if op_type in OPERATORS:
            return OPERATORS[op_type](left, right)
        raise ValueError(f"Unsupported binary operator: {op_type}")
    elif isinstance(node, ast.UnaryOp):
        operand = _safe_eval(node.operand)
        op_type = type(node.op)
        if op_type in OPERATORS:
            return OPERATORS[op_type](operand)
        raise ValueError(f"Unsupported unary operator: {op_type}")
    elif isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id.lower() in MATH_FUNCTIONS:
            func = MATH_FUNCTIONS[node.func.id.lower()]
            args = [_safe_eval(arg) for arg in node.args]
            return func(*args)
        raise ValueError(f"Unsupported function call: {getattr(node.func, 'id', 'unknown')}")
    else:
        raise ValueError(f"Disallowed expression syntax: {type(node).__name__}")


@Friday.register_on_cmd(
    ["calc", "math", "calculate"],
    cmd_help={
        "help": "Safely calculate complex mathematical expressions (supports sqrt, log, sin, cos, pi, etc.).",
        "example": "calc 2**8 + sqrt(144) * pi",
    },
    requires_input=True,
)
async def calculate_math(c: Client, m: Message):
    expr = m.user_input.strip()

    try:
        parsed = ast.parse(expr, mode="eval")
        result = _safe_eval(parsed)

        # Format clean numbers
        if isinstance(result, float) and result.is_integer():
            formatted_result = f"{int(result):,}"
        elif isinstance(result, float):
            formatted_result = f"{result:,.6f}".rstrip("0").rstrip(".")
        else:
            formatted_result = f"{result:,}"

        report = (
            "🧮 <b>Calculation Result:</b>\n\n"
            f"<b>Input:</b> <code>{expr}</code>\n"
            f"<b>Output:</b> <code>{formatted_result}</code>"
        )
        await m.handle_message(report)
    except ZeroDivisionError:
        await m.handle_message("❌ Error: Division by zero.")
    except Exception as e:
        await m.handle_message(f"❌ Calculation Error: <code>{e}</code>")
