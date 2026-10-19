#!/usr/bin/env python3
"""神策：近6个月各区域水果店均动销 SKU，供 fruit_active_sku 阈值建议。"""
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL_SCRIPTS = ROOT / ".cursor" / "skills" / "sensors" / "scripts"
sys.path.insert(0, str(SKILL_SCRIPTS))

from sensors_common import run_sql, start_session  # noqa: E402
from workspace_config import load_config  # noqa: E402

OUT = ROOT / "data" / "问题引擎" / "神策_水果区域月均值_202504-202609.csv"
OUT_META = ROOT / "data" / "问题引擎" / "神策_水果6月_meta.json"

AREAS = [
    "粤西区",
    "粤东区",
    "华东区",
    "长沙区",
    "成都区",
    "重庆区",
    "武汉区",
    "郑州区",
    "南京区",
    "合肥区",
    "天津区",
    "西安区",
    "运营中心直管",
]

MONTHS = [
    ("2026-04", "2026-04-01", "2026-04-30"),
    ("2026-05", "2026-05-01", "2026-05-31"),
    ("2026-06", "2026-06-01", "2026-06-30"),
    ("2026-07", "2026-07-01", "2026-07-31"),
    ("2026-08", "2026-08-01", "2026-08-31"),
    ("2026-09", "2026-09-01", "2026-09-30"),
]


def sql_area_fruit(db: str, area: str, start: str, end: str, ym: str) -> str:
    a = area.replace("'", "''")
    return f"""
SELECT
  '{ym}' AS ym,
  '{a}' AS sensors_area,
  AVG(shop_sku) AS fruit_avg_active_sku,
  COUNT(*) AS shop_cnt
FROM (
  SELECT
    TRIM(UPPER(CAST(shop_id AS STRING))) AS shop_id,
    COUNT(DISTINCT sku_code) AS shop_sku
  FROM {db}.events
  WHERE event = 'payOrderDetail'
    AND date >= '{start}' AND date <= '{end}'
    AND big_category = '水果类'
    AND shop_operate_area = '{a}'
    AND shop_id IS NOT NULL
  GROUP BY 1
) t
"""


def rows_from_result(payload: dict) -> list[dict]:
    if payload.get("error"):
        raise RuntimeError(payload["error"])
    cols = payload.get("columns") or []
    data = payload.get("data") or []
    return [{cols[i]: row[i] for i in range(len(cols))} for row in data]


def main() -> int:
    cfg = load_config(str(ROOT / "sensors.workspace.yaml"))
    db = cfg.database
    sid = start_session("问题引擎水果6月区域均值", cfg)
    rows: list[dict] = []
    for area in AREAS:
        for ym, s, e in MONTHS:
            res = run_sql(sid, sql_area_fruit(db, area, s, e, ym), cfg, limit=5000)
            for r in rows_from_result(res):
                r["manage_area"] = area
                rows.append(r)

    below15_by_area: dict[str, int] = defaultdict(int)
    for r in rows:
        avg = float(r.get("fruit_avg_active_sku") or 0)
        if avg < 15:
            below15_by_area[r["manage_area"]] += 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["ym", "manage_area", "sensors_area", "fruit_avg_active_sku", "shop_cnt"],
        )
        w.writeheader()
        for r in rows:
            w.writerow(r)

    suggestions = []
    for area, cnt in below15_by_area.items():
        if cnt >= 3:
            suggestions.append(
                {
                    "manage_area": area,
                    "months_below_15": cnt,
                    "suggest_threshold_note": "过半区域每月<15时改yaml下沿至仍低于18的一档（v1.8）",
                }
            )

    meta = {"session": sid, "rows": len(rows), "threshold_suggestions": suggestions}
    OUT_META.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
