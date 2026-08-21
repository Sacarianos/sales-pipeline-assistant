"""The safety boundary the fallback lane runs generated pandas expressions
through. Recorded in ADR-0006: this replaces the sqlglot guarantee V1's plan
would have rested on, rebuilt on Python's own `ast` module instead of SQL.

`run` takes an expression string and the frames it may reference, and either
returns a validated, executed result or a rejection — nothing in between. It
never repairs, never partially executes, and never retries with the
offending clause stripped, because a repaired query answers a question
nobody asked.

Validation is an allowlist walk over the parsed AST, not a regex and not a
blocklist. A blocklist has to anticipate every escape; an allowlist only has
to be small, and this one is small on purpose. Any attribute name beginning
with an underscore is rejected by one rule, which is what closes
`__class__`, `__globals__`, `__subclasses__`, and the rest of that family
without enumerating them.

`validate` always runs before `execute`, and `execute` binds only the given
frames with `__builtins__` emptied, so a name the allowlist somehow let
through still resolves to nothing — the two are independent layers, not one
relying on the other to have been correct.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Union

import pandas as pd

# Deliberately small, and living in exactly one place. A method nobody put
# here is a refusal, not a bug report. Nothing that takes a callable
# (`apply`, `agg` with a function, `eval`) is on this list: with no Lambda,
# comprehension, or free-standing Name available to pass as that callable,
# there would be nothing safe to hand it anyway.
ALLOWED_METHODS = frozenset(
    {
        "sum", "mean", "median", "min", "max", "count", "nunique", "std", "var",
        "size", "all", "any", "abs", "round",
        "sort_values", "sort_index", "nlargest", "nsmallest",
        "groupby", "agg",
        "reset_index", "rename",
        "head", "tail",
        "value_counts", "unique",
        "isin", "isna", "notna", "fillna", "dropna", "drop_duplicates",
        "astype", "copy",
    }
)

# Attribute access allowed without a call following it.
ALLOWED_PROPERTIES = frozenset(
    {"loc", "iloc", "columns", "index", "values", "dtypes", "empty", "shape", "T"}
)

ALLOWED_CMPOPS = (ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn)
ALLOWED_BOOLOPS = (ast.And, ast.Or)
ALLOWED_BINOPS = (
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.BitAnd, ast.BitOr, ast.BitXor,
)
ALLOWED_UNARYOPS = (ast.Not, ast.USub, ast.UAdd, ast.Invert)

# A result larger than this truncates for display; the full count still
# reports, so a leader reading the panel knows how much was cut.
ROW_CAP = 200


class Rejected(Exception):
    """Raised while walking the AST; carries the human-readable reason a
    caller of `validate` turns into a `SandboxRejection`."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class SandboxResult:
    value: object  # pd.DataFrame | pd.Series | a Python/numpy scalar
    row_count: int | None
    truncated: bool


@dataclass(frozen=True)
class SandboxRejection:
    reason: str


def _validate_node(node: ast.AST, frame_names: frozenset[str]) -> None:
    if isinstance(node, ast.Expression):
        _validate_node(node.body, frame_names)
    elif isinstance(node, ast.Name):
        if node.id not in frame_names:
            raise Rejected(f"'{node.id}' is not one of the frames this lane exposes")
    elif isinstance(node, ast.Constant):
        if not isinstance(node.value, (int, float, str, bool)) and node.value is not None:
            raise Rejected(f"constant of type '{type(node.value).__name__}' is not allowed")
    elif isinstance(node, ast.Attribute):
        if node.attr.startswith("_"):
            raise Rejected(f"attribute '{node.attr}' is not allowed")
        if node.attr not in ALLOWED_METHODS and node.attr not in ALLOWED_PROPERTIES:
            raise Rejected(f"attribute '{node.attr}' is not on the allowlist")
        _validate_node(node.value, frame_names)
    elif isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Attribute):
            raise Rejected("only method calls on a frame are allowed, not bare function calls")
        if node.func.attr not in ALLOWED_METHODS:
            raise Rejected(f"method '{node.func.attr}' is not on the allowlist")
        _validate_node(node.func, frame_names)
        for arg in node.args:
            _validate_node(arg, frame_names)
        for kw in node.keywords:
            _validate_node(kw.value, frame_names)
    elif isinstance(node, ast.Subscript):
        _validate_node(node.value, frame_names)
        _validate_node(node.slice, frame_names)
    elif isinstance(node, ast.Slice):
        for part in (node.lower, node.upper, node.step):
            if part is not None:
                _validate_node(part, frame_names)
    elif isinstance(node, (ast.List, ast.Tuple)):
        for elt in node.elts:
            _validate_node(elt, frame_names)
    elif isinstance(node, ast.Compare):
        _validate_node(node.left, frame_names)
        for op in node.ops:
            if not isinstance(op, ALLOWED_CMPOPS):
                raise Rejected(f"comparison '{type(op).__name__}' is not allowed")
        for comparator in node.comparators:
            _validate_node(comparator, frame_names)
    elif isinstance(node, ast.BoolOp):
        if not isinstance(node.op, ALLOWED_BOOLOPS):
            raise Rejected(f"boolean operator '{type(node.op).__name__}' is not allowed")
        for value in node.values:
            _validate_node(value, frame_names)
    elif isinstance(node, ast.BinOp):
        if not isinstance(node.op, ALLOWED_BINOPS):
            raise Rejected(f"operator '{type(node.op).__name__}' is not allowed")
        _validate_node(node.left, frame_names)
        _validate_node(node.right, frame_names)
    elif isinstance(node, ast.UnaryOp):
        if not isinstance(node.op, ALLOWED_UNARYOPS):
            raise Rejected(f"unary operator '{type(node.op).__name__}' is not allowed")
        _validate_node(node.operand, frame_names)
    else:
        raise Rejected(f"'{type(node).__name__}' is not an allowed expression form")


