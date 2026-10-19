#!/usr/bin/env python3
"""将问题引擎跑批产物导出为 qwen grader_agent 可评分的 Markdown。"""

from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_default_run = ROOT / "问题引擎" / "runs" / "2026-10-16"
RUN_DIR = Path(os.environ.get("ENGINE_RUN_DIR", str(_default_run)))
if not RUN_DIR.is_absolute():
    RUN_DIR = (ROOT / RUN_DIR).resolve()

OUT = ROOT / "BA-ai-knowledge-base" / "qwen_md_grader" / "问题引擎-经营诊断-202609-产品评价稿.md"


def main() -> None:
    report_path = RUN_DIR / "report.json"
    if not report_path.is_file():
        raise SystemExit(f"missing {report_path}")

    report = json.loads(report_path.read_text(encoding="utf-8"))
    ceo_path = RUN_DIR / "问题清单_公司重要问题榜.md"
    if not ceo_path.is_file():
        ceo_path = RUN_DIR / "问题清单_公司短清单.md"
    ceo_md = ceo_path.read_text(encoding="utf-8")
    store_sample = ""
    sp = RUN_DIR / "问题清单_店长单_样张.md"
    if sp.is_file():
        store_sample = sp.read_text(encoding="utf-8")
    ranked = RUN_DIR / "problems_ranked.json"
    ranked_note = ""
    if ranked.is_file():
        rows = json.loads(ranked.read_text(encoding="utf-8"))
        ranked_note = f"全国贡献 80% 切片共 {len(rows)} 条（`problems_ranked.json`）。\n"

    checks = report.get("checks") or {}
    p1 = report.get("p1_stats") or {}
    lines = [
        "# 门店经营诊断问题引擎 · 2026-09 回放产品输出（自解释稿）",
        "",
        "## 产品定位",
        "",
        "穷尽发现 + 统一提炼：CEO / 区总 / 督导 / 店长共用同一套叶子不等式与阈值；",
        "角色差异仅在可见范围。CEO 默认视图为全国月频问题按贡献累计 80%。",
        f"引擎版本：**{report.get('engine_version', '—')}** · 统计月：**{report.get('month', '—')}**",
        "",
        "## 跑批自检（规则 Grader / checks）",
        "",
        f"- checks.passed：**{checks.get('passed')}**",
        f"- 问题行合计：{len(report.get('problems') or [])}",
        f"- CEO 重要问题榜：{len(report.get('ceo_upgrades') or [])} 条",
        f"- P1：promo={p1.get('promo')} member={p1.get('member')} m1a={p1.get('m1a')} o1={p1.get('o1')}",
        ranked_note,
        "---",
        "",
        "## 公司重要问题榜（全文）",
        "",
        ceo_md.strip(),
        "",
    ]
    if store_sample:
        lines += ["---", "", "## 店长单样张（同源 problem_id）", "", store_sample.strip(), ""]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(OUT)


if __name__ == "__main__":
    main()
