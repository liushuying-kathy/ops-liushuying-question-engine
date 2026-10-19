"""B1-2：O1 订购达标 — 有目标写达成，无目标写「无目标」不占假达标。"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Callable


def apply_o1_per_area(
    problems: list,
    Problem: Any,
    *,
    data_dir: Path,
    manage_areas: list[str],
    exclude_regions: set[str],
    thresholds: dict,
    fnum: Callable,
    fmt_pct: Callable,
) -> dict[str, int]:
    """按管理区登记 O1；返回 {with_target, no_target, below_threshold}。"""
    order_path = data_dir / "区域订购达标_202509.csv"
    by_area: dict[str, dict] = {}
    if order_path.is_file():
        with order_path.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                area = row.get("manage_area") or row.get("manageArea") or ""
                if area:
                    by_area[area] = row

    o_cfg = thresholds.get("order_attain") or {}
    o_thr = float(o_cfg.get("threshold") or 0.90)
    enabled = bool(o_cfg.get("enabled"))
    counts = {"with_target": 0, "no_target": 0, "below_threshold": 0}

    for area in sorted(manage_areas):
        if area in exclude_regions:
            continue
        row = by_area.get(area) or {}
        tgt = fnum(row.get("order_target") or row.get("orderTarget"))
        inbound = fnum(row.get("inbound_amt_day_avg") or row.get("inboundAmtDayAvg"))
        rate = fnum(row.get("order_attain_rate") or row.get("orderAttainRate"))

        if tgt is None or tgt <= 0:
            counts["no_target"] += 1
            problems.append(
                Problem(
                    scope=area,
                    trigger_id="T4",
                    alert_level="目标缺失",
                    cadence="月",
                    region_level="管理区",
                    message=(
                        f"9月{area}店日均订购额目标缺失，不写达标率。"
                        f"宽表 inbound 店日均约{inbound:.0f}元/店日。"
                        if inbound is not None
                        else f"9月{area}店日均订购额目标缺失，不写达标率。"
                    ),
                    raw={
                        "order_attain": "无目标",
                        "order_target": None,
                        "inbound_day_avg": inbound,
                        "target_table": o_cfg.get("target_table")
                        or "operation_center_region_target_mi",
                    },
                    process_leaf="O1",
                    parallel=True,
                )
            )
            continue

        counts["with_target"] += 1
        if rate is not None and rate < o_thr:
            counts["below_threshold"] += 1
            lvl = "提示" if enabled else "描述"
            if enabled:
                msg = (
                    f"9月{area}店日均订购额达成率约{fmt_pct(rate)}，低于阈值{fmt_pct(o_thr)}。"
                )
            else:
                msg = (
                    f"9月{area}订购达成率约{fmt_pct(rate)}（目标有数），"
                    "order_attain.enabled 为 false，仅登记。"
                )
            problems.append(
                Problem(
                    scope=area,
                    trigger_id="T4",
                    alert_level=lvl,
                    cadence="月",
                    region_level="管理区",
                    message=msg + "来源：宽表 inbound + 区域目标表，统计截至 2026-09-30【确认】。",
                    raw={
                        "order_attain_rate": rate,
                        "order_target": tgt,
                        "inbound_day_avg": inbound,
                        "order_attain_enabled": enabled,
                    },
                    process_leaf="O1",
                    parallel=True,
                )
            )

    return counts
