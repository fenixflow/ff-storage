"""
MongoDB query compiler for ff-storage filter expressions.

Compiles FilterExpression and CompositeExpression objects into MongoDB query
documents, enabling the same F proxy syntax to work with both SQL and MongoDB:

    from ff_storage import F, MongoRepository

    # Same syntax, different backend
    results = await repo.find(F.price > 100, F.status == "active")

    # Compiled to: {"$and": [{"price": {"$gt": 100}}, {"status": "active"}]}
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Union

from .expressions import CompositeExpression, FilterExpression

# Regex metacharacters that need escaping when converting LIKE patterns
_REGEX_META = re.compile(r"([.+*?^${}()|[\]\\])")


def _escape_regex(value: str) -> str:
    """Escape regex metacharacters in a string."""
    return _REGEX_META.sub(r"\\\1", value)


def _like_to_regex(pattern: str) -> tuple[str, str]:
    """
    Convert a SQL LIKE pattern to a MongoDB regex pattern.

    Handles patterns produced by FieldProxy methods:
    - contains("test")   -> LIKE '%test%'   -> regex: test
    - startswith("ab")   -> LIKE 'ab%'      -> regex: ^ab
    - endswith("cd")     -> LIKE '%cd'      -> regex: cd$
    - icontains("test")  -> ILIKE '%test%'  -> regex: test (case-insensitive)

    Returns:
        Tuple of (regex_pattern, options_string).
        options_string is "i" for case-insensitive, "" otherwise.
    """
    # Strip the % wildcards and determine anchoring
    starts_with_pct = pattern.startswith("%")
    ends_with_pct = pattern.endswith("%")

    # Remove leading/trailing % for the core value
    core = pattern
    if starts_with_pct:
        core = core[1:]
    if ends_with_pct:
        core = core[:-1]

    # Unescape SQL LIKE escape sequences (from _escape_like_pattern)
    core = core.replace("\\%", "%").replace("\\_", "_").replace("\\\\", "\\")

    # Escape regex metacharacters in the core value
    escaped = _escape_regex(core)

    # Build regex with anchors
    if not starts_with_pct and ends_with_pct:
        # startswith: LIKE 'ab%'
        return f"^{escaped}", ""
    elif starts_with_pct and not ends_with_pct:
        # endswith: LIKE '%cd'
        return f"{escaped}$", ""
    elif starts_with_pct and ends_with_pct:
        # contains: LIKE '%test%'
        return escaped, ""
    else:
        # Exact match via LIKE (no wildcards)
        return f"^{escaped}$", ""


def compile_filter(
    expr: Union[FilterExpression, CompositeExpression],
) -> Dict[str, Any]:
    """
    Compile a single FilterExpression or CompositeExpression to a MongoDB query document.

    Args:
        expr: A FilterExpression or CompositeExpression from the query builder.

    Returns:
        MongoDB query document (dict).

    Examples:
        >>> compile_filter(FilterExpression("price", ">", 100))
        {"price": {"$gt": 100}}

        >>> compile_filter(FilterExpression("status", "=", "active"))
        {"status": "active"}

        >>> compile_filter(OR(F.a == 1, F.b == 2))
        {"$or": [{"a": 1}, {"b": 2}]}
    """
    if isinstance(expr, CompositeExpression):
        return _compile_composite(expr)
    elif isinstance(expr, FilterExpression):
        return _compile_single(expr)
    else:
        raise TypeError(f"Expected FilterExpression or CompositeExpression, got {type(expr)}")


def compile_filters(
    expressions: List[Union[FilterExpression, CompositeExpression]],
) -> Dict[str, Any]:
    """
    Compile multiple expressions into a single MongoDB query with implicit $and.

    If there's only one expression, returns it directly (no $and wrapper).

    Args:
        expressions: List of filter expressions.

    Returns:
        MongoDB query document.

    Examples:
        >>> compile_filters([F.price > 100, F.status == "active"])
        {"$and": [{"price": {"$gt": 100}}, {"status": "active"}]}

        >>> compile_filters([F.status == "active"])
        {"status": "active"}

        >>> compile_filters([])
        {}
    """
    if not expressions:
        return {}
    if len(expressions) == 1:
        return compile_filter(expressions[0])

    compiled = [compile_filter(expr) for expr in expressions]
    return {"$and": compiled}


def _compile_single(expr: FilterExpression) -> Dict[str, Any]:
    """Compile a FilterExpression to a MongoDB query document."""
    field = expr.field
    op = expr.operator
    value = expr.value

    # Equality
    if op == "=":
        return {field: value}

    # Inequality
    if op == "!=":
        return {field: {"$ne": value}}

    # Comparison operators
    op_map = {
        ">": "$gt",
        ">=": "$gte",
        "<": "$lt",
        "<=": "$lte",
    }
    if op in op_map:
        return {field: {op_map[op]: value}}

    # NULL checks
    if op == "IS NULL":
        return {field: None}
    if op == "IS NOT NULL":
        return {field: {"$ne": None}}

    # IN / NOT IN
    if op == "IN":
        if not value:
            # Empty IN matches nothing — use an impossible condition
            return {"_impossible": True}
        return {field: {"$in": list(value)}}
    if op == "NOT IN":
        if not value:
            # Empty NOT IN matches everything
            return {}
        return {field: {"$nin": list(value)}}

    # BETWEEN
    if op == "BETWEEN":
        low, high = value
        return {field: {"$gte": low, "$lte": high}}

    # LIKE (case-sensitive)
    if op == "LIKE":
        regex, _ = _like_to_regex(value)
        return {field: {"$regex": regex}}

    # ILIKE (case-insensitive)
    if op == "ILIKE":
        regex, _ = _like_to_regex(value)
        return {field: {"$regex": regex, "$options": "i"}}

    # Subquery operators not supported in MongoDB
    if op in ("IN_SUBQUERY", "NOT IN_SUBQUERY"):
        raise NotImplementedError(
            f"Subquery operators ({op}) are not supported in MongoDB. "
            "Use aggregation pipelines with $lookup instead."
        )

    raise ValueError(f"Unsupported operator for MongoDB: {op!r}")


def _compile_composite(expr: CompositeExpression) -> Dict[str, Any]:
    """Compile a CompositeExpression (AND/OR) to a MongoDB query document."""
    mongo_op = "$and" if expr.operator == "AND" else "$or"
    compiled = [compile_filter(sub) for sub in expr.expressions]
    return {mongo_op: compiled}
