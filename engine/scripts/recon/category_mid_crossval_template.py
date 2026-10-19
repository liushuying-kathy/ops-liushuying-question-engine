#!/usr/bin/env python3
"""店×中分类 Hive vs 神策 TopN 偏差登记（交叉验模板；需互映 CSV 落盘后运行）。"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "问题引擎"
HIVE = DATA / "Hive_店级中分类月销_202509.csv"
SENS = DATA / "神策_店级中分类月销_202509.csv"
BRIDGE = DATA / "店号互映_20260930.csv"
OUT = DATA / "中分类交叉验_TopN_202609.csv"
TOP_N = 20
TOL = 0.20


def main() -> int:
    missing = [p for p in (HIVE, SENS, BRIDGE) if not p.is_file()]
    if missing:
        print("missing inputs (export via MCP + dim snapshot):")
        for p in missing:
            print(f"  - {p}")
        print("bridge columns: sp_store_id,sensors_store_key,hive_store_id")
        return 2

    bridge: dict[str, str] = {}
    for row in csv.DictReader(BRIDGE.open(encoding="utf-8-sig", newline="")):
        sp = (row.get("sp_store_id") or "").strip().upper()
        sk = (row.get("sensors_store_key") or row.get("sap_shop_id") or "").strip()
        hk = (row.get("hive_store_id") or row.get("store_id") or sp).strip()
        if sp and sk:
            bridge[sk] = sp
        if sp and hk:
            bridge[f"hive:{hk}"] = sp

    def agg(path: Path, key_field: str, use_bridge: str) -> dict[tuple[str, str], float]:
        out: dict[tuple[str, str], float] = defaultdict(float)
        for row in csv.DictReader(path.open(encoding="utf-8-sig", newline="")):
            raw_key = (row.get("store_key") or row.get("store_id") or "").strip()
            if use_bridge == "sensors":
                sp = bridge.get(raw_key)
            else:
                sp = bridge.get(f"hive:{raw_key}") or bridge.get(raw_key)
            if not sp:
                continue
            mid = (row.get(key_field) or row.get("mid_category_name") or "").strip()
            if not mid:
                continue
            out[(sp, mid)] += float(row.get("paid_amt") or row.get("total_sale_amt") or 0)
        return out

    hive_a = agg(HIVE, "mid_category_name", "hive")
    sens_a = agg(SENS, "mid_category", "sensors")
    by_store: dict[str, list[tuple[str, float, float]]] = defaultdict(list)
    for key in set(hive_a) | set(sens_a):
        h = hive_a.get(key, 0.0)
        s = sens_a.get(key, 0.0)
        if h <= 0 and s <= 0:
            continue
        gap = abs(s - h) / h if h > 0 else 1.0
        by_store[key[0]].append((key[1], h, s, gap))

    rows = []
    for store, items in by_store.items():
        items.sort(key=lambda x: x[1], reverse=True)
        for mid, h, s, gap in items[:TOP_N]:
            rows.append(
                {
                    "sp_store_id": store,
                    "mid_category": mid,
                    "hive_amt": f"{h:.2f}",
                    "sensors_amt": f"{s:.2f}",
                    "gap_pct": f"{gap * 100:.2f}",
                    "status": "过门" if gap <= TOL else "超阈",
                }
            )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["sp_store_id", "mid_category", "hive_amt", "sensors_amt", "gap_pct", "status"],
        )
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
