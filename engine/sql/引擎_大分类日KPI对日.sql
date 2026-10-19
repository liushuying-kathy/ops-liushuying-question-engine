-- 问题引擎 · 管理区域×大分类 日 KPI（2025-09 / 2026-09，对日）
-- store_agg_dim=门店 & category_tier=大分类；按营业店日加权。
-- 两年店挂 2026-09-30 维表。

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
        ,w.report_date
        ,w.category_name
        ,CASE
            WHEN w.report_date BETWEEN p.y25_start AND p.y25_end THEN '2025-09'
            WHEN w.report_date BETWEEN p.y26_start AND p.y26_end THEN '2026-09'
        END AS ym
        ,w.bf19_sale_amt_store_day_avg
        ,w.bf19_cust_num_store_day_avg
        ,w.bf19_sales_weight_store_day_avg
        ,w.store_business_day_cnt
    FROM default_catalog.ads_business_analysis.operation_center_wide_store_di w
    CROSS JOIN params p
    INNER JOIN dim dm
        ON TRIM(UPPER(CAST(w.sp_store_id AS STRING))) = dm.store_id
    WHERE w.store_agg_dim = '门店'
      AND w.category_tier = '大分类'
      AND w.category_name IN ('蔬菜类', '猪肉类', '水果类', '水产类', '冷藏及加工类', '预制菜')
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
        ,report_date
        ,category_name
        ,ym
        ,SUM(bf19_sale_amt_store_day_avg * store_business_day_cnt) AS bf19_sale
        ,SUM(bf19_cust_num_store_day_avg * store_business_day_cnt) AS bf19_cust
        ,SUM(bf19_sales_weight_store_day_avg * store_business_day_cnt) AS bf19_wt
        ,SUM(store_business_day_cnt) AS biz_days
    FROM base
    WHERE ym IS NOT NULL
    GROUP BY manage_area, report_date, category_name, ym
)

SELECT
    manage_area
    ,CAST(report_date AS STRING) AS report_date
    ,category_name
    ,ym
    ,'2026-09-30' AS dim_snap
    ,ROUND(bf19_sale / NULLIF(biz_days, 0), 4) AS bf19_sale_day_avg
    ,ROUND(bf19_cust / NULLIF(biz_days, 0), 4) AS bf19_cust_day_avg
    ,ROUND(bf19_wt / NULLIF(biz_days, 0), 4) AS bf19_weight_day_avg
    ,ROUND(bf19_sale / NULLIF(bf19_wt, 0), 4) AS bf19_avg_price
    ,biz_days
FROM agg
ORDER BY manage_area, ym, report_date, category_name
