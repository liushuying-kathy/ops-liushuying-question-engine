#!/usr/bin/env python3
"""从已有 run 的 problems.json 重渲染 L3 清单（不重新取数）。用于样张/呈现验收。"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

ENGINE_DIR = Path(__file__).resolve().parents[1]
ROOT = ENGINE_DIR.parent
if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))

from engine.problem_tree import build_executive_trees  # noqa: E402
from engine.rank import pick_cfo_contribution_fold  # noqa: E402
from engine.render import render_markdown_lists  # noqa: E402

_default = ENGINE_DIR / "runs" / "2026-10-16"
RUN_DIR = Path(os.environ.get("ENGINE_RUN_DIR", str(_default)))
if not RUN_DIR.is_absolute():
    RUN_DIR = (ROOT / RUN_DIR).resolve()
CONFIG_DIR = ENGINE_DIR / "config"


def _load_yaml(path: Path) -> dict:
    try:
        import yaml
    except ImportError:
        raise RuntimeError("需要 PyYAML: pip install pyyaml") from None
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _row_ns(d: dict) -> SimpleNamespace:
    o = SimpleNamespace()
    for k, v in d.items():
        setattr(o, k, v)
    return o


def _problem_row_to_dict(p: SimpleNamespace) -> dict:
    return {k: v for k, v in p.__dict__.items() if not k.startswith("_")}


def _ensure_executive_artifacts(
    problems: list[dict], report: dict, thresholds: dict
) -> tuple[list[dict], list[dict], dict]:
    ceo = report.get("ceo_upgrades") or []
    cfo = report.get("cfo_upgrades") or []
    trees_path = RUN_DIR / "problem_trees.json"
    trees: dict | None = None
    if trees_path.is_file():
        try:
            trees = json.loads(trees_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            trees = None

    need_cfo = not cfo and (thresholds.get("cfo_view") or {}).get("enabled")
    need_trees = trees is None or not ((trees.get("ceo") or []) or (trees.get("cfo") or []))
    if need_cfo or need_trees:
        if need_cfo:
            prob_objs = [_row_ns(p) for p in problems]
            cfo = [_problem_row_to_dict(p) for p in pick_cfo_contribution_fold(prob_objs, thresholds)]
        if need_trees:
            trees = build_executive_trees(problems, ceo, cfo)
            trees_path.write_text(
                json.dumps(trees, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        report["cfo_upgrades"] = cfo
        report["problem_trees_schema"] = (trees or {}).get("schema")
        (RUN_DIR / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    if trees is None:
        trees = {}
    return ceo, cfo, trees


def main() -> int:
    prob_path = RUN_DIR / "problems.json"
    rep_path = RUN_DIR / "report.json"
    if not prob_path.is_file() or not rep_path.is_file():
        print(f"missing {prob_path} or {rep_path}", file=sys.stderr)
        return 1
    problems = json.loads(prob_path.read_text(encoding="utf-8"))
    report = json.loads(rep_path.read_text(encoding="utf-8"))
    thresholds = _load_yaml(CONFIG_DIR / "thresholds.yaml")
    ceo, cfo, trees = _ensure_executive_artifacts(problems, report, thresholds)
    render_markdown_lists(RUN_DIR, problems, ceo, cfo_upgrades=cfo, problem_trees=trees)
    out_files = [
        "问题清单_公司重要问题榜.md",
        "问题清单_CFO重要问题榜.md",
        "问题清单_区域经营包.md",
        "问题清单_督导单.md",
        "问题清单_店长单_样张.md",
        "问题清单_区域日下发_样张.md",
    ]
    present = [f for f in out_files if (RUN_DIR / f).is_file()]
    print(
        json.dumps(
            {
                "run_dir": str(RUN_DIR),
                "ceo": len(ceo),
                "cfo": len(cfo),
                "trees_ceo": len((trees or {}).get("ceo") or []),
                "written": present,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
