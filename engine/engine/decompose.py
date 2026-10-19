"""LMDI 与加法型缺口分解。"""
from __future__ import annotations

import math
from typing import Iterable


def lmdi_contributions(
    parent_curr: float,
    parent_prev: float,
    factors: list[tuple[str, float, float]],
) -> dict[str, float] | None:
    """
    两因子乘法 parent = f1 * f2（可扩展多因子连乘）。
    返回各因子对 parent 变化的贡献（元/店日同量纲）。
    """
    if parent_prev <= 0 or parent_curr <= 0:
        return None
    for _, c, p in factors:
        if c <= 0 or p <= 0:
            return None
    delta = parent_curr - parent_prev
    denom = math.log(parent_curr) - math.log(parent_prev)
    if abs(denom) < 1e-15:
        return None
    L = delta / denom
    out: dict[str, float] = {}
    for name, c, p in factors:
        out[name] = L * (math.log(c) - math.log(p))
    return out


def additive_shares(
    deltas: list[tuple[str, float]],
) -> dict[str, float]:
    """同号拖累项内份额，和为 1。"""
    pos = [(n, d) for n, d in deltas if d < 0]
    total = sum(-d for _, d in pos)
    if total <= 0:
        return {}
    return {n: (-d) / total for n, d in pos}


def contribution_ratio(child_gap: float, parent_gap: float) -> float | None:
    if parent_gap == 0:
        return None
    return child_gap / parent_gap
