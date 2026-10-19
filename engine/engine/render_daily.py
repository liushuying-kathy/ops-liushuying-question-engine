"""区域日下发 Markdown（§5.2 · 下发包样张）。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .issue_bundle import (
    build_daily_issue_bundle,
    index_daily_region,
    pick_dispatch_day,
    render_daily_bundle_markdown,
)
from .render import _month_cn


def render_daily_dispatch_markdown(
    problems: list[dict],
    data_month: str = "2026-09",
    present_note: str = "",
) -> str:
    highlights, by_key = index_daily_region(problems)
    dispatch_day = pick_dispatch_day(problems, month_prefix=(data_month or "")[:7])
    if not dispatch_day:
        return "# 区域日下发\n\n当月无 `daily_highlight` 日扫主行，未生成下发包。\n"

    month_label = _month_cn(data_month)
    lines = [f"# {dispatch_day} 日问题下发（样张）\n\n"]
    lines.append("## 本页说明\n\n")
    lines.append(
        f"- **回答什么**：{dispatch_day} 每个管理区域主标题 **择一** 焦点叶（排序用），"
        f"包体仍展当日全链 + 商品分支有数全列 + 消费者可见项（择一≠只渲染叶名）。\n"
    )
    lines.append(f"- **数据月份**：{month_label}；对照为定比去年同星期几（364）。\n")
    lines.append("- **不进公司重要问题榜**；与公司月榜下发包分工不同。\n")
    if present_note:
        lines.append(f"- {present_note}\n")
    lines.append(
        "- **排序**：当日主叶子同比降幅从大到小（绝对值）。\n\n"
    )

    rows: list[tuple[float, str, dict]] = []
    for (area, day), primary in highlights.items():
        if day != dispatch_day:
            continue
        y = (primary.get("raw") or {}).get("yoy")
        sort_key = float(y) if y is not None else 0.0
        bundle = build_daily_issue_bundle(primary, by_key.get((area, day), []), problems)
        rows.append((sort_key, area, bundle))

    rows.sort(key=lambda x: x[0])
    for _, _, bundle in rows:
        lines.extend(render_daily_bundle_markdown(bundle))

    return "".join(lines)


def write_daily_dispatch_sample(
    run_dir: Path,
    problems: list[dict],
    data_month: str = "",
    present_note: str = "",
) -> str | None:
    run_dir = Path(run_dir)
    if not data_month:
        rep = run_dir / "report.json"
        if rep.is_file():
            try:
                data_month = json.loads(rep.read_text(encoding="utf-8")).get("month") or ""
            except (json.JSONDecodeError, OSError):
                data_month = ""
    text = render_daily_dispatch_markdown(problems, data_month=data_month, present_note=present_note)
    out = run_dir / "问题清单_区域日下发_样张.md"
    out.write_text(text, encoding="utf-8")
    dispatch_day = pick_dispatch_day(problems, month_prefix=(data_month or "")[:7])
    return dispatch_day
