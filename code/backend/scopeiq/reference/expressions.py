"""Safe evaluator for the quantity expressions stored in rule tables (e.g. 'ceil(powered_new / 6)').

Only arithmetic, comparisons, the conditional expression and a few whitelisted functions are allowed, so
analysts can edit rule quantities in data without a code release and without arbitrary code execution.
"""
from __future__ import annotations

import ast
import math
from functools import lru_cache
from typing import Any, Mapping

from scopeiq.common.errors import RuleError

_FUNCS = {"ceil": math.ceil, "floor": math.floor, "max": max, "min": min, "abs": abs, "round": round, "int": int}
_NODES = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Compare, ast.IfExp, ast.Call, ast.Name, ast.Load, ast.Constant,
          ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow, ast.USub, ast.UAdd,
          ast.Gt, ast.GtE, ast.Lt, ast.LtE, ast.Eq, ast.NotEq, ast.BoolOp, ast.And, ast.Or)


@lru_cache(maxsize=512)
def _compile(expr: str):
    try:
        tree = ast.parse(str(expr).strip(), mode="eval")
    except SyntaxError as exc:
        raise RuleError(f"Invalid quantity expression {expr!r}", details={"expr": expr}) from exc
    for node in ast.walk(tree):
        if not isinstance(node, _NODES):
            raise RuleError(f"Expression element {type(node).__name__} not allowed in {expr!r}")
        if isinstance(node, ast.Call) and not (isinstance(node.func, ast.Name) and node.func.id in _FUNCS):
            raise RuleError(f"Function not allowed in {expr!r}")
    return compile(tree, "<rule-expr>", "eval")


def evaluate(expr: Any, variables: Mapping[str, Any]) -> float:
    if expr is None or (isinstance(expr, str) and not expr.strip()):
        return 0
    if isinstance(expr, (int, float)):
        return expr
    code = _compile(str(expr))
    try:
        return eval(code, {"__builtins__": {}}, {**_FUNCS, **variables})  # noqa: S307 - AST whitelisted above
    except NameError as exc:
        raise RuleError(f"Unknown variable in {expr!r}: {exc}", details={"expr": expr, "known": sorted(variables)}) from exc
