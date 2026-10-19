-- 剔除新店（老店加盟+老店直营）区域月 KPI

WITH params AS (
    SELECT DATE '2025-09-01' AS y25_start, DATE '2025-09-30' AS y25_end
        ,DATE '2026-09-01' AS y26_start, DATE '2026-09-30' AS y26_end
        ,DATE '2026-09-30' AS dim_pt_26, DATE '2025-09-30' AS dim_pt_25
),
dim26 AS (
    SELECT TRIM(UPPER(CAST(d.sp_store_id AS STRING))) AS store_id
        ,CASE TRIM(d.manage_area_name) WHEN '粤西' THEN '粤西区' WHEN '粤东' THEN '粤东区' ELSE TRIM(d.manage_area_name) END AS manage_area
    FROM default_catalog.ads_business_analysis.operation_center_dim_store_profile_di d
    CROSS JOIN params p
    WHERE d.report_date = p.dim_pt_26 AND d.sp_level = '1' AND COALESCE(d.open_days, 0) > 90
      AND TRIM(d.manage_area_name) NOT IN ('香港','澳门','香港区','澳门区')
      AND TRIM(CAST(d.sp_type AS STRING)) IN ('10','20')
),
dim25 AS (
    SELECT TRIM(UPPER(CAST(d.sp_store_id AS STRING))) AS store_id
        ,CASE TRIM(d.manage_area_name) WHEN '粤西' THEN '粤西区' WHEN '粤东' THEN '粤东区' ELSE TRIM(d.manage_area_name) END AS manage_area
    FROM default_catalog.ads_business_analysis.operation_center_dim_store_profile_di d
    CROSS JOIN params p
    WHERE d.report_date = p.dim_pt_25 AND d.sp_level = '1' AND COALESCE(d.open_days, 0) > 90
      AND TRIM(d.manage_area_name) NOT IN ('香港','澳门','香港区','澳门区')
      AND TRIM(CAST(d.sp_type AS STRING)) IN ('10','20')
),
w26 AS (
    SELECT TRIM(UPPER(CAST(w.sp_store_id AS STRING))) AS store_id
        ,SUM(w.sale_amt_store_day_avg * w.store_business_day_cnt) AS sale_amt
        ,SUM(w.store_business_day_cnt) AS biz_days
    FROM default_catalog.ads_business_analysis.operation_center_wide_store_di w
    CROSS JOIN params p
    WHERE w.store_agg_dim = '门店' AND w.category_tier = '门店' AND w.category_name = '门店'
      AND COALESCE(w.store_business_day_cnt, 0) > 0
      AND w.report_date BETWEEN p.y26_start AND p.y26_end
    GROUP BY 1
),
w25 AS (
    SELECT TRIM(UPPER(CAST(w.sp_store_id AS STRING))) AS store_id
        ,SUM(w.sale_amt_store_day_avg * w.store_business_day_cnt) AS sale_amt
        ,SUM(w.store_business_day_cnt) AS biz_days
    FROM default_catalog.ads_business_analysis.operation_center_wide_store_di w
    CROSS JOIN params p
    WHERE w.store_agg_dim = '门店' AND w.category_tier = '门店' AND w.category_name = '门店'
      AND COALESCE(w.store_business_day_cnt, 0) > 0
      AND w.report_date BETWEEN p.y25_start AND p.y25_end
    GROUP BY 1
),
a26 AS (
    SELECT d.manage_area, SUM(w.sale_amt) AS sale_amt, SUM(w.biz_days) AS biz_days
    FROM dim26 d INNER JOIN w26 w ON d.store_id = w.store_id GROUP BY d.manage_area
),
a25 AS (
    SELECT d.manage_area, SUM(w.sale_amt) AS sale_amt, SUM(w.biz_days) AS biz_days
    FROM dim25 d INNER JOIN w25 w ON d.store_id = w.store_id GROUP BY d.manage_area
)
SELECT a26.manage_area
    ,ROUND(a26.sale_amt / NULLIF(a26.biz_days, 0), 4) AS sale_day_avg_curr
    ,ROUND(a25.sale_amt / NULLIF(a25.biz_days, 0), 4) AS sale_day_avg_prev
FROM a26
LEFT JOIN a25 ON a26.manage_area = a25.manage_area
UNION ALL
SELECT a25.manage_area
    ,NULL AS sale_day_avg_curr
    ,ROUND(a25.sale_amt / NULLIF(a25.biz_days, 0), 4) AS sale_day_avg_prev
FROM a25
LEFT JOIN a26 ON a26.manage_area = a25.manage_area
WHERE a26.manage_area IS NULL
ORDER BY 1
