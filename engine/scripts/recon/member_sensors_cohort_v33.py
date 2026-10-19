#!/usr/bin/env python3
"""神策：会员活跃与上月留存（区域×月）。新增/回流需首购日，全表扫描易 504，默认仅输出留存结构。"""
from __future__ import annotations

import csv
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL_SCRIPTS = ROOT / ".cursor" / "skills" / "sensors" / "scripts"
sys.path.insert(0, str(SKILL_SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sensors_common import run_sql, start_session  # noqa: E402
from workspace_config import load_config  # noqa: E402
from member_sensors_monthly import rows_from_result  # noqa: E402

OUT = ROOT / "data" / "问题引擎" / "神策_会员cohort_202509.csv"

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


def sql_retained_structure(db: str, prev_s: str, prev_e: str, curr_s: str, curr_e: str) -> str:
    return f"""
WITH prev AS (
  SELECT shop_operate_area AS area, distinct_id
  FROM {db}.events
  WHERE event = 'payOrderDetail'
    AND date >= '{prev_s}' AND date <= '{prev_e}'
    AND virtual_is_member_thattime = '是'
    AND shop_operate_area IS NOT NULL
    AND TRIM(shop_operate_area) <> ''
  GROUP BY shop_operate_area, distinct_id
),
curr AS (
  SELECT shop_operate_area AS area, distinct_id
  FROM {db}.events
  WHERE event = 'payOrderDetail'
    AND date >= '{curr_s}' AND date <= '{curr_e}'
    AND virtual_is_member_thattime = '是'
    AND shop_operate_area IS NOT NULL
    AND TRIM(shop_operate_area) <> ''
  GROUP BY shop_operate_area, distinct_id
)
SELECT
  c.area AS sensors_area,
  COUNT(*) AS active_members,
  SUM(CASE WHEN p.distinct_id IS NOT NULL THEN 1 ELSE 0 END) AS retained
FROM curr c
LEFT JOIN prev p ON c.area = p.area AND c.distinct_id = p.distinct_id
GROUP BY c.area
"""


def sql_incremental_split(
    db: str, prev_s: str, prev_e: str, curr_s: str, curr_e: str, hist_start: str = "2023-01-01"
) -> str:
    """增量会员在 hist_start 前无会员消费视为新增（近似首购落在本期）。"""
    return f"""
WITH prev AS (
  SELECT shop_operate_area AS area, distinct_id
  FROM {db}.events
  WHERE event = 'payOrderDetail'
    AND date >= '{prev_s}' AND date <= '{prev_e}'
    AND virtual_is_member_thattime = '是'
    AND shop_operate_area IS NOT NULL
  GROUP BY shop_operate_area, distinct_id
),
curr AS (
  SELECT shop_operate_area AS area, distinct_id
  FROM {db}.events
  WHERE event = 'payOrderDetail'
    AND date >= '{curr_s}' AND date <= '{curr_e}'
    AND virtual_is_member_thattime = '是'
    AND shop_operate_area IS NOT NULL
  GROUP BY shop_operate_area, distinct_id
),
inc AS (
  SELECT c.area, c.distinct_id
  FROM curr c
  LEFT JOIN prev p ON c.area = p.area AND c.distinct_id = p.distinct_id
  WHERE p.distinct_id IS NULL
),
hist AS (
  SELECT i.area, i.distinct_id, 1 AS seen_before
  FROM inc i
  INNER JOIN {db}.events e
    ON e.distinct_id = i.distinct_id
   AND e.shop_operate_area = i.area
  WHERE e.event = 'payOrderDetail'
    AND e.virtual_is_member_thattime = '是'
    AND e.date >= '{hist_start}' AND e.date < '{curr_s}'
  GROUP BY i.area, i.distinct_id
)
SELECT
  i.area AS sensors_area,
  COUNT(*) AS incremental_members,
  SUM(CASE WHEN h.seen_before IS NULL THEN 1 ELSE 0 END) AS new_members,
  SUM(CASE WHEN h.seen_before IS NOT NULL THEN 1 ELSE 0 END) AS returning_members
FROM inc i
LEFT JOIN hist h ON i.area = h.area AND i.distinct_id = h.distinct_id
GROUP BY i.area
"""


def sql_incremental_split_area(
    db: str,
    area: str,
    prev_s: str,
    prev_e: str,
    curr_s: str,
    curr_e: str,
    hist_start: str = "2025-01-01",
) -> str:
    esc = area.replace("'", "''")
    ap = f"AND shop_operate_area = '{esc}'"
    return f"""
WITH prev AS (
  SELECT distinct_id FROM {db}.events
  WHERE event = 'payOrderDetail' AND virtual_is_member_thattime = '是'
    AND date >= '{prev_s}' AND date <= '{prev_e}' {ap}
  GROUP BY distinct_id
),
curr AS (
  SELECT distinct_id FROM {db}.events
  WHERE event = 'payOrderDetail' AND virtual_is_member_thattime = '是'
    AND date >= '{curr_s}' AND date <= '{curr_e}' {ap}
  GROUP BY distinct_id
),
inc AS (
  SELECT c.distinct_id FROM curr c
  LEFT JOIN prev p ON c.distinct_id = p.distinct_id
  WHERE p.distinct_id IS NULL
),
hist AS (
  SELECT i.distinct_id, 1 AS seen_before
  FROM inc i
  INNER JOIN {db}.events e ON e.distinct_id = i.distinct_id
  WHERE e.event = 'payOrderDetail' AND e.virtual_is_member_thattime = '是'
    AND e.date >= '{hist_start}' AND e.date < '{curr_s}' {ap}
  GROUP BY i.distinct_id
)
SELECT
  '{esc}' AS sensors_area,
  COUNT(*) AS incremental_members,
  SUM(CASE WHEN h.seen_before IS NULL THEN 1 ELSE 0 END) AS new_members,
  SUM(CASE WHEN h.seen_before IS NOT NULL THEN 1 ELSE 0 END) AS returning_members
FROM inc i
LEFT JOIN hist h ON i.distinct_id = h.distinct_id
"""


def run_with_retry(sid: str, cfg, sql: str, retries: int = 3) -> list[dict]:
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            res = run_sql(sid, sql, cfg, limit=50000)
            return rows_from_result(res)
        except RuntimeError as e:
            last_err = e
            if attempt < retries:
                time.sleep(10 * (attempt + 1))
                continue
            raise
    raise last_err or RuntimeError("cohort query failed")


def main() -> int:
    cfg = load_config(str(ROOT / "sensors.workspace.yaml"))
    db = cfg.database
    sid = start_session("问题引擎v33会员cohort", cfg)
    prev_s, prev_e = "2025-09-01", "2025-09-30"
    curr_s, curr_e = "2026-09-01", "2026-09-30"
    sql = sql_retained_structure(db, prev_s, prev_e, curr_s, curr_e)
    raw = run_with_retry(sid, cfg, sql)
    split_by_area: dict[str, dict] = {}
    small_areas = ("南京区", "天津区", "西安区", "合肥区", "运营中心直管")
    for area in small_areas:
        try:
            srows = run_with_retry(
                sid,
                cfg,
                sql_incremental_split_area(db, area, prev_s, prev_e, curr_s, curr_e),
                retries=0,
            )
            if srows:
                split_by_area[area] = srows[0]
        except RuntimeError:
            continue

    rows: list[dict] = []
    for d in raw:
        active = float(d.get("active_members") or 0)
        retained = float(d.get("retained") or 0)
        incremental = max(active - retained, 0)
        area = (d.get("sensors_area") or "").strip()
        sp = split_by_area.get(area) or {}
        new_m = sp.get("new_members")
        ret_m = sp.get("returning_members")
        reliable = "1" if area in split_by_area and new_m is not None else "0"
        note = (
            "增量拆分：2025-01-01 至统计月前无会员消费记为新增，其余为回流【估算】"
            if reliable == "1"
            else "拆分失败时仅输出活跃与上月留存"
        )
        rows.append(
            {
                "ym": "2026-09",
                "manage_area": AREA_MAP.get(area, area),
                "sensors_area": area,
                "active_members": int(active),
                "retained": int(retained),
                "incremental_members": int(incremental),
                "new_members": int(float(new_m)) if new_m is not None and reliable == "1" else "",
                "returning_members": int(float(ret_m)) if ret_m is not None and reliable == "1" else "",
                "split_reliable": reliable,
                "split_note": note,
            }
        )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "ym",
        "manage_area",
        "sensors_area",
        "active_members",
        "retained",
        "incremental_members",
        "new_members",
        "returning_members",
        "split_reliable",
        "split_note",
    ]
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
