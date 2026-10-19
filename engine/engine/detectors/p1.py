"""P1 不等式：促销、订购销售、四格、会员、品类对账、位置沿入口。"""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import Callable


def _area_entry_metric(problems: list, area: str) -> str:
    for e in ("E1", "E2", "E3"):
        for p in problems:
            if p.scope == area and p.entry_id == e and p.cadence == "月":
                return e
    return "E2"


def apply_p1_detectors(
    problems: list,
    Problem,
    *,
    data_dir: Path,
    reg_by_area: dict,
    reg_rows: list[dict],
    cell_rows: list[dict],
    month_label: str,
    month_prev: str,
    pairs: dict[str, str],
    exclude_regions: set[str],
    thresholds: dict,
    yoy: Callable,
    fnum: Callable,
    fmt_yoy_cn: Callable,
    fmt_pct: Callable,
    weaker_than: Callable,
    profit_rate: Callable,
) -> dict:
    stats = {
        "promo": 0,
        "m1": 0,
        "m2": 0,
        "cells": 0,
        "member": 0,
        "category_recon": 0,
        "s2": 0,
        "m1a": 0,
        "m1b": 0,
        "o1": 0,
    }

    def area_metric(area: str, field: str, ym: str):
        row = reg_by_area.get(area, {}).get(ym, {})
        return fnum(row.get(field))

    sale_key = "saleDayAvg" if reg_rows and "saleDayAvg" in reg_rows[0] else "sale_day_avg"
    promo_key = "promoDiscountRate" if reg_rows and "promoDiscountRate" in reg_rows[0] else "promo_discount_rate"
    hour_key = "hourDiscountRate" if reg_rows and "hourDiscountRate" in reg_rows[0] else "hour_discount_rate"
    w_key = "purchaseWeightDayAvg" if reg_rows and "purchaseWeightDayAvg" in reg_rows[0] else "purchase_weight_day_avg"
    sw_key = "salesWeightDayAvg" if reg_rows and "salesWeightDayAvg" in reg_rows[0] else "sales_weight_day_avg"

    promo_path = data_dir / "区域门店发起促销月_202509.csv"
    active_by_area: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    if promo_path.is_file():
        for row in csv.DictReader(promo_path.open(encoding="utf-8-sig")):
            ym = (row.get("ym") or "").strip()
            area = row.get("manage_area") or row.get("manageArea") or ""
            if not area or area in exclude_regions:
                continue
            amt = fnum(row.get("shop_promotion_amt") or row.get("shopPromotionAmt"))
            if amt is not None and amt > 0 and ym in (month_label, month_prev):
                active_by_area[area][ym] += amt

    for area in sorted(reg_by_area.keys()):
        if area in exclude_regions:
            continue
        ctrl = pairs.get(area)
        entry = _area_entry_metric(problems, area)

        sale_c = area_metric(area, sale_key, month_label)
        sale_p = area_metric(area, sale_key, month_prev)
        y_sale = yoy(sale_c, sale_p)
        ap_c = area_metric(area, "articleProfitDayAvg" if "articleProfitDayAvg" in (reg_rows[0] if reg_rows else {}) else "article_profit_day_avg", month_label)
        ap_p = area_metric(area, "articleProfitDayAvg" if "articleProfitDayAvg" in (reg_rows[0] if reg_rows else {}) else "article_profit_day_avg", month_prev)
        y_ap = yoy(ap_c, ap_p)

        pr_c = area_metric(area, promo_key, month_label)
        pr_p = area_metric(area, promo_key, month_prev)
        hr_c = area_metric(area, hour_key, month_label)
        hr_p = area_metric(area, hour_key, month_prev)
        y_pr = yoy(pr_c, pr_p) if pr_c is not None and pr_p else None
        y_hr = yoy(hr_c, hr_p) if hr_c is not None and hr_p else None
        ctrl_y_pr = ctrl_y_hr = None
        if ctrl:
            ctrl_y_pr = yoy(area_metric(ctrl, promo_key, month_label), area_metric(ctrl, promo_key, month_prev))
            ctrl_y_hr = yoy(area_metric(ctrl, hour_key, month_label), area_metric(ctrl, hour_key, month_prev))

        if y_pr is not None and y_pr > 0 and (ctrl_y_pr is None or (y_pr - ctrl_y_pr) > 0):
            problems.append(
                Problem(
                    scope=area,
                    trigger_id="T13",
                    alert_level="提示",
                    cadence="月",
                    message=(
                        f"9月{area}全天促销折扣率同比上升{fmt_pct(y_pr)}，"
                        f"折扣力度大于对照区{ctrl or ''}。"
                        "来源：operation_center_wide_store_di，统计截至 2026-09-30【确认】。"
                    ),
                    raw={"promo_rate_yoy": y_pr, "parallel": True},
                    process_leaf="M1",
                    parallel=True,
                    reliability="确认",
                    source="operation_center_wide_store_di",
                )
            )
            stats["m1"] += 1
            stats["promo"] += 1
            m1b_cfg = thresholds.get("m1b_passive") or {}
            if m1b_cfg.get("mode") == "rate_minus_active":
                sale_c = area_metric(area, sale_key, month_label)
                biz_c = area_metric(
                    area,
                    "bizDays" if reg_rows and "bizDays" in reg_rows[0] else "biz_days",
                    month_label,
                ) or 30
                month_sale_c = (sale_c or 0) * biz_c
                act_c = active_by_area.get(area, {}).get(month_label, 0.0)
                active_rate_c = act_c / month_sale_c if month_sale_c > 0 else None
                pr_val = float(pr_c) if pr_c is not None else 0.0
                passive_c = (
                    max(0.0, pr_val - min(active_rate_c or 0.0, pr_val))
                    if active_rate_c is not None
                    else None
                )
                pas_txt = fmt_pct(passive_c) if passive_c is not None else "待算"
                act_txt = fmt_pct(active_rate_c) if active_rate_c is not None else "待算"
                problems.append(
                    Problem(
                        scope=area,
                        trigger_id="T13",
                        alert_level="描述",
                        cadence="月",
                        message=(
                            f"9月{area}与M1并行：估算被动促销折扣率约{pas_txt}，"
                            f"主动额占销售额约{act_txt}（促销率减主动占比，分母为销售额【估算】）。"
                            "来源：wide_store_di+shop_promotion_amt，统计截至 2026-09-30【估算】。"
                        ),
                        raw={
                            "passive_rate_est": passive_c,
                            "active_rate_on_sale": active_rate_c,
                            "m1b_mode": "rate_minus_active",
                            "parallel": True,
                        },
                        process_leaf="M1b",
                        parallel=True,
                        reliability="估算",
                        source="operation_center_wide_store_di+product_center_business_v3",
                    )
                )
                stats["m1b"] += 1
                stats["promo"] += 1

        if y_hr is not None and y_hr > 0 and (ctrl_y_hr is None or (y_hr - ctrl_y_hr) > 0):
            problems.append(
                Problem(
                    scope=area,
                    trigger_id="T13",
                    alert_level="提示",
                    cadence="月",
                    message=(
                        f"9月{area}时段折扣率同比上升{fmt_pct(y_hr)}，"
                        "挂在19点后销售并行观察。"
                        "来源：operation_center_wide_store_di，统计截至 2026-09-30【确认】。"
                    ),
                    raw={"hour_rate_yoy": y_hr, "parallel": True},
                    process_leaf="M2",
                    parallel=True,
                    reliability="确认",
                    source="operation_center_wide_store_di",
                )
            )
            stats["m2"] += 1
            stats["promo"] += 1

        sw_c = area_metric(area, sw_key, month_label)
        sw_p = area_metric(area, sw_key, month_prev)
        y_sw = yoy(sw_c, sw_p)
        if y_sw is not None and y_sw < 0:
            problems.append(
                Problem(
                    scope=area,
                    trigger_id="T1",
                    alert_level="提示",
                    cadence="月",
                    message=(
                        f"9月{area}店日均销售重量{fmt_yoy_cn(y_sw)}，与销售额并行观察。"
                        "来源：operation_center_wide_store_di，统计截至 2026-09-30【确认】。"
                    ),
                    raw={"sales_weight_yoy": y_sw, "parallel": True},
                    process_leaf="S2",
                    parallel=True,
                )
            )
            stats["s2"] += 1

        parent_y = y_ap if entry in ("E2", "E1") else y_sale
        if parent_y is None:
            parent_y = y_sale

    for r in cell_rows:
        area = r.get("manageArea") or r.get("manage_area")
        cell = r.get("cell") or ""
        if not area or area in exclude_regions or cell == "未分型":
            continue
        sy = yoy(fnum(r.get("saleDayAvgCurr") or r.get("sale_day_avg_curr")), fnum(r.get("saleDayAvgPrev") or r.get("sale_day_avg_prev")))
        parent_sy = yoy(
            area_metric(area, sale_key, month_label),
            area_metric(area, sale_key, month_prev),
        )
        if sy is not None and sy < 0 and parent_sy is not None and (sy - parent_sy) < 0:
            ctrl = pairs.get(area)
            ctrl_cell_y = None
            for r2 in cell_rows:
                if (r2.get("manageArea") or r2.get("manage_area")) == ctrl and (r2.get("cell") or "") == cell:
                    ctrl_cell_y = yoy(
                        fnum(r2.get("saleDayAvgCurr") or r2.get("sale_day_avg_curr")),
                        fnum(r2.get("saleDayAvgPrev") or r2.get("sale_day_avg_prev")),
                    )
            if ctrl_cell_y is not None and (sy - ctrl_cell_y) < 0:
                problems.append(
                    Problem(
                        scope=f"{area}·{cell}",
                        trigger_id="T1",
                        alert_level="提示",
                        cadence="月",
                        region_level="店型",
                        parent_scope=area,
                        message=(
                            f"9月{area}{cell}店日均销售{fmt_yoy_cn(sy)}，"
                            f"弱于本区整体{fmt_pct(parent_sy - sy) if parent_sy else '—'}。"
                            "来源：四格月KPI，统计截至 2026-09-30【确认】。"
                        ),
                        raw={"sale_yoy": sy, "parent_yoy": parent_sy, "cell": cell},
                        process_leaf="S1",
                    )
                )
                stats["cells"] += 1

    cohort_path = data_dir / "神策_会员cohort_202509.csv"
    if cohort_path.is_file():
        for row in csv.DictReader(cohort_path.open(encoding="utf-8-sig")):
            area = row.get("manage_area") or row.get("manageArea") or ""
            if not area or area in exclude_regions:
                continue
            ret = fnum(row.get("retained"))
            active = fnum(row.get("active_members"))
            split_rel = (row.get("split_reliable") or "").strip()
            if split_rel == "0" and active and ret is not None and ret / active < 0.7:
                inc = fnum(row.get("incremental_members"))
                problems.append(
                    Problem(
                        scope=area,
                        trigger_id="T10",
                        alert_level="提示",
                        cadence="月",
                        message=(
                            f"9月{area}会员活跃{int(active)}人，其中上月也消费{int(ret)}人，"
                            f"留存率约{fmt_pct(ret / active)}。"
                            f"{'当月回流或新客约' + str(int(inc)) + '人（未拆新增/回流）。' if inc is not None else ''}"
                            "挂在B1并行观察。"
                            "来源：神策 payOrderDetail，统计截至 2026-09-30【估算】。"
                        ),
                        raw=row,
                        process_leaf="B1a",
                        parallel=True,
                        reliability="估算",
                        source="sensors_payOrderDetail",
                    )
                )
                stats["member"] += 1
                continue
            new_m = fnum(row.get("new_members"))
            ret_m = fnum(row.get("returning_members"))
            if active and new_m is not None and ret is not None:
                new_share = new_m / active
                if new_share < 0.05 and ret / active < 0.7:
                    problems.append(
                        Problem(
                            scope=area,
                            trigger_id="T10",
                            alert_level="提示",
                            cadence="月",
                            message=(
                                f"9月{area}会员活跃{int(active)}人，留存{int(ret)}人，新增{int(new_m)}人，回流{int(ret_m or 0)}人。"
                                "新增占比偏低，挂在B1并行观察。"
                                "来源：神策 payOrderDetail，统计截至 2026-09-30【估算】。"
                            ),
                            raw=row,
                            process_leaf="B1a",
                            parallel=True,
                            reliability="估算",
                            source="sensors_payOrderDetail",
                        )
                    )
                    stats["member"] += 1

    member_path = data_dir / "神策_会员区域月指标_202509同比.csv"
    if member_path.is_file():
        by_m: dict[str, dict[str, dict]] = defaultdict(dict)
        for row in csv.DictReader(member_path.open(encoding="utf-8-sig")):
            a = row.get("manage_area") or ""
            ym = row.get("ym") or ""
            if a and ym:
                by_m[a][ym] = row
        for area, months in by_m.items():
            if area in exclude_regions:
                continue
            c = months.get(month_label) or {}
            p = months.get(month_prev) or {}
            fy = yoy(fnum(c.get("freq")), fnum(p.get("freq")))
            if fy is not None and fy < 0:
                problems.append(
                    Problem(
                        scope=area,
                        trigger_id="T10",
                        alert_level="提示",
                        cadence="月",
                        message=(
                            f"9月{area}会员购买频次{fmt_yoy_cn(fy)}，弱于上期。"
                            "来源：神策 payOrderDetail，统计截至 2026-09-30【估算】。"
                        ),
                        raw={"freq_yoy": fy},
                        process_leaf="C1a",
                        reliability="估算",
                        source="sensors_payOrderDetail",
                    )
                )
                stats["member"] += 1

    if promo_path.is_file():
        by_area_cat: dict[str, list[float]] = defaultdict(list)
        for row in csv.DictReader(promo_path.open(encoding="utf-8-sig")):
            if (row.get("ym") or "").strip() != month_label:
                continue
            area = row.get("manage_area") or row.get("manageArea") or ""
            if not area or area in exclude_regions:
                continue
            amt = fnum(row.get("shop_promotion_amt") or row.get("shopPromotionAmt"))
            if amt is not None and amt > 0:
                by_area_cat[area].append(amt)
        for area, amts in by_area_cat.items():
            total = sum(amts)
            top = max(amts) if amts else 0
            if total > 0 and top / total >= 0.35:
                problems.append(
                    Problem(
                        scope=area,
                        trigger_id="T13",
                        alert_level="提示",
                        cadence="月",
                        message=(
                            f"9月{area}门店发起促销额{total/10000:.1f}万元，"
                            f"单大分类占比约{fmt_pct(top/total)}，挂在M1a并行观察。"
                            "来源：product_center_business_v3_info_di，统计截至 2026-09-30【确认】。"
                        ),
                        raw={"shop_promo_total": total, "top_share": top / total},
                        process_leaf="M1a",
                        parallel=True,
                        reliability="确认",
                    )
                )
                stats["m1a"] += 1

    from engine.category_big_crosswalk import (  # noqa: PLC0415
        aggregate_sensors_for_recon,
        aggregate_wide_for_recon,
        load_crosswalk,
    )

    recon_path = data_dir / "神策_区域大分类月销_202509.csv"
    cat_bd_path = data_dir / "店级大分类销售月_202509同比.csv"
    if recon_path.is_file() and cat_bd_path.is_file():
        xwalk = load_crosswalk()
        sens_rows = list(csv.DictReader(recon_path.open(encoding="utf-8-sig")))
        wide_rows = list(csv.DictReader(cat_bd_path.open(encoding="utf-8-sig")))
        sens = aggregate_sensors_for_recon(sens_rows, cfg=xwalk)
        wide = aggregate_wide_for_recon(wide_rows, month_label=month_label, cfg=xwalk)
        tol = thresholds.get("recon") or {}
        tol_v = tol.get("category_tol")
        for key, w_amt in wide.items():
            s_amt = sens.get(key, 0.0)
            if w_amt <= 0:
                continue
            gap = abs(s_amt - w_amt) / w_amt if s_amt else 1.0
            if tol_v is not None and gap > float(tol_v):
                problems.append(
                    Problem(
                        scope=key[0],
                        trigger_id="T12",
                        alert_level="描述",
                        cadence="月",
                        message=(
                            f"9月{key[0]}{key[1]}神策与宽表销售额偏差{gap*100:.1f}%，"
                            "已按大分类对照表合并肉禽蛋/标品等键；中分类下钻仍标口径未对齐。"
                            "来源：对账门+category_big_crosswalk，统计截至 2026-09-30【估算】。"
                        ),
                        raw={
                            "category": key[1],
                            "gap_pct": gap,
                            "product_gate": "口径未对齐",
                            "recon_crosswalk": "category_big_crosswalk.yaml",
                        },
                        process_leaf="B2b",
                    )
                )
                stats["category_recon"] += 1

    return stats
