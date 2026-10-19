#!/usr/bin/env python3
"""神策：管理区域×大分类 9月销售额（对账门输入）。"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "问题引擎"
SKILL_SCRIPTS = ROOT / ".cursor" / "skills" / "sensors" / "scripts"
sys.path.insert(0, str(SKILL_SCRIPTS))
sys.path.insert(0, str(ENGINE))

from sensors_common import run_sql, start_session  # noqa: E402
from workspace_config import load_config  # noqa: E402

from engine.category_big_crosswalk import (  # noqa: E402
    map_sensors_big,
    recon_wide_key_from_sensors_canonical,
)

OUT = ROOT / "data" / "问题引擎" / "神策_区域大分类月销_202509.csv"

AREA_MAP = {
    "粤西区": "粤西区",
    "粤东区": "粤东区",
    "华东区": "华东区",
    "长沙区": "长沙区",
    "成都区": "成都区",
    "重庆区": "重庆区",
    "武汉区": "武汉区",
    "郑州区": "郑州区",
    "南京区": "南京区",
    "合肥区": "合肥区",
    "天津区": "天津区",
    "西安区": "西安区",
    "运营中心直管": "运营中心直管",
}


def sql_area_category(db: str, start: str, end: str) -> str:
    return f"""
SELECT
  shop_operate_area AS sensors_area,
  big_category,
  SUM(COALESCE(p_paid_amt, 0)) AS paid_amt,
  COUNT(DISTINCT distinct_id) AS buyers
FROM {db}.events
WHERE event = 'payOrderDetail'
  AND date >= '{start}' AND date <= '{end}'
  AND shop_operate_area IS NOT NULL
  AND TRIM(shop_operate_area) <> ''
  AND big_category IS NOT NULL
GROUP BY shop_operate_area, big_category
"""


def main() -> int:
    cfg = load_config(str(ROOT / "sensors.workspace.yaml"))
    sid = start_session("问题引擎v33区域大分类对账", cfg)
    res = run_sql(sid, sql_area_category(cfg.database, "2026-09-01", "2026-09-30"), cfg, limit=50000)
    cols = res.get("columns") or []
    rows = []
    for row in res.get("data") or []:
        d = {cols[i]: row[i] for i in range(len(cols))}
        d["manage_area"] = AREA_MAP.get((d.get("sensors_area") or "").strip(), d.get("sensors_area"))
        d["ym"] = "2026-09"
        raw_big = (d.get("big_category") or "").strip()
        canon = map_sensors_big(raw_big) or ""
        d["canonical_big_category"] = canon
        d["recon_wide_key"] = recon_wide_key_from_sensors_canonical(canon) or ""
        rows.append(d)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "ym",
        "manage_area",
        "sensors_area",
        "big_category",
        "canonical_big_category",
        "recon_wide_key",
        "paid_amt",
        "buyers",
    ]
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
