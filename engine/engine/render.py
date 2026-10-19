"""问题句渲染与咨询级措辞 lint；对外 Markdown 遵循 self-explanation（先说明本页看什么，再列结论）。"""

from __future__ import annotations



import json

import re

from collections import Counter

from pathlib import Path

from typing import Any



BANNED = re.compile(

    r"(显著|明显|大幅|大量|很多|部分|可能|或许|大概|进行了|开展了|被认为|或有望|有望)"

)



_LEAF_METRIC = {

    "S1": "店日均销售额",

    "E2": "店日均补贴前毛利额",

    "E3": "补贴前毛利率",

    "B1": "19点前来客",

    "O2": "进货重量",

    "E1": "店日均净利",

    "B1a": "会员活跃",

    "M1a": "门店促销",

    "O1": "订购达标",

}



_SOURCE_TABLE = {

    "operation_center_wide_store_di": "门店经营宽表（按营业店日汇总）",

    "operation_center_store_loss_profit_oa_mi": "考核净利月表",

    "operation_center_dim_store_profile_di": "门店维表",

}





def lint_message(text: str) -> list[str]:

    violations: list[str] = []

    for m in BANNED.finditer(text):

        violations.append(f"禁用词:{m.group(0)}")

    return violations





def format_money(x: float | None) -> str:

    if x is None:

        return "—"

    return f"{x:,.0f}"





def format_pct_ratio(y: float | None, digits: int = 1) -> str:

    if y is None:

        return "—"

    return f"{y * 100:.{digits}f}%"





def _month_cn(ym: str) -> str:

    ym = (ym or "").strip()

    m = re.match(r"^(\d{4})-(\d{2})$", ym)

    if not m:

        return ym or "统计月"

    return f"{m.group(1)}年{int(m.group(2))}月"





def _metric_type(p: dict) -> str:

    leaf = (p.get("process_leaf") or "").strip()

    if leaf in _LEAF_METRIC:

        return _LEAF_METRIC[leaf]

    eid = (p.get("entry_id") or "").strip()
    if eid == "E2":
        return "店日均补贴前毛利额"
    if eid == "E3":
        return "补贴前毛利率"
    if eid == "E1":
        return "店日均净利"

    msg = p.get("message") or ""

    if "会员人均消费" in msg or leaf == "B1a":
        return "会员人均消费"

    if "销售" in msg and "19点前" not in msg:

        return "店日均销售额"

    if "毛利额" in msg:

        return "店日均补贴前毛利额"

    if "毛利率" in msg:

        return "补贴前毛利率"

    if "来客" in msg:

        return "19点前来客"

    if "进货重量" in msg:

        return "进货重量"

    return "经营指标"





def _impact_scope(p: dict) -> str:

    scope = str(p.get("scope") or "")

    rl = p.get("region_level") or ""

    ot = p.get("object_type") or ""

    if scope in ("全国", "全国不含港澳"):

        return "全国"

    if ot == "store" or rl == "店" or str(p.get("alert_level", "")).startswith("店"):

        return "单店"

    if scope and "区" in scope and rl == "管理区":

        return "管理区域"

    if ot == "supervisor":

        return "督导名下汇总"

    return "管理区域"





def _confidence(p: dict) -> str:

    msg = p.get("message") or ""

    if "【估算】" in msg or p.get("entry_id") == "E1":

        return "估算"

    rel = (p.get("reliability") or "").strip()

    if rel == "确认" or "【确认】" in msg:

        return "已核对"

    if "待宽表" in (p.get("alert_level") or "") or "待字段" in (p.get("alert_level") or ""):

        return "待补数"

    if "【假设】" in msg:

        return "假设"

    return "已核对"





