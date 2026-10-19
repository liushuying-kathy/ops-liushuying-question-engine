#!/usr/bin/env python3
"""神策 CLI：区域×月会员指标（T10/T15 补充）。Hive 不经此脚本。"""
from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL_SCRIPTS = ROOT / ".cursor" / "skills" / "sensors" / "scripts"
sys.path.insert(0, str(SKILL_SCRIPTS))

from sensors_common import decode_output, run_sql, start_session  # noqa: E402
from workspace_config import load_config  # noqa: E402

OUT_CSV = ROOT / "data" / "问题引擎" / "神策_会员区域月指标_202509同比.csv"
OUT_CHURN = ROOT / "data" / "问题引擎" / "神策_会员流失区域_202509.csv"
OUT_CHURN_MOM = ROOT / "data" / "问题引擎" / "神策_会员流失区域_环比_202509.csv"

# 神策 shop_operate_area → 宽表管理区域
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


def sql_regional_member_month(db: str, start: str, end: str, ym: str) -> str:
    """下单时会员（virtual_is_member_thattime=是）的 ARPU、频次、件单数代理。"""
    return f"""
SELECT
  '{ym}' AS ym,
  shop_operate_area AS sensors_area,
  COUNT(DISTINCT distinct_id) AS member_buyers,
  COUNT(DISTINCT COALESCE(uni_order_id, order_id)) AS member_orders,
  SUM(COALESCE(p_paid_amt, 0)) AS member_paid_amt,
  SUM(COALESCE(goods_number, 0)) AS member_pieces
FROM {db}.events
WHERE event = 'payOrderDetail'
  AND date >= '{start}' AND date <= '{end}'
  AND virtual_is_member_thattime = '是'
  AND shop_operate_area IS NOT NULL
  AND TRIM(shop_operate_area) <> ''
GROUP BY shop_operate_area
"""


def sql_national_member_month(db: str, start: str, end: str, ym: str) -> str:
    return f"""
SELECT
  '{ym}' AS ym,
  '全国不含港澳' AS sensors_area,
  COUNT(DISTINCT distinct_id) AS member_buyers,
  COUNT(DISTINCT COALESCE(uni_order_id, order_id)) AS member_orders,
  SUM(COALESCE(p_paid_amt, 0)) AS member_paid_amt,
  SUM(COALESCE(goods_number, 0)) AS member_pieces
FROM {db}.events
WHERE event = 'payOrderDetail'
  AND date >= '{start}' AND date <= '{end}'
  AND virtual_is_member_thattime = '是'
"""


def sql_regional_churn(db: str, prev_start: str, prev_end: str, curr_start: str, curr_end: str) -> str:
    """上月活跃会员、本月未消费占比（区域）。两期各 distinct_id。"""
    return f"""
WITH prev AS (
  SELECT shop_operate_area AS area, distinct_id
  FROM {db}.events
  WHERE event = 'payOrderDetail'
    AND date >= '{prev_start}' AND date <= '{prev_end}'
    AND virtual_is_member_thattime = '是'
    AND shop_operate_area IS NOT NULL
  GROUP BY shop_operate_area, distinct_id
),
curr AS (
  SELECT shop_operate_area AS area, distinct_id
  FROM {db}.events
  WHERE event = 'payOrderDetail'
    AND date >= '{curr_start}' AND date <= '{curr_end}'
    AND virtual_is_member_thattime = '是'
    AND shop_operate_area IS NOT NULL
  GROUP BY shop_operate_area, distinct_id
),
churned AS (
  SELECT p.area, COUNT(*) AS churn_cnt
  FROM prev p
  LEFT JOIN curr c ON p.area = c.area AND p.distinct_id = c.distinct_id
  WHERE c.distinct_id IS NULL
  GROUP BY p.area
),
prev_cnt AS (
  SELECT area, COUNT(*) AS prev_cnt FROM prev GROUP BY area
)
SELECT
  pc.area AS sensors_area,
  pc.prev_cnt,
  COALESCE(ch.churn_cnt, 0) AS churn_cnt,
  COALESCE(ch.churn_cnt, 0) * 1.0 / NULLIF(pc.prev_cnt, 0) AS churn_rate
FROM prev_cnt pc
LEFT JOIN churned ch ON pc.area = ch.area
"""


