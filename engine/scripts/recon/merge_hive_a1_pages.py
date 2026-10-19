#!/usr/bin/env python3
"""合并 A1 分页 CSV（GROKBOT export_query 分片）为单文件。首文件保留表头，其余跳过表头。"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGES_DIR = ROOT / "data" / "问题引擎" / "_scratch" / "a1_pages"
OUT = ROOT / "data" / "问题引擎" / "Hive_店日中级KPI_202509.csv"


def main() -> int:
    if not PAGES_DIR.is_dir():
        print(f"missing {PAGES_DIR}")
        return 2
    parts = sorted(PAGES_DIR.glob("page_*.csv"))
    if not parts:
        print(f"no page_*.csv in {PAGES_DIR}")
        return 2
    total = 0
    header: list[str] | None = None
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8-sig", newline="") as out_f:
        writer: csv.writer | None = None
        for i, p in enumerate(parts):
            with p.open(encoding="utf-8-sig", newline="") as inf:
                reader = csv.reader(inf)
                rows = list(reader)
            if not rows:
                continue
            if i == 0:
                header = rows[0]
                writer = csv.writer(out_f)
                writer.writerow(header)
                data = rows[1:]
            else:
                data = rows[1:] if rows[0] == header else rows
            if writer:
                writer.writerows(data)
                total += len(data)
    print(f"merged {len(parts)} parts, {total} data rows -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
