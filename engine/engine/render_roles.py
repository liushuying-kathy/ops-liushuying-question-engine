"""全角色 L3：CEO / CFO / 区域经营 / 督导任务 / 店长链路（B4-*）。"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from .issue_bundle import build_issue_bundle, render_bundle_markdown, render_daily_bundle_markdown
from .problem_tree import problem_dict_to_tree, store_operating_tree
from .render import (
    _humanize_message,
    _metric_type,
    _month_cn,
    build_attribution_blocks,
    build_exec_and_attribution,
)


def _tree_sections_md(tree: dict[str, Any], rank: int = 0, share_note: str = "") -> list[str]:
    """由 problem_tree 节点渲染与下发包相同结构。"""
    bundle = {
        "scope": tree["scope"],
        "primary_leaf": tree["primary_leaf"],
        "headline": tree["headline"],
        "tomorrow": tree["tomorrow"],
        "decompose": tree["sections"].get("decompose") or [],
        "parallel": tree["sections"].get("parallel") or [],
        "category": tree["sections"].get("category") or [],
        "member": tree["sections"].get("member") or [],
        "positioning": tree["sections"].get("positioning") or [],
    }
    lines = render_bundle_markdown(bundle, rank, share_note)
    spatial = tree["sections"].get("spatial") or []
    cells = tree["sections"].get("store_cells") or []
    if spatial:
        idx = len(lines) - 1
        insert = ["### 空间下钻（大区 / 省市）\n\n"]
        for s in spatial:
            chain = s.get("spatial_chain") or []
            chain_txt = " → ".join(str(x) for x in chain if x) if len(chain) > 1 else ""
            prefix = f"（{chain_txt}）" if chain_txt else ""
            insert.append(
                f"- [{s.get('granularity')}] {s.get('scope')}{prefix}："
                f"{_humanize_message(s.get('message') or '')}\n"
            )
        insert.append("\n")
        lines[idx:idx] = insert
    if cells:
        idx = len(lines) - 1
        insert = ["### 店型四格（弱于本区整体优先）\n\n"]
        for c in cells:
            insert.append(f"- {c.get('cell')}：{_humanize_message(c.get('message') or '')}\n")
        insert.append("\n")
        lines[idx:idx] = insert
    return lines


def render_cfo_important_list(
    problems: list[dict],
    cfo_upgrades: list[dict],
    trees: dict[str, Any],
    data_month: str,
    present_note: str,
) -> str:
    month_label = _month_cn(data_month)
    lines = [f"# {month_label} · CFO 重要问题榜（净利/毛利入口 80%）\n\n"]
    lines.append("## 本页说明\n\n")
    lines.append(
        "- **读者**：CFO / 财务 BP；优先 **店日均净利【估算】、店日均补贴前毛利额、补贴前毛利率**。\n"
    )
    lines.append(f"- **数据月份**：{month_label}。\n")
    lines.append("- **与 CEO 榜关系**：CEO 榜看全国经营影响排序；本榜只看利润入口叶子，权重已上调净利/毛利额；已算 LMDI 分量直接呈现，不要求自行拆解。\n\n")
    tree_by_id = {t["problem_id"]: t for t in (trees.get("cfo") or [])}
    for i, p in enumerate(cfo_upgrades, 1):
        pid = p.get("problem_id") or (p.get("raw") or {}).get("problem_id")
        tree = tree_by_id.get(pid) or problem_dict_to_tree(p, problems)
        lines.extend(_tree_sections_md(tree, i, ""))
    return "".join(lines)


def render_region_operating_packages(
    problems: list[dict],
    ceo_upgrades: list[dict],
    data_month: str,
) -> str:
    month_label = _month_cn(data_month)
    lines = [f"# {month_label} · 区域经营包\n\n", "## 本页说明\n\n"]
    lines.append("- **读者**：区总 / 战区运营；每管理区域一节完整下发包（与 CEO 榜同源主行）。\n\n")
    for i, p in enumerate(ceo_upgrades, 1):
        tree = problem_dict_to_tree(p, problems)
        lines.extend(_tree_sections_md(tree, i, ""))
    return "".join(lines)


def render_supervisor_task_list(
    problems: list[dict],
    ceo_upgrades: list[dict],
    data_month: str,
    stores_per_sup: int = 20,
) -> str:
    month_label = _month_cn(data_month)
    ceo_areas = {p.get("scope") for p in ceo_upgrades if p.get("scope")}
    area_rank = {p.get("scope"): i for i, p in enumerate(ceo_upgrades)}
    area_problem_id = {
        p.get("scope"): (p.get("problem_id") or (p.get("raw") or {}).get("problem_id"))
        for p in ceo_upgrades
        if p.get("scope")
    }

    stores: list[dict] = []
    for p in problems:
        if not str(p.get("alert_level", "")).startswith("店"):
            continue
        raw = p.get("raw") or {}
        area = raw.get("manage_area") or p.get("parent_scope") or ""
        if area not in ceo_areas:
            continue
        stores.append(p)

    by_sup: dict[str, list[dict]] = defaultdict(list)
    for p in stores:
        sup = (p.get("supervisor_id") or (p.get("raw") or {}).get("zone_supper_id") or "").strip()
        if not sup:
            sup = "待督导归属"
        by_sup[sup].append(p)

    def store_sort_key(p: dict) -> tuple:
        raw = p.get("raw") or {}
        y = raw.get("sale_yoy")
        try:
            sy = float(y) if y is not None else 0.0
        except (TypeError, ValueError):
            sy = 0.0
        area = raw.get("manage_area") or ""
        return (area_rank.get(area, 999), sy)

    lines = [f"# {month_label} · 督导任务单\n\n", "## 本页说明\n\n"]
    lines.append(
        "- **读者**：督导；只列 **公司榜涉及管理区** 内、需跟店的门店（店·强提示/跟店线）。\n"
    )
    lines.append("- **怎么用**：按督导工号巡店；每店含问题类型与对照类型标签；「现在复查」与主叶子一致；详情见店长链路单。\n\n")
    lines.append("## 本月三件事（与公司榜同源）\n\n")
    for j, blk in enumerate(build_attribution_blocks(problems, ceo_upgrades), 1):
        lines.append(f"{j}）{blk['title']}\n")
    lines.append("\n---\n\n# 分督导\n\n")

    for sup in sorted(by_sup.keys()):
        rows = sorted(by_sup[sup], key=store_sort_key)[:stores_per_sup]
        if not rows:
            continue
        lines.append(f"## 督导（工号 {sup}）\n\n")
        agg = [p for p in problems if p.get("object_type") == "supervisor" and p.get("scope") == sup]
        if agg:
            lines.append(f"- 汇总：{_humanize_message(agg[0].get('message') or '')}\n\n")
        for p in rows:
            raw = p.get("raw") or {}
            area = raw.get("manage_area") or "—"
            sid = p.get("scope") or "—"
            metric = _metric_type(p)
            pid = p.get("problem_id") or raw.get("problem_id") or ""
            apid = area_problem_id.get(area) or ""
            # 问题类型（过程段中文）+ 对照类型
            leaf = (p.get("process_leaf") or "").strip()
            eid = (p.get("entry_id") or "").strip()
            type_cn = {
                "E1": "入口", "E2": "入口", "E3": "入口",
                "O1": "订购", "O2": "订购",
                "S1": "销售", "S2": "销售", "B1": "销售", "B2": "拆分",
                "M1": "促销", "M1a": "促销", "M1b": "促销", "M2": "促销",
                "B1a": "会员", "C1b": "消费者",
            }.get(leaf) or ("入口" if eid in ("E1", "E2", "E3") else "销售")
            msg0 = p.get("message") or ""
            raw0 = p.get("raw") or {}
            if "环比" in msg0:
                cmp_cn = "环比"
            elif "定比" in msg0 or raw0.get("compare_basis") == "364" or raw0.get("ref_same_date_yoy") is not None:
                cmp_cn = "定比_364（去年同星期几）" if ("定比" in msg0 or raw0.get("ref_same_date_yoy") is not None) else "同比"
            elif "同比" in msg0:
                cmp_cn = "同比"
            elif raw0.get("ref_wow_7d") is not None:
                cmp_cn = "7日对照（raw.ref_wow_7d 有值；是否称环比【待核】）"
            else:
                cmp_cn = "同比（本行无独立环比字段）"
            lines.append(f"### 店 {sid}（{area}）· {metric}\n\n")
            lines.append(f"- 问题类型：{type_cn}；对照类型：{cmp_cn}\n")
            if pid or apid:
                lines.append(f"- 店 problem_id：`{pid}`；榜区同源：`{apid}`\n\n")
            else:
                lines.append("\n")
            lines.append(f"{_humanize_message(p.get('message') or '')}\n\n")
            lines.append(f"现在复查：{metric}（类型={type_cn}，对照={cmp_cn}）。\n\n")
    return "".join(lines)


def render_store_chain_sample(
    problems: list[dict],
    ceo_upgrades: list[dict],
    data_month: str,
    limit: int = 20,
) -> str:
    month_label = _month_cn(data_month)
    ceo_areas = {p.get("scope") for p in ceo_upgrades if p.get("scope")}
    area_rank = {p.get("scope"): i for i, p in enumerate(ceo_upgrades)}

    candidates: list[dict] = []
    for p in problems:
        if p.get("object_type") != "store" or not str(p.get("alert_level", "")).startswith("店"):
            continue
        raw = p.get("raw") or {}
        if raw.get("manage_area") not in ceo_areas:
            continue
        candidates.append(p)
    candidates.sort(
        key=lambda p: (
            area_rank.get((p.get("raw") or {}).get("manage_area"), 999),
            0 if "跟店" in (p.get("message") or "") else 1,
            p.get("scope") or "",
        )
    )
    sample = candidates[:limit]

    lines = [f"# {month_label} · 店长经营链路单（样张）\n\n", "## 本页说明\n\n"]
    lines.append(
        "- **读者**：店长；与公司榜同区域的到店核对单。\n"
    )
    lines.append("- **结构**：订购 → 销售 → 促销 → 会员/消费者（同店月频行归类，缺则留空）。\n\n")

    for p in sample:
        raw = p.get("raw") or {}
        area = raw.get("manage_area") or ""
        tree = store_operating_tree(p, problems, area)
        sid = tree["store_id"]
        lines.append(f"## 店 {sid}（{area}）\n\n")
        lines.append(f"**跟店主提示**：{_humanize_message(tree.get('headline') or '')}\n\n")
        ch = tree.get("chain") or {}
        if ch.get("order"):
            lines.append("**订购**\n\n")
            for m in ch["order"]:
                lines.append(f"- {_humanize_message(m)}\n")
            lines.append("\n")
        if ch.get("sale"):
            lines.append("**销售与客流**\n\n")
            for m in ch["sale"]:
                lines.append(f"- {_humanize_message(m)}\n")
            lines.append("\n")
        if ch.get("promo"):
            lines.append("**促销**\n\n")
            for m in ch["promo"]:
                lines.append(f"- {_humanize_message(m)}\n")
            lines.append("\n")
        if ch.get("consumer"):
            lines.append("**消费者与会员**\n\n")
            for m in ch["consumer"]:
                lines.append(f"- {_humanize_message(m)}\n")
            lines.append("\n")
        lines.append(
            f"现在复查：沿订购→销售→促销→消费者链核对「{_metric_type(p)}」；"
            f"缺段见上方占位，不写未给出的业务数。\n\n"
        )
    return "".join(lines)
