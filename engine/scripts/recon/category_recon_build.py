#!/usr/bin/env python3
"""按 category_big_crosswalk 重算区域×大分类对账明细，并导出口径对照表。"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "问题引擎"))

from engine.category_big_crosswalk import (  # noqa: E402
    aggregate_sensors_for_recon,
    aggregate_wide_for_recon,
    crosswalk_rows_for_export,
    load_crosswalk,
)

DATA = ROOT / "data" / "问题引擎"
MONTH = "2026-09"
TOL = 0.15


def main() -> int:
    cfg = load_crosswalk()
    sens_rows = list(csv.DictReader((DATA / "神策_区域大分类月销_202509.csv").open(encoding="utf-8-sig", newline="")))
    wide_rows = list(csv.DictReader((DATA / "店级大分类销售月_202509同比.csv").open(encoding="utf-8-sig", newline="")))
    sens = aggregate_sensors_for_recon(sens_rows, cfg=cfg)
    wide = aggregate_wide_for_recon(wide_rows, month_label=MONTH, cfg=cfg)

    out_recon = DATA / "大分类对账_202609.csv"
    out_map = DATA / "大分类口径对照表.csv"
    out_map.parent.mkdir(parents=True, exist_ok=True)

    with out_map.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["sensors_big_category", "canonical_big", "recon_wide_key", "note"],
        )
        w.writeheader()
        w.writerows(crosswalk_rows_for_export(cfg))

    keys = sorted(set(wide) | set(sens))
    ok = fail = 0
    detail: list[dict] = []
    for key in keys:
        w_amt = wide.get(key, 0.0)
        s_amt = sens.get(key, 0.0)
        if w_amt <= 0 and s_amt <= 0:
            continue
        if w_amt <= 0:
            gap = 1.0
            status = "仅神策"
        else:
            gap = abs(s_amt - w_amt) / w_amt if s_amt else 1.0
            status = "过门" if gap <= TOL else "超阈"
        if w_amt > 0:
            if gap <= TOL:
                ok += 1
            else:
                fail += 1
        detail.append(
            {
                "ym": MONTH,
                "manage_area": key[0],
                "recon_wide_key": key[1],
                "wide_sale_amt": f"{w_amt:.2f}",
                "sensors_paid_amt": f"{s_amt:.2f}",
                "gap_pct": f"{gap * 100:.2f}",
                "status": status,
            }
        )

    with out_recon.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "ym",
                "manage_area",
                "recon_wide_key",
                "wide_sale_amt",
                "sensors_paid_amt",
                "gap_pct",
                "status",
            ],
        )
        w.writeheader()
        w.writerows(detail)

    print(f"wrote {out_map} ({out_map.stat().st_size} bytes)")
    print(f"wrote {out_recon} pairs with wide>0: ok={ok} fail={fail} (tol={TOL})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
