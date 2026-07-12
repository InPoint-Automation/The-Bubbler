# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# calculator

import ast
import math
import operator
import re

def _pow(a, b):
    if abs(b) > 512 or abs(a) > 1e6:
        raise ValueError("pow operand too large")
    return a ** b


_BIN = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: _pow,
}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}

_FUNCS = {
    "sqrt": math.sqrt, "abs": abs, "round": round,
    "min": min, "max": max, "sin": math.sin, "cos": math.cos,
    "tan": math.tan, "radians": math.radians, "degrees": math.degrees,
    "hypot": math.hypot, "atan": math.atan, "atan2": math.atan2,
}
_CONSTS = {"pi": math.pi, "tau": math.tau, "e": math.e}


def _eval_node(node):
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(
                node.value, (int, float)):
            raise ValueError("bad constant")
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
        return _BIN[type(node.op)](_eval_node(node.left),
                                   _eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_eval_node(node.operand))
    if isinstance(node, ast.Name) and node.id in _CONSTS:
        return _CONSTS[node.id]
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
            and node.func.id in _FUNCS and not node.keywords:
        return _FUNCS[node.func.id](*[_eval_node(a) for a in node.args])
    raise ValueError("unsupported expression")


def _prep(expr):
    """^ -> **, comma decimals -> dots."""
    s = expr.strip()
    s = s.replace("^", "**").replace("×", "*").replace("÷", "/")
    s = s.replace("−", "-")
    if "(" not in s and not any(c.isalpha() for c in s):
        s = s.replace(",", ".")
    return s


def safe_eval(expr):
    """Eval arithmetic. Float, or None if invalid."""
    if not expr or not expr.strip():
        return None
    try:
        tree = ast.parse(_prep(expr), mode="eval")
        val = _eval_node(tree)
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            return None
        fval = float(val)
    except (ValueError, SyntaxError, TypeError, ZeroDivisionError,
            OverflowError, RecursionError):
        return None
    if fval != fval or fval in (float("inf"), float("-inf")):
        return None
    return fval


def format_num(v):
    """Trim float noise + trailing zeros."""
    if v is None:
        return ""
    v = round(float(v), 10)
    if v == 0:
        v = 0.0
    s = ("%.10f" % v).rstrip("0").rstrip(".")
    return s or "0"

_FORCE_OPS = set("*()^×÷")
_AMBIG_OPS = set("+-/")


def _auto_eval(s):
    """Bare entry is arithmetic?"""
    if any(c in _FORCE_OPS for c in s):
        return True
    body = s[1:]
    if any(c in _AMBIG_OPS for c in body):
        return "." in s or "," in s
    return False


def split_readings(text):
    """whitespace/semicolons"""
    return [t for t in re.split(r"[\s;]+", (text or "").strip()) if t]


def eval_measure(text):
    """measure entry"""
    s = (text or "").strip()
    if not s:
        return s, False
    forced = s.startswith("=")
    expr = s[1:].strip() if forced else s
    if not forced:
        try:
            float(expr.replace(",", "."))
            return s, False
        except ValueError:
            pass
        if not _auto_eval(expr):
            return s, False
    v = safe_eval(expr)
    if v is None:
        return s, False
    return format_num(v), True
