"""空间三档索引（B1-13）：管理区 → 运营大区 / 省 / 市。"""
from __future__ import annotations

from typing import Any


def spatial_nodes_for_area(problems: list[dict], manage_area: str, limit: int = 12) -> list[dict]:
    provinces = {
        p.get("scope")
        for p in problems
        if p.get("cadence") == "月"
        and (p.get("region_level") or "") == "省"
        and (p.get("parent_scope") or "") == manage_area
    }
    out: list[dict] = []
    for p in problems:
        if p.get("cadence") != "月":
            continue
        rl = p.get("region_level") or ""
        if rl not in ("运营大区", "省", "市"):
            continue
        raw = p.get("raw") or {}
        ps = (p.get("parent_scope") or "").strip()
        ma = (raw.get("manage_area") or p.get("object_key") or "").strip()
        if rl in ("运营大区", "省") and ps == manage_area:
            ok = True
        elif rl == "市" and ma == manage_area:
            ok = ps in provinces or ps == manage_area or not ps
        else:
            ok = False
        if not ok:
            continue
        chain = raw.get("spatial_chain")
        if not chain:
            chain = [manage_area]
            if rl == "运营大区":
                chain.append(p.get("scope"))
            elif rl == "省":
                chain.extend([p.get("scope")])
            elif rl == "市":
                if ps and ps != manage_area:
                    chain.extend([ps, p.get("scope")])
                else:
                    chain.append(p.get("scope"))
        out.append(
            {
                "granularity": rl,
                "scope": p.get("scope"),
                "parent_scope": ps,
                "spatial_chain": chain,
                "message": p.get("message"),
                "problem_id": p.get("problem_id"),
            }
        )
    order = {"运营大区": 0, "省": 1, "市": 2}
    out.sort(key=lambda x: (order.get(x["granularity"], 9), str(x.get("scope") or "")))
    return out[:limit]
