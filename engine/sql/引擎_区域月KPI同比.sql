-- 问题引擎 · 管理区域月 KPI（2025-09 / 2026-09）
-- 只从 store_agg_dim = '门店' 的店级行，按营业店日加权。不用宽表「管理区域」预汇总行。
-- 维表在 2025-09-30、2025-09-01、2025-08-31、2025-12-31 都没有 sp_level=1 的行，最早抽到的是 2026-08-31。
-- 因此两年的店都挂 2026-09-30 的管理区域。这不是「各用统计月末快照」，结果列 dimSnap 写明这一点。

WITH params AS (
    SELECT
        DATE '2025-09-01' AS y25_start
        ,DATE '2025-09-30' AS y25_end
        ,DATE '2026-09-01' AS y26_start
        ,DATE '2026-09-30' AS y26_end
),

dim AS (
    SELECT
        TRIM(UPPER(CAST(d.sp_store_id AS STRING))) AS store_id
        ,CASE TRIM(d.manage_area_name)
            WHEN '粤西' THEN '粤西区'
            WHEN '粤东' THEN '粤东区'
            ELSE TRIM(d.manage_area_name)
        END AS manage_area
    FROM default_catalog.ads_business_analysis.operation_center_dim_store_profile_di d
    CROSS JOIN params p
    WHERE d.report_date = p.y26_end
      AND d.sp_level = '1'
      AND TRIM(d.manage_area_name) NOT IN ('香港', '澳门', '香港区', '澳门区', '孵化项目')
      AND TRIM(COALESCE(d.sap_area_name, '')) NOT IN ('', '无人柜', 'X')
),

base AS (
    SELECT
        dm.manage_area
        ,CASE
            WHEN w.report_date BETWEEN p.y25_start AND p.y25_end THEN '2025-09'
            WHEN w.report_date BETWEEN p.y26_start AND p.y26_end THEN '2026-09'
        END AS ym
        ,w.sale_amt_store_day_avg
        ,w.bf19_cust_num_store_day_avg
        ,w.purchase_weight_store_day_avg
        ,w.sales_weight_store_day_avg
        ,w.article_profit_store_day_avg
        ,w.budget_sale_amt_store_day_avg
        ,w.bf19_cust_unit_price
        ,w.promo_discount_rate
        ,w.hour_discount_rate
        ,w.lp_sale_amt_store_day_avg
        ,w.store_business_day_cnt
    FROM default_catalog.ads_business_analysis.operation_center_wide_store_di w
    CROSS JOIN params p
    INNER JOIN dim dm
        ON TRIM(UPPER(CAST(w.sp_store_id AS STRING))) = dm.store_id
    WHERE w.store_agg_dim = '门店'
      AND w.category_tier = '门店'
      AND w.category_name = '门店'
      AND COALESCE(w.store_business_day_cnt, 0) > 0
      AND w.sp_store_id IS NOT NULL
      AND (
          w.report_date BETWEEN p.y25_start AND p.y25_end
          OR w.report_date BETWEEN p.y26_start AND p.y26_end
      )
),

agg AS (
    SELECT
        manage_area
        ,ym
        ,SUM(sale_amt_store_day_avg * store_business_day_cnt) AS sale_amt
        ,SUM(bf19_cust_num_store_day_avg * store_business_day_cnt) AS bf19_cust
        ,SUM(purchase_weight_store_day_avg * store_business_day_cnt) AS purchase_weight
        ,SUM(sales_weight_store_day_avg * store_business_day_cnt) AS sales_weight
        ,SUM(article_profit_store_day_avg * store_business_day_cnt) AS article_profit
        ,SUM(budget_sale_amt_store_day_avg * store_business_day_cnt) AS budget_sale
        ,SUM(bf19_cust_unit_price * bf19_cust_num_store_day_avg * store_business_day_cnt) AS bf19_price_num
        ,SUM(promo_discount_rate * lp_sale_amt_store_day_avg * store_business_day_cnt) AS promo_disc_w
        ,SUM(hour_discount_rate * lp_sale_amt_store_day_avg * store_business_day_cnt) AS hour_disc_w
        ,SUM(lp_sale_amt_store_day_avg * store_business_day_cnt) AS lp_sale_w
        ,SUM(store_business_day_cnt) AS biz_days
    FROM base
    WHERE ym IS NOT NULL
    GROUP BY manage_area, ym
)

SELECT
    manage_area
    ,ym
    ,'2026-09-30' AS dim_snap
    ,ROUND(sale_amt / NULLIF(biz_days, 0), 4) AS sale_day_avg
    ,ROUND(bf19_cust / NULLIF(biz_days, 0), 4) AS bf19_cust_day_avg
    ,ROUND(purchase_weight / NULLIF(biz_days, 0), 4) AS purchase_weight_day_avg
    ,ROUND(sales_weight / NULLIF(biz_days, 0), 4) AS sales_weight_day_avg
    ,ROUND(article_profit / NULLIF(biz_days, 0), 4) AS article_profit_day_avg
    ,ROUND(article_profit / NULLIF(sale_amt, 0), 6) AS article_profit_rate
    ,ROUND(sale_amt / NULLIF(budget_sale, 0), 4) AS sale_achievement
    ,ROUND(bf19_price_num / NULLIF(bf19_cust, 0), 4) AS bf19_unit_price
    ,ROUND(promo_disc_w / NULLIF(lp_sale_w, 0), 6) AS promo_discount_rate
    ,ROUND(hour_disc_w / NULLIF(lp_sale_w, 0), 6) AS hour_discount_rate
    ,biz_days
FROM agg
ORDER BY manage_area, ym
