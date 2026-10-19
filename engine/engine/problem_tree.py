"""问题树 JSON 真源（B3-1/B3-2）：由 L1 行 + issue_bundle 组装。"""
from __future__ import annotations

from typing import Any

from .issue_bundle import build_issue_bundle, build_daily_issue_bundle, index_daily_region
from .spatial import spatial_nodes_for_area


def _spatial_nodes(problems: list[dict], manage_area: str) -> list[dict]:
    return spatial_nodes_for_area(problems, manage_area, limit=12)


def _store_cell_nodes(problems: list[dict], manage_area: str, leaf: str) -> list[dict]:
    cells: list[tuple[float, dict]] = []
    for p in problems:
        if p.get("cadence") != "月" or p.get("region_level") != "店型":
            continue
        if (p.get("parent_scope") or "") != manage_area:
            continue
        if leaf and (p.get("process_leaf") or "") != leaf:
            continue
        raw = p.get("raw") or {}
        y = raw.get("sale_yoy")
        try:
            key = float(y) if y is not None else 0.0
        except (TypeError, ValueError):
            key = 0.0
        cells.append((key, p))
    cells.sort(key=lambda x: x[0])
    return [
        {
            "cell": (p.get("raw") or {}).get("cell") or p.get("scope"),
            "message": p.get("message"),
            "problem_id": p.get("problem_id"),
        }
        for _, p in cells[:4]
    ]


def problem_dict_to_tree(primary: dict, problems: list[dict]) -> dict[str, Any]:
    bundle = build_issue_bundle(primary, problems)
    area = bundle["scope"]
    leaf = bundle["primary_leaf"]
    return {
        "problem_id": primary.get("problem_id") or (primary.get("raw") or {}).get("problem_id"),
        "scope": area,
        "primary_leaf": leaf,
        "entry_id": primary.get("entry_id") or "",
        "headline": bundle["headline"],
        "tomorrow": bundle["tomorrow"],
        "sections": {
            "decompose": bundle["decompose"],
            "parallel": bundle["parallel"],
            "category": bundle["category"],
            "member": bundle["member"],
            "positioning": bundle["positioning"],
            "spatial": _spatial_nodes(problems, area),
            "store_cells": _store_cell_nodes(problems, area, leaf if leaf in ("S1", "E2") else "S1"),
        },
    }


def build_executive_trees(
    problems: list[dict],
    ceo_primaries: list[dict],
    cfo_primaries: list[dict],
) -> dict[str, Any]:
    ceo_trees = [problem_dict_to_tree(p, problems) for p in ceo_primaries]
    cfo_trees = [problem_dict_to_tree(p, problems) for p in cfo_primaries]
    cfo_ids = {t["problem_id"] for t in cfo_trees}
    for t in ceo_trees:
        t["in_cfo_fold"] = t["problem_id"] in cfo_ids
    return {
        "schema": "problem_tree.v1",
        "ceo": ceo_trees,
        "cfo": cfo_trees,
    }


def store_operating_tree(store_row: dict, problems: list[dict], manage_area: str) -> dict[str, Any]:
    """单店：跟店提示 + 同店月频行（订购→销售→促销→消费者全链投影）。"""
    sid = str(store_row.get("scope") or "")
    rows = [
        p
        for p in problems
        if p.get("object_type") == "store"
        and str(p.get("scope") or "") == sid
        and p.get("cadence") == "月"
    ]
    # 日扫同店行也纳入销售段（有数则展，不发明）
    daily_rows = [
        p
        for p in problems
        if p.get("object_type") == "store"
        and str(p.get("scope") or "") == sid
        and p.get("cadence") == "日"
    ]
    chain = {
        "order": [],
        "sale": [],
        "promo": [],
        "consumer": [],
    }
    for p in rows:
        leaf = (p.get("process_leaf") or "").strip()
        msg = p.get("message") or ""
        if leaf in ("O1", "O2") or "订购" in msg or "进货" in msg:
            chain["order"].append(msg)
        elif leaf in ("S1", "S2", "B1", "E2", "E3", "E1") or "销售" in msg or "来客" in msg or "毛利" in msg or "净利" in msg:
            chain["sale"].append(msg)
        elif leaf in ("M1", "M2", "M1a", "M1b") or "促销" in msg or "折扣" in msg:
            chain["promo"].append(msg)
        elif leaf in ("B1a", "B2", "B2b", "C1b") or "会员" in msg or "客单价" in msg:
            chain["consumer"].append(msg)
        else:
            if msg:
                chain["consumer"].append(msg)
    for p in daily_rows[:12]:
        msg = p.get("message") or ""
        if msg and msg not in chain["sale"]:
            chain["sale"].append(msg)
    if not chain["order"]:
        for p in problems:
            if (
                p.get("cadence") == "月"
                and p.get("scope") == manage_area
                and (p.get("process_leaf") or "") == "O2"
            ):
                chain["order"].append(
                    (p.get("message") or "") + "（管理区进货重量，店级无订购目标表）"
                )
                break
        if not chain["order"]:
            attain = (store_row.get("raw") or {}).get("order_attain")
            if attain:
                chain["order"].append(f"订购达标：{attain}（区域口径）")
            else:
                chain["order"].append(
                    "订购目标：全公司目标表未接入，不占假达标；进货重量见区域月频并行片。"
                )
    if not any("客件数" in (x or "") for x in chain["consumer"]):
        chain["consumer"].append(
            "客件数：【旁路/待核】（字段未解冻，节点占位，不写业务数）。"
        )
    headline = store_row.get("message") or ""
    if headline and headline not in chain["sale"]:
        chain["sale"].insert(0, headline)
    return {
        "store_id": sid,
        "manage_area": manage_area,
        "headline": store_row.get("message"),
        "process_leaf": store_row.get("process_leaf"),
        "chain": chain,
    }
