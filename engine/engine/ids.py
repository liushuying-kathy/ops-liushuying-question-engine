"""全局 problem_id（v4.0-core）：跨角色投影同一行。"""
from __future__ import annotations

import hashlib


def make_problem_id(
    *,
    cadence: str,
    object_type: str,
    scope: str,
    trigger_id: str,
    process_leaf: str = "",
    entry_id: str = "",
    report_date: str = "",
) -> str:
    key = "|".join(
        [
            cadence or "",
            object_type or "manage_area",
            str(scope or ""),
            entry_id or "",
            process_leaf or "",
            trigger_id or "",
            report_date or "",
        ]
    )
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def assign_problem_ids(problems: list) -> None:
    for p in problems:
        raw = getattr(p, "raw", None) or {}
        if not isinstance(raw, dict):
            raw = {}
        rid = str(raw.get("report_date") or "")[:10]
        ot = getattr(p, "object_type", None) or "manage_area"
        if str(getattr(p, "alert_level", "")).startswith("店"):
            ot = "store"
        pid = make_problem_id(
            cadence=getattr(p, "cadence", "") or "月",
            object_type=ot,
            scope=str(getattr(p, "scope", "") or ""),
            trigger_id=getattr(p, "trigger_id", "") or "",
            process_leaf=getattr(p, "process_leaf", "") or "",
            entry_id=getattr(p, "entry_id", "") or "",
            report_date=rid,
        )
        p.problem_id = pid
        raw["problem_id"] = pid
        p.raw = raw
