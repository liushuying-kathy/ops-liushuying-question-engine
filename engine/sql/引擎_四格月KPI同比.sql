-- 四格月 KPI v2：店级双月 inner join 后再聚合（修复 prev 列全空）

WITH params AS (
    SELECT DATE '2025-09-01' AS y25_start, DATE '2025-09-30' AS y25_end
        ,DATE '2026-09-01' AS y26_start, DATE '2026-09-30' AS y26_end
        ,DATE '2026-09-30' AS dim_pt
),
dim AS (
    SELECT TRIM(UPPER(CAST(d.sp_store_id AS STRING))) AS store_id
        ,CASE TRIM(d.manage_area_name)
            WHEN '粤西' THEN '粤西区'
            WHEN '粤东' THEN '粤东区'
            ELSE TRIM(d.manage_area_name)
        END AS manage_area
        ,CASE TRIM(CAST(d.sp_type AS STRING))
            WHEN '10' THEN '直营'
            WHEN '20' THEN '加盟'
            ELSE NULL
        END AS store_type
        ,d.open_days
    FROM default_catalog.ads_business_analysis.operation_center_dim_store_profile_di d
    CROSS JOIN params p
    WHERE d.report_date = p.dim_pt
      AND d.sp_level = '1'
      AND TRIM(d.manage_area_name) NOT IN ('香港','澳门','香港区','澳门区')
),
w26 AS (
    SELECT TRIM(UPPER(CAST(w.sp_store_id AS STRING))) AS store_id
        ,SUM(w.sale_amt_store_day_avg * w.store_business_day_cnt) AS sale_amt
        ,SUM(w.bf19_cust_num_store_day_avg * w.store_business_day_cnt) AS bf19_cust
        ,SUM(w.purchase_weight_store_day_avg * w.store_business_day_cnt) AS purchase_weight
        ,SUM(w.store_business_day_cnt) AS biz_days
    FROM default_catalog.ads_business_analysis.operation_center_wide_store_di w
    CROSS JOIN params p
    WHERE w.store_agg_dim = '门店'
      AND w.category_tier = '门店' AND w.category_name = '门店'
      AND COALESCE(w.store_business_day_cnt, 0) > 0
      AND w.report_date BETWEEN p.y26_start AND p.y26_end
    GROUP BY 1
),
w25 AS (
    SELECT TRIM(UPPER(CAST(w.sp_store_id AS STRING))) AS store_id
        ,SUM(w.sale_amt_store_day_avg * w.store_business_day_cnt) AS sale_amt
        ,SUM(w.bf19_cust_num_store_day_avg * w.store_business_day_cnt) AS bf19_cust
        ,SUM(w.purchase_weight_store_day_avg * w.store_business_day_cnt) AS purchase_weight
        ,SUM(w.store_business_day_cnt) AS biz_days
    FROM default_catalog.ads_business_analysis.operation_center_wide_store_di w
    CROSS JOIN params p
    WHERE w.store_agg_dim = '门店'
      AND w.category_tier = '门店' AND w.category_name = '门店'
      AND COALESCE(w.store_business_day_cnt, 0) > 0
      AND w.report_date BETWEEN p.y25_start AND p.y25_end
    GROUP BY 1
),
store_pair AS (
    SELECT
        d.manage_area
        ,CASE
            WHEN d.store_type IS NULL OR d.open_days IS NULL THEN '未分型'
            WHEN d.open_days <= 90 THEN CONCAT('新店·', d.store_type)
            ELSE CONCAT('老店·', d.store_type)
        END AS cell
        ,w26.sale_amt AS sale_amt_26, w25.sale_amt AS sale_amt_25
        ,w26.bf19_cust AS bf19_26, w25.bf19_cust AS bf19_25
        ,w26.purchase_weight AS pw_26, w25.purchase_weight AS pw_25
        ,w26.biz_days AS days_26, w25.biz_days AS days_25
    FROM dim d
    INNER JOIN w26 ON d.store_id = w26.store_id
    LEFT JOIN w25 ON d.store_id = w25.store_id
    WHERE d.store_type IS NOT NULL AND d.open_days IS NOT NULL
)
SELECT manage_area, cell
    ,ROUND(SUM(sale_amt_26) / NULLIF(SUM(days_26), 0), 4) AS sale_day_avg_curr
    ,ROUND(SUM(sale_amt_25) / NULLIF(SUM(days_25), 0), 4) AS sale_day_avg_prev
    ,ROUND(SUM(bf19_26) / NULLIF(SUM(days_26), 0), 4) AS bf19_cust_day_avg_curr
    ,ROUND(SUM(bf19_25) / NULLIF(SUM(days_25), 0), 4) AS bf19_cust_day_avg_prev
    ,ROUND(SUM(pw_26) / NULLIF(SUM(days_26), 0), 4) AS purchase_weight_day_avg_curr
    ,ROUND(SUM(pw_25) / NULLIF(SUM(days_25), 0), 4) AS purchase_weight_day_avg_prev
FROM store_pair
GROUP BY manage_area, cell
ORDER BY manage_area, cell
