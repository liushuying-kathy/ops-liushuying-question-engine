"""跑批后自检（A46–A55）。"""
from __future__ import annotations

from typing import Any


def _raw(p) -> dict:
    if isinstance(p, dict):
        return p.get("raw") or {}
    return getattr(p, "raw", None) or {}


def _get(p, key: str):
    if isinstance(p, dict):
        return p.get(key)
    return getattr(p, key, None)


def run_checks(
    report: dict[str, Any],
    style_violations: list[dict],
    problems: list | None = None,
    thresholds: dict | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {"passed": True, "items": []}
    problems = problems or []

    def add(item: dict) -> None:
        if not item.get("ok"):
            out["passed"] = False
        out["items"].append(item)

    add(
        {
            "check": "A51_style_violations",
            "count": len(style_violations or []),
            "ok": not style_violations,
        }
    )

    upgrades = report.get("ceo_upgrades") or []
    e1_ok = all("【估算】" in (u.get("message") or "") for u in upgrades if u.get("entry_id") == "E1")
    add({"check": "A55_e1_reliability", "ok": e1_ok or not any(u.get("entry_id") == "E1" for u in upgrades)})

    p1 = report.get("p1_stats") or {}
    add(
        {
            "check": "A54_p1_detectors",
            "stats": p1,
            "ok": all(k in p1 for k in ("promo", "cells", "member", "s2", "m1a", "o1")),
        }
    )

    daily = sum(1 for p in problems if _get(p, "cadence") == "日")
    highlight = sum(1 for p in problems if _raw(p).get("daily_highlight"))
    add({"check": "A48_daily_full_scan", "daily_rows": daily, "highlights": highlight, "ok": daily > 0 and highlight > 0})

    daily_364 = sum(
        1 for p in problems if _get(p, "cadence") == "日" and _raw(p).get("compare_basis") == "same_weekday_364"
    )
    add(
        {
            "check": "A49_daily_compare_364",
            "rows": daily_364,
            "ok": daily_364 > 0
            and (thresholds or {}).get("compare", {}).get("daily_primary") == "same_weekday_364",
        }
    )

    e2_lmdi = sum(1 for p in problems if _get(p, "entry_id") == "E2" and _raw(p).get("lmdi"))
    add(
        {
            "check": "A46_lmdi_attached",
            "e2_with_lmdi": e2_lmdi,
            "ok": e2_lmdi >= 1 and (thresholds or {}).get("contribution_method") == "lmdi",
        }
    )

    store_strong = [p for p in problems if "强提示" in (_get(p, "alert_level") or "")]
    bad_leaf = sum(
        1
        for p in store_strong[:400]
        if _get(p, "trigger_id") == "T3"
        and _get(p, "process_leaf") not in ("", "B1", "S1", "T3", "B2", "E2")
    )
    add({"check": "A50_store_process_leaf", "store_strong": len(store_strong), "ok": len(store_strong) > 0 and bad_leaf == 0})

    add(
        {
            "check": "A52_data_freshness",
            "wide_max": report.get("connections", {}).get("wide_max_date"),
            "ok": bool(report.get("connections", {}).get("wide_max_date")),
        }
    )

    member_p = (p1.get("member") or 0) + (p1.get("m1a") or 0)
    add({"check": "A53_member_tree", "member_problems": member_p, "ok": member_p > 0})

    by_id = {}
    for p in problems:
        pid = _get(p, "problem_id") or _raw(p).get("problem_id")
        if pid:
            by_id[pid] = p
    ceo = report.get("ceo_upgrades") or []
    a62_ok = True
    a62_n = 0
    for u in ceo:
        pid = u.get("problem_id") or (u.get("raw") or {}).get("problem_id")
        if not pid or pid not in by_id:
            continue
        src = by_id[pid]
        if isinstance(src, dict):
            src_leaf, src_trig = src.get("process_leaf"), src.get("trigger_id")
        else:
            src_leaf, src_trig = _get(src, "process_leaf"), _get(src, "trigger_id")
        if u.get("process_leaf") != src_leaf or u.get("trigger_id") != src_trig:
            a62_ok = False
        a62_n += 1
    add(
        {
            "check": "A62_ceo_store_same_id",
            "compared": a62_n,
            "ok": a62_ok and a62_n >= 1 and bool(report.get("problems_ranked")),
        }
    )

    data_leaves = {"M1a", "B1a", "S2", "M1", "M2", "O1"}
    fired = {
        _get(p, "process_leaf")
        for p in problems
        if _get(p, "process_leaf") in data_leaves and _get(p, "cadence") == "月"
    }
    add(
        {
            "check": "A63_registered_leaves_with_data",
            "fired": sorted(fired),
            "missing": sorted(data_leaves - fired),
            "ok": data_leaves <= fired,
        }
    )

    store_daily = sum(
        1 for p in problems if _get(p, "cadence") == "日" and _raw(p).get("store_daily")
    )
    add(
        {
            "check": "A64_store_daily_layer",
            "rows": store_daily,
            "ok": store_daily > 0
            if (thresholds or {}).get("daily_scan", {}).get("open_store_layer")
            else True,
        }
    )

    contrib_ok = 0
    for u in ceo:
        raw_u = u.get("raw") or {}
        c = u.get("contribution")
        if isinstance(c, (int, float)) and c > 0:
            contrib_ok += 1
        elif raw_u.get("contribution_gap_store_day") is not None:
            contrib_ok += 1
    add(
        {
            "check": "A65_ceo_contribution_gap",
            "with_gap": contrib_ok,
            "ceo_rows": len(ceo),
            "ok": contrib_ok >= max(1, len(ceo) // 2),
        }
    )

    spatial_linked = sum(
        1
        for p in problems
        if _get(p, "cadence") == "月"
        and (_get(p, "region_level") or "") == "市"
        and (_raw(p).get("spatial_chain") or [])
    )
    add(
        {
            "check": "A66_spatial_chain_city",
            "city_rows": spatial_linked,
            "ok": spatial_linked >= 1,
        }
    )

    depth_leaves = {"CAT_MID", "CAT_SUB", "CAT_SKU"}
    depth_fired = {
        _get(p, "process_leaf")
        for p in problems
        if _get(p, "process_leaf") in depth_leaves and (_raw(p).get("vacancy") or _get(p, "alert_level") in ("统计月无分区", "待日销售表"))
    }
    add(
        {
            "check": "A67_category_depth_vacancy",
            "leaves": sorted(depth_fired),
            "ok": depth_leaves <= depth_fired,
        }
    )

    o1_no_target = sum(
        1
        for p in problems
        if _get(p, "process_leaf") == "O1"
        and _get(p, "cadence") == "月"
        and (_raw(p).get("order_attain") == "无目标" or _get(p, "alert_level") == "目标缺失")
    )
    add(
        {
            "check": "A68_o1_per_area_no_target",
            "rows": o1_no_target,
            "ok": o1_no_target >= 10,
        }
    )

    m1b_ok = any(_get(p, "process_leaf") == "M1b" for p in problems)
    b2a_ok = any(_get(p, "process_leaf") == "B2a" for p in problems)
    add(
        {
            "check": "A69_m1b_b2a_vacancy",
            "m1b": m1b_ok,
            "b2a": b2a_ok,
            "ok": m1b_ok and b2a_ok,
        }
    )

    return out
