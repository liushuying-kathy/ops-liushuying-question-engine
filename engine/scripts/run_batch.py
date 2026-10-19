#!/usr/bin/env python3
"""问题引擎 v3.3 跑批：bdapp + 神策 CLI 实时取数。不编造数，缺字段只标状态。"""
from __future__ import annotations

import csv
import json
import math
import os
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass, asdict, field
from datetime import date, timedelta
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parents[1]
if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))

from engine.checks import run_checks  # noqa: E402
from engine.category_depth import register_category_depth_vacancies  # noqa: E402
from engine.o1_boundary import apply_o1_per_area  # noqa: E402
from engine.promo_consumer import (  # noqa: E402
    register_b2a_vacancy,
    register_c1b_area_projection,
    register_m1b_vacancy,
)
from engine.contribute import attach_e2_lmdi, seal_monthly_contributions  # noqa: E402
from engine.daily_scan import apply_daily_scan_v33  # noqa: E402
from engine.detectors import apply_p1_detectors  # noqa: E402
from engine.fetch import merge_store_daily_kpi  # noqa: E402
from engine.problem_tree import build_executive_trees  # noqa: E402
from engine.rank import attach_tree_paths, finalize_ranking, pick_cfo_contribution_fold, rank_problems  # noqa: E402
from engine.render import lint_message, render_markdown_lists  # noqa: E402
from engine.fetch import probe_wide_max_date, run_bdapp as fetch_run_bdapp  # noqa: E402
from engine.fetch import run_python_script  # noqa: E402
from engine.store import LocalRunStore  # noqa: E402

try:
    import yaml
except ImportError:
    yaml = None

ROOT = Path(__file__).resolve().parents[2]
SQL_DIR = ROOT / "sql" / "问题引擎"
DATA_DIR = ROOT / "data" / "问题引擎"
# 2026-10-14 / 2026-10-15 冻结。v3.3 默认写到 2026-10-16。
_run_env = os.environ.get("ENGINE_RUN_DIR", "2026-10-16")
RUN_DIR = (
    (ROOT / _run_env).resolve()
    if ("/" in _run_env or "\\" in _run_env)
    else (ROOT / "问题引擎" / "runs" / _run_env).resolve()
)
CONFIG_DIR = ROOT / "问题引擎" / "config"

MONTH_LABEL = "2026-09"
MONTH_PREV = "2025-09"

PAIRS = {
    "粤西区": "粤东区",
    "华东区": "长沙区",
    "成都区": "重庆区",
    "武汉区": "郑州区",
}
SHARE_SMALL = {"合肥区", "南京区", "天津区", "西安区"}
EXCLUDE_REGIONS = {"澳门区", "澳门"}


