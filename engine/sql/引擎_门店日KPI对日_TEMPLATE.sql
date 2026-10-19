-- 问题引擎 · 门店日 KPI（2025-09 / 2026-09，对日）· 按管理区分片取数
-- 占位 {{MANAGE_AREA}} 由 fetch.merge_store_daily_kpi 替换；合并为 data/问题引擎/门店日KPI_202509对日.csv

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
        ,CASE TRIM(CAST(d.sp_type AS STRING)) WHEN '10' THEN '直营' WHEN '20' THEN '加盟' ELSE NULL END AS store_type
        ,d.open_days
    FROM default_catalog.ads_business_analysis.operation_center_dim_store_profile_di d
    CROSS JOIN params p
    WHERE d.report_date = p.y26_end
      AND d.sp_level = '1'
      AND TRIM(d.manage_area_name) NOT IN ('香港', '澳门', '香港区', '澳门区', '孵化项目')
      AND TRIM(COALESCE(d.sap_area_name, '')) NOT IN ('', '无人柜', 'X')
      AND CASE TRIM(d.manage_area_name)
            WHEN '粤西' THEN '粤西区'
            WHEN '粤东' THEN '粤东区'
            ELSE TRIM(d.manage_area_name)
        END = '{{MANAGE_AREA}}'
),

base AS (
    SELECT
        dm.store_id
        ,dm.manage_area
        ,CASE
            WHEN dm.store_type IS NULL OR dm.open_days IS NULL THEN '未分型'
            WHEN dm.open_days <= 90 THEN CONCAT('新店·', dm.store_type)
            ELSE CONCAT('老店·', dm.store_type)
        END AS cell
        ,w.report_date
        ,CASE
            WHEN w.report_date BETWEEN p.y25_start AND p.y25_end THEN '2025-09'
            WHEN w.report_date BETWEEN p.y26_start AND p.y26_end THEN '2026-09'
        END AS ym
        ,w.sale_amt_store_day_avg
        ,w.bf19_cust_num_store_day_avg
        ,w.purchase_weight_store_day_avg
        ,w.article_profit_store_day_avg
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
)

SELECT
    store_id AS storeId
    ,manage_area AS manageArea
    ,cell
    ,CAST(report_date AS STRING) AS reportDate
    ,ym
    ,ROUND(sale_amt_store_day_avg, 4) AS saleDayAvg
    ,ROUND(bf19_cust_num_store_day_avg, 4) AS bf19CustDayAvg
    ,ROUND(article_profit_store_day_avg, 4) AS articleProfitDayAvg
    ,ROUND(purchase_weight_store_day_avg, 4) AS purchaseWeightDayAvg
FROM base
WHERE ym IS NOT NULL
ORDER BY store_id, ym, report_date