def _humanize_message(text: str) -> str:

    if not text:

        return ""

    out = text.strip()

    for tech, human in _SOURCE_TABLE.items():

        out = out.replace(tech, human)

    out = re.sub(

        r"来源：[^，。]+，统计截至\s*(\d{4}-\d{2}-\d{2})【([^】]+)】",

        r"数据截至\1，【\2】",

        out,

    )

    out = re.sub(

        r"来源：[^，。]+，统计截至\s*(\d{4}-\d{2})【([^】]+)】",

        r"数据截至\1，【\2】",

        out,

    )

    out = re.sub(
        r"在叶子\s+(\w+)\s+触及强提示",
        lambda m: f"在「{_LEAF_METRIC.get(m.group(1), m.group(1))}」上收到强跟店提示",
        out,
    )
    out = re.sub(r"督导编码\s+(\S+)", r"督导（工号 \1）", out)

    return out


def _pick_store_samples(problems: list[dict], ceo_upgrades: list[dict], limit: int = 20) -> list[dict]:
    ceo_areas = {p.get("scope") for p in ceo_upgrades if p.get("scope")}
    ceo_leaves = {(p.get("process_leaf") or "").strip() for p in ceo_upgrades if p.get("process_leaf")}
    area_rank = {p.get("scope"): i for i, p in enumerate(ceo_upgrades)}

    candidates: list[dict] = []
    for p in problems:
        if p.get("object_type") != "store":
            continue
        if not str(p.get("alert_level", "")).startswith("店"):
            continue
        raw = p.get("raw") or {}
        area = raw.get("manage_area") or p.get("parent_scope") or ""
        if area not in ceo_areas:
            continue
        leaf = (p.get("process_leaf") or "").strip()
        if ceo_leaves and leaf and leaf not in ceo_leaves:
            continue
        candidates.append(p)

    candidates.sort(
        key=lambda p: (
            area_rank.get((p.get("raw") or {}).get("manage_area"), 999),
            0 if "跟店提示" in (p.get("message") or "") else 1,
            p.get("scope") or "",
        )
    )
    if len(candidates) >= limit:
        return candidates[:limit]

    extra: list[dict] = []
    seen = {id(p) for p in candidates}
    for p in problems:
        if id(p) in seen:
            continue
        if p.get("object_type") != "store" or not str(p.get("alert_level", "")).startswith("店"):
            continue
        msg = p.get("message") or ""
        if "店日均销售" in msg or "毛利额" in msg:
            extra.append(p)
    return (candidates + extra)[:limit]


def _count_monthly_leaf(problems: list[dict], leaf: str, region_only: bool = True) -> int:

    n = 0

    for p in problems:

        if p.get("cadence") != "月":

            continue

        if region_only and p.get("region_level") != "管理区":

            continue

        if p.get("process_leaf") == leaf and p.get("alert_level") in (

            "提示",

            "升级",

            "份额小",

        ):

            n += 1

    return n





def _store_strong_by_leaf(problems: list[dict], leaf: str) -> int:

    return sum(

        1

        for p in problems

        if str(p.get("alert_level", "")).startswith("店")

        and p.get("process_leaf") == leaf

        and p.get("cadence") == "月"

    )





