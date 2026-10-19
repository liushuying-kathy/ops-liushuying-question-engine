"""B1-7：中/小分类、SKU 深度 — 无分区时登记空缺行（不编造触发）。"""
from __future__ import annotations

from typing import Any, Callable


def register_category_depth_vacancies(problems: list, Problem: Any) -> None:
    """全国登记三条空缺，供 Grader / 附录 C 对齐。"""
    rows = [
        (
            "CAT_MID",
            "T12",
            "统计月无分区",
            "店级中分类（宽表 category_tier=中分类）",
            (
                "商分 ADS 店级中分类宽表 2026-09 仍无分区（最新 2026-07-31）。"
                "Hive 店×中分类可走 dal_manage_full_link_store_dc_article_info_di（second_category，total_sale_amt）；"
                "神策 payOrderDetail.mid_category 脚本见 category_sensors_mid_sub_month_v33.py。"
                "店号须经维表互映；交叉验完成前不写业务中分类客单。"
            ),
            {
                "mid_v2_max": "2026-07-31",
                "mid_v2_202609_cnt": 0,
                "hive_fl_table": "dal_manage_full_link_store_dc_article_info_di",
                "sensors_field": "mid_category",
            },
        ),
        (
            "CAT_SUB",
            "T12",
            "统计月无分区",
            "店级小分类（宽表 category_tier=小分类）",
            (
                "商分 ADS 店级小分类宽表 2026-09 仍无分区（2026-07-17～07-22 短窗）。"
                "Hive 同表 third_category；神策 category（基础三级）。"
                "sql/问题引擎/hive_store_sub_category_month_202509.sql 待 MCP 落盘。"
            ),
            {
                "sub_min": "2026-07-17",
                "sub_max": "2026-07-22",
                "sub_202609_cnt": 0,
                "hive_fl_table": "dal_manage_full_link_store_dc_article_info_di",
                "sensors_field": "category",
            },
        ),
        (
            "CAT_SKU",
            "T10",
            "待日销售表",
            "SKU 日销售与商品编码",
            (
                "SKU 下钻要等店日销售表与商品编码对齐，状态是待日销售表。"
                "购物篮金额/重量占比已有 C1c 登记，不重复升成公司入口。"
            ),
            {"sku": "待日销售表", "table": "operation_center_store_daily"},
        ),
    ]
    for leaf, trig, alert, title, msg, raw in rows:
        problems.append(
            Problem(
                scope="全国",
                trigger_id=trig,
                alert_level=alert,
                cadence="月",
                region_level="全国",
                message=f"【{title}】{msg}",
                raw={**raw, "category_depth": leaf, "vacancy": True},
                process_leaf=leaf,
                parallel=True,
            )
        )
