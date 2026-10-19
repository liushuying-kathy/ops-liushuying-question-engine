"""统一重要性排序（v4.0）：全国贡献累计切片，与角色投影解耦。"""
from __future__ import annotations

from typing import Any

from .ids import assign_problem_ids


def _weight(p: Any) -> float:
    raw = getattr(p, "raw", None) or {}
    if not isinstance(raw, dict):
        raw = {}
    c = getattr(p, "contribution", None) or raw.get("contribution")
    if isinstance(c, (int, float)) and c > 0:
        return float(c)
    gap = raw.get("contribution_gap_store_day")
    if isinstance(gap, (int, float)):
        return abs(float(gap))
    if isinstance(c, str) and c.replace(".", "", 1).isdigit():
        return float(c)
    lmdi = raw.get("lmdi")
    if isinstance(lmdi, dict):
        return sum(abs(float(v)) for v in lmdi.values() if v is not None)
    y = raw.get("yoy") or raw.get("sale_yoy") or raw.get("yoy_primary")
    base = raw.get("curr") or raw.get("sale_day_avg_curr") or raw.get("value") or 1.0
    try:
        yf = float(y) if y is not None else 0.0
        bf = float(base) if base is not None else 1.0
    except (TypeError, ValueError):
        return 0.0
    return abs(yf) * max(abs(bf), 1.0)


def pick_national_contribution_fold(
    problems: list,
    *,
    fold: float = 0.80,
    cadence: str = "月",
) -> list:
    """全国视角：按权重降序累加至 fold（默认 80%），与店长/区总同一批 problem 行。"""
    pool = []
    for p in problems:
        if getattr(p, "cadence", None) != cadence:
            continue
        if getattr(p, "blocked", False):
            continue
        lvl = getattr(p, "alert_level", "") or ""
        if lvl in ("待宽表", "待字段", "目标缺失", "描述"):
            continue
        w = _weight(p)
        if w <= 0:
            continue
        pool.append((w, p))
    if not pool:
        return []
    pool.sort(key=lambda x: x[0], reverse=True)
    total = sum(w for w, _ in pool)
    if total <= 0:
        return [p for _, p in pool]
    acc = 0.0
    out = []
    for w, p in pool:
        out.append(p)
        acc += w
        if acc / total >= fold:
            break
    return out


def rank_problems(problems: list, thresholds: dict | None = None) -> list[dict]:
    """全量月频可排序行 + 权重；供 problems_ranked.json 与 CEO 80% 切片。"""
    thresholds = thresholds or {}
    fold = float((thresholds.get("ceo_view") or {}).get("fold") or thresholds.get("contribution_fold") or 0.80)
    cadence = str((thresholds.get("ceo_view") or {}).get("cadence") or "月")
    pool: list[tuple[float, Any]] = []
    for p in problems:
        if getattr(p, "cadence", None) != cadence:
            continue
        if getattr(p, "blocked", False):
            continue
        lvl = getattr(p, "alert_level", "") or ""
        if lvl in ("待宽表", "待字段", "目标缺失", "描述"):
            continue
        if lvl in ("提示", "升级", "份额小") or "强提示" in lvl:
            w = _weight(p)
            if w > 0:
                pool.append((w, p))
    pool.sort(key=lambda x: x[0], reverse=True)
    total = sum(w for w, _ in pool)
    acc = 0.0
    out: list[dict] = []
    for w, p in pool:
        acc += w
        cum = acc / total if total > 0 else 1.0
        out.append(
            {
                "problem_id": getattr(p, "problem_id", "") or (getattr(p, "raw", None) or {}).get("problem_id"),
                "scope": getattr(p, "scope", ""),
                "object_type": getattr(p, "object_type", ""),
                "process_leaf": getattr(p, "process_leaf", ""),
                "trigger_id": getattr(p, "trigger_id", ""),
                "alert_level": getattr(p, "alert_level", ""),
                "weight": w,
                "cum_share": round(cum, 6),
                "in_ceo_fold": cum <= fold or len(out) == 1,
            }
        )
        if total > 0 and acc / total >= fold:
            break
    return out


def _is_cfo_candidate(p: Any) -> bool:
    eid = (getattr(p, "entry_id", None) or "").strip()
    if eid in ("E1", "E2", "E3"):
        return True
    leaf = (getattr(p, "process_leaf", None) or "").strip()
    return leaf in ("E2", "E3")


def pick_cfo_contribution_fold(
    problems: list,
    thresholds: dict | None = None,
) -> list:
    """CFO 视图：仅入口 E1/E2/E3（及 E2/E3 过程叶），全国 80% 切片。"""
    thresholds = thresholds or {}
    cv = thresholds.get("cfo_view") or {}
    fold = float(cv.get("fold") or (thresholds.get("ceo_view") or {}).get("fold") or 0.80)
    cadence = str(cv.get("cadence") or "月")
    pool: list[tuple[float, Any]] = []
    for p in problems:
        if getattr(p, "cadence", None) != cadence:
            continue
        if getattr(p, "blocked", False):
            continue
        if not _is_cfo_candidate(p):
            continue
        lvl = getattr(p, "alert_level", "") or ""
        if lvl in ("待宽表", "待字段", "目标缺失", "描述"):
            continue
        w = _weight(p)
        eid = (getattr(p, "entry_id", None) or "").strip()
        if eid == "E1":
            w *= float(cv.get("e1_weight_boost") or 1.25)
        elif eid == "E2":
            w *= float(cv.get("e2_weight_boost") or 1.1)
        elif eid == "E3":
            w *= float(cv.get("e3_weight_boost") or 1.05)
        if w <= 0:
            continue
        pool.append((w, p))
    if not pool:
        return []
    pool.sort(key=lambda x: x[0], reverse=True)
    total = sum(w for w, _ in pool)
    acc = 0.0
    out = []
    for w, p in pool:
        out.append(p)
        acc += w
        if total > 0 and acc / total >= fold:
            break
    return out


def attach_tree_paths(ranked: list[dict], problem_trees: dict | None) -> list[dict]:
    """B2-3：CEO 榜条在 problems_ranked 上挂 tree_path。"""
    if not problem_trees:
        return ranked
    by_id: dict[str, str] = {}
    for t in problem_trees.get("ceo") or []:
        pid = str(t.get("problem_id") or "")
        if not pid:
            continue
        by_id[pid] = f"{t.get('scope') or ''}/{t.get('primary_leaf') or ''}"
    for r in ranked:
        pid = str(r.get("problem_id") or "")
        if pid in by_id:
            r["tree_path"] = by_id[pid]
    return ranked


def finalize_ranking(problems: list, thresholds: dict) -> tuple[list[dict], list]:
    """annotate + problem_id + ranked meta；返回 (ranked_json, ceo_slice_problems)。"""
    assign_problem_ids(problems)
    ranked = rank_problems(problems, thresholds)
    by_id = {getattr(p, "problem_id", None): p for p in problems}
    ceo = []
    seen: set[str] = set()
    for r in ranked:
        if not r.get("in_ceo_fold"):
            continue
        pid = r.get("problem_id")
        if pid and pid not in seen and pid in by_id:
            ceo.append(by_id[pid])
            seen.add(pid)
    if not ceo:
        ceo = pick_national_contribution_fold(
            problems,
            fold=float((thresholds.get("ceo_view") or {}).get("fold") or 0.80),
            cadence=str((thresholds.get("ceo_view") or {}).get("cadence") or "月"),
        )
    return ranked, ceo
