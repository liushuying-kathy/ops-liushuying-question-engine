#!/usr/bin/env python3
"""神策 CLI：店级会员月指标 + 水果动销 SKU（T10 店级与丰富度）。按区域分片。"""
from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL_SCRIPTS = ROOT / ".cursor" / "skills" / "sensors" / "scripts"
sys.path.insert(0, str(SKILL_SCRIPTS))

from sensors_common import run_sql, start_session  # noqa: E402
from workspace_config import load_config  # noqa: E402

OUT_STORE = ROOT / "data" / "问题引擎" / "神策_会员店级月指标_202509同比.csv"
OUT_FRUIT = ROOT / "data" / "问题引擎" / "神策_水果店动销SKU_202609.csv"
OUT_META = ROOT / "data" / "问题引擎" / "神策_会员店级取数_meta.json"

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
    "香港区": "香港区",
    "运营中心直管": "运营中心直管",
}

SENSOR_AREAS = list(AREA_MAP.keys())


def rows_from_result(payload: dict) -> list[dict]:
    if payload.get("error"):
        raise RuntimeError(payload["error"])
    cols = payload.get("columns") or []
    data = payload.get("data") or []
    return [{cols[i]: row[i] for i in range(len(cols))} for row in data]


def sql_store_member_month(db: str, area: str, start: str, end: str, ym: str) -> str:
    area_esc = area.replace("'", "''")
    return f"""
SELECT
  '{ym}' AS ym,
  TRIM(UPPER(CAST(shop_id AS STRING))) AS shop_id,
  shop_operate_area AS sensors_area,
  COUNT(DISTINCT distinct_id) AS member_buyers,
  COUNT(DISTINCT COALESCE(uni_order_id, order_id)) AS member_orders,
  SUM(COALESCE(p_paid_amt, 0)) AS member_paid_amt,
  SUM(COALESCE(goods_number, 0)) AS member_pieces
FROM {db}.events
WHERE event = 'payOrderDetail'
  AND date >= '{start}' AND date <= '{end}'
  AND virtual_is_member_thattime = '是'
  AND shop_operate_area = '{area_esc}'
  AND shop_id IS NOT NULL
  AND TRIM(CAST(shop_id AS STRING)) <> ''
GROUP BY TRIM(UPPER(CAST(shop_id AS STRING))), shop_operate_area
"""


def sql_fruit_sku_month(db: str, area: str, start: str, end: str) -> str:
    area_esc = area.replace("'", "''")
    return f"""
SELECT
  TRIM(UPPER(CAST(shop_id AS STRING))) AS shop_id,
  shop_operate_area AS sensors_area,
  COUNT(DISTINCT sku_code) AS fruit_active_sku
FROM {db}.events
WHERE event = 'payOrderDetail'
  AND date >= '{start}' AND date <= '{end}'
  AND big_category = '水果类'
  AND shop_operate_area = '{area_esc}'
  AND shop_id IS NOT NULL
  AND TRIM(CAST(shop_id AS STRING)) <> ''
GROUP BY TRIM(UPPER(CAST(shop_id AS STRING))), shop_operate_area
"""


def enrich_store_row(r: dict) -> dict:
    buyers = float(r.get("member_buyers") or 0)
    orders = float(r.get("member_orders") or 0)
    amt = float(r.get("member_paid_amt") or 0)
    pieces = float(r.get("member_pieces") or 0)
    area = (r.get("sensors_area") or "").strip()
    r["manage_area"] = AREA_MAP.get(area, area)
    r["arpu"] = amt / buyers if buyers else None
    r["freq"] = orders / buyers if buyers else None
    r["pieces_per_order"] = pieces / orders if orders else None
    r["data_source"] = "sensors_payOrderDetail_store"
    return r


def main() -> int:
    cfg = load_config(str(ROOT / "sensors.workspace.yaml"))
    db = cfg.database
    sid = start_session("问题引擎会员店级与水果SKU", cfg)

    periods = [
        ("2025-09", "2025-09-01", "2025-09-30"),
        ("2026-09", "2026-09-01", "2026-09-30"),
    ]
    store_rows: list[dict] = []
    fruit_rows: list[dict] = []
    shards: list[str] = []

    for area in SENSOR_AREAS:
        shards.append(area)
        for ym, s, e in periods:
            res = run_sql(sid, sql_store_member_month(db, area, s, e, ym), cfg, limit=50000)
            store_rows.extend(map(enrich_store_row, rows_from_result(res)))
        res = run_sql(sid, sql_fruit_sku_month(db, area, "2026-09-01", "2026-09-30"), cfg, limit=50000)
        for r in rows_from_result(res):
            sa = (r.get("sensors_area") or "").strip()
            r["manage_area"] = AREA_MAP.get(sa, sa)
            r["ym"] = "2026-09"
            fruit_rows.append(r)

    OUT_STORE.parent.mkdir(parents=True, exist_ok=True)
    store_fields = [
        "ym",
        "shop_id",
        "manage_area",
        "sensors_area",
        "member_buyers",
        "member_orders",
        "member_paid_amt",
        "member_pieces",
        "arpu",
        "freq",
        "pieces_per_order",
        "data_source",
    ]
    with OUT_STORE.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=store_fields, extrasaction="ignore")
        w.writeheader()
        for r in store_rows:
            w.writerow(r)

    with OUT_FRUIT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["ym", "shop_id", "manage_area", "sensors_area", "fruit_active_sku"])
        w.writeheader()
        for r in fruit_rows:
            w.writerow(r)

    meta = {
        "session": sid,
        "store_rows": len(store_rows),
        "fruit_rows": len(fruit_rows),
        "shards": shards,
        "periods": periods,
        "fruit_month": "2026-09",
        "wallet_weight_note": "会员购买重量待宽表",
        "fruit_threshold_note": "丰富度阈值 yaml fruit_active_sku=15；近6个月分布改阈值为后续",
    }
    OUT_META.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
