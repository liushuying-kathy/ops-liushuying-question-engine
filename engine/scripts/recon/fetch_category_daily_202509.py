#!/usr/bin/env python3
"""分片拉取 2026-09 大分类日 KPI 并合并（避免 bdapp 30s 超时）。"""
from __future__ import annotations

import csv
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SQL_DIR = ROOT / "sql" / "问题引擎"
OUT = ROOT / "data" / "问题引擎" / "大分类日KPI_202509对日.csv"
SHARDS = (
    ("引擎_大分类日KPI_202509对日_上旬.sql", "_scratch_cat_daily_h1.csv"),
    ("引擎_大分类日KPI_202509对日_下旬.sql", "_scratch_cat_daily_h2.csv"),
)


def main() -> int:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "tools" / "qdm_bdapp")
    data_dir = OUT.parent
    data_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    header: list[str] | None = None
    for sql_name, scratch in SHARDS:
        sql_path = SQL_DIR / sql_name
        if not sql_path.is_file():
            print(f"skip missing {sql_path}", file=sys.stderr)
            continue
        out_path = data_dir / scratch
        cmd = [
            sys.executable,
            "-m",
            "qdm_bdapp",
            "--all-pages",
            str(sql_path),
            str(out_path),
        ]
        print("run", " ".join(cmd), flush=True)
        subprocess.run(cmd, env=env, check=True, cwd=str(ROOT))
        with out_path.open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            if header is None:
                header = reader.fieldnames
            rows.extend(list(reader))
    if not rows or not header:
        print("no rows merged", file=sys.stderr)
        return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        w.writerows(rows)
    print(f"merged {len(rows)} rows -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