def build_attribution_blocks(problems: list[dict], ceo_upgrades: list[dict]) -> list[dict]:

    """从当次 problems 聚合归因与建议动作（不编造未算指标）。"""

    sale_ceo = sum(1 for p in ceo_upgrades if _metric_type(p) == "店日均销售额")

    e2_ceo = sum(1 for p in ceo_upgrades if _metric_type(p) == "店日均补贴前毛利额")

    b1_regions = _count_monthly_leaf(problems, "B1")

    s1_regions = _count_monthly_leaf(problems, "S1")

    s1_stores = _store_strong_by_leaf(problems, "S1")

    b1a_n = _count_monthly_leaf(problems, "B1a", region_only=True)



    blocks: list[dict] = []



    if sale_ceo or s1_regions:

        blocks.append(

            {

                "title": "店日均销售比去年同期偏弱",

                "evidence": (

                    f"公司重要问题榜里 {sale_ceo} 条和销售有关；"

                    f"另有 {s1_regions} 个管理区域在当月收到「店日均销售」提示；"

                    f"{s1_stores} 家门店在跟店清单里也是销售拖累。"

                ),

                "action": (

                    "本周各战区在榜内区域各抽 3 家店，把店日均销售与 19 点前来客、客单价放在同一张表里，"

                    "写清主要是客流还是单价；下周用同一口径看同比有没有收窄【收窄幅度待业务拍板】。"

                ),

            }

        )



    if e2_ceo or _count_monthly_leaf(problems, "E2"):

        e2_regions = _count_monthly_leaf(problems, "E2")

        blocks.append(

            {

                "title": "店日均补贴前毛利额比去年同期偏弱",

                "evidence": (

                    f"公司重要问题榜里 {e2_ceo} 条和毛利额有关；"

                    f"当月另有 {e2_regions} 个管理区域单独提示毛利额下滑。"

                ),

                "action": (

                    "商品与营运对榜内区域做大分类量价核对，10 月内各出一页「哪几个品类拖毛利」；"

                    "由管理区商品负责人和区总签字确认【是否进材料待拍板】。"

                ),

            }

        )



    if b1_regions:

        blocks.append(

            {

                "title": "19点前来客比去年同期偏弱",

                "evidence": f"当月有 {b1_regions} 个管理区域的 19 点前来客触发了提示（不含日度重复提醒）。",

                "action": (

                    "督导在这些区域各选 5 家老店，把 19 点前来客和店日均销售对照看；"

                    "连续 3 天仍提示来客问题时，先定是客流还是转化【目标待业务拍板】。"

                ),

            }

        )



    if b1a_n or any(p.get("process_leaf") == "B1a" for p in ceo_upgrades):

        blocks.append(

            {

                "title": "会员活跃结构需要单独看",

                "evidence": f"当月有 {b1a_n} 个管理区域登记了会员结构并行观察（含新增与留存）。",

                "action": (

                    "会员组按区域出一版会员销售同比；督导在下滑最明显的店里核对会员消费占比；"

                    "11 月用同一口径复盘【涉及估算的字段已在正文标注】。"

                ),

            }

        )



    if not blocks:

        blocks.append(

            {

                "title": "当月没有单一主因占绝对多数",

                "evidence": "公司重要问题榜条目较分散，尚不宜用一句话概括全国。",

                "action": "按榜从上往下逐条核对过程指标；现在复查榜第一条对应的拆解路径。",

            }

        )



    return blocks[:5]





def _self_explain_intro(

    role: str,

    data_month: str,

    present_note: str,

    ceo_count: int,

    problem_count: int,

) -> list[str]:

    month_label = _month_cn(data_month)

    lines = [f"# {month_label} · {role}\n"]

    lines.append("## 本页说明\n")

    if role == "公司重要问题榜":

        lines.append(

            f"- **回答什么**：全国哪些管理区域的问题，按「对全国经营影响」从大到小排；"

            f"下列 {ceo_count} 条合计约覆盖八成权重（与「先看大头」一致）。\n"

        )

        lines.append(f"- **数据月份**：{month_label}（店按营业店日加权同比）。\n")

        if present_note:

            lines.append(f"- **生成说明**：{present_note}\n")

        lines.append(

            f"- **怎么用**：榜内每一节是一条 **下发包**（一个主叶子 + 拆解/并行/品类/会员）；"

            f"先看「本月三件事」，再按榜逐区落实。区域单含同区完整行。\n"

        )

        lines.append(f"- **规模提示**：引擎当月共写出 {problem_count:,} 条提示行，本榜只保留影响最大的部分。\n\n")

    elif role == "区域单":

        lines.append(

            f"- **回答什么**：每个管理区域在 {month_label} 收到了哪些月度提示（含销售、毛利、来客等），按区域分组。\n"

        )

        lines.append("- **怎么用**：本区在榜上有名时，以榜条为准往下拆；本页是完整区域视角。\n\n")

    elif role == "督导单":

        lines.append(

            f"- **回答什么**：按督导聚合的跟店提示（{month_label}），便于巡店时对照。\n"

        )

        lines.append("- **怎么用**：前部「本月三件事」与公司榜同源；下列条目按引擎输出顺序截取前 200 条。\n\n")

    else:

        lines.append(

            f"- **回答什么**：与公司重要问题榜**同一组问题**下的门店样例（{month_label}），方便到店核对数字。\n"

        )

        lines.append("- **怎么用**：先读榜里对应区域，再到店核对经营数据；本页最多展示 20 家。\n\n")

    return lines





