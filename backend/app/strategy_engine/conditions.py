"""Condition/logic operator evaluation over indicator series."""
from __future__ import annotations

import numpy as np
import pandas as pd


def _align(left: pd.Series | np.ndarray, right: pd.Series | np.ndarray | float) -> tuple[np.ndarray, np.ndarray]:
    a = np.asarray(left, dtype=float)
    if isinstance(right, (int, float, np.floating)):
        b = np.full_like(a, float(right))
        return a, b
    b = np.asarray(right, dtype=float)
    n = min(len(a), len(b))
    return (a[-n:], b[-n:]) if n else (a[:0], b[:0])


def compare(operator: str, left: pd.Series | np.ndarray, right: pd.Series | float) -> pd.Series:
    a, b = _align(left, right)
    if operator == "<":
        out = a < b
    elif operator == ">":
        out = a > b
    elif operator == "<=":
        out = a <= b
    elif operator == ">=":
        out = a >= b
    elif operator == "==":
        out = np.isclose(a, b)
    elif operator == "!=":
        out = ~np.isclose(a, b)
    else:
        out = np.zeros(len(a), dtype=bool)
    return pd.Series(out, dtype="boolean").mask(~(np.isfinite(a) & np.isfinite(b)))


def crosses_above(left: pd.Series | np.ndarray, right: pd.Series | np.ndarray) -> pd.Series:
    a, b = _align(left, right)
    out = np.zeros(len(a), dtype=bool)
    if len(a) >= 2:
        out[1:] = (a[:-1] <= b[:-1]) & (a[1:] > b[1:])
    return pd.Series(out)


def crosses_below(left: pd.Series | np.ndarray, right: pd.Series | np.ndarray) -> pd.Series:
    a, b = _align(left, right)
    out = np.zeros(len(a), dtype=bool)
    if len(a) >= 2:
        out[1:] = (a[:-1] >= b[:-1]) & (a[1:] < b[1:])
    return pd.Series(out)


def _bool_arrays(*operands):
    arrays = [pd.Series(op, dtype="boolean") for op in operands]
    if not arrays:
        return []
    n = min(len(a) for a in arrays)
    return [a.iloc[-n:].reset_index(drop=True) if n else a.iloc[:0] for a in arrays]


def logical_and(*operands):
    arrays = _bool_arrays(*operands)
    if not arrays:
        return pd.Series([], dtype="boolean")
    result = arrays[0]
    for arr in arrays[1:]:
        result = result & arr
    return result


def logical_or(*operands):
    arrays = _bool_arrays(*operands)
    if not arrays:
        return pd.Series([], dtype="boolean")
    result = arrays[0]
    for arr in arrays[1:]:
        result = result | arr
    return result


def logical_not(operand):
    return ~pd.Series(operand, dtype="boolean")
