-- 老店·加盟 / 老店·直营 内部分层 19点前来客店日均（2025-09 vs 2026-09）

WITH params AS (
    SELECT DATE '2026-09-01' AS layer_start, DATE '2026-09-30' AS layer_end
        ,DATE '2026-09-30' AS dim_pt
        ,DATE '2025-09-01' AS y25_start, DATE '2025-09-30' AS y25_end
        ,DATE '2026-09-01' AS y26_start, DATE '2026-09-30' AS y26_end
),
layer_tag AS (
    SELECT TRIM(l.store_name) AS store_name, TRIM(CAST(l.data_bucket AS STRING)) AS layer_bucket
    FROM default_catalog.ads_business_analysis.operation_resource_store_layer_list l
    CROSS JOIN params p
    WHERE l.start_date = p.layer_start AND l.end_date = p.layer_end
),
dim AS (
    SELECT TRIM(UPPER(CAST(d.sp_store_id AS STRING))) AS store_id
        ,TRIM(d.sp_store_name) AS store_name
        ,CASE TRIM(d.manage_area_name) WHEN '粤西' THEN '粤西区' WHEN '粤东' THEN '粤东区' ELSE TRIM(d.manage_area_name) END AS manage_area
        ,CASE TRIM(CAST(d.sp_type AS STRING)) WHEN '10' THEN '直营' WHEN '20' THEN '加盟' ELSE NULL END AS store_type
    FROM default_catalog.ads_business_analysis.operation_center_dim_store_profile_di d
    CROSS JOIN params p
    WHERE d.report_date = p.dim_pt AND d.sp_level = '1' AND COALESCE(d.open_days, 0) > 90
      AND TRIM(d.manage_area_name) NOT IN ('香港','澳门','香港区','澳门区')
),
cohort AS (
    SELECT d.manage_area, CONCAT('老店·', d.store_type) AS cell, lt.layer_bucket, d.store_id
    FROM dim d
    INNER JOIN layer_tag lt ON d.store_name = lt.store_name
    WHERE d.store_type IS NOT NULL
),
w26 AS (
    SELECT TRIM(UPPER(CAST(w.sp_store_id AS STRING))) AS store_id
        ,SUM(w.bf19_cust_num_store_day_avg * w.store_business_day_cnt) AS bf19_cust
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
        ,SUM(w.bf19_cust_num_store_day_avg * w.store_business_day_cnt) AS bf19_cust
        ,SUM(w.store_business_day_cnt) AS biz_days
    FROM default_catalog.ads_business_analysis.operation_center_wide_store_di w
    CROSS JOIN params p
    WHERE w.store_agg_dim = '门店' AND w.category_tier = '门店' AND w.category_name = '门店'
      AND COALESCE(w.store_business_day_cnt, 0) > 0
      AND w.report_date BETWEEN p.y25_start AND p.y25_end
    GROUP BY 1
),
agg26 AS (
    SELECT c.manage_area, c.cell, c.layer_bucket
        ,SUM(w.bf19_cust) AS bf19_cust, SUM(w.biz_days) AS biz_days
    FROM cohort c INNER JOIN w26 w ON c.store_id = w.store_id
    GROUP BY c.manage_area, c.cell, c.layer_bucket
),
agg25 AS (
    SELECT c.manage_area, c.cell, c.layer_bucket
        ,SUM(w.bf19_cust) AS bf19_cust, SUM(w.biz_days) AS biz_days
    FROM cohort c INNER JOIN w25 w ON c.store_id = w.store_id
    GROUP BY c.manage_area, c.cell, c.layer_bucket
)
SELECT COALESCE(a26.manage_area, a25.manage_area) AS manage_area
    ,COALESCE(a26.cell, a25.cell) AS cell
    ,COALESCE(a26.layer_bucket, a25.layer_bucket) AS layer_bucket
    ,ROUND(a26.bf19_cust / NULLIF(a26.biz_days, 0), 4) AS bf19_cust_day_avg_curr
    ,ROUND(a25.bf19_cust / NULLIF(a25.biz_days, 0), 4) AS bf19_cust_day_avg_prev
FROM agg26 a26
FULL OUTER JOIN agg25 a25
    ON a26.manage_area = a25.manage_area AND a26.cell = a25.cell AND a26.layer_bucket = a25.layer_bucket
ORDER BY manage_area, cell, layer_bucket