def _check_mutual_exclusion(tree: ast.AST, groups: tuple[frozenset[str], ...]) -> None:
    """Reject an expression that names more than one frame from the same
    group, regardless of how it combines them.

    This is deliberately a whole-tree check run after the per-node walk,
    not something folded into `_validate_node`: which frames may never
    appear together is a fact about what the frames *mean* to a caller (two
    snapshots of the same deals that must never be blended), not a property
    of any single AST node. A caller with no such groups gets no
    constraint, which is what keeps this module itself free of any
    knowledge of what "deals_q1" or "deals_q2" mean.
    """
    if not groups:
        return
    referenced = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    for group in groups:
        hit = referenced & group
        if len(hit) > 1:
            raise Rejected(
                f"an expression may not reference more than one of "
                f"{sorted(group)} together - it references {sorted(hit)}"
            )


def validate(
    expression: str,
    frame_names: frozenset[str],
    *,
    mutually_exclusive: tuple[frozenset[str], ...] = (),
) -> ast.Expression:
    """Parse `expression` and walk it against the allowlist.

    Returns the parsed tree on success. Raises `Rejected` on the first
    disallowed construct — there is no partial validation and no repair, so
    one bad clause anywhere in the expression rejects the whole thing.

    `mutually_exclusive` names groups of frames that may never appear
    together in one expression, checked after every individual node has
    already passed. Passing frame names that aren't in `frame_names` is
    harmless — they simply can never be referenced at all, so the group
    can never trigger.
    """
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise Rejected(f"not a valid expression: {exc.msg}") from exc
    _validate_node(tree, frame_names)
    _check_mutual_exclusion(tree, mutually_exclusive)
    return tree


def execute(tree: ast.Expression, frames: dict[str, pd.DataFrame]) -> object:
    """Run an already-validated tree with builtins emptied and only the
    given frames bound.

    This is not itself the safety boundary — `validate` is — but binding
    nothing except the frames and stripping builtins here means a bug in
    `validate` would still leave nothing reachable to exploit, rather than
    the whole guarantee resting on one layer being right.
    """
    compiled = compile(tree, "<fallback-expression>", "eval")
    return eval(compiled, {"__builtins__": {}}, dict(frames))  # noqa: S307


def run(
    expression: str,
    frames: dict[str, pd.DataFrame],
    *,
    mutually_exclusive: tuple[frozenset[str], ...] = (),
) -> Union[SandboxResult, SandboxRejection]:
    """Validate, then execute, then check the result's shape. Never both at
    once and never out of order: an expression that fails validation is
    never handed to `execute`."""
    try:
        tree = validate(expression, frozenset(frames), mutually_exclusive=mutually_exclusive)
    except Rejected as exc:
        return SandboxRejection(reason=exc.reason)

    try:
        value = execute(tree, frames)
    except Exception as exc:  # noqa: BLE001 — any runtime failure is a rejection, not a crash
        return SandboxRejection(reason=f"the expression raised {type(exc).__name__}: {exc}")

    if isinstance(value, (pd.DataFrame, pd.Series)):
        full_count = len(value)
        if full_count > ROW_CAP:
            return SandboxResult(value=value.head(ROW_CAP), row_count=full_count, truncated=True)
        return SandboxResult(value=value, row_count=full_count, truncated=False)

    if isinstance(value, (int, float, str, bool)) or value is None:
        return SandboxResult(value=value, row_count=None, truncated=False)

    # Covers numpy scalars (np.float64, np.int64, np.bool_) that pandas
    # aggregations return, which are not instances of the plain Python types
    # checked above.
    if hasattr(value, "item") and getattr(value, "shape", None) == ():
        return SandboxResult(value=value.item(), row_count=None, truncated=False)

    return SandboxRejection(
        reason=f"result of type '{type(value).__name__}' is not a DataFrame, Series, or scalar"
    )


__all__ = [
    "ALLOWED_METHODS",
    "ALLOWED_PROPERTIES",
    "ROW_CAP",
    "Rejected",
    "SandboxRejection",
    "SandboxResult",
    "execute",
    "run",
    "validate",
]