def rows_from_result(payload: dict) -> list[dict]:
    if payload.get("error"):
        raise RuntimeError(payload["error"])
    cols = payload.get("columns") or []
    data = payload.get("data") or []
    out = []
    for row in data:
        out.append({cols[i]: row[i] for i in range(len(cols))})
    return out


def enrich_metrics(r: dict) -> dict:
    buyers = float(r.get("member_buyers") or 0)
    orders = float(r.get("member_orders") or 0)
    amt = float(r.get("member_paid_amt") or 0)
    pieces = float(r.get("member_pieces") or 0)
    area = r.get("sensors_area") or ""
    manage = AREA_MAP.get(area.strip(), area.strip())
    r["manage_area"] = manage
    r["arpu"] = amt / buyers if buyers else None
    r["freq"] = orders / buyers if buyers else None
    r["pieces_per_order"] = pieces / orders if orders else None
    r["pieces_per_buyer"] = pieces / buyers if buyers else None
    r["data_source"] = "sensors_payOrderDetail"
    r["wallet_weight_note"] = "会员购买重量待专题表；件单/件数仅作钱包件数腿"
    return r


def main() -> int:
    cfg = load_config(str(ROOT / "sensors.workspace.yaml"))
    db = cfg.database
    sid = start_session("问题引擎会员区域月T10T15", cfg)

    periods = [
        ("2025-09", "2025-09-01", "2025-09-30"),
        ("2026-09", "2026-09-01", "2026-09-30"),
    ]
    all_rows: list[dict] = []
    for ym, s, e in periods:
        for sql in (sql_national_member_month(db, s, e, ym),):
            res = run_sql(sid, sql, cfg, limit=50000)
            all_rows.extend(map(enrich_metrics, rows_from_result(res)))
        res = run_sql(sid, sql_regional_member_month(db, s, e, ym), cfg, limit=50000)
        all_rows.extend(map(enrich_metrics, rows_from_result(res)))

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "ym",
        "manage_area",
        "sensors_area",
        "member_buyers",
        "member_orders",
        "member_paid_amt",
        "member_pieces",
        "arpu",
        "freq",
        "pieces_per_order",
        "pieces_per_buyer",
        "data_source",
        "wallet_weight_note",
    ]
    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in all_rows:
            w.writerow(r)

    churn_res = run_sql(
        sid,
        sql_regional_churn(db, "2025-08-01", "2025-08-31", "2026-09-01", "2026-09-30"),
        cfg,
        limit=50000,
    )
    churn_rows = rows_from_result(churn_res)
    mom_specs = [
        ("mom_2026-09", "2026-08-01", "2026-08-31", "2026-09-01", "2026-09-30"),
        ("mom_2025-09", "2025-08-01", "2025-08-31", "2025-09-01", "2025-09-30"),
    ]
    mom_rows: list[dict] = []
    for label, ps, pe, cs, ce in mom_specs:
        res = run_sql(sid, sql_regional_churn(db, ps, pe, cs, ce), cfg, limit=50000)
        for r in rows_from_result(res):
            r["cohort"] = label
            r["manage_area"] = AREA_MAP.get((r.get("sensors_area") or "").strip(), r.get("sensors_area"))
            mom_rows.append(r)
    with OUT_CHURN_MOM.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["cohort", "manage_area", "sensors_area", "prev_cnt", "churn_cnt", "churn_rate"],
        )
        w.writeheader()
        for r in mom_rows:
            w.writerow(r)

    with OUT_CHURN.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["manage_area", "sensors_area", "prev_cnt", "churn_cnt", "churn_rate"],
        )
        w.writeheader()
        for r in churn_rows:
            r["manage_area"] = AREA_MAP.get((r.get("sensors_area") or "").strip(), r.get("sensors_area"))
            w.writerow(r)

    meta = {
        "session": sid,
        "rows": len(all_rows),
        "churn_regions": len(churn_rows),
        "churn_mom_rows": len(mom_rows),
        "hive": "未接入：bdapp 无 hive.* 权限，见 tools/qdm_bdapp 说明",
    }
    (ROOT / "data" / "问题引擎" / "神策_会员取数_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(meta, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