def load_yaml(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if yaml:
        return yaml.safe_load(text)
    raise RuntimeError("需要 PyYAML: pip install pyyaml")


def run_bdapp(sql_name: str, out_name: str) -> Path:
    return fetch_run_bdapp(SQL_DIR / sql_name, DATA_DIR / out_name)


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def fnum(x) -> float | None:
    if x is None or x == "":
        return None
    try:
        v = float(x)
        if math.isnan(v):
            return None
        return v
    except (TypeError, ValueError):
        return None


def yoy(curr: float | None, prev: float | None) -> float | None:
    if curr is None or prev is None or prev == 0:
        return None
    return (curr - prev) / prev


def fmt_pct(x: float | None, digits: int = 1) -> str:
    if x is None:
        return "—"
    return f"{x * 100:.{digits}f}%"


def fmt_yoy_cn(y: float | None) -> str:
    if y is None:
        return "同比—"
    if y >= 0:
        return f"同比上升{fmt_pct(y)}"
    return f"同比下降{fmt_pct(-y)}"


def block_suffix(blocked: bool, reason: str) -> str:
    if blocked and reason:
        return f"（公司月度不升级：{reason}）"
    return ""


def weaker_than(self_yoy: float | None, ref_yoy: float | None) -> bool:
    if self_yoy is None or ref_yoy is None:
        return False
    return (self_yoy - ref_yoy) < 0


def _store_val(s: dict, *keys: str):
    for k in keys:
        v = s.get(k)
        if v is not None and v != "":
            return v
    return None


def store_bf19_curr(s: dict) -> float | None:
    return fnum(_store_val(s, "bf19CustDayAvgCurr", "bf19_cust_day_avg_curr"))


def store_bf19_for_t6(s: dict, start_open_day: int = 4) -> float | None:
    """新店 T6 优先开业第 N 天起（宽表日过滤）店日均 19 点前来客。"""
    if (s.get("cell") or "").startswith("新店"):
        d4 = fnum(_store_val(s, "bf19CustDayAvgCurrD4", "bf19_cust_day_avg_curr_d4"))
        if d4 is not None:
            return d4
    return store_bf19_curr(s)


def store_qualified_bf19(s: dict) -> float | None:
    return fnum(_store_val(s, "qualifiedBf19Curr", "qualified_bf19_curr"))


def store_region_bf19_mean(store_rows: list[dict], area: str) -> float | None:
    for s in store_rows:
        if (s.get("manageArea") or s.get("manage_area")) != area:
            continue
        m = fnum(_store_val(s, "regionBf19MeanCurr", "region_bf19_mean_curr"))
        if m is not None:
            return m
    vals = [
        store_bf19_curr(s)
        for s in store_rows
        if (s.get("manageArea") or s.get("manage_area")) == area and (s.get("cell") or "") != "未分型"
    ]
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


def new_store_traffic_unmet(
    s: dict,
    *,
    qualified_ratio: float,
    region_mean: float | None,
    fallback_region_ratio: float,
    bf19: float | None = None,
) -> bool:
    if bf19 is None:
        bf19 = store_bf19_curr(s)
    q = store_qualified_bf19(s)
    if q is not None and q > 0 and bf19 is not None:
        return bf19 < q * qualified_ratio
    if region_mean is not None and bf19 is not None:
        return bf19 < region_mean * fallback_region_ratio
    return False


@dataclass
class Problem:
    scope: str
    trigger_id: str
    alert_level: str
    message: str
    raw: dict
    traffic_basis: str = ""
    open_basis: str = ""
    wallet_basis: str = ""
    supervisor_id: str = ""
    blocked: bool = False
    cadence: str = "月"
    region_level: str = "管理区"
    parent_scope: str = ""
    entry_id: str = ""
    process_leaf: str = ""
    object_type: str = "manage_area"
    object_key: str = ""
    value: float | None = None
    delta: float | None = None
    delta_pct: float | None = None
    contribution: str = ""
    parallel: bool = False
    episode_id: str = ""
    streak_days: int = 0
    event_label: str = ""
    false_positive: bool = False
    fp_reason: str = ""
    reliability: str = ""
    source: str = ""
    compare_basis: str = ""
    problem_id: str = ""


def exclude_new_sale_yoy(cell_rows: list[dict], area: str) -> float | None:
    """剔除新店 = 老店·加盟 + 老店·直营，按营业店日加权同比。"""
    old_cells = ("老店·加盟", "老店·直营")
    c_num = c_den = p_num = p_den = 0.0
    for r in cell_rows:
        if (r.get("manageArea") or r.get("manage_area")) != area:
            continue
        if (r.get("cell") or "") not in old_cells:
            continue
        sc = fnum(r.get("saleDayAvgCurr") or r.get("sale_day_avg_curr"))
        sp = fnum(r.get("saleDayAvgPrev") or r.get("sale_day_avg_prev"))
        # 无店日列时用 sale 水平近似加权（四格 SQL 未回传 biz_days）
        if sc is not None:
            c_num += sc
            c_den += 1
        if sp is not None:
            p_num += sp
            p_den += 1
    curr = c_num / c_den if c_den else None
    prev = p_num / p_den if p_den else None
    return yoy(curr, prev)


def national_from_regions(rows: list[dict], metric: str) -> tuple[float | None, float | None]:
    """按营业店日加权合成全国（管理区域行之和，不含港澳已在 SQL 剔除）。"""
    c_num = c_den = p_num = p_den = 0.0
    for r in rows:
        area = r.get("manageArea") or r.get("manage_area")
        if area in EXCLUDE_REGIONS:
            continue
        ym = r.get("ym")
        days = fnum(r.get("bizDays") or r.get("biz_days")) or 0
        val = fnum(r.get(metric))
        if val is None or days <= 0:
            continue
        if ym == MONTH_LABEL:
            c_num += val * days
            c_den += days
        elif ym == MONTH_PREV:
            p_num += val * days
            p_den += days
    curr = c_num / c_den if c_den else None
    prev = p_num / p_den if p_den else None
    return curr, prev


def run_member_sensors() -> None:
    for name in ("member_sensors_monthly.py", "member_sensors_cohort_v33.py", "category_sensors_monthly_v33.py"):
        script = ROOT / "问题引擎" / "scripts" / name
        if script.is_file():
            run_python_script(script)


def run_fruit_sensors_6m() -> None:
    script = ROOT / "问题引擎" / "scripts" / "fruit_sensors_6m.py"
    run_python_script(script)


def load_regional_finance(thresholds: dict) -> dict[tuple[str, str], dict]:
    """(manage_area, ym) -> 行；仅 allowed_sources。"""
    fin_cfg = thresholds.get("finance_metrics") or {}
    if not fin_cfg.get("enabled"):
        return {}
    allowed = set(fin_cfg.get("allowed_sources") or [])
    paths = []
    for name in (fin_cfg.get("primary_file"), fin_cfg.get("fallback_file")):
        if not name:
            continue
        p = DATA_DIR / name
        if p.is_file():
            paths.append(p)
    if not paths:
        return {}
    out: dict[tuple[str, str], dict] = {}
    for path in paths:
        for r in read_csv(path):
            src = (r.get("data_source") or "").strip()
            if allowed and src not in allowed:
                continue
            area = r.get("manage_area") or ""
            ym = r.get("ym") or ""
            if area and ym:
                out[(area, ym)] = r
    return out


def finance_block(
    fin_row: dict | None,
    thresholds: dict,
) -> tuple[bool, str]:
    if not fin_row or not thresholds.get("block_dual_achievement"):
        return False, ""
    rev = fnum(fin_row.get("revenue_achievement"))
    pretax = fnum(fin_row.get("pretax_profit_achievement"))
    if rev is not None and pretax is not None and rev >= 1.0 and pretax >= 1.0:
        return True, f"收入达成{rev:.2%}且税前利润达成{pretax:.2%}（来源:{fin_row.get('data_source')})"
    return False, ""


def run_member_sensors_store_fruit() -> None:
    run_python_script(ROOT / "问题引擎" / "scripts" / "member_sensors_store_fruit.py")


def norm_store_id(x) -> str:
    return (x or "").strip().upper()


def probe_member_store_id_match(store_rows: list[dict], store_member_csv: Path) -> dict:
    if not store_member_csv.is_file():
        return {"matched": 0, "sensor_shops": 0, "rate": None, "note": "无店级神策 CSV"}
    bd_ids = {norm_store_id(_store_val(s, "storeId", "store_id")) for s in store_rows}
    bd_ids.discard("")
    sensor_ids = set()
    for r in read_csv(store_member_csv):
        if r.get("ym") != MONTH_LABEL:
            continue
        sid = norm_store_id(r.get("shop_id"))
        if sid:
            sensor_ids.add(sid)
    matched = len(bd_ids & sensor_ids)
    rate = matched / len(sensor_ids) if sensor_ids else None
    return {
        "matched": matched,
        "sensor_shops_curr": len(sensor_ids),
        "bdapp_stores": len(bd_ids),
        "rate": rate,
    }


def apply_member_store_richness(
    problems: list[Problem],
    thresholds: dict,
    store_member_csv: Path,
    fruit_csv: Path,
    member_by: dict,
) -> None:
    """店级 T10 + 区域 T10 丰富度伴随（水果店均动销 SKU）。"""
    if not store_member_csv.is_file():
        return
    rows = read_csv(store_member_csv)
    by_shop_ym: dict[tuple[str, str], dict] = {}
    for r in rows:
        by_shop_ym[(norm_store_id(r.get("shop_id")), r.get("ym") or "")] = r

    fruit_by_area: dict[str, list[float]] = defaultdict(list)
    if fruit_csv.is_file():
        for r in read_csv(fruit_csv):
            cnt = fnum(r.get("fruit_active_sku"))
            area = r.get("manage_area") or ""
            if cnt is not None and area:
                fruit_by_area[area].append(cnt)

    area_arpu: dict[str, float] = {}
    for (area, ym), r in member_by.items():
        if ym == MONTH_LABEL and area and area not in ("全国不含港澳", ""):
            v = fnum(r.get("arpu"))
            if v is not None:
                area_arpu[area] = v

    fruit_thr = float(thresholds.get("fruit_active_sku", 15))
    area_fruit_avg = {a: sum(v) / len(v) for a, v in fruit_by_area.items() if v}

    for p in problems:
        if p.trigger_id != "T10" or p.alert_level == "店·提示":
            continue
        if p.scope in EXCLUDE_REGIONS or p.scope in ("全国", "全国不含港澳"):
            continue
        if p.alert_level not in ("提示", "升级", "份额小"):
            continue
        avg = area_fruit_avg.get(p.scope)
        if avg is None or avg >= fruit_thr:
            continue
        p.raw = {**p.raw, "fruit_avg_active_sku": avg, "richness_note": "水果店均动销SKU低于15且区域ARPU已提示（单月2026-09）"}

    for shop, r26 in ((k[0], v) for k, v in by_shop_ym.items() if k[1] == MONTH_LABEL):
        if not shop:
            continue
        buyers = fnum(r26.get("member_buyers"))
        if buyers is None or buyers <= 0:
            continue
        r25 = by_shop_ym.get((shop, MONTH_PREV), {})
        arpu_c, arpu_p = fnum(r26.get("arpu")), fnum(r25.get("arpu"))
        ay = yoy(arpu_c, arpu_p)
        area = r26.get("manage_area") or ""
        region_arpu = area_arpu.get(area)
        weak_yoy = ay is not None and ay < 0
        weak_abs = region_arpu is not None and arpu_c is not None and arpu_c < region_arpu
        if not (weak_yoy or weak_abs):
            continue
        py = yoy(fnum(r26.get("pieces_per_order")), fnum(r25.get("pieces_per_order")))
        wb = "件数" if py is not None and py < 0 else ("只有金额" if weak_yoy else "")
        problems.append(
            Problem(
                scope=shop,
                trigger_id="T10",
                alert_level="店·提示",
                message=(
                    f"本店会员人均消费{fmt_yoy_cn(ay)}"
                    f"{'' if not weak_abs else '，低于本区会员平均水平'}"
                    "（会员订单行为初算，待与会员月报对账）。"
                ),
                raw={
                    "manage_area": area,
                    "arpu_curr": arpu_c,
                    "arpu_prev": arpu_p,
                    "arpu_yoy": ay,
                    "region_arpu_curr": region_arpu,
                    "member_buyers": buyers,
                },
                wallet_basis=wb,
            )
        )


def apply_member_t10_t15(
    problems: list[Problem],
    thresholds: dict,
    member_csv: Path,
    churn_csv: Path,
) -> dict:
    """神策补充 T10/T15（区域/全国；重量仍缺失）。返回 member_index 供督导 wallet 统计。"""
    if not member_csv.is_file():
        return {}
    rows = read_csv(member_csv)
    by_area_ym: dict[tuple[str, str], dict] = {}
    for r in rows:
        area = r.get("manage_area") or ""
        ym = r.get("ym") or ""
        by_area_ym[(area, ym)] = r

    nat26 = by_area_ym.get(("全国不含港澳", MONTH_LABEL), {})
    nat25 = by_area_ym.get(("全国不含港澳", MONTH_PREV), {})
    nat_arpu_yoy = yoy(fnum(nat26.get("arpu")), fnum(nat25.get("arpu")))
    nat_piece_yoy = yoy(fnum(nat26.get("pieces_per_order")), fnum(nat25.get("pieces_per_order")))
    nat_freq_yoy = yoy(fnum(nat26.get("freq")), fnum(nat25.get("freq")))

    def wallet_basis(arpu_yoy: float | None, piece_yoy: float | None) -> str:
        if piece_yoy is not None and piece_yoy < 0:
            return "件数"
        return "缺失" if arpu_yoy is None or arpu_yoy >= 0 else "只有金额"

    wb_nat = wallet_basis(nat_arpu_yoy, nat_piece_yoy)
    if nat_arpu_yoy is not None and nat_arpu_yoy < 0:
        problems.append(
            Problem(
                scope="全国",
                trigger_id="T10",
                alert_level="升级",
                message=(
                    f"全国会员人均消费{fmt_yoy_cn(nat_arpu_yoy)}；"
                    f"单客购买件数{'走弱' if nat_piece_yoy is not None and nat_piece_yoy < 0 else '待拆'}"
                    "，建议运营中心会员专题跟进（行为数据初算）。"
                ),
                raw={
                    "arpu_curr": fnum(nat26.get("arpu")),
                    "arpu_prev": fnum(nat25.get("arpu")),
                    "arpu_yoy": nat_arpu_yoy,
                    "freq_yoy": nat_freq_yoy,
                    "pieces_per_order_yoy": nat_piece_yoy,
                    "member_buyers_curr": nat26.get("member_buyers"),
                },
                wallet_basis=wb_nat,
            )
        )
    else:
        problems.append(
            Problem(
                scope="全国",
                trigger_id="T10",
                alert_level="提示",
                message="全国会员人均消费未达月度重点关注线（行为数据初算）。",
                raw={"arpu_yoy": nat_arpu_yoy},
                wallet_basis=wb_nat,
            )
        )

    arpu_low = thresholds.get("arpu_low_vs_national", 0.8)
    for (area, ym), r26 in by_area_ym.items():
        if ym != MONTH_LABEL or area in ("全国不含港澳", "") or area in EXCLUDE_REGIONS:
            continue
        r25 = by_area_ym.get((area, MONTH_PREV), {})
        arpu_c, arpu_p = fnum(r26.get("arpu")), fnum(r25.get("arpu"))
        ay = yoy(arpu_c, arpu_p)
        nat_arpu_c = fnum(nat26.get("arpu"))
        low_abs = nat_arpu_c is not None and arpu_c is not None and arpu_c < nat_arpu_c * arpu_low
        weak = ay is not None and nat_arpu_yoy is not None and (ay - nat_arpu_yoy) < 0
        if weak or low_abs:
            py = yoy(fnum(r26.get("pieces_per_order")), fnum(r25.get("pieces_per_order")))
            problems.append(
                Problem(
                    scope=area,
                    trigger_id="T10",
                    alert_level="提示",
                    message=(
                        f"本区会员人均消费{fmt_yoy_cn(ay)}，"
                        f"{'低于全国平均水平' if low_abs else '表现弱于全国'}"
                        "（行为数据初算）。"
                    ),
                    raw={"arpu_yoy": ay, "arpu_curr": arpu_c, "national_arpu_yoy": nat_arpu_yoy, "low_abs": low_abs},
                    wallet_basis=wallet_basis(ay, py),
                )
            )

    mom_by_area: dict[str, dict[str, float]] = defaultdict(dict)
    mom_path = churn_csv.parent / "神策_会员流失区域_环比_202509.csv"
    if mom_path.is_file():
        for mr in read_csv(mom_path):
            area = mr.get("manage_area") or mr.get("sensors_area")
            cohort = mr.get("cohort") or ""
            rate = fnum(mr.get("churn_rate"))
            if area and rate is not None:
                mom_by_area[area][cohort] = rate

    if churn_csv.is_file():
        churn_rows = read_csv(churn_csv)
        for cr in churn_rows:
            area = cr.get("manage_area") or cr.get("sensors_area")
            if not area or area in EXCLUDE_REGIONS:
                continue
            rate = fnum(cr.get("churn_rate"))
            if rate is None:
                continue
            m26 = mom_by_area.get(area, {}).get("mom_2026-09")
            m25 = mom_by_area.get(area, {}).get("mom_2025-09")
            churn_yoy = yoy(m26, m25) if m26 is not None and m25 is not None else None
            problems.append(
                Problem(
                    scope=area,
                    trigger_id="T15",
                    alert_level="提示",
                    message=(
                        f"上月活跃会员中约{fmt_pct(rate, 0)}在本统计月尚未消费"
                        "（行为数据初算，待与会员月报对账）。"
                    ),
                    raw={
                        "churn_rate": rate,
                        "prev_cnt": cr.get("prev_cnt"),
                        "churn_cnt": cr.get("churn_cnt"),
                        "cohort_note": "2025-08 vs 2026-09 跨期代理",
                        "churn_rate_mom_2026": m26,
                        "churn_rate_mom_2025": m25,
                        "churn_rate_mom_yoy": churn_yoy,
                    },
                )
            )

    return by_area_ym


def profit_rate(profit_day: float | None, sale_day: float | None) -> float | None:
    """补贴前毛利率 = 补贴前毛利额店日均 / 销售额店日均。

    区域月 SQL 里两个店日均共用营业店日作分母，所以这个比等于
    SUM(毛利额×店日) / SUM(销售额×店日)，不是把率再平均。
    """
    if profit_day is None or sale_day is None or sale_day == 0:
        return None
    return profit_day / sale_day


def apply_opera_descriptive(
    problems: list[Problem],
    sub_rows: list[dict],
    parent_sale_yoy: dict[str, float | None],
    parent_bf19_yoy: dict[str, float | None],
    parent_weight_yoy: dict[str, float | None],
) -> None:
    """运营大区只描述、不升级。省、市没有月表时不发提示。"""
    if not sub_rows:
        problems.append(
            Problem(
                scope="全国",
                trigger_id="T1",
                alert_level="待宽表",
                cadence="月",
                region_level="运营大区",
                message="没有运营大区月表，管理区下面不展开大区。",
                raw={"source": "运营大区月KPI_202509同比.csv"},
            )
        )
        return
    weight_ready = any(("weightYoy" in r) or ("weight_yoy" in r) for r in sub_rows)
    for r in sub_rows:
        area = r.get("manageArea") or r.get("manage_area")
        name = r.get("operaSubRegion") or r.get("opera_sub_region")
        if not area or not name or area in EXCLUDE_REGIONS:
            continue
        sy = fnum(r.get("saleYoy") if "saleYoy" in r else r.get("sale_yoy"))
        py = parent_sale_yoy.get(area)
        if sy is not None and sy < 0 and weaker_than(sy, py) and py is not None:
            gap_pp = (py - sy) * 100
            problems.append(
                Problem(
                    scope=name,
                    trigger_id="T1",
                    alert_level="描述",
                    cadence="月",
                    region_level="运营大区",
                    parent_scope=area,
                    object_key=area,
                    message=(
                        f"9月{name}店日均销售{fmt_yoy_cn(sy)}，"
                        f"比{area}同期弱{gap_pp:.1f}个百分点。"
                        "只说明拖累落在这一层，不单独升级。"
                    ),
                    raw={
                        "sale_yoy": sy,
                        "parent_sale_yoy": py,
                        "gap_pp": round(sy - py, 6),
                        "store_cnt": fnum(r.get("storeCnt") or r.get("store_cnt")),
                        "ceo_upgrade": False,
                        "manage_area": area,
                        "spatial_chain": [area, name],
                    },
                )
            )
        by = fnum(r.get("bf19Yoy") if "bf19Yoy" in r else r.get("bf19_yoy"))
        pb = parent_bf19_yoy.get(area)
        if by is not None and by < 0 and weaker_than(by, pb) and pb is not None:
            gap_pp = (pb - by) * 100
            problems.append(
                Problem(
                    scope=name,
                    trigger_id="T3",
                    alert_level="描述",
                    cadence="月",
                    region_level="运营大区",
                    parent_scope=area,
                    object_key=area,
                    message=(
                        f"9月{name}19点前来客{fmt_yoy_cn(by)}，"
                        f"比{area}同期弱{gap_pp:.1f}个百分点。"
                        "只说明拖累落在这一层，不单独升级。"
                    ),
                    raw={
                        "bf19_yoy": by,
                        "parent_bf19_yoy": pb,
                        "gap_pp": round(by - pb, 6),
                        "store_cnt": fnum(r.get("storeCnt") or r.get("store_cnt")),
                        "ceo_upgrade": False,
                        "manage_area": area,
                        "spatial_chain": [area, name],
                    },
                )
            )
        if weight_ready:
            wy = fnum(r.get("weightYoy") or r.get("weight_yoy"))
            pw = parent_weight_yoy.get(area)
            if wy is not None and wy < 0 and weaker_than(wy, pw) and pw is not None:
                gap_pp = (pw - wy) * 100
                problems.append(
                    Problem(
                        scope=name,
                        trigger_id="T4",
                        alert_level="描述",
                        cadence="月",
                        region_level="运营大区",
                        parent_scope=area,
                        object_key=area,
                        message=(
                            f"9月{name}进货重量{fmt_yoy_cn(wy)}，"
                            f"比{area}同期弱{gap_pp:.1f}个百分点。"
                            "只说明这一层，不单独升级。订购目标仍然缺失。"
                        ),
                        raw={
                            "weight_yoy": wy,
                            "parent_weight_yoy": pw,
                            "order_attain": "目标缺失",
                            "ceo_upgrade": False,
                            "manage_area": area,
                            "spatial_chain": [area, name],
                        },
                    )
                )
    if not weight_ready:
        problems.append(
            Problem(
                scope="全国",
                trigger_id="T4",
                alert_level="待重取数",
                cadence="月",
                region_level="运营大区",
                message=(
                    "运营大区层目前只有店日均销售和19点前来客。"
                    "进货重量、补贴前毛利额、补贴前毛利率要重取运营大区月表后才写。"
                    "日净利这一层仍然没有日表。"
                ),
                raw={"pending_columns": ["weight_yoy", "profit_amt_yoy", "profit_rate_yoy", "T14"]},
            )
        )


def apply_category_facts(problems: list[Problem], cat_rows: list[dict], thresholds: dict) -> None:
    """品类事实句。商品门六条未验完时不进解释层，不写成原因。"""
    if not cat_rows:
        problems.append(
            Problem(
                scope="全国",
                trigger_id="T12",
                alert_level="待宽表",
                cadence="月",
                message="没有管理区域×大分类量价表，品类事实句留空。",
                raw={"product_gate": "待剥离"},
            )
        )
        return
    cats = ("蔬菜类", "猪肉类", "水果类", "水产类", "冷藏及加工类", "预制菜")
    bucket: dict[tuple[str, str, str], dict] = {}
    for cr in cat_rows:
        area = cr.get("manageArea") or cr.get("manage_area")
        cat = cr.get("categoryName") or cr.get("category_name")
        ym = cr.get("ym")
        if area and cat and ym:
            bucket[(area, cat, ym)] = cr

    def day_avg(row: dict, *keys: str) -> float | None:
        for k in keys:
            if k in row:
                return fnum(row.get(k))
        return None

    def total(row: dict, *keys: str) -> float | None:
        v = day_avg(row, *keys)
        days = fnum(row.get("bizDays") or row.get("biz_days"))
        if v is None or days is None:
            return None
        return v * days

    fold_at = float(thresholds.get("contribution_fold") or 0.80)
    areas = sorted({k[0] for k in bucket if k[1] in cats})
    for area in areas:
        weight_now = 0.0
        weight_ok = False
        for cat in cats:
            cur = bucket.get((area, cat, MONTH_LABEL))
            if not cur:
                continue
            w = total(cur, "bf19WeightDayAvg", "bf19_weight_day_avg")
            if w is not None:
                weight_now += w
                weight_ok = True
        drops = []
        for cat in cats:
            cur = bucket.get((area, cat, MONTH_LABEL))
            prev = bucket.get((area, cat, MONTH_PREV))
            if not cur or not prev:
                continue
            sy = yoy(
                day_avg(cur, "bf19SaleDayAvg", "bf19_sale_day_avg"),
                day_avg(prev, "bf19SaleDayAvg", "bf19_sale_day_avg"),
            )
            if sy is None or sy >= 0:
                continue
            sale_c = total(cur, "bf19SaleDayAvg", "bf19_sale_day_avg")
            sale_p = total(prev, "bf19SaleDayAvg", "bf19_sale_day_avg")
            decline = (sale_p - sale_c) if sale_c is not None and sale_p is not None and sale_p > sale_c else 0.0
            w_c = total(cur, "bf19WeightDayAvg", "bf19_weight_day_avg")
            drops.append(
                {
                    "cat": cat,
                    "sale_yoy": sy,
                    "cust_yoy": yoy(
                        day_avg(cur, "bf19CustDayAvg", "bf19_cust_day_avg"),
                        day_avg(prev, "bf19CustDayAvg", "bf19_cust_day_avg"),
                    ),
                    "weight_yoy": yoy(
                        day_avg(cur, "bf19WeightDayAvg", "bf19_weight_day_avg"),
                        day_avg(prev, "bf19WeightDayAvg", "bf19_weight_day_avg"),
                    ),
                    "price_yoy": yoy(
                        day_avg(cur, "bf19AvgPrice", "bf19_avg_price"),
                        day_avg(prev, "bf19AvgPrice", "bf19_avg_price"),
                    ),
                    "decline": decline,
                    "weight_share": (w_c / weight_now) if weight_ok and w_c is not None and weight_now else None,
                }
            )
        ranked = sorted(drops, key=lambda x: x["decline"], reverse=True)
        decline_total = sum(x["decline"] for x in ranked)
        cum = 0.0
        for item in ranked:
            share = item["decline"] / decline_total if decline_total else None
            fold = cum >= fold_at
            if share:
                cum += share
            problems.append(
                Problem(
                    scope=area,
                    trigger_id="T12",
                    alert_level="描述",
                    cadence="月",
                    region_level="管理区",
                    message=(
                        f"9月{item['cat']}：19点前销售{fmt_yoy_cn(item['sale_yoy'])}，"
                        f"该类来客{fmt_yoy_cn(item['cust_yoy'])}，"
                        f"销售重量{fmt_yoy_cn(item['weight_yoy'])}，"
                        f"均价{fmt_yoy_cn(item['price_yoy'])}。"
                        "这是品类事实，不写成原因。"
                    ),
                    raw={
                        "category": item["cat"],
                        "sale_yoy": item["sale_yoy"],
                        "cust_yoy": item["cust_yoy"],
                        "weight_yoy": item["weight_yoy"],
                        "price_yoy": item["price_yoy"],
                        "decline_share": share,
                        "weight_share": item["weight_share"],
                        "category_sale_share": share,
                        "contribution": "贡献待算",
                        "fold": fold,
                        "product_gate": "待剥离",
                        "explain_layer": False,
                        "member_purchase_weight": "待宽表",
                    },
                )
            )


def prior_strong_store_ids() -> tuple[set[str], str]:
    runs = ROOT / "问题引擎" / "runs"
    found = []
    if runs.is_dir():
        for p in runs.glob("*/problems.json"):
            if p.parent.resolve() == RUN_DIR.resolve():
                continue
            found.append(p)
    if not found:
        return set(), "无上期快照，连续两期置顶不生效"
    latest = max(found, key=lambda p: p.stat().st_mtime)
    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return set(), "上期 problems.json 无法读取"
    ids = {
        str(row.get("scope"))
        for row in data
        if row.get("alert_level") == "店·强提示" and row.get("scope")
    }
    return ids, latest.parent.name


def project_object_sheets(problems: list[Problem]) -> None:
    """督导单按 group_manager_code。加盟商单暂按 contract_franchisee_id。运营经理按 zone_supper_id。"""
    by_sup: dict[str, dict[str, list[str]]] = {}
    for p in problems:
        if p.alert_level != "店·强提示":
            continue
        code = (p.supervisor_id or "").strip()
        if not code or code == "待督导归属":
            continue
        leaf = p.process_leaf or "S1"
        by_sup.setdefault(code, {}).setdefault(leaf, []).append(str(p.scope))
    _sup_leaf_cn = {
        "S1": "店日均销售额",
        "B1": "19点前来客",
        "E2": "店日均补贴前毛利额",
        "E1": "店日均净利",
    }
    for code, leaf_map in by_sup.items():
        for leaf, stores in leaf_map.items():
            leaf_cn = _sup_leaf_cn.get(leaf, leaf)
            problems.append(
                Problem(
                    scope=code,
                    trigger_id={"S1": "T1", "B1": "T3", "E2": "T13", "E1": "T14"}.get(leaf, "T1"),
                    alert_level="提示",
                    cadence="月",
                    message=(
                        f"督导（工号 {code}）名下 {len(stores)} 家店在「{leaf_cn}」上收到强跟店提示。"
                        "来源：门店月KPI，统计截至 2026-09-30【确认】。"
                    ),
                    raw={"store_ids": stores, "key": "group_manager_code", "process_leaf": leaf},
                    supervisor_id=code,
                    object_type="supervisor",
                    object_key=code,
                    process_leaf=leaf,
                )
            )
    by_fr: dict[str, list[str]] = {}
    missing_fr: list[str] = []
    for p in problems:
        if p.alert_level != "店·强提示":
            continue
        if "加盟" not in str((p.raw or {}).get("cell") or ""):
            continue
        fid = str((p.raw or {}).get("contract_franchisee_id") or "").strip()
        if not fid:
            missing_fr.append(str(p.scope))
            continue
        by_fr.setdefault(fid, []).append(str(p.scope))
    for fid, stores in by_fr.items():
        problems.append(
            Problem(
                scope=fid,
                trigger_id="T8",
                alert_level="提示",
                cadence="月",
                message=(
                    f"签约加盟商 {fid} 名下 {len(stores)} 家加盟店有强提示。"
                    "键暂用 contract_franchisee_id。只用 franchisee_id 会漏掉仅有合同编码的店。"
                    "业务仍要确认这张单指哪套编码。"
                ),
                raw={"store_ids": stores, "key": "contract_franchisee_id"},
                object_type="franchisee",
                object_key=fid,
            )
        )
    if missing_fr:
        problems.append(
            Problem(
                scope="全国",
                trigger_id="T8",
                alert_level="提示",
                cadence="月",
                message=f"{len(missing_fr)} 家强提示加盟店没有 contract_franchisee_id。不改用店名归集。",
                raw={"store_ids": missing_fr, "key": "contract_franchisee_id"},
                object_type="franchisee",
                object_key="无签约加盟商编码",
            )
        )
    by_ops: dict[str, list[str]] = {}
    for p in problems:
        if p.alert_level != "店·强提示":
            continue
        oid = str((p.raw or {}).get("zone_supper_id") or "").strip()
        if not oid:
            continue
        by_ops.setdefault(oid, []).append(str(p.scope))
    for oid, stores in by_ops.items():
        problems.append(
            Problem(
                scope=oid,
                trigger_id="T1",
                alert_level="提示",
                cadence="月",
                message=f"运营经理编码 {oid} 名下 {len(stores)} 家店有强提示。键是 zone_supper_id，不按姓名归店。",
                raw={"store_ids": stores, "key": "zone_supper_id"},
                object_type="ops_manager",
                object_key=oid,
            )
        )


def annotate_objects(problems: list[Problem]) -> None:
    leaf = {"T1": "S1", "T2": "S1", "T3": "B1", "T4": "O2"}
    for p in problems:
        if str(p.alert_level).startswith("店"):
            p.object_type = "store"
            p.object_key = str(p.scope)
        elif p.object_type in ("supervisor", "franchisee", "ops_manager"):
            if not p.object_key:
                p.object_key = "待字段"
        elif not p.object_key:
            p.object_key = p.scope
        if p.trigger_id in ("T1", "T5", "T6", "T7") and p.alert_level == "升级":
            p.alert_level = "提示"
        if not p.process_leaf and p.trigger_id in leaf:
            p.process_leaf = leaf[p.trigger_id]


def pick_ceo_view(
    problems: list[Problem], thresholds: dict
) -> tuple[list[Problem], list[dict]]:
    """CEO 视图：v4 全国贡献 80% + problems_ranked；否则 v3 每区一条入口。"""
    annotate_objects(problems)
    cv = thresholds.get("ceo_view") or {}
    if cv.get("mode") == "national_contribution_fold":
        ranked, ceo = finalize_ranking(problems, thresholds)
        if ceo:
            return ceo, ranked
    from engine.ids import assign_problem_ids

    assign_problem_ids(problems)
    ranked = rank_problems(problems, thresholds)
    return pick_entry_shortlist(problems, thresholds), ranked


def pick_entry_shortlist(problems: list[Problem], thresholds: dict) -> list[Problem]:
    """v3：一个管理区只留一条入口。顺序 E1、E2、E3。被阻断的那条不往下替补。"""
    annotate_objects(problems)
    by_area: dict[str, list[Problem]] = {}
    for p in problems:
        if p.region_level != "管理区" or p.cadence != "月" or p.entry_id not in ("E1", "E2", "E3"):
            continue
        by_area.setdefault(p.scope, []).append(p)
    chosen: list[Problem] = []
    for area, rows in by_area.items():
        e1_enabled = bool((thresholds.get("entry_shortlist") or {}).get("e1_enabled", True))
        e1 = None
        if e1_enabled:
            e1 = next(
                (
                    p
                    for p in rows
                    if p.entry_id == "E1"
                    and (
                        (isinstance(p.raw.get("yoy"), (int, float)) and p.raw["yoy"] < 0)
                        or (isinstance(p.raw.get("curr"), (int, float)) and p.raw["curr"] < 0)
                    )
                ),
                None,
            )
        e2 = next(
            (
                p
                for p in rows
                if p.entry_id == "E2" and isinstance(p.raw.get("yoy"), (int, float)) and p.raw["yoy"] < 0
            ),
            None,
        )
        e3 = None
        for p in rows:
            if p.entry_id != "E3":
                continue
            y = p.raw.get("yoy")
            ctrl = p.raw.get("ctrl_rate_yoy")
            if isinstance(y, (int, float)) and (y < 0 or (isinstance(ctrl, (int, float)) and y < ctrl)):
                e3 = p
                break
        if e1 is not None:
            pick = e1
        elif e2 is not None:
            pick = e2
        else:
            pick = e3
        if pick is None or pick.blocked:
            continue
        if area in SHARE_SMALL:
            pick.alert_level = "份额小"
            continue
        pick.alert_level = "升级"
        chosen.append(pick)
    return chosen


def apply_geo_location(problems: list[Problem]) -> None:
    """省、市只做定位。销售或补贴前毛利额同比小于 0 才写提示，不进短清单。"""
    path = DATA_DIR / "省市月KPI_202509同比.csv"
    if not path.is_file():
        return
    by: dict[tuple[str, str, str], dict[str, dict]] = {}
    for r in read_csv(path):
        area = r.get("manageArea") or r.get("manage_area")
        level = r.get("locLevel") or r.get("loc_level")
        name = (r.get("locName") or r.get("loc_name") or "").strip()
        ym = r.get("ym")
        if area and level and name and ym and area not in EXCLUDE_REGIONS:
            by.setdefault((area, level, name), {})[ym] = r
    for (area, level, name), months in by.items():
        cur = months.get(MONTH_LABEL) or {}
        prev = months.get(MONTH_PREV) or {}
        parent = (cur.get("parentLoc") or cur.get("parent_loc") or prev.get("parentLoc") or prev.get("parent_loc") or "")
        sale_y = yoy(
            fnum(cur.get("saleDayAvg") or cur.get("sale_day_avg")),
            fnum(prev.get("saleDayAvg") or prev.get("sale_day_avg")),
        )
        profit_y = yoy(
            fnum(cur.get("articleProfitDayAvg") or cur.get("article_profit_day_avg")),
            fnum(prev.get("articleProfitDayAvg") or prev.get("article_profit_day_avg")),
        )
        where = f"{area}{parent}{name}" if level == "市" and parent else f"{area}{name}"
        ps = area if level == "省" or not parent else parent
        if level == "市" and parent:
            ps = parent
        spatial_chain = [area, name] if level == "省" else ([area, parent, name] if parent else [area, name])
        if sale_y is not None and sale_y < 0:
            problems.append(
                Problem(
                    scope=name,
                    trigger_id="T1",
                    alert_level="提示",
                    cadence="月",
                    region_level=level,
                    parent_scope=ps,
                    message=f"{where}9月店日均销售{fmt_yoy_cn(sale_y)}。这是省或市定位，不占公司短清单。",
                    raw={
                        "sale_yoy": sale_y,
                        "dim_snap": "2026-09-30",
                        "manage_area": area,
                        "spatial_chain": spatial_chain,
                        "loc_parent": parent,
                    },
                    object_type="geo_loc",
                    object_key=area,
                    process_leaf="S1",
                )
            )
        if profit_y is not None and profit_y < 0:
            problems.append(
                Problem(
                    scope=name,
                    trigger_id="T13",
                    alert_level="提示",
                    cadence="月",
                    region_level=level,
                    parent_scope=ps,
                    message=f"{where}9月店日均补贴前毛利额{fmt_yoy_cn(profit_y)}。这是定位，不是该管理区的公司入口。",
                    raw={
                        "yoy": profit_y,
                        "dim_snap": "2026-09-30",
                        "manage_area": area,
                        "spatial_chain": spatial_chain,
                        "loc_parent": parent,
                    },
                    object_type="geo_loc",
                    object_key=area,
                )
            )


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (RUN_DIR / "config").mkdir(parents=True, exist_ok=True)
    thresholds = load_yaml(CONFIG_DIR / "thresholds.yaml")
    pairs_cfg = load_yaml(CONFIG_DIR / "pairs.yaml")

    if os.environ.get("SKIP_SENSORS") != "1":
        run_member_sensors()
        run_member_sensors_store_fruit()
        if os.environ.get("SKIP_FRUIT_6M") != "1":
            run_fruit_sensors_6m()

    # 本次快照
    for name in ("thresholds.yaml", "pairs.yaml", "regions.yaml"):
        src = CONFIG_DIR / name
        dst = RUN_DIR / "config" / name
        body = "# 本次快照\n" + src.read_text(encoding="utf-8")
        dst.write_text(body, encoding="utf-8")

    queries = [
        ("引擎_区域月KPI_202509同比.sql", "区域月KPI_202509同比.csv"),
        ("引擎_四格月KPI_202509同比_v2.sql", "四格月KPI_202509同比.csv"),
        ("引擎_老店分层客流_202509同比.sql", "老店分层客流_202509同比.csv"),
        ("引擎_门店月KPI_202509_督导.sql", "门店月KPI_202509_督导.csv"),
        ("引擎_区域不良率_202509同比.sql", "区域不良率_202509同比.csv"),
        ("引擎_店级大分类销售月_202509同比.sql", "店级大分类销售月_202509同比.csv"),
        ("引擎_大分类量价_202509同比.sql", "大分类量价_202509同比.csv"),
        ("引擎_运营大区月KPI_202509同比.sql", "运营大区月KPI_202509同比.csv"),
        ("引擎_区域OA月结净利汇总_202509同比.sql", "区域OA月结净利汇总_202509同比.csv"),
        ("引擎_区域考核净利_202509同比.sql", "区域考核净利_202509同比.csv"),
        ("引擎_省市月KPI_202509同比.sql", "省市月KPI_202509同比.csv"),
        ("引擎_管理区域日KPI_202509对日.sql", "管理区域日KPI_202509对日.csv"),
        ("引擎_大分类日KPI_202509样周.sql", "大分类日KPI_202509样周.csv"),
        ("引擎_区域门店发起促销月_202509.sql", "区域门店发起促销月_202509.csv"),
        ("引擎_区域订购达标_202509.sql", "区域订购达标_202509.csv"),
        ("引擎_宽表最新分区探针.sql", "_scratch/probe_v33_wide_maxdate.csv"),
    ]
    if os.environ.get("SKIP_BDAPP") != "1":
        for sql, out in queries:
            run_bdapp(sql, out)

    reg_rows = read_csv(DATA_DIR / "区域月KPI_202509同比.csv")
    if os.environ.get("SKIP_BDAPP") != "1" and (thresholds.get("daily_scan") or {}).get("open_store_layer"):
        areas = sorted(
            {
                r.get("manageArea") or r.get("manage_area")
                for r in reg_rows
                if (r.get("manageArea") or r.get("manage_area")) not in EXCLUDE_REGIONS
            }
        )
        areas = [a for a in areas if a]
        if areas:
            merge_store_daily_kpi(SQL_DIR, DATA_DIR, areas, run_bdapp_fn=run_bdapp)
    cell_rows = read_csv(DATA_DIR / "四格月KPI_202509同比.csv")
    layer_rows = read_csv(DATA_DIR / "老店分层客流_202509同比.csv")
    store_rows = read_csv(DATA_DIR / "门店月KPI_202509_督导.csv")
    bad_rows = read_csv(DATA_DIR / "区域不良率_202509同比.csv")
    cat_path = DATA_DIR / "店级大分类销售月_202509同比.csv"
    cat_rows = read_csv(cat_path) if cat_path.is_file() else []

    # 区域指标索引
    reg_by_area: dict[str, dict[str, dict]] = defaultdict(dict)
    for r in reg_rows:
        area = r["manageArea"] if "manageArea" in r else r["manage_area"]
        reg_by_area[area][r["ym"]] = r

    def area_metric(area: str, field: str, ym: str) -> float | None:
        row = reg_by_area.get(area, {}).get(ym, {})
        return fnum(row.get(field))

    nat_sale_c, nat_sale_p = national_from_regions(reg_rows, "saleDayAvg" if "saleDayAvg" in reg_rows[0] else "sale_day_avg")
    nat_bf19_c, nat_bf19_p = national_from_regions(reg_rows, "bf19CustDayAvg" if reg_rows and "bf19CustDayAvg" in reg_rows[0] else "bf19_cust_day_avg")
    nat_w_c, nat_w_p = national_from_regions(reg_rows, "purchaseWeightDayAvg" if reg_rows and "purchaseWeightDayAvg" in reg_rows[0] else "purchase_weight_day_avg")
    nat_yoy_sale = yoy(nat_sale_c, nat_sale_p)
    nat_yoy_bf19 = yoy(nat_bf19_c, nat_bf19_p)
    nat_yoy_w = yoy(nat_w_c, nat_w_p)

    problems: list[Problem] = []
    ceo_upgrades: list[Problem] = []
    reg_fin = load_regional_finance(thresholds)

    strong_thr = thresholds["store_strong_hint_yoy"]
    ach_thr = thresholds["achievement_hint"]

    # 未分型占比（店级）
    untyped = sum(1 for s in store_rows if s.get("cell") == "未分型")
    typed = sum(1 for s in store_rows if s.get("cell") != "未分型")
    untyped_share = untyped / (typed + untyped) if (typed + untyped) else 0

    oa_by: dict[tuple[str, str], dict] = {}
    oa_path = DATA_DIR / "区域考核净利_202509同比.csv"
    if oa_path.is_file():
        for r in read_csv(oa_path):
            area_name = r.get("manageArea") or r.get("manage_area")
            ym = r.get("ym")
            if area_name and ym:
                oa_by[(area_name, ym)] = r

    def oa_metric(area_name: str, ym: str, camel: str, snake: str) -> float | None:
        row = oa_by.get((area_name, ym)) or {}
        return fnum(row.get(camel) if row.get(camel) not in (None, "") else row.get(snake))

    for area in sorted(reg_by_area.keys()):
        if area in EXCLUDE_REGIONS:
            continue
        ctrl = PAIRS.get(area)
        sale_c = area_metric(area, "saleDayAvg" if "saleDayAvg" in reg_rows[0] else "sale_day_avg", MONTH_LABEL)
        sale_p = area_metric(area, "saleDayAvg" if "saleDayAvg" in reg_rows[0] else "sale_day_avg", MONTH_PREV)
        bf19_c = area_metric(area, "bf19CustDayAvg" if "bf19CustDayAvg" in reg_rows[0] else "bf19_cust_day_avg", MONTH_LABEL)
        bf19_p = area_metric(area, "bf19CustDayAvg" if "bf19CustDayAvg" in reg_rows[0] else "bf19_cust_day_avg", MONTH_PREV)
        w_c = area_metric(area, "purchaseWeightDayAvg" if "purchaseWeightDayAvg" in reg_rows[0] else "purchase_weight_day_avg", MONTH_LABEL)
        w_p = area_metric(area, "purchaseWeightDayAvg" if "purchaseWeightDayAvg" in reg_rows[0] else "purchase_weight_day_avg", MONTH_PREV)
        ach = area_metric(area, "saleAchievement" if "saleAchievement" in reg_rows[0] else "sale_achievement", MONTH_LABEL)

        y_sale = yoy(sale_c, sale_p)
        y_bf19 = yoy(bf19_c, bf19_p)
        y_w = yoy(w_c, w_p)

        ctrl_y_sale = ctrl_y_bf19 = ctrl_y_w = None
        if ctrl:
            ctrl_y_sale = yoy(
                area_metric(ctrl, "saleDayAvg" if "saleDayAvg" in reg_rows[0] else "sale_day_avg", MONTH_LABEL),
                area_metric(ctrl, "saleDayAvg" if "saleDayAvg" in reg_rows[0] else "sale_day_avg", MONTH_PREV),
            )
            ctrl_y_bf19 = yoy(
                area_metric(ctrl, "bf19CustDayAvg" if "bf19CustDayAvg" in reg_rows[0] else "bf19_cust_day_avg", MONTH_LABEL),
                area_metric(ctrl, "bf19CustDayAvg" if "bf19CustDayAvg" in reg_rows[0] else "bf19_cust_day_avg", MONTH_PREV),
            )
            ctrl_y_w = yoy(
                area_metric(ctrl, "purchaseWeightDayAvg" if "purchaseWeightDayAvg" in reg_rows[0] else "purchase_weight_day_avg", MONTH_LABEL),
                area_metric(ctrl, "purchaseWeightDayAvg" if "purchaseWeightDayAvg" in reg_rows[0] else "purchase_weight_day_avg", MONTH_PREV),
            )

        blocked = False
        block_reason = ""
        fin_row = reg_fin.get((area, MONTH_LABEL))
        fin_blocked, fin_msg = finance_block(fin_row, thresholds)
        if fin_blocked:
            blocked = True
            block_reason = fin_msg

        area_untyped = sum(1 for s in store_rows if s.get("manageArea", s.get("manage_area")) == area and s.get("cell") == "未分型")
        area_typed = sum(1 for s in store_rows if s.get("manageArea", s.get("manage_area")) == area and s.get("cell") != "未分型")
        area_untyped_share = area_untyped / (area_untyped + area_typed) if (area_untyped + area_typed) else 0
        if area_untyped_share >= thresholds["untyped_share_block"]:
            blocked = True
            block_reason = block_reason or f"未分型占比{area_untyped_share:.1%}"

        # T9（仅当有对接 CSV 且非空达成字段；非 ADS 实取）
        if fin_row:
            pretax_ach = fnum(fin_row.get("pretax_profit_achievement"))
            pretax_yoy = fnum(fin_row.get("pretax_profit_yoy"))
            roll_pp = fnum(fin_row.get("rolling_forecast_pp"))
            roll_thr = float(thresholds.get("rolling_forecast_pp", -3)) / 100
            t9_hit = False
            if pretax_ach is not None and pretax_ach < ach_thr:
                t9_hit = True
            if roll_pp is not None and roll_pp <= roll_thr:
                t9_hit = True
            if pretax_yoy is not None and pretax_yoy < 0:
                t9_hit = True
            if t9_hit:
                t9_parts = []
                if pretax_ach is not None:
                    t9_parts.append(f"税前利润预算达成约{fmt_pct(pretax_ach)}")
                if roll_pp is not None:
                    t9_parts.append(f"较滚动预测低约{fmt_pct(-roll_pp) if roll_pp < 0 else fmt_pct(roll_pp)}")
                if pretax_yoy is not None and pretax_yoy < 0:
                    t9_parts.append(fmt_yoy_cn(pretax_yoy))
                t9_msg = "；".join(t9_parts) or "利润指标触及预警"
                t9_msg += "。请财务BP与区总对齐（对接表数据，非宽表结账数）。"
                problems.append(
                    Problem(
                        scope=area,
                        trigger_id="T9",
                        alert_level="提示",
                        message=t9_msg,
                        raw={
                            "pretax_profit_achievement": pretax_ach,
                            "pretax_profit_yoy": pretax_yoy,
                            "rolling_forecast_pp": roll_pp,
                            "revenue_achievement": fnum(fin_row.get("revenue_achievement")),
                            "data_source": fin_row.get("data_source"),
                            "note": fin_row.get("note"),
                        },
                        blocked=blocked,
                    )
                )

        ctrl_label = ctrl or "对照区"
        bf19_sale_c = area_metric(
            area,
            "bf19SaleDayAvg" if "bf19SaleDayAvg" in reg_rows[0] else "bf19_sale_day_avg",
            MONTH_LABEL,
        )
        bf19_sale_p = area_metric(
            area,
            "bf19SaleDayAvg" if "bf19SaleDayAvg" in reg_rows[0] else "bf19_sale_day_avg",
            MONTH_PREV,
        )
        pu_c = (bf19_sale_c / bf19_c) if bf19_sale_c is not None and bf19_c else None
        pu_p = (bf19_sale_p / bf19_p) if bf19_sale_p is not None and bf19_p else None
        y_bf19_price = yoy(pu_c, pu_p)
        # T1 区域提示
        if y_sale is not None and y_sale < 0 and (
            weaker_than(y_sale, ctrl_y_sale) or weaker_than(y_sale, nat_yoy_sale)
        ):
            decomp_parts: list[str] = []
            if y_bf19 is not None:
                decomp_parts.append(f"19点前来客{fmt_yoy_cn(y_bf19)}")
            if y_bf19_price is not None:
                decomp_parts.append(f"19点前客单价{fmt_yoy_cn(y_bf19_price)}")
            decomp_suffix = ""
            if decomp_parts:
                decomp_suffix = (
                    "销售额按 §4.1 拆开看："
                    + "；".join(decomp_parts)
                    + "。不写成谁导致谁。"
                )
            problems.append(
                Problem(
                    scope=area,
                    trigger_id="T1",
                    alert_level="提示",
                    cadence="月",
                    region_level="管理区",
                    object_type="manage_area",
                    object_key=area,
                    process_leaf="S1",
                    message=(
                        f"9月店日均销售额{fmt_yoy_cn(y_sale)}，表现弱于{ctrl_label}及全国"
                        f"{block_suffix(blocked, block_reason)}。"
                        f"{decomp_suffix}"
                    ),
                    raw={
                        "sale_yoy": y_sale,
                        "ctrl_yoy": ctrl_y_sale,
                        "national_yoy": nat_yoy_sale,
                        "sale_day_avg_curr": sale_c,
                        "sale_day_avg_prev": sale_p,
                        "bf19_yoy": y_bf19,
                        "bf19_price_yoy": y_bf19_price,
                        "weight_yoy": y_w,
                        "s1_decompose": {
                            "B1_bf19_yoy": y_bf19,
                            "B2_bf19_price_yoy": y_bf19_price,
                            "O2_weight_yoy": y_w,
                        },
                    },
                    blocked=blocked,
                )
            )

        # T3（须同比 < 0）
        if (
            y_bf19 is not None
            and y_bf19 < 0
            and weaker_than(y_bf19, ctrl_y_bf19)
            and weaker_than(y_bf19, nat_yoy_bf19)
        ):
            problems.append(
                Problem(
                    scope=area,
                    trigger_id="T3",
                    alert_level="提示",
                    message=f"9月19点前来客{fmt_yoy_cn(y_bf19)}，表现弱于{ctrl_label}及全国。",
                    raw={"bf19_yoy": y_bf19, "ctrl_yoy": ctrl_y_bf19, "national_yoy": nat_yoy_bf19},
                    blocked=blocked,
                )
            )

        # T4
        if y_w is not None and y_w < 0 and weaker_than(y_w, ctrl_y_w):
            problems.append(
                Problem(
                    scope=area,
                    trigger_id="T4",
                    alert_level="提示",
                    message=f"9月进货重量{fmt_yoy_cn(y_w)}，表现弱于{ctrl_label}。",
                    raw={"weight_yoy": y_w, "ctrl_yoy": ctrl_y_w, "order_attain": "目标缺失"},
                    blocked=blocked,
                )
            )

        # T13 补贴前毛利额、补贴前毛利率。率 = 额 / 销售额，不平均率列。
        ap_c = area_metric(
            area,
            "articleProfitDayAvg" if "articleProfitDayAvg" in reg_rows[0] else "article_profit_day_avg",
            MONTH_LABEL,
        )
        ap_p = area_metric(
            area,
            "articleProfitDayAvg" if "articleProfitDayAvg" in reg_rows[0] else "article_profit_day_avg",
            MONTH_PREV,
        )
        y_amt = yoy(ap_c, ap_p)
        rate_c = profit_rate(ap_c, sale_c)
        rate_p = profit_rate(ap_p, sale_p)
        y_rate = yoy(rate_c, rate_p)
        ctrl_y_rate = None
        if ctrl:
            ctrl_y_rate = yoy(
                profit_rate(
                    area_metric(ctrl, "articleProfitDayAvg" if "articleProfitDayAvg" in reg_rows[0] else "article_profit_day_avg", MONTH_LABEL),
                    area_metric(ctrl, "saleDayAvg" if "saleDayAvg" in reg_rows[0] else "sale_day_avg", MONTH_LABEL),
                ),
                profit_rate(
                    area_metric(ctrl, "articleProfitDayAvg" if "articleProfitDayAvg" in reg_rows[0] else "article_profit_day_avg", MONTH_PREV),
                    area_metric(ctrl, "saleDayAvg" if "saleDayAvg" in reg_rows[0] else "sale_day_avg", MONTH_PREV),
                ),
            )
        if y_amt is not None and y_amt < 0:
            p_e2 = Problem(
                scope=area,
                trigger_id="T13",
                alert_level="提示",
                message=(
                    f"9月{area}店日均补贴前毛利额{fmt_yoy_cn(y_amt)}。"
                    "来源：operation_center_wide_store_di，统计截至 2026-09-30【确认】。"
                ),
                raw={"measure": "补贴前毛利额", "yoy": y_amt, "curr": ap_c, "prev": ap_p},
                blocked=blocked,
                entry_id="E2",
                value=ap_c,
                delta=(ap_c - ap_p) if ap_c is not None and ap_p is not None else None,
                delta_pct=y_amt,
                reliability="确认",
                source="operation_center_wide_store_di",
            )
            attach_e2_lmdi(p_e2, sale_c, sale_p, rate_c, rate_p, ap_c, ap_p)
            problems.append(p_e2)
        rate_hit = y_rate is not None and (
            y_rate < 0 or weaker_than(y_rate, ctrl_y_rate)
        )
        if rate_hit:
            problems.append(
                Problem(
                    scope=area,
                    trigger_id="T13",
                    alert_level="提示",
                    message=(
                        f"9月补贴前毛利率{fmt_yoy_cn(y_rate)}。"
                        "这是赚钱效率，和毛利额分开看。"
                    ),
                    raw={
                        "measure": "补贴前毛利率",
                        "yoy": y_rate,
                        "rate_curr": rate_c,
                        "rate_prev": rate_p,
                        "amount_yoy": y_amt,
                        "ctrl_rate_yoy": ctrl_y_rate,
                        "diverged_from_amount": y_amt is not None and (y_amt < 0) != (y_rate < 0),
                    },
                    blocked=blocked,
                    entry_id="E3",
                )
            )

        np_c = oa_metric(area, MONTH_LABEL, "lossNpDayAvg", "loss_np_day_avg")
        np_p = oa_metric(area, MONTH_PREV, "lossNpDayAvg", "loss_np_day_avg")
        y_np = yoy(np_c, np_p)
        if (y_np is not None and y_np < 0) or (np_c is not None and np_c < 0):
            level_txt = f"约{np_c:.0f}元" if np_c is not None else "金额缺失"
            problems.append(
                Problem(
                    scope=area,
                    trigger_id="T14",
                    alert_level="提示",
                    message=(
                        f"9月考核净利润按营业天数摊到店日{fmt_yoy_cn(y_np)}，{level_txt}。"
                        "【估算】算法是月表 loss_net_profit 除以 loss_sale_days，待业务拍板为唯一官方公式。"
                        "这不是店日宽表净利，也不是月结 stl_net_profit。"
                        "来源：operation_center_store_loss_profit_oa_mi，统计截至 2026-09【估算】。"
                    ),
                    reliability="估算",
                    raw={
                        "measure": "考核净利店日均",
                        "column": "loss_net_profit",
                        "yoy": y_np,
                        "curr": np_c,
                        "prev": np_p,
                        "stl_not_e1": True,
                        "dim_snap": "2026-09-30",
                    },
                    blocked=blocked,
                    entry_id="E1",
                )
            )

        # T2 达成 / 滚测（滚测仅 finance CSV）
        roll_pp_fin = fnum(fin_row.get("rolling_forecast_pp")) if fin_row else None
        roll_thr_pp = float(thresholds.get("rolling_forecast_pp", -3)) / 100
        t2_roll = roll_pp_fin is not None and roll_pp_fin <= roll_thr_pp
        if ach is not None and ach < ach_thr:
            problems.append(
                Problem(
                    scope=area,
                    trigger_id="T2",
                    alert_level="提示",
                    message=f"9月销售额预算达成约{fmt_pct(ach)}，低于建议关注线（销售额预算，非税前利润）。",
                    raw={"sale_achievement": ach, "rolling_forecast_pp": roll_pp_fin},
                    blocked=blocked,
                )
            )
        elif t2_roll:
            problems.append(
                Problem(
                    scope=area,
                    trigger_id="T2",
                    alert_level="提示",
                    message=f"9月表现较滚动预测低约{fmt_pct(-roll_pp_fin) if roll_pp_fin and roll_pp_fin < 0 else fmt_pct(roll_pp_fin)}（对接表数据）。",
                    raw={"sale_achievement": ach, "rolling_forecast_pp": roll_pp_fin},
                    blocked=blocked,
                )
            )

        # T5 尾部只作定位。销售、进货重量、来客已各写一条，这里不再合并。
        layers = [r for r in layer_rows if (r.get("manageArea") or r.get("manage_area")) == area]
        if layers:
            yoys = {}
            for lr in layers:
                lb = lr.get("layerBucket") or lr.get("layer_bucket")
                yv = yoy(
                    fnum(lr.get("bf19CustDayAvgCurr") or lr.get("bf19_cust_day_avg_curr")),
                    fnum(lr.get("bf19CustDayAvgPrev") or lr.get("bf19_cust_day_avg_prev")),
                )
                if lb and yv is not None:
                    yoys[lb] = yv
            tail = yoys.get("尾部")
            others = [yoys[k] for k in yoys if k != "尾部"]
            branch1 = others and all(v >= 0 for v in others)
            branch2 = False
            if tail is not None:
                need = [yoys.get("头部"), yoys.get("中上"), yoys.get("中下")]
                if all(v is not None for v in need):
                    branch2 = tail < need[0] and tail < need[1] and tail < need[2]
            # v1.8.2：尾部同比不为负，不升级，也不写「尾部偏弱」。
            if tail is not None and tail < 0 and (branch1 or branch2):
                problems.append(
                    Problem(
                        scope=area,
                        trigger_id="T5",
                        alert_level="提示",
                        message=(
                            f"老店「尾部」19点前来客{fmt_yoy_cn(tail)}，"
                            "弱于本区其他客流分层。这是店型定位，不占公司短清单。"
                        ),
                        raw={"layer_bf19_yoy": yoys, "branch1": branch1, "branch2": branch2},
                        blocked=blocked,
                    )
                )

        # T6 新店：盈亏平衡路径优先，缺 OA/客单则退回区域85%
        nt_cfg = thresholds["new_store_traffic"]
        q_ratio = float(nt_cfg.get("qualified_ratio_suggest", 0.90))
        fb_ratio = float(nt_cfg.get("fallback_region_ratio", 0.85))
        city_ratio = float(nt_cfg.get("fallback_city_ratio", 0.70))
        new_stores = [
            s
            for s in store_rows
            if (s.get("manageArea") or s.get("manage_area")) == area and (s.get("cell") or "").startswith("新店")
        ]
        if new_stores:
            region_mean = store_region_bf19_mean(store_rows, area)
            unmet_primary = 0
            unmet_85_cnt = 0
            unmet_be90_cnt = 0
            strengthened_cnt = 0
            path_be = path_fb = 0
            d4_cnt = 0
            for s in new_stores:
                bf19 = store_bf19_for_t6(s)
                if fnum(_store_val(s, "bf19CustDayAvgCurrD4", "bf19_cust_day_avg_curr_d4")) is not None:
                    d4_cnt += 1
                q = store_qualified_bf19(s)
                if q is not None and q > 0:
                    path_be += 1
                else:
                    path_fb += 1
                if new_store_traffic_unmet(
                    s,
                    qualified_ratio=q_ratio,
                    region_mean=region_mean,
                    fallback_region_ratio=fb_ratio,
                    bf19=bf19,
                ):
                    unmet_primary += 1
                if region_mean is not None and bf19 is not None and bf19 < region_mean * fb_ratio:
                    unmet_85_cnt += 1
                if q is not None and q > 0 and bf19 is not None and bf19 < q * q_ratio:
                    unmet_be90_cnt += 1
                city_m = fnum(_store_val(s, "cityBf19MeanCurr", "city_bf19_mean_curr"))
                if city_m is not None and bf19 is not None and bf19 < city_m * city_ratio:
                    strengthened_cnt += 1
            share = unmet_primary / len(new_stores) if new_stores else 0
            if path_be > 0 and path_fb == 0:
                t_basis = "盈亏平衡"
                msg = (
                    f"新店{len(new_stores)}家：按本店盈亏平衡测算，"
                    f"{unmet_primary}家未达建议客流线（标准的90%），未达标占比{fmt_pct(share)}。"
                )
            elif path_be > 0:
                t_basis = "混合"
                msg = (
                    f"新店{len(new_stores)}家客流未达标占比{fmt_pct(share)}"
                    f"（{path_be}家按盈亏平衡测算、{path_fb}家按区域均值口径）。"
                )
            else:
                t_basis = "区域85"
                msg = f"新店{len(new_stores)}家中{unmet_primary}家19点前客流低于区域均值85%。"
            t6_raw = {
                "new_store_cnt": len(new_stores),
                "unmet_primary_cnt": unmet_primary,
                "unmet_share": share,
                "unmet_85_cnt": unmet_85_cnt,
                "unmet_breakeven_90_cnt": unmet_be90_cnt,
                "strengthened_city_70_cnt": strengthened_cnt,
                "region_bf19_mean": region_mean,
                "breakeven_path_stores": path_be,
                "fallback_path_stores": path_fb,
                "qualified_ratio": q_ratio,
                "new_store_bf19_open_day4_cnt": d4_cnt,
                "block_reason": block_reason,
            }
            if share >= nt_cfg.get("upgrade_unmet_share", 0.50):
                problems.append(
                    Problem(
                        scope=area,
                        trigger_id="T6",
                        alert_level="提示",
                        message=msg + " 这是新店定位，不占公司短清单。",
                        raw=t6_raw,
                        traffic_basis=t_basis,
                        blocked=blocked,
                    )
                )
            elif unmet_primary >= 1:
                problems.append(
                    Problem(
                        scope=area,
                        trigger_id="T6",
                        alert_level="提示",
                        message=(
                            f"新店{len(new_stores)}家：按本店盈亏平衡测算，"
                            f"{unmet_primary}家未达建议客流线，请督导跟新店清单。"
                        ),
                        raw=t6_raw,
                        traffic_basis=t_basis,
                        blocked=blocked,
                    )
                )
            elif unmet_85_cnt >= 1:
                problems.append(
                    Problem(
                        scope=area,
                        trigger_id="T6",
                        alert_level="提示",
                        message=(
                            f"新店{len(new_stores)}家：按盈亏平衡测算暂无升级线以上缺口；"
                            f"并列披露{unmet_85_cnt}家低于区域均值85%，供与会议材料对照。"
                        ),
                        raw={**t6_raw, "material_line_note": "9月回放若与材料不一致，并列不凑数"},
                        traffic_basis=t_basis if path_be else "区域85",
                        blocked=blocked,
                    )
                )

        # T11 不良率
        bad_area = [b for b in bad_rows if (b.get("manageArea") or b.get("manage_area")) == area]
        b26 = next((b for b in bad_area if b.get("ym") == MONTH_LABEL), None)
        b25 = next((b for b in bad_area if b.get("ym") == MONTH_PREV), None)
        if b26 and b25:
            r26 = fnum(b26.get("badRate") or b26.get("bad_rate"))
            r25 = fnum(b25.get("badRate") or b25.get("bad_rate"))
            if r26 is not None and r25 is not None:
                pp = (r26 - r25) * 100
                if pp >= thresholds["bad_rate_yoy_pp"] or r26 >= thresholds["bad_rate_abs"]:
                    problems.append(
                        Problem(
                            scope=area,
                            trigger_id="T11",
                            alert_level="提示",
                            message=(
                                f"区域不良店占比约{fmt_pct(r26, 1)}，"
                                f"较上年同期上升约{pp:.1f}个百分点。"
                            ),
                            raw={"bad_rate_curr": r26, "bad_rate_prev": r25, "yoy_pp": pp},
                            blocked=blocked,
                        )
                    )

    p1_stats = apply_p1_detectors(
        problems,
        Problem,
        data_dir=DATA_DIR,
        reg_by_area=reg_by_area,
        reg_rows=reg_rows,
        cell_rows=cell_rows,
        month_label=MONTH_LABEL,
        month_prev=MONTH_PREV,
        pairs=PAIRS,
        exclude_regions=EXCLUDE_REGIONS,
        thresholds=thresholds,
        yoy=yoy,
        fnum=fnum,
        fmt_yoy_cn=fmt_yoy_cn,
        fmt_pct=fmt_pct,
        weaker_than=weaker_than,
        profit_rate=profit_rate,
    )
    o1_stats = apply_o1_per_area(
        problems,
        Problem,
        data_dir=DATA_DIR,
        manage_areas=sorted(reg_by_area.keys()),
        exclude_regions=EXCLUDE_REGIONS,
        thresholds=thresholds,
        fnum=fnum,
        fmt_pct=fmt_pct,
    )
    p1_stats["o1"] = o1_stats.get("below_threshold", 0) + o1_stats.get("no_target", 0)
    p1_stats["o1_boundary"] = o1_stats

    member_by = apply_member_t10_t15(
        problems,
        thresholds,
        DATA_DIR / "神策_会员区域月指标_202509同比.csv",
        DATA_DIR / "神策_会员流失区域_202509.csv",
    )
    apply_member_store_richness(
        problems,
        thresholds,
        DATA_DIR / "神策_会员店级月指标_202509同比.csv",
        DATA_DIR / "神策_水果店动销SKU_202609.csv",
        member_by,
    )

    # 店强提示 + 督导
    grid_alerted = {(p.scope, p.trigger_id) for p in problems if p.alert_level in ("提示", "升级", "份额小")}
    sup_summary: dict[str, dict] = defaultdict(lambda: {"strong": 0, "wallet": defaultdict(int), "pinned": 0})
    prior_ids, prior_note = prior_strong_store_ids()

    for s in store_rows:
        area = s.get("manageArea") or s.get("manage_area")
        cell = s.get("cell") or ""
        if cell == "未分型":
            continue
        sy = yoy(fnum(s.get("saleDayAvgCurr") or s.get("sale_day_avg_curr")), fnum(s.get("saleDayAvgPrev") or s.get("sale_day_avg_prev")))
        ty = yoy(fnum(s.get("bf19CustDayAvgCurr") or s.get("bf19_cust_day_avg_curr")), fnum(s.get("bf19CustDayAvgPrev") or s.get("bf19_cust_day_avg_prev")))
        npv = fnum(s.get("netProfitDayAvgCurr") or s.get("net_profit_day_avg_curr"))
        sup = (s.get("supervisorId") or s.get("supervisor_id") or "").strip()
        if not sup:
            sup = "待督导归属"
        strong_leaf = ""
        strong = False
        if sy is not None and sy <= strong_thr:
            strong = True
            strong_leaf = "S1"
        if ty is not None and ty <= strong_thr:
            strong = True
            strong_leaf = "B1" if strong_leaf != "S1" else strong_leaf
        ap_sy = yoy(
            fnum(s.get("articleProfitDayAvgCurr") or s.get("article_profit_day_avg_curr")),
            fnum(s.get("articleProfitDayAvgPrev") or s.get("article_profit_day_avg_prev")),
        )
        if ap_sy is not None and ap_sy <= strong_thr:
            strong = True
            strong_leaf = "E2"
        if npv is not None and npv < 0:
            strong = True
            strong_leaf = "E1"
        if strong:
            biz_days = fnum(s.get("bizDaysCurr") or s.get("biz_days_curr"))
            close_date = str(s.get("closeDate") or s.get("close_date") or "").strip()
            if close_date:
                open_basis = "闭店日期"
            elif biz_days is not None and biz_days > 0:
                open_basis = "在场反推"
            else:
                open_basis = ""
            store_id = str(s.get("storeId") or s.get("store_id") or "")
            pinned = bool(store_id and store_id in prior_ids)
            seg: list[str] = []
            if sy is not None and sy <= strong_thr:
                seg.append(f"店日均销售{fmt_yoy_cn(sy)}")
            if ty is not None and ty <= strong_thr:
                seg.append(f"19点前来客{fmt_yoy_cn(ty)}")
            if ap_sy is not None and ap_sy <= strong_thr:
                seg.append(f"店日均补贴前毛利额{fmt_yoy_cn(ap_sy)}")
            if npv is not None and npv < 0:
                seg.append(f"店日均净利约{npv:.0f}元【估算】")
            store_msg = "9月跟店提示：" + ("；".join(seg) if seg else "经营指标触及跟店线") + "。"
            trig_map = {"S1": "T1", "B1": "T3", "E2": "T13", "E1": "T14"}
            problems.append(
                Problem(
                    scope=s.get("storeId") or s.get("store_id"),
                    trigger_id=trig_map.get(strong_leaf, "T1"),
                    alert_level="店·强提示",
                    message=store_msg,
                    process_leaf=strong_leaf or "S1",
                    raw={
                        "sale_yoy": sy,
                        "bf19_yoy": ty,
                        "net_profit_day_avg": npv,
                        "net_profit_basis": "loss_net_profit/loss_sale_days，未拍板为唯一官方公式",
                        "franchisee_id": (s.get("franchiseeId") or s.get("franchisee_id") or "").strip(),
                        "contract_franchisee_id": (s.get("contractFranchiseeId") or s.get("contract_franchisee_id") or "").strip(),
                        "zone_supper_id": (s.get("zoneSupperId") or s.get("zone_supper_id") or "").strip(),
                        "cell": cell,
                        "manage_area": area,
                        "supervisor_pin": pinned,
                        "prior_run": prior_note,
                    },
                    supervisor_id=sup,
                    open_basis=open_basis,
                )
            )
            if sup != "待督导归属":
                sup_summary[sup]["strong"] += 1
                if pinned:
                    sup_summary[sup]["pinned"] += 1
                r26 = member_by.get((area or "", MONTH_LABEL), {})
                r25 = member_by.get((area or "", MONTH_PREV), {})
                py = yoy(fnum(r26.get("pieces_per_order")), fnum(r25.get("pieces_per_order")))
                ay = yoy(fnum(r26.get("arpu")), fnum(r25.get("arpu")))
                if py is not None and py < 0:
                    sup_summary[sup]["wallet"]["件数"] += 1
                elif ay is not None and ay < 0:
                    sup_summary[sup]["wallet"]["只有金额"] += 1

    price_path = DATA_DIR / "大分类量价_202509同比.csv"
    price_rows = read_csv(price_path) if price_path.is_file() else []
    apply_category_facts(problems, price_rows, thresholds)
    parent_sale = {}
    parent_bf19 = {}
    parent_weight = {}
    w_key = "purchaseWeightDayAvg" if "purchaseWeightDayAvg" in reg_rows[0] else "purchase_weight_day_avg"
    for area in reg_by_area:
        parent_sale[area] = yoy(
            area_metric(area, "saleDayAvg" if "saleDayAvg" in reg_rows[0] else "sale_day_avg", MONTH_LABEL),
            area_metric(area, "saleDayAvg" if "saleDayAvg" in reg_rows[0] else "sale_day_avg", MONTH_PREV),
        )
        parent_bf19[area] = yoy(
            area_metric(area, "bf19CustDayAvg" if "bf19CustDayAvg" in reg_rows[0] else "bf19_cust_day_avg", MONTH_LABEL),
            area_metric(area, "bf19CustDayAvg" if "bf19CustDayAvg" in reg_rows[0] else "bf19_cust_day_avg", MONTH_PREV),
        )
        parent_weight[area] = yoy(
            area_metric(area, w_key, MONTH_LABEL),
            area_metric(area, w_key, MONTH_PREV),
        )
    opera_path = DATA_DIR / "运营大区月KPI_202509同比.csv"
    opera_rows = read_csv(opera_path) if opera_path.is_file() else []
    apply_opera_descriptive(problems, opera_rows, parent_sale, parent_bf19, parent_weight)
    problems.append(
        Problem(
            scope="全国",
            trigger_id="T4",
            alert_level="目标缺失",
            cadence="月",
            message=(
                "店日均订购额的实际数用宽表 inbound_amt_store_day_avg，宽表没有 order_amt 列。"
                "订购额目标仅在少数运营大区有数；各管理区 O1 行已分写「有目标/无目标」，不占假达标。"
                "订购重量目标、销售重量目标都没有。全国不写汇总达标率。进货重量仍只看同比。"
            ),
            raw={
                "order_attain": "分管理区登记",
                "actual_column": "inbound_amt_store_day_avg",
                "target_table": "operation_center_region_target_mi",
                "weight_target": "没有",
            },
        )
    )
    problems.append(
        Problem(
            scope="全国",
            trigger_id="T2",
            alert_level="目标缺失",
            cadence="月",
            message=(
                "销售重量没有目标列。店日均销售额目标在经营中心目标表，"
                "和宽表销售额预算不是同一个数，本月不替换销售额达成的除数。"
            ),
            raw={
                "sales_weight_attain": "目标缺失",
                "sale_amt_target_table": "operation_center_region_target_mi",
                "replace_t2_denominator": False,
            },
        )
    )
    problems.append(
        Problem(
            scope="全国",
            trigger_id="T3",
            alert_level="待会员表",
            cadence="月",
            message="店日宽表没有新客、老客列。神策没有统一的新老客窗口，不能把 90 天写成已定口径。$is_first_day 是首日访问，不填充这一叶。",
            raw={"new_old_split": "待会员表", "not_buy_member_num": True},
            process_leaf="B1a",
        )
    )
    register_b2a_vacancy(problems, Problem, thresholds)
    problems.append(
        Problem(
            scope="全国",
            trigger_id="T10",
            alert_level="待会员表",
            cadence="月",
            message="购买频次不是源表字段。已有店级导出是会员订单数除以 distinct_id，带会员条件，没有限制线下。不把来客数写成频次，也不把频次写成至少来两天的占比。",
            raw={"frequency": "待会员表"},
            process_leaf="C1a",
        )
    )
    problems.append(
        Problem(
            scope="全国",
            trigger_id="T15",
            alert_level="口径未对齐",
            cadence="月",
            message=(
                "商品次7日复购率按 buy_again_member_num 除以 buy_member_num 现算。"
                "表是 product_center_business_sku_v3_info_di，粒度是区域×商品×日。"
                "repurchase_rate 现网经常是 0，不用这一列。"
                "各商品会员数不能相加当店或区域复购。"
                "店月「至少来两次」没有现成商分字段，本次不写。"
            ),
            raw={
                "table": "product_center_business_sku_v3_info_di",
                "grain": "区域×商品×日",
                "again_column": "buy_again_member_num",
                "repurchase_rate_comment": "现网经常为0，率要现算",
                "sep_2026_rows": 663352,
            },
            process_leaf="C1b",
        )
    )
    problems.append(
        Problem(
            scope="全国",
            trigger_id="T10",
            alert_level="待日销售表",
            cadence="月",
            message="购物篮的 SKU 要等日销售表和商品编码对齐，状态是待日销售表。重量占比没有会员购买重量，状态是待宽表。金额占比不升成公司入口。",
            raw={"sku": "待日销售表", "weight_share": "待宽表"},
            process_leaf="C1c",
        )
    )
    register_category_depth_vacancies(problems, Problem)
    if not p1_stats.get("m1b"):
        register_m1b_vacancy(problems, Problem, thresholds)
    p1_stats["c1b_area"] = register_c1b_area_projection(problems, Problem, EXCLUDE_REGIONS)

    # 日扫描：店日净利仍无日表。销售/来客/重量日提示受 delay_checked 约束。
    problems.append(
        Problem(
            scope="日扫描",
            trigger_id="T14",
            alert_level="待宽表",
            cadence="日",
            message="店日宽表没有净利，日扫不发净利提示。月度考核净利走月表 E1。假日仍带 event_label 发日提示。",
            raw={"calendar_note": "2026-09-24~26 中秋不发日提示；月度仍含"},
        )
    )
    run_store = LocalRunStore(RUN_DIR.parent)
    apply_daily_scan_v33(
        problems,
        Problem,
        data_dir=DATA_DIR,
        month_label=MONTH_LABEL,
        month_prev=MONTH_PREV,
        exclude_regions=EXCLUDE_REGIONS,
        thresholds=thresholds,
        fmt_yoy_cn=fmt_yoy_cn,
        yoy=yoy,
        fnum=fnum,
        store=run_store,
    )
    apply_geo_location(problems)
    seal_monthly_contributions(problems)
    project_object_sheets(problems)

    # 阈值建议（分布）
    threshold_suggestions = []
    cand = [-0.05, -0.08, -0.10, -0.15, -0.20]
    flagged_stores = []
    for s in store_rows:
        sy = yoy(fnum(s.get("saleDayAvgCurr") or s.get("sale_day_avg_curr")), fnum(s.get("saleDayAvgPrev") or s.get("sale_day_avg_prev")))
        if sy is not None:
            flagged_stores.append(sy)
    for c in cand:
        threshold_suggestions.append(
            {
                "key": "store_strong_hint_yoy",
                "candidate": c,
                "store_cnt_hit": sum(1 for v in flagged_stores if v <= c),
            }
        )

    nt_cfg = thresholds["new_store_traffic"]
    fb_ratio = float(nt_cfg.get("fallback_region_ratio", 0.85))
    new_unmet_rates = []
    for area in reg_by_area:
        ns = [s for s in store_rows if (s.get("manageArea") or s.get("manage_area")) == area and (s.get("cell") or "").startswith("新店")]
        if not ns:
            continue
        region_mean = store_region_bf19_mean(store_rows, area)
        for ratio in (0.90, 1.00):
            unmet = sum(
                1
                for s in ns
                if new_store_traffic_unmet(
                    s,
                    qualified_ratio=ratio,
                    region_mean=region_mean,
                    fallback_region_ratio=fb_ratio,
                )
                and store_qualified_bf19(s) is not None
            )
            be_cnt = sum(1 for s in ns if store_qualified_bf19(s) is not None)
            if be_cnt:
                new_unmet_rates.append(
                    {
                        "manage_area": area,
                        "path": "盈亏平衡",
                        "qualified_ratio": ratio,
                        "unmet_cnt": unmet,
                        "new_store_cnt": be_cnt,
                        "unmet_share": unmet / be_cnt,
                    }
                )
        fb_ns = [s for s in ns if store_qualified_bf19(s) is None]
        if fb_ns and region_mean is not None:
            unmet_fb = sum(
                1
                for s in fb_ns
                if store_bf19_curr(s) is not None and store_bf19_curr(s) < region_mean * fb_ratio
            )
            new_unmet_rates.append(
                {
                    "manage_area": area,
                    "path": "区域85",
                    "qualified_ratio": fb_ratio,
                    "unmet_cnt": unmet_fb,
                    "new_store_cnt": len(fb_ns),
                    "unmet_share": unmet_fb / len(fb_ns),
                }
            )

    ceo_upgrades, problems_ranked = pick_ceo_view(problems, thresholds)
    cfo_upgrades: list[Problem] = []
    if (thresholds.get("cfo_view") or {}).get("enabled"):
        cfo_upgrades = pick_cfo_contribution_fold(problems, thresholds)
    prob_dicts = [asdict(p) for p in problems]
    ceo_dicts = [asdict(p) for p in ceo_upgrades]
    cfo_dicts = [asdict(p) for p in cfo_upgrades]
    problem_trees = build_executive_trees(prob_dicts, ceo_dicts, cfo_dicts)
    problems_ranked = attach_tree_paths(problems_ranked, problem_trees)
    (RUN_DIR / "problem_trees.json").write_text(
        json.dumps(problem_trees, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (RUN_DIR / "problems_ranked.json").write_text(
        json.dumps(problems_ranked, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    ceo_share_small = [p for p in problems if p.alert_level == "份额小"]
    (RUN_DIR / "problems.json").write_text(
        json.dumps([asdict(p) for p in problems], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    ceo_member_slot = [
        p
        for p in problems
        if p.trigger_id in ("T10", "T15")
        and p.scope in ("全国", "全国不含港澳")
        and p.alert_level == "升级"
    ]

    fruit_thr_suggestions = []
    fruit_meta = DATA_DIR / "神策_水果6月_meta.json"
    if fruit_meta.is_file():
        try:
            fruit_thr_suggestions = json.loads(fruit_meta.read_text(encoding="utf-8")).get("threshold_suggestions") or []
        except json.JSONDecodeError:
            pass

    style_violations: list[dict] = []
    for p in problems:
        for v in lint_message(p.message):
            style_violations.append({"scope": p.scope, "trigger": p.trigger_id, "violation": v})

    scratch_wide = DATA_DIR / "_scratch" / "probe_v33_wide_maxdate.csv"
    wide_max = probe_wide_max_date(scratch_wide)

    report = {
        "month": MONTH_LABEL,
        "engine_version": "4.1-core",
        "style_violations": style_violations,
        "connections": {
            "bdapp": "ok",
            "wide_max_date": wide_max,
            "sensors": "member_monthly_via_cli",
            "sensors_store": "payOrderDetail_store_member_fruit",
            "hive": "不可用（bdapp 无 hive.* SELECT 权限）",
            "tables": [
                "operation_center_wide_store_di",
                "operation_center_dim_store_profile_di",
                "operation_center_store_loss_profit_oa_mi",
                "operation_resource_store_layer_list",
                "sensors:payOrderDetail",
            ],
            "member_store_id_match": probe_member_store_id_match(
                store_rows, DATA_DIR / "神策_会员店级月指标_202509同比.csv"
            ),
        },
        "field_map": {},
        "problems": [asdict(p) for p in problems],
        "supervisor_summary": dict(sup_summary),
        "threshold_suggestions": threshold_suggestions,
        "new_store_qualified": new_unmet_rates,
        "ceo_upgrades": ceo_dicts,
        "cfo_upgrades": cfo_dicts,
        "problems_ranked": problems_ranked,
        "problem_trees_schema": problem_trees.get("schema"),
        "ceo_share_small": [asdict(p) for p in ceo_share_small],
        "ceo_member_slot": [asdict(p) for p in ceo_member_slot],
        "untyped_share_national": untyped_share,
        "finance_metrics_rows": len(reg_fin),
        "fruit_active_sku_suggestions": fruit_thr_suggestions,
        "pending_data": {
            "member_purchase_weight": "待专题表；神策 payOrderDetail 无标准重量腿",
            "t14_daily_net_profit": "店日宽表无净利。月度 E1 用 OA loss_net_profit / loss_sale_days，月结 stl 不进 E1",
            "pretax_profit_ads": "阻断/T9 真源见 区域税前利润指标_对接_TEMPLATE.csv",
            "daily_scan_delay_checked": bool((thresholds.get("daily_scan") or {}).get("delay_checked")),
            "order_target": "目标缺失；必订中分类日表不是订购目标",
            "sales_weight_target": "目标缺失",
            "new_old_customer": "窗口天数和全店或分类都未拍板。不把90天写成口径",
            "repurchase": "商品次7日率=buy_again_member_num/buy_member_num。repurchase_rate 现网常0。店月至少来两次无商分字段",
            "promo_active_passive": "promo_organizer_name 设计有、现网空",
            "province_city_kpi": "省、市已按维表切开并店日加权。市名为空的店只进省",
            "ops_manager": "zone_supper_id 可按人归店",
            "franchisee_key": "暂用 contract_franchisee_id。业务仍要确认单指哪套编码",
            "store_key": "神策 shop_id、sap_shop_id 不直接等于 sp_store_id、sap_store_id，经维表互映，禁止店名 JOIN",
            "goods_number": "称重多为千克小数、标品多为整数，没有硬称重标识，不能全品类加总",
            "supervisor_pin": prior_note,
            "t5_tail_must_be_negative": "尾部只作定位标签，不进短清单",
            "shortlist_rule": "v4.0：CEO=全国月频贡献累计80%；v3回退=每区E1/E2/E3择一",
            "frozen_run": "runs/2026-10-14 不覆盖。本脚本写出 runs/2026-10-15",
        },
    }
    report["p1_stats"] = p1_stats
    report["checks"] = run_checks(report, style_violations, problems, thresholds)
    (RUN_DIR / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    render_markdown_lists(
        RUN_DIR,
        prob_dicts,
        ceo_dicts,
        cfo_upgrades=cfo_dicts,
        problem_trees=problem_trees,
    )
    print(json.dumps({"month": MONTH_LABEL, "checks": report["checks"], "ceo_upgrades": len(ceo_upgrades)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
