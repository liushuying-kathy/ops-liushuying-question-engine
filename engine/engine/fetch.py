"""bdapp 与神策脚本取数、新鲜度探针。"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # 工作区根（问题引擎/engine/fetch.py）


def run_bdapp(sql_path: Path, out_path: Path, *, retries: int = 3) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "tools" / "qdm_bdapp")
    cmd = [
        sys.executable,
        "-m",
        "qdm_bdapp",
        "--all-pages",
        str(sql_path),
        str(out_path),
    ]
    last_err = ""
    for attempt in range(retries):
        r = subprocess.run(
            cmd,
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if r.returncode == 0:
            return out_path
        last_err = r.stderr or r.stdout or ""
        if attempt < retries - 1:
            time.sleep(2 + attempt * 2)
    raise RuntimeError(f"bdapp 失败 {sql_path.name}: {last_err}")


def run_python_script(script_path: Path, *, cwd: Path | None = None) -> None:
    r = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=str(cwd or ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if r.returncode != 0:
        raise RuntimeError(f"{script_path.name} 失败: {r.stderr or r.stdout}")


def merge_store_daily_kpi(
    sql_dir: Path,
    data_dir: Path,
    manage_areas: list[str],
    *,
    run_bdapp_fn=None,
) -> Path:
    """按管理区分片拉店日 KPI 并合并（规避 2 万行上限）。"""
    import csv

    if run_bdapp_fn is None:
        run_bdapp_fn = run_bdapp
    template_path = sql_dir / "引擎_门店日KPI_202509对日_TEMPLATE.sql"
    if not template_path.is_file():
        raise FileNotFoundError(template_path)
    template = template_path.read_text(encoding="utf-8")
    scratch_sql = sql_dir / "_scratch"
    scratch_sql.mkdir(parents=True, exist_ok=True)
    scratch_data = data_dir / "_scratch"
    scratch_data.mkdir(parents=True, exist_ok=True)
    out_path = data_dir / "门店日KPI_202509对日.csv"
    all_rows: list[dict] = []
    header: list[str] | None = None
    for area in manage_areas:
        sql_text = template.replace("{{MANAGE_AREA}}", area)
        sql_file = scratch_sql / f"store_daily_{area}.sql"
        sql_file.write_text(sql_text, encoding="utf-8")
        part = scratch_data / f"门店日KPI_{area}.csv"
        run_bdapp_fn(sql_file, part)
        with part.open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            if header is None and reader.fieldnames:
                header = list(reader.fieldnames)
            for row in reader:
                all_rows.append(row)
    if not header:
        return out_path
    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
        w.writeheader()
        w.writerows(all_rows)
    return out_path


def probe_wide_max_date(scratch_csv: Path, default: str = "2026-10-15") -> str:
    """从探针 CSV 或 scratch 读取宽表 MAX(report_date)。"""
    if scratch_csv.is_file():
        import csv

        with scratch_csv.open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        if rows:
            raw = (
                rows[0].get("maxReportDate")
                or rows[0].get("max_report_date")
                or rows[0].get("max_report_date")
            )
            if raw is None or raw == "":
                return default
            s = str(raw).strip()
            if s.isdigit() and len(s) >= 12:
                from datetime import datetime, timezone

                ts = int(s)
                if ts > 10_000_000_000:
                    ts //= 1000
                return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
            return s[:10] if len(s) >= 10 else s
    return default
