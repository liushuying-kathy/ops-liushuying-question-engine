"""区域月频贡献闭合（B2-1）：元/店日缺口，供 rank 80% 与复核。"""
from __future__ import annotations

from typing import Any

from .decompose import lmdi_contributions


def _as_raw(problem: Any) -> dict:
    raw = getattr(problem, "raw", None) or {}
    if not isinstance(raw, dict):
        raw = {}
    problem.raw = raw
    return raw


def attach_numeric_contribution(problem: Any, gap_store_day: float | None) -> None:
    """gap_store_day = 当期店日均 − 上期店日均（元/店日，可正可负）。排序用绝对值。"""
    if gap_store_day is None:
        return
    raw = _as_raw(problem)
    raw["contribution_gap_store_day"] = round(float(gap_store_day), 4)
    problem.contribution = abs(float(gap_store_day))


def attach_sale_contribution(
    problem: Any,
    sale_curr: float | None,
    sale_prev: float | None,
) -> None:
    if sale_curr is None or sale_prev is None:
        return
    attach_numeric_contribution(problem, sale_curr - sale_prev)


def attach_e2_lmdi(
    problem,
    sale_curr: float | None,
    sale_prev: float | None,
    rate_curr: float | None,
    rate_prev: float | None,
    ap_curr: float | None,
    ap_prev: float | None,
) -> None:
    if ap_curr is None or ap_prev is None:
        return
    attach_numeric_contribution(problem, ap_curr - ap_prev)
    parts = lmdi_contributions(
        ap_curr,
        ap_prev,
        [("S1", sale_curr or 0, sale_prev or 0), ("E3", rate_curr or 0, rate_prev or 0)],
    )
    if not parts:
        problem.contribution = "贡献待算"
        return
    raw = _as_raw(problem)
    problem.contribution = abs(ap_curr - ap_prev)
    raw["lmdi"] = parts
    total = sum(parts.values())
    if abs(total) > 1e-9 and ap_curr != ap_prev:
        raw["lmdi_check_sum"] = total / (ap_curr - ap_prev)
    labels = {"S1": "店日均销售额", "E3": "补贴前毛利率"}
    bits = [
        f"{labels.get(k, k)}约{v:,.0f}元/店日"
        for k, v in parts.items()
    ]
    if bits and problem.message and "LMDI" not in problem.message:
        problem.message = (
            problem.message.rstrip("。")
            + "。毛利额变化拆解（LMDI）："
            + "；".join(bits)
            + "。不写成因果。"
        )


def seal_monthly_contributions(problems: list) -> None:
    """补全未挂贡献的月频入口/主过程行（不覆盖已有数值 contribution）。"""
    for p in problems:
        if getattr(p, "cadence", None) != "月":
            continue
        if getattr(p, "blocked", False):
            continue
        raw = getattr(p, "raw", None) or {}
        if not isinstance(raw, dict):
            continue
        cur_c = getattr(p, "contribution", None)
        if isinstance(cur_c, (int, float)) and cur_c > 0:
            continue
        if raw.get("contribution_gap_store_day") is not None:
            continue

        eid = (getattr(p, "entry_id", None) or "").strip()
        leaf = (getattr(p, "process_leaf", None) or "").strip()
        rl = getattr(p, "region_level", "") or ""

        if eid == "E1" or raw.get("measure") == "店日均净利":
            c = raw.get("curr")
            prev = raw.get("prev")
            if c is not None and prev is not None:
                attach_numeric_contribution(p, float(c) - float(prev))
            continue

        if eid == "E2" or raw.get("measure") == "补贴前毛利额":
            c = raw.get("curr")
            prev = raw.get("prev")
            if c is not None and prev is not None:
                attach_numeric_contribution(p, float(c) - float(prev))
            continue

        if leaf == "S1" and rl == "管理区":
            sc = raw.get("sale_day_avg_curr")
            sp = raw.get("sale_day_avg_prev")
            if sc is not None and sp is not None:
                attach_sale_contribution(p, float(sc), float(sp))
