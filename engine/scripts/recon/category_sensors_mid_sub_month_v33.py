#!/usr/bin/env python3
"""神策：店×中分类 / 店×小分类 9 月销售额（B1-7 交叉验输入）。"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL_SCRIPTS = ROOT / ".cursor" / "skills" / "sensors" / "scripts"
sys.path.insert(0, str(SKILL_SCRIPTS))

from sensors_common import run_sql, start_session  # noqa: E402
from workspace_config import load_config  # noqa: E402

OUT_MID = ROOT / "data" / "问题引擎" / "神策_店级中分类月销_202509.csv"
OUT_SUB = ROOT / "data" / "问题引擎" / "神策_店级小分类月销_202509.csv"


def sql_store_mid(db: str, start: str, end: str) -> str:
    return f"""
SELECT
  COALESCE(sap_shop_id, shop_id) AS store_key,
  shop_operate_area,
  mid_category,
  SUM(COALESCE(p_paid_amt, 0)) AS paid_amt
FROM {db}.events
WHERE event = 'payOrderDetail'
  AND date >= '{start}' AND date <= '{end}'
  AND mid_category IS NOT NULL
  AND TRIM(mid_category) <> ''
GROUP BY COALESCE(sap_shop_id, shop_id), shop_operate_area, mid_category
"""


def sql_store_sub(db: str, start: str, end: str) -> str:
    return f"""
SELECT
  COALESCE(sap_shop_id, shop_id) AS store_key,
  shop_operate_area,
  category,
  SUM(COALESCE(p_paid_amt, 0)) AS paid_amt
FROM {db}.events
WHERE event = 'payOrderDetail'
  AND date >= '{start}' AND date <= '{end}'
  AND category IS NOT NULL
  AND TRIM(category) <> ''
GROUP BY COALESCE(sap_shop_id, shop_id), shop_operate_area, category
"""


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    cfg = load_config(str(ROOT / "sensors.workspace.yaml"))
    sid = start_session("问题引擎v33店级中小分类", cfg)
    for label, sql, out, fields in (
        (
            "mid",
            sql_store_mid(cfg.database, "2026-09-01", "2026-09-30"),
            OUT_MID,
            ["ym", "store_key", "shop_operate_area", "mid_category", "paid_amt"],
        ),
        (
            "sub",
            sql_store_sub(cfg.database, "2026-09-01", "2026-09-30"),
            OUT_SUB,
            ["ym", "store_key", "shop_operate_area", "category", "paid_amt"],
        ),
    ):
        res = run_sql(sid, sql, cfg, limit=50000)
        cols = res.get("columns") or []
        rows = []
        for row in res.get("data") or []:
            d = {cols[i]: row[i] for i in range(len(cols))}
            d["ym"] = "2026-09"
            rows.append(d)
        write_csv(out, fields, rows)
        print(f"{label}: wrote {len(rows)} rows to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
