#!/usr/bin/env python3
"""合并 A1 按管理区分片 CSV → Hive_店日中级KPI_202509.csv"""
from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INDIR = ROOT / "data" / "问题引擎" / "_scratch" / "a1_by_area"
OUT = ROOT / "data" / "问题引擎" / "Hive_店日中级KPI_202509.csv"


def _shard_files() -> list[Path]:
    all_files = sorted(INDIR.glob("Hive_店日中级KPI_202509_*.csv"))
    prefix = "Hive_店日中级KPI_202509_"
    suffixes = {p.stem.removeprefix(prefix) for p in all_files}
    child_manages: set[str] = set()
    sap_with_halves: set[str] = set()
    halves_with_weeks: set[str] = set()
    for suffix in suffixes:
        if "_" in suffix:
            child_manages.add(suffix.split("_", 1)[0])
        if suffix.endswith("_H1") or suffix.endswith("_H2"):
            sap_with_halves.add(suffix[:-3])
        if "_H1_W" in suffix or "_H2_W" in suffix:
            halves_with_weeks.add(suffix.rsplit("_", 1)[0])
    out: list[Path] = []
    for p in all_files:
        suffix = p.stem.removeprefix(prefix)
        if "_" not in suffix and suffix in child_manages:
            continue
        if suffix in sap_with_halves:
            continue
        if suffix in halves_with_weeks:
            continue
        out.append(p)
    return out


def main() -> int:
    files = _shard_files()
    if not files:
        print(f"no shards in {INDIR}")
        return 2
    total = 0
    with OUT.open("w", encoding="utf-8-sig", newline="") as out_f:
        writer = None
        header = None
        for i, p in enumerate(files):
            rows = list(csv.reader(p.open(encoding="utf-8-sig", newline="")))
            if not rows:
                continue
            if i == 0:
                header = rows[0]
                writer = csv.writer(out_f)
                writer.writerow(header)
                body = rows[1:]
            else:
                body = rows[1:] if rows[0] == header else rows
            writer.writerows(body)
            total += len(body)
    print(f"merged {len(files)} shards, {total} rows -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
