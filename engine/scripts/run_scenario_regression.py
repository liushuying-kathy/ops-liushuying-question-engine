#!/usr/bin/env python3
"""B5-1：对照 验收/场景用例_经营发现.md 对权威 run 做轻量回归（不取数）。"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parents[1]
ROOT = ENGINE_DIR.parent
RUN_DIR = Path(os.environ.get("ENGINE_RUN_DIR", str(ENGINE_DIR / "runs" / "2026-10-18")))
if not RUN_DIR.is_absolute():
    RUN_DIR = (ROOT / RUN_DIR).resolve()


def _read(name: str) -> str:
    p = RUN_DIR / name
    return p.read_text(encoding="utf-8") if p.is_file() else ""


def _status(ok: bool, partial: bool = False) -> str:
    if ok:
        return "绿"
    if partial:
        return "黄"
    return "红"


def run_checks() -> dict:
    report_path = RUN_DIR / "report.json"
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else {}
    ceo = report.get("ceo_upgrades") or []
    cfo = report.get("cfo_upgrades") or []
    trees_path = RUN_DIR / "problem_trees.json"
    trees = json.loads(trees_path.read_text(encoding="utf-8")) if trees_path.is_file() else {}

    ceo_md = _read("问题清单_公司重要问题榜.md")
    cfo_md = _read("问题清单_CFO重要问题榜.md")
    sup_md = _read("问题清单_督导单.md")
    store_md = _read("问题清单_店长单_样张.md")
    daily_md = _read("问题清单_区域日下发_样张.md")

    e2_in_ceo = any((p.get("process_leaf") == "E2" or p.get("entry_id") == "E2") for p in ceo)
    lmdi_ceo = "LMDI" in ceo_md or "毛利额变化拆解" in ceo_md

    e1_cfo = any(p.get("entry_id") == "E1" for p in cfo) or "店日均净利" in cfo_md
    e2_cfo = sum(1 for p in cfo if p.get("process_leaf") == "E2" or p.get("entry_id") == "E2") >= 3

    tianjin = "天津区" in ceo_md and "店日均销售" in ceo_md
    bundle_cat = "大分类" in ceo_md or "蔬菜类" in ceo_md

    cells = "店型四格" in ceo_md
    spatial = "空间下钻" in ceo_md
    spatial_chain = "→" in ceo_md and "天津" in ceo_md
    tree_spatial = any((t.get("sections") or {}).get("spatial") for t in (trees.get("ceo") or []))
    ranked_path = RUN_DIR / "problems_ranked.json"
    contrib_gap = False
    if ranked_path.is_file():
        ranked = json.loads(ranked_path.read_text(encoding="utf-8"))
        contrib_gap = any(
            isinstance(r.get("weight"), (int, float)) and r.get("tree_path")
            for r in (ranked[:20] if isinstance(ranked, list) else [])
        )

    daily_one = "主叶子" in daily_md or "现在复查" in daily_md
    daily_cat_factor = "当日大分类单因子" in daily_md or bool(
        re.search(r"类.*因子|大类.*来客", daily_md)
    )

    sup_tasks = sup_md.count("### 店") >= 5 and "现在复查" in sup_md
    store_chain = "销售与客流" in store_md and (
        "会员与消费者" in store_md or "跟店主提示" in store_md
    )
    store_o = "**订购**" in store_md and (
        "O1" in store_md or "进货" in store_md or "订购目标" in store_md
    )
    sup_pid = "problem_id" in sup_md and "榜区同源" in sup_md

    m_parallel = "折扣率" in ceo_md or "促销" in ceo_md

    scenarios = {
        "S01": _status(e2_in_ceo and lmdi_ceo, partial=e2_in_ceo),
        "S02": _status(e2_cfo and e1_cfo, partial=e2_cfo or bool(cfo)),
        "S03": _status(tianjin and bundle_cat, partial=tianjin),
        "S04": _status(bundle_cat),
        "S05": _status(cells),
        "S06": _status(tree_spatial and spatial and spatial_chain, partial=spatial),
        "S07": _status(spatial and spatial_chain, partial=tree_spatial),
        "S08": _status(daily_one),
        "S09": _status(daily_cat_factor),
        "S10": _status(sup_tasks and sup_pid, partial=sup_tasks),
        "S11": _status(store_o and store_chain, partial=store_chain),
        "S12": _status(m_parallel, partial="并行观察" in ceo_md),
    }
    red = [k for k, v in scenarios.items() if v == "红"]
    tree_rep = RUN_DIR / "tree_bundle_grader_report.json"
    tree_pass = False
    tree_pct = 0.0
    if tree_rep.is_file():
        tr = json.loads(tree_rep.read_text(encoding="utf-8"))
        tree_pass = bool(tr.get("passed"))
        tree_pct = float(tr.get("percent") or 0)

    return {
        "run_dir": str(RUN_DIR),
        "engine_version": report.get("engine_version"),
        "tree_bundle_grader_passed": tree_pass,
        "tree_bundle_grader_pct": tree_pct,
        "ceo_upgrades": len(ceo),
        "cfo_upgrades": len(cfo),
        "problem_trees": trees.get("schema"),
        "scenarios": scenarios,
        "failed": red,
        "passed": len(red) == 0,
    }


def main() -> int:
    if not (RUN_DIR / "report.json").is_file():
        print(json.dumps({"error": "missing report.json", "run_dir": str(RUN_DIR)}, ensure_ascii=False))
        return 1
    tree_rep = RUN_DIR / "tree_bundle_grader_report.json"
    if not tree_rep.is_file():
        import subprocess

        subprocess.run(
            [sys.executable, str(ROOT / "问题引擎" / "scripts" / "run_tree_bundle_grader.py")],
            env={**os.environ, "ENGINE_RUN_DIR": str(RUN_DIR)},
            check=False,
        )
    out = run_checks()
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
