#!/usr/bin/env python3
"""Hive 大类/店×中类 9 月 CSV 落盘（starrocks-db MCP + bdp-sso）。"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from hive_mcp_client import export_query_to_file, get_bdp_token, query_all_rows  # noqa: E402

DATA = ROOT / "data" / "问题引擎"
SQL_DIR = ROOT / "sql" / "问题引擎"

OUT_REGION = DATA / "Hive_区域大分类月销_202509.csv"
OUT_MID = DATA / "Hive_店级中分类月销_202509.csv"

SQL_REGION = (SQL_DIR / "hive_region_big_category_month_202509.sql").read_text(encoding="utf-8")
SQL_MID = """
SELECT
  TRIM(f.store_id) AS store_id,
  TRIM(p.manage_area_name) AS manage_area,
  TRIM(f.second_category_id) AS second_category_id,
  TRIM(f.second_category_name) AS mid_category_name,
  SUM(COALESCE(f.total_sale_amt, 0)) AS total_sale_amt
FROM hive.dal_full_link.dal_manage_full_link_store_dc_article_info_di f
INNER JOIN hive.dim.dim_store_profile p
  ON TRIM(f.store_id) = TRIM(p.sp_store_id)
WHERE f.business_date >= '2026-09-01'
  AND f.business_date <= '2026-09-30'
  AND p.sp_level = '1'
  AND TRIM(p.manage_area_name) NOT IN ('香港区', '澳门区', '香港', '澳门')
  AND f.second_category_name IS NOT NULL
  AND TRIM(f.second_category_name) <> ''
GROUP BY
  TRIM(f.store_id),
  TRIM(p.manage_area_name),
  TRIM(f.second_category_id),
  TRIM(f.second_category_name)
ORDER BY manage_area, store_id, mid_category_name
"""


def _write_region_from_rows(rows: list[dict], path: Path) -> None:
    fields = ["manage_area", "first_category_name", "total_sale_amt", "ym"]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({**r, "ym": "2026-09"})


def _write_mid_from_export(path: Path) -> None:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    lines = text.splitlines()
    if not lines:
        return
    # export may already be CSV with header
    out = DATA / "Hive_店级中分类月销_202509.csv"
    if path != out:
        out.write_text(text, encoding="utf-8-sig")
    else:
        # add ym column if missing
        reader = csv.DictReader(lines)
        if reader.fieldnames and "ym" not in reader.fieldnames:
            rows = list(reader)
            with out.open("w", encoding="utf-8-sig", newline="") as f:
                w = csv.DictWriter(f, fieldnames=[*(reader.fieldnames or []), "ym"])
                w.writeheader()
                for r in rows:
                    r["ym"] = "2026-09"
                    w.writerow(r)


def main() -> int:
    token = get_bdp_token()
    region_sql = "\n".join(
        line for line in SQL_REGION.splitlines() if not line.strip().startswith("--")
    ).strip()
    print("fetch region big category...")
    rows = query_all_rows(region_sql, token=token)
    if not rows:
        print("region query returned 0 rows, trying export_query...")
        tmp = DATA / "_scratch_hive_region_big.csv"
        export_query_to_file(region_sql, str(tmp), token=token)
        rows = list(csv.DictReader(tmp.open(encoding="utf-8-sig", newline="")))
    _write_region_from_rows(rows, OUT_REGION)
    print(f"wrote {len(rows)} rows -> {OUT_REGION}")

    print("fetch store x mid (export)...")
    mid_tmp = DATA / "_scratch_hive_store_mid.csv"
    export_query_to_file(SQL_MID, str(mid_tmp), token=token, max_rows=100000)
    _write_mid_from_export(mid_tmp)
    print(f"mid export -> {OUT_MID}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
