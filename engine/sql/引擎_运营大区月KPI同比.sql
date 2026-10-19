-- 管理区域下钻：运营大区用维表 sap_area_name（如粤西一区）。
-- 维表没有 2025-09-30 分区，两年店都挂 2026-09-30。已落盘旧 CSV 若仍是 area_description，以这次重取为准。

WITH params AS (
    SELECT DATE '2026-09-01' AS y26_start, DATE '2026-09-30' AS y26_end
        ,DATE '2025-09-01' AS y25_start, DATE '2025-09-30' AS y25_end
        ,DATE '2026-09-30' AS dim_pt
),
dim AS (
    SELECT TRIM(UPPER(CAST(d.sp_store_id AS STRING))) AS store_id
        ,CASE TRIM(d.manage_area_name) WHEN '粤西' THEN '粤西区' WHEN '粤东' THEN '粤东区' ELSE TRIM(d.manage_area_name) END AS manage_area
        ,TRIM(d.sap_area_name) AS opera_sub_region
    FROM default_catalog.ads_business_analysis.operation_center_dim_store_profile_di d
    CROSS JOIN params p
    WHERE d.report_date = p.dim_pt AND d.sp_level = '1'
      AND TRIM(d.manage_area_name) NOT IN ('香港','澳门','香港区','澳门区')
      AND TRIM(d.sap_area_name) IS NOT NULL AND TRIM(d.sap_area_name) <> ''
      AND TRIM(d.sap_area_name) NOT IN ('无人柜', 'X')
),
w26 AS (
    SELECT TRIM(UPPER(CAST(w.sp_store_id AS STRING))) AS store_id
        ,SUM(w.sale_amt_store_day_avg * w.store_business_day_cnt) AS sale_amt
        ,SUM(w.bf19_cust_num_store_day_avg * w.store_business_day_cnt) AS bf19_cust
        ,SUM(w.purchase_weight_store_day_avg * w.store_business_day_cnt) AS purchase_weight
        ,SUM(w.article_profit_store_day_avg * w.store_business_day_cnt) AS article_profit
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
        ,SUM(w.bf19_cust_num_store_day_avg * w.store_business_day_cnt) AS bf19_cust
        ,SUM(w.purchase_weight_store_day_avg * w.store_business_day_cnt) AS purchase_weight
        ,SUM(w.article_profit_store_day_avg * w.store_business_day_cnt) AS article_profit
        ,SUM(w.store_business_day_cnt) AS biz_days
    FROM default_catalog.ads_business_analysis.operation_center_wide_store_di w
    CROSS JOIN params p
    WHERE w.store_agg_dim = '门店' AND w.category_tier = '门店' AND w.category_name = '门店'
      AND COALESCE(w.store_business_day_cnt, 0) > 0
      AND w.report_date BETWEEN p.y25_start AND p.y25_end
    GROUP BY 1
),
st AS (
    SELECT d.manage_area
        ,d.opera_sub_region
        ,SUM(w26.sale_amt) / NULLIF(SUM(w26.biz_days), 0) AS sale_day_avg_26
        ,SUM(w25.sale_amt) / NULLIF(SUM(w25.biz_days), 0) AS sale_day_avg_25
        ,SUM(w26.bf19_cust) / NULLIF(SUM(w26.biz_days), 0) AS bf19_day_avg_26
        ,SUM(w25.bf19_cust) / NULLIF(SUM(w25.biz_days), 0) AS bf19_day_avg_25
        ,SUM(w26.purchase_weight) / NULLIF(SUM(w26.biz_days), 0) AS weight_day_avg_26
        ,SUM(w25.purchase_weight) / NULLIF(SUM(w25.biz_days), 0) AS weight_day_avg_25
        ,SUM(w26.article_profit) / NULLIF(SUM(w26.sale_amt), 0) AS profit_rate_26
        ,SUM(w25.article_profit) / NULLIF(SUM(w25.sale_amt), 0) AS profit_rate_25
        ,SUM(w26.article_profit) / NULLIF(SUM(w26.biz_days), 0) AS profit_day_avg_26
        ,SUM(w25.article_profit) / NULLIF(SUM(w25.biz_days), 0) AS profit_day_avg_25
        ,COUNT(DISTINCT d.store_id) AS store_cnt
    FROM dim d
    INNER JOIN w26 ON d.store_id = w26.store_id
    LEFT JOIN w25 ON d.store_id = w25.store_id
    GROUP BY d.manage_area, d.opera_sub_region
)
SELECT manage_area
    ,opera_sub_region
    ,store_cnt
    ,ROUND(sale_day_avg_26, 4) AS sale_day_avg_curr
    ,ROUND(sale_day_avg_25, 4) AS sale_day_avg_prev
    ,ROUND((sale_day_avg_26 - sale_day_avg_25) / NULLIF(sale_day_avg_25, 0), 6) AS sale_yoy
    ,ROUND((bf19_day_avg_26 - bf19_day_avg_25) / NULLIF(bf19_day_avg_25, 0), 6) AS bf19_yoy
    ,ROUND((weight_day_avg_26 - weight_day_avg_25) / NULLIF(weight_day_avg_25, 0), 6) AS weight_yoy
    ,ROUND((profit_day_avg_26 - profit_day_avg_25) / NULLIF(profit_day_avg_25, 0), 6) AS profit_amt_yoy
    ,ROUND((profit_rate_26 - profit_rate_25) / NULLIF(profit_rate_25, 0), 6) AS profit_rate_yoy
FROM st
ORDER BY manage_area, sale_yoy ASC
