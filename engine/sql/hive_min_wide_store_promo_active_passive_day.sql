-- 问题引擎 · Hive 最小宽表草案 ② 店×日 促销主动/被动分解（M1/M1b 同窗【估算】）
-- 导出：starrocks-db MCP export_query → data/问题引擎/Hive_店日促销分解_202509.csv
-- 真源：hive.dal_full_link.dal_manage_full_link_store_dc_article_info_di
-- 可选增强：hive.dim.dim_store_promotion_info_da（p_source='shop' 等，品×活动粒度，本草案先店日汇总）
--
-- 口径说明（与产品拍板 / engine m1b_passive 对齐）：
--   · 主动促销额：SUM(shop_promotion_amt)
--   · 促销折扣额：SUM(promotion_discount_amt)；时段：SUM(hour_discount_amt)
--   · 19点前：bf19_promotion_amt、bf19_lp_sale_amt、bf19_sale_amt
--   · passive_promo_amt_est = GREATEST(0, promotion_discount_amt - shop_promotion_amt) 店日合计【估算】
--   · passive_rate_on_bf19_lp_est = passive / bf19_lp（lp>0）；禁止无分母外推
--   · 与宽表 promo_discount_rate 对账前须统一分母（原价 vs 销售额、19点前 vs 全天）

WITH store_dim AS (
    SELECT
        TRIM(p.sp_store_id) AS store_id
        ,TRIM(p.manage_area_name) AS manage_area
        ,CAST(p.inc_day AS DATE) AS dim_day
    FROM hive.dim.dim_store_profile p
    WHERE p.sp_level = '1'
      AND TRIM(p.manage_area_name) NOT IN ('香港区', '澳门区', '香港', '澳门')
      AND p.inc_day >= '2026-09-01'
      AND p.inc_day <= '2026-09-30'
),

fl AS (
    SELECT
        TRIM(f.store_id) AS store_id
        ,f.business_date
        ,COALESCE(f.shop_promotion_amt, 0) AS shop_promotion_amt
        ,COALESCE(f.promotion_discount_amt, 0) AS promotion_discount_amt
        ,COALESCE(f.hour_discount_amt, 0) AS hour_discount_amt
        ,COALESCE(f.member_discount_amt, 0) AS member_discount_amt
        ,COALESCE(f.discount_amt, 0) AS discount_amt
        ,COALESCE(f.bf19_promotion_amt, 0) AS bf19_promotion_amt
        ,COALESCE(f.bf19_promotion_discount_amt, 0) AS bf19_promotion_discount_amt
        ,COALESCE(f.bf19_sale_amt, 0) AS bf19_sale_amt
        ,COALESCE(f.bf19_lp_sale_amt, 0) AS bf19_lp_sale_amt
        ,COALESCE(f.total_sale_amt, 0) AS total_sale_amt
        ,COALESCE(f.lp_sale_amt, 0) AS lp_sale_amt
    FROM hive.dal_full_link.dal_manage_full_link_store_dc_article_info_di f
    WHERE f.business_date >= DATE '2026-09-01'
      AND f.business_date <= DATE '2026-09-30'
      AND COALESCE(f.business_flag, '1') = '1'
)

SELECT
    fl.business_date
    ,fl.store_id
    ,d.manage_area
    ,SUM(fl.shop_promotion_amt) AS active_shop_promotion_amt
    ,SUM(fl.promotion_discount_amt) AS promotion_discount_amt
    ,SUM(fl.hour_discount_amt) AS hour_discount_amt
    ,SUM(fl.member_discount_amt) AS member_discount_amt
    ,SUM(fl.discount_amt) AS discount_amt_total
    ,SUM(fl.bf19_promotion_amt) AS bf19_promotion_discount_amt
    ,SUM(fl.bf19_promotion_discount_amt) AS bf19_promotion_sale_discount_amt
    ,SUM(fl.bf19_sale_amt) AS bf19_sale_amt
    ,SUM(fl.bf19_lp_sale_amt) AS bf19_lp_sale_amt
    ,SUM(fl.total_sale_amt) AS total_sale_amt
    ,SUM(fl.lp_sale_amt) AS lp_sale_amt
    ,GREATEST(
        0,
        SUM(fl.promotion_discount_amt) - SUM(fl.shop_promotion_amt)
    ) AS passive_promo_amt_est
    ,CASE
        WHEN SUM(fl.bf19_lp_sale_amt) > 0
        THEN GREATEST(
            0,
            SUM(fl.promotion_discount_amt) - SUM(fl.shop_promotion_amt)
        ) / SUM(fl.bf19_lp_sale_amt)
    END AS passive_rate_on_bf19_lp_est
    ,CASE
        WHEN SUM(fl.bf19_lp_sale_amt) > 0
        THEN SUM(fl.shop_promotion_amt) / SUM(fl.bf19_lp_sale_amt)
    END AS active_rate_on_bf19_lp_est
    ,CASE
        WHEN SUM(fl.bf19_lp_sale_amt) > 0
        THEN SUM(fl.promotion_discount_amt) / SUM(fl.bf19_lp_sale_amt)
    END AS promo_discount_rate_on_bf19_lp_est
    ,CASE
        WHEN SUM(fl.lp_sale_amt) > 0
        THEN SUM(fl.hour_discount_amt) / SUM(fl.lp_sale_amt)
    END AS hour_discount_rate_on_lp_est
FROM fl
INNER JOIN store_dim d
    ON fl.store_id = d.store_id
   AND fl.business_date = d.dim_day
GROUP BY
    fl.business_date
    ,fl.store_id
    ,d.manage_area
ORDER BY
    fl.business_date
    ,d.manage_area
    ,fl.store_id
