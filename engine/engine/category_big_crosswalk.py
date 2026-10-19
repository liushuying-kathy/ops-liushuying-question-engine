"""大分类口径对照：神策 / 商分宽表 / Hive 统一到 canonical 与对账键。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_CFG_NAME = "category_big_crosswalk.yaml"
_ENGINE_ROOT = Path(__file__).resolve().parents[1]


def _config_path() -> Path:
    return _ENGINE_ROOT / "config" / _CFG_NAME


def load_crosswalk(path: Path | None = None) -> dict[str, Any]:
    p = path or _config_path()
    with p.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def map_sensors_big(raw: str, cfg: dict[str, Any] | None = None) -> str | None:
    cfg = cfg or load_crosswalk()
    key = (raw or "").strip()
    if not key:
        return None
    return (cfg.get("sensors_big_to_canonical") or {}).get(key, key)


def map_bdapp_big(raw: str, cfg: dict[str, Any] | None = None) -> str | None:
    cfg = cfg or load_crosswalk()
    key = (raw or "").strip()
    if not key:
        return None
    table = cfg.get("bdapp_big_to_canonical") or {}
    return table.get(key, key)


def recon_wide_key_from_sensors_canonical(canonical: str, cfg: dict[str, Any] | None = None) -> str | None:
    cfg = cfg or load_crosswalk()
    c = (canonical or "").strip()
    if not c:
        return None
    roll = (cfg.get("recon") or {}).get("sensors_canonical_to_wide_key") or {}
    return roll.get(c, c)


def _meat_amount_from_raw(area_raw: dict[str, float]) -> float:
    """同区若同时有「猪肉类/禽类」与「肉禽蛋类」，只计明细项，避免神策双轨重复。"""
    pork = area_raw.get("猪肉类", 0.0)
    bird = area_raw.get("禽类", 0.0)
    lump = area_raw.get("肉禽蛋类", 0.0)
    if pork > 0 or bird > 0:
        return pork + bird
    return lump + pork + bird


def aggregate_sensors_for_recon(
    rows: list[dict[str, Any]],
    *,
    area_key: str = "manage_area",
    cat_key: str = "big_category",
    amt_key: str = "paid_amt",
    cfg: dict[str, Any] | None = None,
) -> dict[tuple[str, str], float]:
    """区域×宽表对账键 → 神策金额合计。"""
    cfg = cfg or load_crosswalk()
    exclude = set((cfg.get("recon") or {}).get("exclude_manage_areas") or [])
    by_area_raw: dict[str, dict[str, float]] = {}
    for row in rows:
        area = (row.get(area_key) or "").strip()
        if area in exclude:
            continue
        raw_cat = str(row.get(cat_key) or "").strip()
        if not raw_cat:
            continue
        try:
            amt = float(row.get(amt_key) or 0)
        except (TypeError, ValueError):
            amt = 0.0
        bucket = by_area_raw.setdefault(area, {})
        bucket[raw_cat] = bucket.get(raw_cat, 0.0) + amt

    meat_keys = {"猪肉类", "禽类", "肉禽蛋类"}
    out: dict[tuple[str, str], float] = {}
    for area, raw_cats in by_area_raw.items():
        meat = _meat_amount_from_raw(raw_cats)
        pork_wkey = recon_wide_key_from_sensors_canonical("猪肉类", cfg)
        if pork_wkey and meat > 0:
            out[(area, pork_wkey)] = out.get((area, pork_wkey), 0.0) + meat
        for raw_cat, amt in raw_cats.items():
            if raw_cat in meat_keys:
                continue
            canon = map_sensors_big(raw_cat, cfg)
            if not canon:
                continue
            wkey = recon_wide_key_from_sensors_canonical(canon, cfg)
            if not wkey:
                continue
            out[(area, wkey)] = out.get((area, wkey), 0.0) + amt
    return out


def aggregate_wide_for_recon(
    rows: list[dict[str, Any]],
    *,
    month_label: str,
    area_key: str = "manageArea",
    cat_key: str = "categoryName",
    cfg: dict[str, Any] | None = None,
) -> dict[tuple[str, str], float]:
    cfg = cfg or load_crosswalk()
    exclude = set((cfg.get("recon") or {}).get("exclude_manage_areas") or [])
    out: dict[tuple[str, str], float] = {}
    for row in rows:
        if (row.get("ym") or "") != month_label:
            continue
        area = (row.get(area_key) or row.get("manage_area") or "").strip()
        if area in exclude:
            continue
        canon = map_bdapp_big(str(row.get(cat_key) or row.get("category_name") or ""), cfg)
        if not canon or canon == "全店":
            continue
        wkey = canon
        month_amt = _wide_month_amount(row, cfg)
        if month_amt is None or month_amt <= 0:
            continue
        out[(area, wkey)] = out.get((area, wkey), 0.0) + month_amt
    return out


def _wide_month_amount(row: dict[str, Any], cfg: dict[str, Any]) -> float | None:
    recon = cfg.get("recon") or {}
    primary = recon.get("wide_amount_field") or "saleAmt"
    for key in (primary, "saleAmt", "sale_amt"):
        v = row.get(key)
        if v is not None and str(v).strip() != "":
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    cur = row.get("bf19SaleDayAvg") or row.get("bf19_sale_day_avg") or row.get("saleDayAvg")
    days = row.get("bizDays") or row.get("biz_days")
    try:
        if cur is not None and days is not None:
            return float(cur) * float(days)
    except (TypeError, ValueError):
        pass
    return None


def crosswalk_rows_for_export(cfg: dict[str, Any] | None = None) -> list[dict[str, str]]:
    """导出对照表行（神策原名 → canonical → 对账键）。"""
    cfg = cfg or load_crosswalk()
    sens = cfg.get("sensors_big_to_canonical") or {}
    roll = (cfg.get("recon") or {}).get("sensors_canonical_to_wide_key") or {}
    rows: list[dict[str, str]] = []
    for raw, canon in sorted(sens.items(), key=lambda x: x[0]):
        if canon is None:
            rows.append(
                {
                    "sensors_big_category": raw,
                    "canonical_big": "",
                    "recon_wide_key": "",
                    "note": "对账排除",
                }
            )
            continue
        wkey = roll.get(canon, canon)
        note = "对账合并至猪肉类" if wkey != canon else ""
        rows.append(
            {
                "sensors_big_category": raw,
                "canonical_big": canon,
                "recon_wide_key": wkey,
                "note": note,
            }
        )
    return rows