def build_exec_and_attribution(

    problems: list[dict],

    ceo_upgrades: list[dict],

    data_month: str = "",

    present_note: str = "",

) -> list[str]:

    month_label = _month_cn(data_month)

    lines = _self_explain_intro(

        "公司重要问题榜",

        data_month,

        present_note,

        len(ceo_upgrades),

        len(problems),

    )

    lines.append("## 本月三件事（归因 + 建议动作）\n\n")

    for i, blk in enumerate(build_attribution_blocks(problems, ceo_upgrades), 1):

        lines.append(f"{i}）**{blk['title']}**\n")

        lines.append(f"- 依据：{blk['evidence']}\n")

        lines.append(f"- 建议动作：{blk['action']}\n\n")



    if ceo_upgrades:

        top = ceo_upgrades[0]

        scope = top.get("scope") or top.get("object_key") or ""

        msg = _humanize_message(top.get("message") or "")

        lines.append("## 先看谁\n\n")

        lines.append(f"榜首是 **{scope}**：{msg}\n\n")

        lines.append(f"现在复查：{_metric_type(top)}。\n\n")

    return lines





def _load_rank_index(run_dir: Path) -> dict[str, dict]:

    path = run_dir / "problems_ranked.json"

    if not path.is_file():

        return {}

    try:

        rows = json.loads(path.read_text(encoding="utf-8"))

    except (json.JSONDecodeError, OSError):

        return {}

    return {str(r.get("problem_id")): r for r in rows if r.get("problem_id")}





def _ceo_entry_lines(
    p: dict,
    rank: int,
    rank_meta: dict | None,
    problems: list[dict],
    tree: dict | None = None,
) -> list[str]:
    from .render_roles import _tree_sections_md
    from .issue_bundle import build_issue_bundle, render_bundle_markdown

    share_note = ""
    if rank_meta and rank_meta.get("cum_share") is not None:
        pct = float(rank_meta["cum_share"]) * 100
        share_note = f"（累计影响约占榜内 {pct:.1f}%）"
    if tree:
        return _tree_sections_md(tree, rank, share_note)
    bundle = build_issue_bundle(p, problems)
    return render_bundle_markdown(bundle, rank, share_note)





