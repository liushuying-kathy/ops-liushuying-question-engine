"""§5.2 第 6 条第 5 步：大分类单因子（日对日 364）。"""
from __future__ import annotations

import csv
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

from .gates import compare_day_primary


def _parse_day(s: str) -> date | None:
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _fnum(x) -> float | None:
    if x is None or x == "":
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def load_category_daily_index(path: Path) -> dict[tuple[str, str, str], dict]:
    """(manage_area, report_date, category_name) -> row."""
    if not path.is_file():
        return {}
    out: dict[tuple[str, str, str], dict] = {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            area = r.get("manageArea") or r.get("manage_area") or ""
            day = (r.get("reportDate") or r.get("report_date") or "")[:10]
            cat = r.get("categoryName") or r.get("category_name") or ""
            ym = r.get("ym") or ""
            if area and day and cat:
                out[(area, day, cat)] = {**r, "ym": ym}
    return out


def pick_category_single_factor(
    index: dict[tuple[str, str, str], dict],
    area: str,
    day_s: str,
    month_label: str,
    month_prev: str,
    yoy: Callable,
    region_yoy_hint: float,
) -> dict[str, Any] | None:
    """降幅最大的一类 × 该类降幅最大的因子（销售/来客/均价）。"""
    d = _parse_day(day_s)
    if not d:
        return None
    prev_primary = compare_day_primary(d).isoformat()
    cats = ("蔬菜类", "猪肉类", "水果类", "水产类", "冷藏及加工类", "预制菜")
    best_cat: tuple[float, str] | None = None
    for cat in cats:
        cur = index.get((area, day_s, cat))
        prev = index.get((area, prev_primary, cat))
        if not cur or not prev:
            continue
        if (cur.get("ym") or "") != month_label or (prev.get("ym") or "") != month_prev:
            continue
        sale_y = yoy(_fnum(cur.get("bf19_sale_day_avg") or cur.get("bf19SaleDayAvg")),
                     _fnum(prev.get("bf19_sale_day_avg") or prev.get("bf19SaleDayAvg")))
        if sale_y is None or sale_y >= region_yoy_hint:
            continue
        if best_cat is None or sale_y < best_cat[0]:
            best_cat = (sale_y, cat)
    if not best_cat:
        return None
    _, cat = best_cat
    cur = index.get((area, day_s, cat)) or {}
    prev = index.get((area, prev_primary, cat)) or {}

    factors: list[tuple[float, str, str, float | None]] = []
    pairs = (
        ("19点前销售", "bf19_sale_day_avg", "bf19SaleDayAvg"),
        ("该类来客", "bf19_cust_day_avg", "bf19CustDayAvg"),
        ("均价", "bf19_avg_price", "bf19AvgPrice"),
    )
    for label, snake, camel in pairs:
        yv = yoy(_fnum(cur.get(snake) or cur.get(camel)), _fnum(prev.get(snake) or prev.get(camel)))
        if yv is not None and yv < region_yoy_hint:
            factors.append((yv, label, cat, yv))
    if not factors:
        factors.append((best_cat[0], "19点前销售", cat, best_cat[0]))
    factors.sort(key=lambda x: x[0])
    yf, flabel, fcat, yval = factors[0]
    return {
        "category": fcat,
        "factor": flabel,
        "yoy": yval,
        "category_sale_yoy": best_cat[0],
    }


def format_category_factor_sentence(
    day_s: str,
    area: str,
    pick: dict[str, Any],
    fmt_yoy_cn: Callable,
) -> str:
    cat = pick["category"]
    fac = pick["factor"]
    return (
        f"{day_s}{area}{cat}{fac}{fmt_yoy_cn(pick['yoy'])}"
        f"（定比去年同星期几）。这是大分类单因子，不写成全店原因。"
    )
