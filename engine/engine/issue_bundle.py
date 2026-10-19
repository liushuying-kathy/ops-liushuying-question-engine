"""月频问题下发包（MECE）：一条榜条 = 一个主叶子 + 同区拆解/并行/品类/会员/定位。"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from .render import _LEAF_METRIC, _humanize_message, _metric_type


def _area_monthly(p: dict) -> bool:
    if p.get("cadence") != "月":
        return False
    if p.get("region_level") != "管理区":
        return False
    ot = p.get("object_type") or "manage_area"
    return ot in ("manage_area", "")


def index_area_monthly(problems: list[dict]) -> dict[str, list[dict]]:
    idx: dict[str, list[dict]] = defaultdict(list)
    for p in problems:
        if _area_monthly(p):
            idx[str(p.get("scope") or "")].append(p)
    return idx


def _yoy_cn(y: float | None) -> str:
    if y is None:
        return "—"
    sign = "上升" if y > 0 else "下降" if y < 0 else "持平"
    return f"{sign}{abs(y) * 100:.1f}%"


def _primary_leaf(p: dict) -> str:
    leaf = (p.get("process_leaf") or "").strip()
    if leaf:
        return leaf
    eid = (p.get("entry_id") or "").strip()
    if eid in ("E1", "E2", "E3"):
        return eid
    trig = p.get("trigger_id") or ""
    return {"T1": "S1", "T3": "B1", "T4": "O2", "T13": "E2"}.get(trig, "")


def _pick_sibling(siblings: list[dict], **want: Any) -> dict | None:
    for p in siblings:
        ok = True
        for k, v in want.items():
            if p.get(k) != v:
                ok = False
                break
        if ok:
            return p
    return None


def _lmdi_lines(raw: dict) -> list[str]:
    lmdi = raw.get("lmdi") or {}
    if not lmdi:
        return []
    lines: list[str] = []
    labels = {"S1": "店日均销售额", "E3": "补贴前毛利率"}
    for k, v in lmdi.items():
        lab = labels.get(k, k)
        lines.append(f"{lab}对毛利额变化的贡献约 {v:,.0f} 元/店日（LMDI，与额同量纲）。")
    return lines


def _weakest_cell_line(problems: list[dict], scope: str) -> str | None:
    """B1-12：同区四格中销售同比最弱一格，进下发包定位节。"""
    cells: list[tuple[float, dict]] = []
    for p in problems:
        if p.get("cadence") != "月" or p.get("region_level") != "店型":
            continue
        if (p.get("parent_scope") or "") != scope:
            continue
        raw = p.get("raw") or {}
        y = raw.get("sale_yoy")
        if y is None:
            continue
        try:
            cells.append((float(y), p))
        except (TypeError, ValueError):
            continue
    if not cells:
        return None
    cells.sort(key=lambda x: x[0])
    p = cells[0][1]
    cell = (p.get("raw") or {}).get("cell") or ""
    msg = _humanize_message(p.get("message") or "")
    return f"店型四格最弱·{cell}：{msg}" if cell else f"店型四格最弱：{msg}"


def _top_categories(siblings: list[dict], limit: int | None = None) -> list[dict]:
    """有数大分类全列（按贡献降序）；limit=None 表示不截断。"""
    cats = [p for p in siblings if p.get("trigger_id") == "T12"]
    def key(p: dict) -> float:
        raw = p.get("raw") or {}
        try:
            return float(raw.get("decline_share") or raw.get("category_sale_share") or 0)
        except (TypeError, ValueError):
            return 0.0
    ordered = sorted(cats, key=key, reverse=True)
    if limit is None:
        return ordered
    return ordered[:limit]


def build_issue_bundle(primary: dict, problems: list[dict]) -> dict[str, Any]:
    """组装单条榜对应的下发包（不编造未成立叶子）。"""
    scope = str(primary.get("scope") or primary.get("object_key") or "")
    idx = index_area_monthly(problems)
    siblings = idx.get(scope, [])
    leaf = _primary_leaf(primary)
    raw = primary.get("raw") or {}

    bundle: dict[str, Any] = {
        "scope": scope,
        "primary_leaf": leaf,
        "headline": _humanize_message(primary.get("message") or ""),
        "decompose": [],
        "parallel": [],
        "category": [],
        "member": [],
        "positioning": [],
        "tomorrow": _metric_type(primary),
    }

    if leaf in ("S1", ""):
        if not leaf:
            leaf = "S1"
        t3 = _pick_sibling(siblings, trigger_id="T3", alert_level="提示")
        if t3:
            bundle["decompose"].append(
                f"19点前来客：{_humanize_message(t3.get('message') or '')}（拆解路径·来客，不写成因果）。"
            )
        else:
            by = raw.get("bf19_yoy")
            py = raw.get("bf19_price_yoy")
            if by is not None:
                bundle["decompose"].append(
                    f"19点前来客同比{_yoy_cn(by)}（来自区域月表，未单独触发全区来客提示时仍作拆解事实）。"
                )
            if py is not None:
                bundle["decompose"].append(f"19点前客单价同比{_yoy_cn(py)}（拆解路径·客单价）。")
            wy = raw.get("weight_yoy")
            if wy is not None:
                bundle["parallel"].append(
                    f"进货重量同比{_yoy_cn(wy)}（并行观察·进货重量，不并进店日均销售额主路径）。"
                )
            if not bundle["decompose"]:
                bundle["decompose"].append(
                    "本月全区19点前来客未达「同比为负且弱于对照」的独立提示；"
                    "请用区域月表核对来客与19点前客单价，不把未成立叶子写成原因。"
                )

        for p in siblings:
            if p.get("problem_id") == primary.get("problem_id"):
                continue
            pl = (p.get("process_leaf") or "").strip()
            if p.get("parallel") or pl in ("S2", "M1", "M2", "M1a", "M1b"):
                bundle["parallel"].append(_humanize_message(p.get("message") or ""))
            elif p.get("trigger_id") == "T1" and pl == "S2":
                bundle["parallel"].append(_humanize_message(p.get("message") or ""))

        for p in _top_categories(siblings):
            bundle["category"].append(_humanize_message(p.get("message") or ""))

        for p in siblings:
            if (p.get("process_leaf") or "") == "B1a":
                bundle["member"].append(_humanize_message(p.get("message") or ""))
        for p in siblings:
            if p.get("trigger_id") in ("T10", "T15") and p.get("alert_level") in ("提示", "升级"):
                msg = _humanize_message(p.get("message") or "")
                if msg and any(k in msg for k in ("会员", "人均", "频次", "未消费", "客单价")):
                    bundle["member"].append(msg)
        b2_msgs = []
        for p in siblings:
            pl = (p.get("process_leaf") or "").strip()
            if pl in ("B2", "B2b") or (
                "客单价" in (p.get("message") or "") and p.get("cadence") == "月"
            ):
                b2_msgs.append(_humanize_message(p.get("message") or ""))
        if not b2_msgs and raw.get("bf19_price_yoy") is not None:
            b2_msgs.append(
                f"19点前客单价同比{_yoy_cn(raw.get('bf19_price_yoy'))}（消费者/会员可见·客单价）。"
            )
        for m in b2_msgs[:3]:
            if m and m not in bundle["member"]:
                bundle["member"].append(m)
        if not any("客件数" in (x or "") for x in bundle["member"]):
            bundle["member"].append(
                "客件数：【旁路/待核】（件单价×客件数字段未解冻，节点占位，不写业务数）。"
            )

        for p in siblings:
            if p.get("trigger_id") == "T5" or "店型" in (p.get("message") or ""):
                bundle["positioning"].append(_humanize_message(p.get("message") or ""))
        weakest = _weakest_cell_line(problems, scope)
        if weakest:
            bundle["positioning"].insert(0, weakest)

    elif leaf in ("E2", "E3") or (primary.get("entry_id") or "") in ("E2", "E3"):
        bundle["decompose"].extend(_lmdi_lines(raw))
        e3 = _pick_sibling(siblings, entry_id="E3", alert_level="提示")
        if e3 and primary.get("entry_id") != "E3":
            bundle["decompose"].append(_humanize_message(e3.get("message") or ""))
        s1 = _pick_sibling(siblings, process_leaf="S1", alert_level="提示")
        if s1:
            bundle["parallel"].append(
                f"店日均销售：{_humanize_message(s1.get('message') or '')}（与毛利额并行观察，不合并成一条原因）。"
            )
        for p in _top_categories(siblings):
            bundle["category"].append(_humanize_message(p.get("message") or ""))
        for p in siblings:
            if (p.get("process_leaf") or "") == "B1a":
                bundle["member"].append(_humanize_message(p.get("message") or ""))
        for p in siblings:
            if p.get("trigger_id") in ("T10", "T15") and p.get("alert_level") in ("提示", "升级"):
                msg = _humanize_message(p.get("message") or "")
                if msg and any(k in msg for k in ("会员", "人均", "频次", "未消费", "客单价")) and msg not in bundle["member"]:
                    bundle["member"].append(msg)
        for p in siblings:
            pl = (p.get("process_leaf") or "").strip()
            if pl in ("B2", "B2b") or "客单价" in (p.get("message") or ""):
                msg = _humanize_message(p.get("message") or "")
                if msg and msg not in bundle["member"]:
                    bundle["member"].append(msg)
        if not any("客件数" in (x or "") for x in bundle["member"]):
            bundle["member"].append(
                "客件数：【旁路/待核】（件单价×客件数字段未解冻，节点占位，不写业务数）。"
            )
        weakest = _weakest_cell_line(problems, scope)
        if weakest:
            bundle["positioning"].insert(0, weakest)

    else:
        for p in _top_categories(siblings):
            bundle["category"].append(_humanize_message(p.get("message") or ""))

    bundle["decompose"] = bundle["decompose"][:8]
    bundle["parallel"] = bundle["parallel"][:6]
    bundle["category"] = bundle["category"][:20]
    bundle["member"] = bundle["member"][:8]
    bundle["positioning"] = bundle["positioning"][:4]
    return bundle


def render_bundle_markdown(bundle: dict[str, Any], rank: int, share_note: str = "") -> list[str]:
    scope = bundle["scope"]
    metric = bundle["tomorrow"]
    lines = [f"## {rank}. {scope} · {metric}{share_note}\n\n"]
    lines.append("### 结论\n\n")
    lines.append(f"{bundle['headline']}\n\n")

    if bundle["decompose"]:
        lines.append("### 恒等拆解\n\n")
        for item in bundle["decompose"]:
            lines.append(f"- {item}\n")
        lines.append("\n")

    if bundle["parallel"]:
        lines.append("### 并行观察（不并进主叶子）\n\n")
        for item in bundle["parallel"]:
            lines.append(f"- {item}\n")
        lines.append("\n")

    if bundle["category"]:
        lines.append("### 商品分支（大分类有数全列）\n\n")
        for item in bundle["category"]:
            lines.append(f"- {item}\n")
        lines.append("\n")

    if bundle["member"]:
        lines.append("### 消费者与会员分支\n\n")
        for item in bundle["member"]:
            lines.append(f"- {item}\n")
        lines.append("\n")

    if bundle["positioning"]:
        lines.append("### 店型定位（不占榜条名额）\n\n")
        for item in bundle["positioning"]:
            lines.append(f"- {item}\n")
        lines.append("\n")

    lines.append(
        f"现在复查：沿「{metric}」核对区域月表与品类加权；"
        f"基准见正文对照口径；品类带商品分支一句；消费者带会员/客单价一句。\n\n"
    )
    return lines


def index_daily_region(problems: list[dict]) -> tuple[dict[tuple[str, str], dict], dict[tuple[str, str], list[dict]]]:
    """(area, day) -> 日下发主行；同键 -> 当日全部区域日行。"""
    highlights: dict[tuple[str, str], dict] = {}
    by_key: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for p in problems:
        if p.get("cadence") != "日" or p.get("region_level") != "管理区":
            continue
        raw = p.get("raw") or {}
        day = str(raw.get("report_date") or "")[:10]
        area = str(p.get("scope") or "")
        if not day or not area:
            continue
        by_key[(area, day)].append(p)
        if raw.get("daily_highlight"):
            highlights[(area, day)] = p
    return highlights, by_key


def pick_dispatch_day(problems: list[dict], month_prefix: str = "2026-09") -> str:
    import os

    forced = os.environ.get("DISPATCH_DAY", "").strip()
    if forced:
        return forced[:10]
    counts: dict[str, int] = defaultdict(int)
    for p in problems:
        if p.get("cadence") != "日":
            continue
        raw = p.get("raw") or {}
        if not raw.get("daily_highlight"):
            continue
        day = str(raw.get("report_date") or "")[:10]
        if month_prefix and not day.startswith(month_prefix):
            continue
        counts[day] += 1
    if not counts:
        return ""
    return max(counts.items(), key=lambda x: (x[1], x[0]))[0]


def build_daily_issue_bundle(
    primary: dict,
    day_rows: list[dict],
    monthly_problems: list[dict],
) -> dict[str, Any]:
    scope = str(primary.get("scope") or "")
    leaf = _primary_leaf(primary)
    raw = primary.get("raw") or {}
    bundle: dict[str, Any] = {
        "scope": scope,
        "primary_leaf": leaf,
        "headline": _humanize_message(primary.get("message") or ""),
        "decompose": [],
        "parallel": [],
        "category": [],
        "member": [],
        "positioning": [],
        "streak": int(raw.get("streak_days") or 0),
        "tomorrow": _metric_type(primary),
        "yoy": raw.get("yoy"),
    }
    for p in day_rows:
        if p is primary:
            continue
        pr = p.get("raw") or {}
        msg = _humanize_message(p.get("message") or "")
        pl = _primary_leaf(p)
        if pr.get("parallel") or "未进日下发" in (p.get("message") or ""):
            if leaf in ("S1", "E2", "E3") and pl in ("B1", "O2", "S1", "E3"):
                bundle["decompose"].append(f"{msg}（不并进主叶子）")
            else:
                bundle["parallel"].append(msg)
    cdf = raw.get("category_daily_factor")
    if isinstance(cdf, dict) and cdf.get("category"):
        fac = cdf.get("factor") or "19点前销售"
        y = cdf.get("yoy")
        ytxt = _yoy_cn(float(y)) if y is not None else "—"
        bundle["category"].insert(
            0,
            f"当日大分类单因子：{cdf['category']}{fac}{ytxt}（定比去年同星期几；焦点不替代全量类表）。",
        )
    monthly_siblings = index_area_monthly(monthly_problems).get(scope, [])
    for p in _top_categories(monthly_siblings):
        bundle["category"].append(
            "当月大分类对照：" + _humanize_message(p.get("message") or "")
        )
    for p in monthly_siblings:
        if (p.get("process_leaf") or "") == "B1a":
            bundle["member"].append("当月会员观察：" + _humanize_message(p.get("message") or ""))
            break
    # 择一只作主标题：保留结构化全链，不再因「另外下降」清空
    bundle["decompose"] = bundle["decompose"][:6]
    bundle["parallel"] = bundle["parallel"][:4]
    return bundle


def render_daily_bundle_markdown(bundle: dict[str, Any]) -> list[str]:
    scope = bundle["scope"]
    leaf = bundle.get("primary_leaf") or ""
    metric = _LEAF_METRIC.get(leaf) or bundle.get("tomorrow") or "经营指标"
    yoy = bundle.get("yoy")
    streak = int(bundle.get("streak") or 0)
    title = f"## {scope}：{metric}"
    if yoy is not None:
        title += f"同比{_yoy_cn(float(yoy))}"
    if streak > 1:
        title += f"，持续第 {streak} 天"
    lines = [title + "\n\n"]
    lines.append(f"{bundle['headline']}\n\n")
    if bundle["decompose"]:
        for item in bundle["decompose"]:
            lines.append(f"{item}\n\n")
    if bundle["parallel"]:
        lines.append("并行观察：\n\n")
        for item in bundle["parallel"]:
            lines.append(f"- {item}\n")
        lines.append("\n")
    if bundle["category"]:
        has_daily = any("当日大分类单因子" in (x or "") for x in bundle["category"])
        lines.append(
            "商品分支（当日焦点 + 当月有数全列）：\n\n"
            if has_daily
            else "商品分支（当月有数全列；日路径未择到类时）：\n\n"
        )
        for item in bundle["category"]:
            lines.append(f"- {item}\n")
        lines.append("\n")
    if bundle["member"]:
        for item in bundle["member"]:
            lines.append(f"- {item}\n")
        lines.append("\n")
    lines.append(
        f"现在复查：主标题为「{metric}」焦点；沿同日全链与商品分支核对日区域宽表，"
        f"基准=定比去年同星期几；另外下降项见正文。\n\n"
    )
    return lines
