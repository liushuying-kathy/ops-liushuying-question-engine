"""B1-5 / B1-9：新老客与被动促销 — 空缺状态登记（不编造触发）。"""
from __future__ import annotations

from typing import Any


def register_b2a_vacancy(problems: list, Problem: Any, thresholds: dict) -> None:
    cfg = thresholds.get("b2a_new_old_customer") or {}
    if cfg.get("enabled"):
        return
    window = cfg.get("window_days")
    win_txt = f"窗口={window}天（近{window}天购≥2次=老客）" if window else "窗口待业务拍板"
    problems.append(
        Problem(
            scope="全国",
            trigger_id="T10",
            alert_level="待会员表",
            cadence="月",
            region_level="全国",
            message=(
                f"【B2a 新老客客单价·估算登记】{win_txt}；本期不升公司入口。"
                "神策 cohort 待 SQL 入批；不用全体客单价填充这一叶。"
            ),
            raw={
                "unit_price_by_cohort": "待拍板",
                "window_days": window,
                "vacancy": True,
            },
            process_leaf="B2a",
            parallel=True,
        )
    )


def register_c1b_area_projection(problems: list, Problem: Any, exclude_regions: set[str]) -> int:
    """B1-10：C1a 已触发的管理区挂 C1b 粒度说明（不汇总假复购率）。"""
    areas: set[str] = set()
    for p in problems:
        scope = getattr(p, "scope", None) or (p.get("scope") if isinstance(p, dict) else None)
        leaf = getattr(p, "process_leaf", None) or (p.get("process_leaf") if isinstance(p, dict) else None)
        cadence = getattr(p, "cadence", None) or (p.get("cadence") if isinstance(p, dict) else None)
        if leaf == "C1a" and cadence == "月" and scope and scope not in exclude_regions:
            areas.add(str(scope))
    n = 0
    for area in sorted(areas):
        problems.append(
            Problem(
                scope=area,
                trigger_id="T15",
                alert_level="口径未对齐",
                cadence="月",
                region_level="管理区",
                message=(
                    f"9月{area}会员频次已挂 C1a；C1b 商品次7日复购只在区域×商品×日可算，"
                    "本区不写汇总复购率。率=buy_again_member_num/buy_member_num，不加总。"
                ),
                raw={"c1b": "region_product_grain", "vacancy": True},
                process_leaf="C1b",
                parallel=True,
            )
        )
        n += 1
    return n


def register_m1b_vacancy(problems: list, Problem: Any, thresholds: dict) -> None:
    cfg = thresholds.get("m1b_passive") or {}
    status = str(cfg.get("status") or "待字段")
    problems.append(
        Problem(
            scope="全国",
            trigger_id="T13",
            alert_level=status,
            cadence="月",
            region_level="全国",
            message=(
                "【M1b 被动促销·估算】本期用宽表促销率与 M1a 主动额（shop_promotion_amt）"
                "同窗分解标【估算】；不依赖 Hive dim_store_promotion_info_da。"
                "算不出则保持空缺，禁止无分母硬轧差。"
            ),
            raw={
                "m1b": status,
                "vacancy": True,
                "active_source": "product_center_business_v3_info_di.shop_promotion_amt",
            },
            process_leaf="M1b",
            parallel=True,
        )
    )