def render_markdown_lists(

    run_dir: Any,

    problems: list[dict],

    ceo_upgrades: list[dict],

    data_month: str = "",

    present_note: str = "",

    cfo_upgrades: list[dict] | None = None,

    problem_trees: dict | None = None,

) -> None:

    run_dir = Path(run_dir)

    run_label = run_dir.name

    if not present_note and run_label:

        present_note = f"呈现样张，目录日期 {run_label}，统计月见上文。"

    if not data_month:

        rep = run_dir / "report.json"

        if rep.is_file():

            try:

                data_month = json.loads(rep.read_text(encoding="utf-8")).get("month") or ""

            except (json.JSONDecodeError, OSError):

                data_month = ""

    if cfo_upgrades is None:
        rep = run_dir / "report.json"
        if rep.is_file():
            try:
                cfo_upgrades = json.loads(rep.read_text(encoding="utf-8")).get("cfo_upgrades") or []
            except (json.JSONDecodeError, OSError):
                cfo_upgrades = []
        else:
            cfo_upgrades = []
    if problem_trees is None:
        pt = run_dir / "problem_trees.json"
        if pt.is_file():
            try:
                problem_trees = json.loads(pt.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                problem_trees = {}
        else:
            problem_trees = {}
    ceo_tree_by_id = {t.get("problem_id"): t for t in (problem_trees.get("ceo") or [])}

    rank_index = _load_rank_index(run_dir)

    exec_lines = build_exec_and_attribution(

        problems, ceo_upgrades, data_month=data_month, present_note=present_note

    )



    lines_ceo = exec_lines + ["---\n\n# 榜序（影响从大到小）\n\n"]

    for i, p in enumerate(ceo_upgrades, 1):

        pid = p.get("problem_id") or (p.get("raw") or {}).get("problem_id") or ""

        lines_ceo.extend(
            _ceo_entry_lines(
                p, i, rank_index.get(str(pid)), problems, ceo_tree_by_id.get(str(pid))
            )
        )

    (run_dir / "问题清单_公司重要问题榜.md").write_text("".join(lines_ceo), encoding="utf-8")

    # 重复产物：短清单=重要榜别名；v2 写指针说明，避免双份同文误读为两套结论
    (run_dir / "问题清单_公司短清单.md").write_text(
        "# 说明：本文件为「公司重要问题榜」别名指针\n\n"
        "请阅读同目录 `问题清单_公司重要问题榜.md`。"
        "是否保留双文件名【待核】。\n",
        encoding="utf-8",
    )

    from .render_roles import (
        render_cfo_important_list,
        render_region_operating_packages,
        render_store_chain_sample,
        render_supervisor_task_list,
    )

    (run_dir / "问题清单_CFO重要问题榜.md").write_text(
        render_cfo_important_list(problems, cfo_upgrades, problem_trees, data_month, present_note),
        encoding="utf-8",
    )
    (run_dir / "问题清单_区域经营包.md").write_text(
        render_region_operating_packages(problems, ceo_upgrades, data_month),
        encoding="utf-8",
    )



    month_label = _month_cn(data_month)

    reg_intro = _self_explain_intro("区域单", data_month, "", len(ceo_upgrades), len(problems))

    reg_intro.append("## 本月三件事（与公司榜同源）\n\n")

    for i, blk in enumerate(build_attribution_blocks(problems, ceo_upgrades), 1):

        reg_intro.append(f"{i}）{blk['title']} — {blk['evidence']}\n")

    reg_intro.append("\n---\n\n# 分管理区域\n\n")



    by_area: dict[str, list[dict]] = {}

    for p in problems:

        if p.get("cadence") == "月" and p.get("region_level") == "管理区":

            by_area.setdefault(p.get("scope", ""), []).append(p)

    ceo_by_area = {p.get("scope"): p for p in ceo_upgrades if p.get("scope")}
    lines_reg = reg_intro

    for area, rows in sorted(by_area.items()):

        lines_reg.append(f"## {area}\n\n")
        if area in ceo_by_area:
            from .issue_bundle import build_issue_bundle

            b = build_issue_bundle(ceo_by_area[area], problems)
            lines_reg.append("### 本区下发包（与公司榜同源）\n\n")
            lines_reg.append(f"**结论** {b['headline']}\n\n")
            if b["decompose"]:
                lines_reg.append("**拆解** " + "；".join(b["decompose"][:3]) + "\n\n")
            if b["category"]:
                lines_reg.append("**大分类** " + b["category"][0] + "\n\n")

        for r in rows[:30]:

            lines_reg.append(f"- {_humanize_message(r.get('message', ''))}\n")

        lines_reg.append("\n")

    (run_dir / "问题清单_区域单.md").write_text("".join(lines_reg), encoding="utf-8")



    (run_dir / "问题清单_督导单.md").write_text(
        render_supervisor_task_list(problems, ceo_upgrades, data_month),
        encoding="utf-8",
    )
    (run_dir / "问题清单_督导任务单.md").write_text(
        "# 说明：本文件为「督导单」别名指针\n\n"
        "请阅读同目录 `问题清单_督导单.md`。是否保留双文件名【待核】。\n",
        encoding="utf-8",
    )

    (run_dir / "问题清单_店长单_样张.md").write_text(
        render_store_chain_sample(problems, ceo_upgrades, data_month, limit=20),
        encoding="utf-8",
    )

    from .render_daily import write_daily_dispatch_sample

    write_daily_dispatch_sample(
        run_dir,
        problems,
        data_month=data_month,
        present_note=f"跑批目录 {run_label}；日样张日期由 DISPATCH_DAY 或当月主行最多的一天自动选取。",
    )


