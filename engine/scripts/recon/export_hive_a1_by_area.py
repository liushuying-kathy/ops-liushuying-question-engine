#!/usr/bin/env python3
"""A1 按管理区分片 export_query → data/问题引擎/_scratch/a1_by_area/，再 concat 全量。

用法（工作区根目录）:
  $env:BDP_SSO_TOKEN = (bdp-sso get-token).Trim()   # 或 Bearer 整行
  python 问题引擎/scripts/export_hive_a1_by_area.py
  python 问题引擎/scripts/export_hive_a1_by_area.py --area 澳门区
  python 问题引擎/scripts/export_hive_a1_by_area.py --merge-only
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SQL_TEMPLATE = ROOT / "sql" / "问题引擎" / "hive_min_wide_store_mid_category_day_202509_by_area.sql"
SQL_SAP_TEMPLATE = ROOT / "sql" / "问题引擎" / "hive_min_wide_store_mid_category_day_202509_by_sap_area.sql"
SQL_DATE_TEMPLATE = ROOT / "sql" / "问题引擎" / "hive_min_wide_store_mid_category_day_202509_by_sap_daterange.sql"
BRIDGE_CSV = ROOT / "data" / "问题引擎" / "店号互映_20260930.csv"
DATE_HALVES: tuple[tuple[str, str, str], ...] = (
    ("2026-09-01", "2026-09-15", "H1"),
    ("2026-09-16", "2026-09-30", "H2"),
)
DATE_WEEKS: dict[str, tuple[tuple[str, str, str], ...]] = {
    "H1": (
        ("2026-09-01", "2026-09-07", "W1"),
        ("2026-09-08", "2026-09-15", "W2"),
    ),
    "H2": (
        ("2026-09-16", "2026-09-22", "W3"),
        ("2026-09-23", "2026-09-30", "W4"),
    ),
}
OUT_DIR = ROOT / "data" / "问题引擎" / "_scratch" / "a1_by_area"
MERGED = ROOT / "data" / "问题引擎" / "Hive_店日中级KPI_202509.csv"
def _mcp_uri() -> str:
    url = (os.getenv("HIVE_MCP_URL") or "").strip()
    if not url:
        raise RuntimeError("请设置环境变量 HIVE_MCP_URL（见仓根 .env.example）")
    return url


MCP_URI = _mcp_uri()

# 与 dim 维表 2026-09 管理区一致（15 区；粤东/粤西体量最大，放后便于先跑小片验链路）
MANAGE_AREAS: tuple[str, ...] = (
    "运营中心直管",
    "澳门区",
    "香港区",
    "西安区",
    "南京区",
    "天津区",
    "合肥区",
    "郑州区",
    "武汉区",
    "重庆区",
    "成都区",
    "长沙区",
    "华东区",
    "粤东区",
    "粤西区",
)


def _token() -> str:
    raw = (os.environ.get("BDP_SSO_TOKEN") or "").strip()
    if not raw:
        import subprocess

        out = subprocess.run(
            ["bdp-sso", "get-token"],
            capture_output=True,
            text=True,
            check=False,
        )
        line = (out.stdout or "").strip().splitlines()[-1] if out.stdout else ""
        raw = line.strip()
    if raw.startswith("Bearer "):
        return raw[7:].strip()
    return raw


def strip_leading_comments(sql: str) -> str:
    lines = sql.splitlines()
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if s == "" or s.startswith("--"):
            i += 1
            continue
        break
    return "\n".join(lines[i:]).strip() + "\n"


def prepare_sql(body: str) -> str:
    s = strip_leading_comments(body)
    if re.match(r"(?is)^\s*with\b", s):
        s = "SELECT * FROM (\n" + s.rstrip() + "\n) _export_wrap\n"
    return s


def sql_for_area(area: str) -> str:
    tpl = SQL_TEMPLATE.read_text(encoding="utf-8")
    body = tpl.replace("__MANAGE_AREA__", area)
    return prepare_sql(body)


def sql_for_sap(manage: str, sap: str) -> str:
    tpl = SQL_SAP_TEMPLATE.read_text(encoding="utf-8")
    body = tpl.replace("__MANAGE_AREA__", manage).replace("__SAP_AREA__", sap)
    return prepare_sql(body)


def sql_for_sap_dates(manage: str, sap: str, start: str, end: str) -> str:
    tpl = SQL_DATE_TEMPLATE.read_text(encoding="utf-8")
    body = (
        tpl.replace("__MANAGE_AREA__", manage)
        .replace("__SAP_AREA__", sap)
        .replace("__DATE_START__", start)
        .replace("__DATE_END__", end)
    )
    return prepare_sql(body)


def parse_shard_suffix(suffix: str) -> tuple[str, str]:
    for manage in sorted(MANAGE_AREAS, key=len, reverse=True):
        pref = manage + "_"
        if suffix.startswith(pref):
            return manage, suffix[len(pref) :]
    raise ValueError(f"cannot parse shard suffix: {suffix}")


def _line_count(path: Path) -> int:
    return sum(1 for _ in path.open(encoding="utf-8-sig", errors="replace"))


def _is_truncated_file(path: Path) -> bool:
    return _line_count(path) >= 100_001


def sap_areas_by_manage() -> dict[str, list[str]]:
    import csv

    m: dict[str, set[str]] = {}
    with BRIDGE_CSV.open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            m.setdefault(r["manage_area"], set()).add(r["sap_area_name"])
    return {k: sorted(v) for k, v in sorted(m.items())}


def _safe_name(s: str) -> str:
    return s.replace("/", "_").replace("\\", "_")


def mcp_export(sql: str, token: str, max_rows: int = 100_000) -> dict:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "export_query",
            "arguments": {"sql": sql, "max_rows": max_rows, "token": token},
        },
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(MCP_URI, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json, text/event-stream")
    req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=900) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            return json.loads(line[5:].strip())
    return json.loads(raw)


def dig_download_url(result: dict) -> tuple[str | None, dict]:
    node = result.get("result") or {}
    texts: list[str] = []
    for item in node.get("content") or []:
        if isinstance(item, dict) and item.get("type") == "text":
            texts.append(item.get("text") or "")
    inner: dict = {}
    for t in texts:
        try:
            obj = json.loads(t)
            if isinstance(obj, dict) and "text" in obj and isinstance(obj["text"], str):
                obj = json.loads(obj["text"])
            if isinstance(obj, dict):
                inner = obj
        except json.JSONDecodeError:
            continue
    url = None
    meta: dict = {}
    if isinstance(inner, dict):
        data = inner.get("data") or {}
        if isinstance(data, dict):
            url = data.get("download_url") or data.get("url")
            meta = {
                "row_count": data.get("row_count"),
                "truncated": data.get("truncated"),
                "file_size": data.get("file_size"),
            }
    if not url:
        blob = json.dumps(result, ensure_ascii=False)
        _hm = re.match(r"https?://([^/]+)/", MCP_URI)
        _host = re.escape(_hm.group(1)) if _hm else r"[^/]+"
        m = re.search(
            rf"https://{_host}/api-bdp-mcps/starrocks-db/api/export/download\?[^\s\"']+",
            blob,
        )
        if m:
            url = m.group(0)
    return url, meta


def _download_url(url: str) -> bytes:
    data = b""
    last_err: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=900) as resp:
                data = resp.read()
            if data:
                return data
        except Exception as e:
            last_err = e
            time.sleep(2.0 * (attempt + 1))
    raise RuntimeError(f"download failed: {last_err}")


def export_sap_range(
    manage: str,
    sap: str,
    tag: str,
    start: str,
    end: str,
    token: str,
    skip_existing: bool,
) -> dict:
    dest = OUT_DIR / f"Hive_店日中级KPI_202509_{_safe_name(manage)}_{_safe_name(sap)}_{tag}.csv"
    if skip_existing and dest.is_file() and dest.stat().st_size > 100 and not _is_truncated_file(dest):
        return {
            "area": manage,
            "sap": sap,
            "tag": tag,
            "path": str(dest),
            "skipped": True,
            "lines": _line_count(dest),
            "bytes": dest.stat().st_size,
        }
    sql = sql_for_sap_dates(manage, sap, start, end)
    t0 = time.time()
    result = mcp_export(sql, token)
    if result.get("error"):
        raise RuntimeError(f"{manage}/{sap}/{tag}: MCP error {result['error']}")
    url, meta = dig_download_url(result)
    if not url:
        raise RuntimeError(f"{manage}/{sap}/{tag}: no download_url")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    data = _download_url(url)
    dest.write_bytes(data)
    nlines = len(data.decode("utf-8-sig", errors="replace").splitlines())
    return {
        "area": manage,
        "sap": sap,
        "tag": tag,
        "path": str(dest),
        "skipped": False,
        "lines": nlines,
        "data_rows": max(0, nlines - 1),
        "bytes": len(data),
        "truncated": meta.get("truncated"),
        "mcp_row_count": meta.get("row_count"),
        "seconds": round(time.time() - t0, 1),
    }


def export_sap_half(
    manage: str, sap: str, half: str, start: str, end: str, token: str, skip_existing: bool
) -> dict:
    dest = OUT_DIR / f"Hive_店日中级KPI_202509_{_safe_name(manage)}_{_safe_name(sap)}_{half}.csv"
    if skip_existing and dest.is_file() and dest.stat().st_size > 100 and not _is_truncated_file(dest):
        return {
            "area": manage,
            "sap": sap,
            "half": half,
            "path": str(dest),
            "skipped": True,
            "lines": _line_count(dest),
            "bytes": dest.stat().st_size,
        }
    row = export_sap_range(manage, sap, half, start, end, token, skip_existing)
    row["half"] = half
    return row


def export_sap_shard(manage: str, sap: str, token: str, skip_existing: bool) -> dict:
    dest = OUT_DIR / f"Hive_店日中级KPI_202509_{_safe_name(manage)}_{_safe_name(sap)}.csv"
    if (
        skip_existing
        and dest.is_file()
        and dest.stat().st_size > 100
        and not _is_truncated_file(dest)
    ):
        lines = dest.read_text(encoding="utf-8-sig", errors="replace").count("\n") + 1
        return {
            "area": manage,
            "sap": sap,
            "path": str(dest),
            "skipped": True,
            "lines": lines,
            "bytes": dest.stat().st_size,
        }
    sql = sql_for_sap(manage, sap)
    t0 = time.time()
    result = mcp_export(sql, token)
    if result.get("error"):
        raise RuntimeError(f"{manage}/{sap}: MCP error {result['error']}")
    url, meta = dig_download_url(result)
    if not url:
        raise RuntimeError(f"{manage}/{sap}: no download_url")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    data = _download_url(url)
    dest.write_bytes(data)
    text = data.decode("utf-8-sig", errors="replace")
    nlines = len(text.splitlines())
    return {
        "area": manage,
        "sap": sap,
        "path": str(dest),
        "skipped": False,
        "lines": nlines,
        "data_rows": max(0, nlines - 1),
        "bytes": len(data),
        "truncated": meta.get("truncated"),
        "mcp_row_count": meta.get("row_count"),
        "seconds": round(time.time() - t0, 1),
    }


def export_area(area: str, token: str, skip_existing: bool) -> dict:
    safe = _safe_name(area)
    dest = OUT_DIR / f"Hive_店日中级KPI_202509_{safe}.csv"
    if (
        skip_existing
        and dest.is_file()
        and dest.stat().st_size > 100
        and not _is_truncated_file(dest)
    ):
        lines = dest.read_text(encoding="utf-8-sig", errors="replace").count("\n") + 1
        return {
            "area": area,
            "path": str(dest),
            "skipped": True,
            "lines": lines,
            "bytes": dest.stat().st_size,
        }
    sql = sql_for_area(area)
    t0 = time.time()
    result = mcp_export(sql, token)
    if result.get("error"):
        raise RuntimeError(f"{area}: MCP error {result['error']}")
    url, meta = dig_download_url(result)
    if not url:
        raise RuntimeError(f"{area}: no download_url in response")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    data = _download_url(url)
    dest.write_bytes(data)
    text = data.decode("utf-8-sig", errors="replace")
    nlines = len(text.splitlines())
    elapsed = time.time() - t0
    return {
        "area": area,
        "path": str(dest),
        "skipped": False,
        "lines": nlines,
        "data_rows": max(0, nlines - 1),
        "bytes": len(data),
        "truncated": meta.get("truncated"),
        "mcp_row_count": meta.get("row_count"),
        "seconds": round(elapsed, 1),
    }


def run_merge() -> int:
    from concat_hive_a1_by_area import main as concat_main

    return concat_main()


def fix_truncated(token: str, skip_existing: bool) -> tuple[list[dict], list[str]]:
    """删掉触顶的管理区整片，按 sap_area 重导。"""
    report_path = OUT_DIR / "_export_report.json"
    truncated: list[str] = []
    if report_path.is_file():
        prev = json.loads(report_path.read_text(encoding="utf-8"))
        for row in prev.get("areas") or []:
            if row.get("truncated"):
                truncated.append(row["area"])
    if not truncated:
        truncated = [
            "重庆区",
            "成都区",
            "长沙区",
            "华东区",
            "粤东区",
            "粤西区",
        ]
    sap_map = sap_areas_by_manage()
    report: list[dict] = []
    failed: list[str] = []
    for manage in truncated:
        parent = OUT_DIR / f"Hive_店日中级KPI_202509_{_safe_name(manage)}.csv"
        if parent.is_file():
            parent.unlink()
        for sap in sap_map.get(manage, []):
            print(f"=== {manage} / {sap} ===")
            try:
                row = export_sap_shard(manage, sap, token, skip_existing)
                report.append(row)
                print(json.dumps(row, ensure_ascii=False))
                if row.get("truncated"):
                    print(f"WARNING: {manage}/{sap} 仍 truncated", file=sys.stderr)
            except Exception as e:
                failed.append(f"{manage}/{sap}")
                print(f"FAIL {manage}/{sap}: {e}", file=sys.stderr)
    return report, failed


def fix_truncated_halves(token: str, skip_existing: bool) -> tuple[list[dict], list[str]]:
    """触顶的 sap 整片 → 半月 H1/H2。"""
    prefix = "Hive_店日中级KPI_202509_"
    report: list[dict] = []
    failed: list[str] = []
    for path in sorted(OUT_DIR.glob("Hive_店日中级KPI_202509_*.csv")):
        suffix = path.stem.removeprefix(prefix)
        if suffix.endswith("_H1") or suffix.endswith("_H2"):
            continue
        if "_" not in suffix:
            continue
        if not _is_truncated_file(path):
            continue
        manage, sap = parse_shard_suffix(suffix)
        print(f"--- split {manage} / {sap} (drop {path.name}) ---")
        path.unlink()
        for start, end, half in DATE_HALVES:
            print(f"=== {manage} / {sap} / {half} ===")
            try:
                row = export_sap_half(manage, sap, half, start, end, token, skip_existing)
                report.append(row)
                print(json.dumps(row, ensure_ascii=False))
                if row.get("truncated"):
                    print(f"WARNING: {manage}/{sap}/{half} 仍 truncated", file=sys.stderr)
            except Exception as e:
                failed.append(f"{manage}/{sap}/{half}")
                print(f"FAIL: {e}", file=sys.stderr)
    return report, failed


def fix_truncated_weeks(token: str, skip_existing: bool) -> tuple[list[dict], list[str]]:
    """触顶的半月片 → 按周 W1–W4。"""
    prefix = "Hive_店日中级KPI_202509_"
    report: list[dict] = []
    failed: list[str] = []
    for path in sorted(OUT_DIR.glob("Hive_店日中级KPI_202509_*.csv")):
        suffix = path.stem.removeprefix(prefix)
        if not (suffix.endswith("_H1") or suffix.endswith("_H2")):
            continue
        if not _is_truncated_file(path):
            continue
        half = "H1" if suffix.endswith("_H1") else "H2"
        base = suffix[:-3]
        manage, sap = parse_shard_suffix(base)
        print(f"--- week-split {manage}/{sap}/{half} ---")
        path.unlink()
        for start, end, week in DATE_WEEKS[half]:
            tag = f"{half}_{week}"
            print(f"=== {manage} / {sap} / {tag} ===")
            try:
                row = export_sap_range(manage, sap, tag, start, end, token, skip_existing)
                report.append(row)
                print(json.dumps(row, ensure_ascii=False))
                if row.get("truncated"):
                    print(f"WARNING: {manage}/{sap}/{tag} 仍 truncated", file=sys.stderr)
            except Exception as e:
                failed.append(f"{manage}/{sap}/{tag}")
                print(f"FAIL: {e}", file=sys.stderr)
    return report, failed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", action="append", help="只跑指定管理区（可多次）")
    ap.add_argument("--skip-existing", action="store_true", help="已有非空分片则跳过")
    ap.add_argument("--fix-truncated", action="store_true", help="管理区触顶后按 sap_area 二级分片")
    ap.add_argument("--fix-halves", action="store_true", help="sap 触顶后按半月 H1/H2 三级分片")
    ap.add_argument("--fix-weeks", action="store_true", help="半月仍触顶时按周 W1–W4 四级分片")
    ap.add_argument("--merge-only", action="store_true")
    ap.add_argument("--no-merge", action="store_true")
    args = ap.parse_args()

    if args.merge_only:
        return run_merge()

    if args.fix_truncated:
        token = _token()
        if not token:
            print("缺少 BDP token", file=sys.stderr)
            return 2
        report, failed = fix_truncated(token, skip_existing=args.skip_existing)
        summary_path = OUT_DIR / "_export_report_sap.json"
        summary_path.write_text(
            json.dumps({"shards": report, "failed": failed}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if failed:
            return 1
        if not args.no_merge:
            return run_merge()
        return 0

    if args.fix_halves:
        token = _token()
        if not token:
            print("缺少 BDP token", file=sys.stderr)
            return 2
        report, failed = fix_truncated_halves(token, skip_existing=args.skip_existing)
        summary_path = OUT_DIR / "_export_report_halves.json"
        summary_path.write_text(
            json.dumps({"shards": report, "failed": failed}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if failed:
            return 1
        if not args.no_merge:
            return run_merge()
        return 0

    if args.fix_weeks:
        token = _token()
        if not token:
            print("缺少 BDP token", file=sys.stderr)
            return 2
        report, failed = fix_truncated_weeks(token, skip_existing=args.skip_existing)
        summary_path = OUT_DIR / "_export_report_weeks.json"
        summary_path.write_text(
            json.dumps({"shards": report, "failed": failed}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if failed:
            return 1
        if not args.no_merge:
            return run_merge()
        return 0

    areas = tuple(args.area) if args.area else MANAGE_AREAS
    token = _token()
    if not token:
        print("缺少 BDP token：bdp-sso get-token 或设置 BDP_SSO_TOKEN", file=sys.stderr)
        return 2

    report: list[dict] = []
    failed: list[str] = []
    for area in areas:
        print(f"=== {area} ===")
        try:
            row = export_area(area, token, skip_existing=args.skip_existing)
            report.append(row)
            print(json.dumps(row, ensure_ascii=False))
            if row.get("truncated"):
                print(f"WARNING: {area} 触达 max_rows，需再拆片", file=sys.stderr)
        except Exception as e:
            failed.append(area)
            print(f"FAIL {area}: {e}", file=sys.stderr)

    summary_path = OUT_DIR / "_export_report.json"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps({"areas": report, "failed": failed}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"report -> {summary_path}")

    if failed:
        return 1
    if not args.no_merge and len(report) == len(areas):
        print("--- merge ---")
        return run_merge()
    return 0


if __name__ == "__main__":
    os.chdir(ROOT)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
