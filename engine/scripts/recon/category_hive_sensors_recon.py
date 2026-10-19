#!/usr/bin/env python3
"""Hive 区域×大分类 vs 神策（对账第二轨，审计 CSV；不驱动 p1 商品门）。"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "问题引擎"
sys.path.insert(0, str(ENGINE))

from engine.category_big_crosswalk import (  # noqa: E402
    aggregate_sensors_for_recon,
    load_crosswalk,
    map_bdapp_big,
)

DATA = ROOT / "data" / "问题引擎"
HIVE_CSV = DATA / "Hive_区域大分类月销_202509.csv"
SENS_CSV = DATA / "神策_区域大分类月销_202509.csv"
OUT = DATA / "大分类对账_Hive神策_202609.csv"
MONTH = "2026-09"
TOL = 0.15


def load_hive_region_agg(path: Path, cfg: dict) -> dict[tuple[str, str], float]:
    hive_map = cfg.get("hive_first_to_canonical") or {}
    out: dict[tuple[str, str], float] = {}
    if not path.is_file():
        return out
    for row in csv.DictReader(path.open(encoding="utf-8-sig", newline="")):
        area = (row.get("manage_area") or row.get("manageArea") or "").strip()
        raw = (row.get("first_category_name") or row.get("categoryName") or "").strip()
        canon = hive_map.get(raw) or map_bdapp_big(raw, cfg) or raw
        if not canon:
            continue
        try:
            amt = float(row.get("total_sale_amt") or row.get("sale_amt") or 0)
        except (TypeError, ValueError):
            amt = 0.0
        out[(area, canon)] = out.get((area, canon), 0.0) + amt
    return out


def main() -> int:
    cfg = load_crosswalk()
    if not SENS_CSV.is_file():
        print(f"missing {SENS_CSV}")
        return 1
    sens_rows = list(csv.DictReader(SENS_CSV.open(encoding="utf-8-sig", newline="")))
    sens = aggregate_sensors_for_recon(sens_rows, cfg=cfg)

    if not HIVE_CSV.is_file():
        print(
            f"missing {HIVE_CSV}; run sql/问题引擎/hive_region_big_category_month_202509.sql "
            "via starrocks-db export_query"
        )
        return 2

    hive = load_hive_region_agg(HIVE_CSV, cfg)
    keys = sorted(set(hive) | set(sens))
    rows_out = []
    ok = fail = 0
    for key in keys:
        h = hive.get(key, 0.0)
        s = sens.get(key, 0.0)
        if h <= 0 and s <= 0:
            continue
        if h <= 0:
            gap = 1.0
            st = "仅神策"
        else:
            gap = abs(s - h) / h if s else 1.0
            st = "过门" if gap <= TOL else "超阈"
            if gap <= TOL:
                ok += 1
            else:
                fail += 1
        rows_out.append(
            {
                "ym": MONTH,
                "manage_area": key[0],
                "category": key[1],
                "hive_total_sale_amt": f"{h:.2f}",
                "sensors_paid_amt": f"{s:.2f}",
                "gap_pct": f"{gap * 100:.2f}",
                "status": st,
            }
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "ym",
                "manage_area",
                "category",
                "hive_total_sale_amt",
                "sensors_paid_amt",
                "gap_pct",
                "status",
            ],
        )
        w.writeheader()
        w.writerows(rows_out)
    print(f"wrote {OUT}; hive>0 pairs ok={ok} fail={fail} (tol={TOL})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
