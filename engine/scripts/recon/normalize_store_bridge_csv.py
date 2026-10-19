#!/usr/bin/env python3
"""bdapp 导出 camelCase 列名 → snake_case（店号互映）。"""
from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "data" / "问题引擎" / "店号互映_20260930.csv"
MAP = {
    "spStoreId": "sp_store_id",
    "spStoreIdRaw": "sp_store_id_raw",
    "hiveStoreId": "hive_store_id",
    "sensorsStoreKey": "sensors_store_key",
    "manageArea": "manage_area",
    "sapAreaName": "sap_area_name",
    "cityDescription": "city_description",
}
FIELDS = list(MAP.values())


def main() -> int:
    rows = list(csv.DictReader(PATH.open(encoding="utf-8-sig", newline="")))
    with PATH.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            out = {}
            for camel, snake in MAP.items():
                out[snake] = r.get(camel) or r.get(snake) or ""
            w.writerow(out)
    print(f"normalized {len(rows)} rows at {PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
