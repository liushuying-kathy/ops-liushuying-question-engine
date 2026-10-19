"""日扫：全量检测 + 定比判据 + 路径择一 + 存续。"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Callable

from .daily_category import (
    format_category_factor_sentence,
    load_category_daily_index,
    pick_category_single_factor,
)
from .gates import compare_day_primary, compare_day_same_date_yoy, compare_day_wow, event_label_for
from .store import EpisodeState, LocalRunStore


def _pick_daily_primary(hits: list[dict]) -> dict | None:
    """§5.2 第 6 条：E2 → E3 → S1/B1/O2 降幅最大 → B2。"""
    if not hits:
        return None
    by_entry = {h["entry"]: h for h in hits}
    if "E2" in by_entry:
        return by_entry["E2"]
    if "E3" in by_entry:
        return by_entry["E3"]
    trio = [h for h in hits if h["entry"] in ("S1", "B1", "O2")]
    if trio:
        return min(trio, key=lambda h: h["yoy_primary"])
    if "B2" in by_entry:
        return by_entry["B2"]
    return None


def _parse_day(s: str) -> date | None:
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def apply_daily_scan_v33(
    problems: list,
    Problem,
    *,
    data_dir: Path,
    month_label: str,
    month_prev: str,
    exclude_regions: set[str],
    thresholds: dict,
    fmt_yoy_cn: Callable,
    yoy: Callable,
    fnum: Callable,
    store: LocalRunStore,
) -> None:
    cfg = thresholds.get("daily_scan") or {}
    if not cfg.get("delay_checked"):
        return
    path = data_dir / "管理区域日KPI_202509对日.csv"
    if not path.is_file():
        return

    import csv

    rows = list(csv.DictReader(path.open(encoding="utf-8-sig")))
    cat_path = data_dir / "大分类日KPI_202509对日.csv"
    if not cat_path.is_file():
        cat_path = data_dir / "大分类日KPI_202509样周.csv"
    cat_index = load_category_daily_index(cat_path)
    by: dict[tuple[str, str, str], dict] = {}
    for r in rows:
        area = r.get("manageArea") or r.get("manage_area")
        day = (r.get("reportDate") or r.get("report_date") or "")[:10]
        ym = r.get("ym")
        if area and day and ym:
            by[(area, day, ym)] = r

    episodes = store.load_episodes()
    region_yoy_hint = float(thresholds.get("region_yoy_hint", 0.0))

    def metric(row: dict, *keys: str):
        for k in keys:
            v = fnum(row.get(k))
            if v is not None:
                return v
        return None

    # 按日、区全量检测
    daily_hits: dict[tuple[str, str], list[dict]] = {}

    for (area, day_s, ym), cur in by.items():
        if ym != month_label or area in exclude_regions:
            continue
        d = _parse_day(day_s)
        if not d:
            continue
        elab = event_label_for(d)
        prev_primary = compare_day_primary(d).isoformat()
        prev_yoy = compare_day_same_date_yoy(d).isoformat()
        prev_wow = compare_day_wow(d).isoformat()
        prev_p = by.get((area, prev_primary, month_prev))
        prev_y = by.get((area, prev_yoy, month_prev))
        prev_w = by.get((area, prev_wow, month_prev))
        if not prev_p:
            continue

        metrics = [
            ("E2", "补贴前毛利额", "articleProfitDayAvg", "article_profit_day_avg", "E2"),
            ("E3", "补贴前毛利率", None, None, "E3"),
            ("S1", "店日均销售额", "saleDayAvg", "sale_day_avg", "S1"),
            ("B1", "19点前来客", "bf19CustDayAvg", "bf19_cust_day_avg", "B1"),
            ("O2", "进货重量", "purchaseWeightDayAvg", "purchase_weight_day_avg", "O2"),
        ]
        ap_c = metric(cur, "articleProfitDayAvg", "article_profit_day_avg")
        ap_p = metric(prev_p, "articleProfitDayAvg", "article_profit_day_avg")
        sale_c = metric(cur, "saleDayAvg", "sale_day_avg")
        sale_p = metric(prev_p, "saleDayAvg", "sale_day_avg")
        rate_c = (ap_c / sale_c) if ap_c and sale_c else None
        rate_p = (ap_p / sale_p) if ap_p and sale_p else None

        hits: list[dict] = []
        for entry, label, camel, snake, leaf in metrics:
            if entry == "E3":
                y = yoy(rate_c, rate_p)
                val = rate_c
            else:
                y = yoy(metric(cur, camel, snake), metric(prev_p, camel, snake))
                val = metric(cur, camel, snake)
            if y is None or y >= region_yoy_hint:
                continue
            ref_yoy = None
            ref_wow = None
            if prev_y:
                if entry == "E3":
                    ref_yoy = yoy(rate_c, (metric(prev_y, camel, snake) and None) or (
                        (metric(prev_y, "articleProfitDayAvg", "article_profit_day_avg") or 0)
                        / (metric(prev_y, "saleDayAvg", "sale_day_avg") or 1)
                        if metric(prev_y, "saleDayAvg", "sale_day_avg")
                        else None
                    ))
                else:
                    ref_yoy = yoy(metric(cur, camel, snake), metric(prev_y, camel, snake))
            if prev_w and entry != "E3":
                ref_wow = yoy(metric(cur, camel, snake), metric(prev_w, camel, snake))
            hits.append(
                {
                    "entry": entry,
                    "leaf": leaf,
                    "label": label,
                    "yoy_primary": y,
                    "ref_same_date_yoy": ref_yoy,
                    "ref_wow_7d": ref_wow,
                    "value": val,
                    "compare_basis": "same_weekday_364",
                }
            )
        bf19_sale_c = metric(cur, "bf19SaleDayAvg", "bf19_sale_day_avg")
        bf19_sale_p = metric(prev_p, "bf19SaleDayAvg", "bf19_sale_day_avg")
        bf19_cust_c = metric(cur, "bf19CustDayAvg", "bf19_cust_day_avg")
        bf19_cust_p = metric(prev_p, "bf19CustDayAvg", "bf19_cust_day_avg")
        if bf19_sale_c and bf19_cust_c and bf19_sale_p and bf19_cust_p and bf19_cust_c > 0 and bf19_cust_p > 0:
            price_c = bf19_sale_c / bf19_cust_c
            price_p = bf19_sale_p / bf19_cust_p
            y_b2 = yoy(price_c, price_p)
            if y_b2 is not None and y_b2 < region_yoy_hint:
                hits.append(
                    {
                        "entry": "B2",
                        "leaf": "B2",
                        "label": "19点前客单价",
                        "yoy_primary": y_b2,
                        "ref_same_date_yoy": None,
                        "ref_wow_7d": None,
                        "value": price_c,
                        "compare_basis": "same_weekday_364",
                    }
                )
        daily_hits[(area, day_s)] = hits

    for (area, day_s), hits in sorted(daily_hits.items()):
        chosen = _pick_daily_primary(hits)
        cat_pick = (
            pick_category_single_factor(
                cat_index, area, day_s, month_label, month_prev, yoy, region_yoy_hint
            )
            if cat_index
            else None
        )
        category_primary = False
        if not chosen and cat_pick:
            chosen = {
                "entry": "T12",
                "leaf": "T12",
                "label": f"{cat_pick['category']}{cat_pick['factor']}",
                "yoy_primary": cat_pick["yoy"],
                "ref_same_date_yoy": None,
                "ref_wow_7d": None,
                "value": None,
                "compare_basis": "same_weekday_364",
            }
            category_primary = True
        if not chosen:
            continue
        d = _parse_day(day_s)
        elab = event_label_for(d) if d else ""
        leaf = chosen["leaf"]
        ep_key = f"{area}|{leaf}"
        prev_ep = episodes.get(ep_key)
        if prev_ep and prev_ep.last_seen_on != day_s:
            # 简化：同日批次内 streak 由上次 state 续
            streak = prev_ep.streak_days + 1 if _adjacent(prev_ep.last_seen_on, day_s) else 1
            ep_id = prev_ep.episode_id if streak > 1 else f"{area}|{leaf}|{day_s}"
        else:
            streak = (prev_ep.streak_days + 1) if prev_ep else 1
            ep_id = prev_ep.episode_id if prev_ep else f"{area}|{leaf}|{day_s}"

        if category_primary and cat_pick:
            msg = format_category_factor_sentence(day_s, area, cat_pick, fmt_yoy_cn)
        else:
            msg = (
                f"{day_s}{area}{chosen['label']}{fmt_yoy_cn(chosen['yoy_primary'])}"
                f"（定比去年同星期几）。"
            )
        decline_others: list[str] = []
        for h in hits:
            if h == chosen:
                continue
            decline_others.append(f"{h['label']}{fmt_yoy_cn(h['yoy_primary'])}")
        if decline_others:
            msg += "另外下降的有：" + "、".join(decline_others) + "。不并进这一条。"
        if chosen["entry"] == "E2":
            for h in hits:
                if h["entry"] == "E3":
                    msg += f"补贴前毛利率{fmt_yoy_cn(h['yoy_primary'])}写在同一条。"
                    break
        if elab:
            msg += f"事件：{elab}。"
        if streak > 1:
            msg += f"持续第{streak}天。"
        msg += "来源：operation_center_wide_store_di，统计截至" + day_s + "【确认】。"

        trig = {
            "S1": "T1",
            "B1": "T3",
            "B2": "T3",
            "O2": "T4",
            "E2": "T13",
            "E3": "T13",
            "T12": "T12",
        }.get(leaf, "T1")
        problems.append(
            Problem(
                scope=area,
                trigger_id=trig,
                alert_level="提示",
                cadence="日",
                region_level="管理区",
                message=msg,
                raw={
                    "yoy": chosen["yoy_primary"],
                    "report_date": day_s,
                    "compare_basis": chosen["compare_basis"],
                    "ref_same_date_yoy": chosen.get("ref_same_date_yoy"),
                    "ref_wow_7d": chosen.get("ref_wow_7d"),
                    "event_label": elab,
                    "episode_id": ep_id,
                    "streak_days": streak,
                    "daily_highlight": True,
                    "category_daily_factor": cat_pick,
                    "category_daily_primary": category_primary,
                },
                process_leaf=leaf,
                entry_id=chosen["entry"] if chosen["entry"] in ("E2", "E3") else "",
            )
        )
        episodes[ep_key] = EpisodeState(
            episode_id=ep_id,
            manage_area=area,
            process_leaf=leaf,
            started_on=ep_id.split("|")[-1],
            last_seen_on=day_s,
            streak_days=streak,
        )

        # 非择一命中写入区域单明细
        for h in hits:
            if h == chosen:
                continue
            problems.append(
                Problem(
                    scope=area,
                    trigger_id="T1",
                    alert_level="提示",
                    cadence="日",
                    region_level="管理区",
                    message=f"{day_s}{area}{h['label']}{fmt_yoy_cn(h['yoy_primary'])}（并行观察，未进日下发）。",
                    raw={"yoy": h["yoy_primary"], "report_date": day_s, "parallel": True},
                    process_leaf=h["leaf"],
                )
            )

    store.save_episodes(episodes)

    if cfg.get("open_store_layer"):
        apply_store_daily_layer(
            problems,
            Problem,
            data_dir=data_dir,
            month_label=month_label,
            month_prev=month_prev,
            exclude_regions=exclude_regions,
            thresholds=thresholds,
            fmt_yoy_cn=fmt_yoy_cn,
            yoy=yoy,
            fnum=fnum,
        )


def apply_store_daily_layer(
    problems: list,
    Problem,
    *,
    data_dir: Path,
    month_label: str,
    month_prev: str,
    exclude_regions: set[str],
    thresholds: dict,
    fmt_yoy_cn: Callable,
    yoy: Callable,
    fnum: Callable,
) -> None:
    """店×日宽表实数；叶子与月频店强提示同一阈值（store_strong_hint_yoy），定比 364。"""
    import csv

    path = data_dir / "门店日KPI_202509对日.csv"
    if not path.is_file():
        return

    strong_thr = float(thresholds.get("store_strong_hint_yoy", -0.10))
    rows = list(csv.DictReader(path.open(encoding="utf-8-sig")))
    by: dict[tuple[str, str, str], dict] = {}
    for r in rows:
        low = {str(k).lower(): v for k, v in r.items()}
        sid = low.get("storeid") or low.get("store_id")
        day = (low.get("reportdate") or low.get("report_date") or "")[:10]
        ym = low.get("ym")
        if sid and day and ym:
            by[(str(sid), day, ym)] = low

    pick_order = ["E2", "E3", "S1", "B1", "O2"]
    trig_map = {"S1": "T1", "B1": "T3", "O2": "T4", "E2": "T13", "E3": "T13"}

    def metric(row: dict, *keys: str):
        for k in keys:
            v = fnum(row.get(k))
            if v is not None:
                return v
        return None

    daily_hits: dict[tuple[str, str], list[dict]] = {}

    for (sid, day_s, ym), cur in by.items():
        if ym != month_label:
            continue
        area = cur.get("managearea") or cur.get("manage_area") or ""
        if area in exclude_regions:
            continue
        cell = (cur.get("cell") or "").strip()
        if cell == "未分型":
            continue
        d = _parse_day(day_s)
        if not d:
            continue
        prev_primary = compare_day_primary(d).isoformat()
        prev_p = by.get((sid, prev_primary, month_prev))
        if not prev_p:
            continue

        ap_c = metric(cur, "articleprofitdayavg", "article_profit_day_avg")
        ap_p = metric(prev_p, "articleprofitdayavg", "article_profit_day_avg")
        sale_c = metric(cur, "saledayavg", "sale_day_avg")
        sale_p = metric(prev_p, "saledayavg", "sale_day_avg")
        rate_c = (ap_c / sale_c) if ap_c and sale_c else None
        rate_p = (ap_p / sale_p) if ap_p and sale_p else None

        metrics = [
            ("E2", "补贴前毛利额", "articleprofitdayavg", "article_profit_day_avg", "E2"),
            ("E3", "补贴前毛利率", None, None, "E3"),
            ("S1", "店日均销售额", "saledayavg", "sale_day_avg", "S1"),
            ("B1", "19点前来客", "bf19custdayavg", "bf19_cust_day_avg", "B1"),
            ("O2", "进货重量", "purchaseweightdayavg", "purchase_weight_day_avg", "O2"),
        ]
        hits: list[dict] = []
        for entry, label, camel, snake, leaf in metrics:
            if entry == "E3":
                y = yoy(rate_c, rate_p)
                val = rate_c
            else:
                y = yoy(metric(cur, camel, snake), metric(prev_p, camel, snake))
                val = metric(cur, camel, snake)
            if y is None or y > strong_thr:
                continue
            hits.append(
                {
                    "entry": entry,
                    "leaf": leaf,
                    "label": label,
                    "yoy_primary": y,
                    "value": val,
                    "compare_basis": "same_weekday_364",
                }
            )
        if hits:
            daily_hits[(sid, day_s)] = (hits, cur, area)

    for (sid, day_s), pack in sorted(daily_hits.items()):
        hits, cur, area = pack
        chosen = None
        for key in pick_order:
            for h in hits:
                if h["entry"] == key:
                    chosen = h
                    break
            if chosen:
                break
        if not chosen:
            continue
        d = _parse_day(day_s)
        elab = event_label_for(d) if d else ""
        leaf = chosen["leaf"]
        msg = (
            f"{day_s}店{sid}{chosen['label']}{fmt_yoy_cn(chosen['yoy_primary'])}"
            f"（定比去年同星期几，店日扫）。"
        )
        if elab:
            msg += f"事件：{elab}。"
        msg += "来源：operation_center_wide_store_di，统计截至" + day_s + "【确认】。"

        problems.append(
            Problem(
                scope=sid,
                trigger_id=trig_map.get(leaf, "T1"),
                alert_level="店·强提示",
                cadence="日",
                region_level="店",
                message=msg,
                object_type="store",
                object_key=sid,
                process_leaf=leaf,
                entry_id=chosen["entry"] if chosen["entry"] in ("E2", "E3") else "",
                raw={
                    "yoy": chosen["yoy_primary"],
                    "report_date": day_s,
                    "compare_basis": chosen["compare_basis"],
                    "event_label": elab,
                    "daily_highlight": True,
                    "store_daily": True,
                    "manage_area": area,
                    "store_same_rules_as_monthly": True,
                },
            )
        )


def _adjacent(prev: str, curr: str) -> bool:
    a, b = _parse_day(prev), _parse_day(curr)
    if not a or not b:
        return False
    return (b - a).days == 1
