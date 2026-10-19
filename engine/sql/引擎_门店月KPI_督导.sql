-- 门店月 KPI + 督导（2026-09 vs 2025-09），供店强提示与督导清单；T6 盈亏平衡

WITH params AS (
    SELECT DATE '2026-09-01' AS y26_start, DATE '2026-09-30' AS y26_end
        ,DATE '2025-09-01' AS y25_start, DATE '2025-09-30' AS y25_end
        ,DATE '2026-09-30' AS dim_pt
        ,30 AS month_cal_days
),
dim AS (
    SELECT TRIM(UPPER(CAST(d.sp_store_id AS STRING))) AS store_id
        ,TRIM(d.sp_store_name) AS store_name
        ,CASE TRIM(d.manage_area_name) WHEN '粤西' THEN '粤西区' WHEN '粤东' THEN '粤东区' ELSE TRIM(d.manage_area_name) END AS manage_area
        ,TRIM(d.city_description) AS city_name
        ,CASE TRIM(CAST(d.sp_type AS STRING)) WHEN '10' THEN '直营' WHEN '20' THEN '加盟' ELSE NULL END AS store_type
        ,d.open_days
        ,TRIM(CAST(d.group_manager_code AS STRING)) AS supervisor_id
        ,TRIM(d.group_manager) AS supervisor_name
        ,TRIM(CAST(d.franchisee_id AS STRING)) AS franchisee_id
        ,TRIM(d.franchisee_name) AS franchisee_name
        ,TRIM(CAST(d.contract_franchisee_id AS STRING)) AS contract_franchisee_id
        ,TRIM(d.contract_franchisee_name) AS contract_franchisee_name
        ,TRIM(CAST(d.zone_supper_id AS STRING)) AS zone_supper_id
        ,TRIM(d.zone_supper_manager) AS zone_supper_manager
        ,TO_DATE(d.sp_origin_start_date) AS open_date
        ,TO_DATE(d.sp_final_end_date) AS close_date
    FROM default_catalog.ads_business_analysis.operation_center_dim_store_profile_di d
    CROSS JOIN params p
    WHERE d.report_date = p.dim_pt AND d.sp_level = '1'
      AND TRIM(d.manage_area_name) NOT IN ('香港','澳门','香港区','澳门区')
),
w26 AS (
    SELECT TRIM(UPPER(CAST(w.sp_store_id AS STRING))) AS store_id
        ,SUM(w.sale_amt_store_day_avg * w.store_business_day_cnt) AS sale_amt
        ,SUM(w.article_profit_store_day_avg * w.store_business_day_cnt) AS article_profit
        ,SUM(w.bf19_cust_num_store_day_avg * w.store_business_day_cnt) AS bf19_cust
        ,SUM(w.bf19_cust_unit_price * w.bf19_cust_num_store_day_avg * w.store_business_day_cnt) AS bf19_price_num
        ,SUM(w.store_business_day_cnt) AS biz_days
    FROM default_catalog.ads_business_analysis.operation_center_wide_store_di w
    CROSS JOIN params p
    WHERE w.store_agg_dim = '门店' AND w.category_tier = '门店' AND w.category_name = '门店'
      AND COALESCE(w.store_business_day_cnt, 0) > 0
      AND w.report_date BETWEEN p.y26_start AND p.y26_end
    GROUP BY 1
),
w26_d4 AS (
    SELECT TRIM(UPPER(CAST(w.sp_store_id AS STRING))) AS store_id
        ,SUM(w.bf19_cust_num_store_day_avg * w.store_business_day_cnt) AS bf19_cust
        ,SUM(w.store_business_day_cnt) AS biz_days
    FROM default_catalog.ads_business_analysis.operation_center_wide_store_di w
    INNER JOIN dim d ON TRIM(UPPER(CAST(w.sp_store_id AS STRING))) = d.store_id
    CROSS JOIN params p
    WHERE w.store_agg_dim = '门店' AND w.category_tier = '门店' AND w.category_name = '门店'
      AND COALESCE(w.store_business_day_cnt, 0) > 0
      AND w.report_date BETWEEN p.y26_start AND p.y26_end
      AND d.open_date IS NOT NULL
      AND w.report_date > DATE_ADD(d.open_date, 2)
    GROUP BY 1
),
w25 AS (
    SELECT TRIM(UPPER(CAST(w.sp_store_id AS STRING))) AS store_id
        ,SUM(w.sale_amt_store_day_avg * w.store_business_day_cnt) AS sale_amt
        ,SUM(w.article_profit_store_day_avg * w.store_business_day_cnt) AS article_profit
        ,SUM(w.bf19_cust_num_store_day_avg * w.store_business_day_cnt) AS bf19_cust
        ,SUM(w.store_business_day_cnt) AS biz_days
    FROM default_catalog.ads_business_analysis.operation_center_wide_store_di w
    CROSS JOIN params p
    WHERE w.store_agg_dim = '门店' AND w.category_tier = '门店' AND w.category_name = '门店'
      AND COALESCE(w.store_business_day_cnt, 0) > 0
      AND w.report_date BETWEEN p.y25_start AND p.y25_end
    GROUP BY 1
),
oa26 AS (
    SELECT TRIM(UPPER(CAST(o.store_id AS STRING))) AS store_id
        ,o.loss_net_profit, o.loss_sale_days
        ,o.stl_except_goods_amt
    FROM default_catalog.ads_business_analysis.operation_center_store_loss_profit_oa_mi o
    CROSS JOIN params p
    WHERE o.year_month = DATE '2026-09-01'
),
base AS (
    SELECT d.store_id, d.store_name, d.manage_area, d.city_name, d.store_type, d.open_days
        ,d.supervisor_id, d.supervisor_name, d.franchisee_id, d.franchisee_name
        ,d.contract_franchisee_id, d.contract_franchisee_name
        ,d.zone_supper_id, d.zone_supper_manager, d.close_date
        ,w26.biz_days AS biz_days_curr
        ,CASE
            WHEN d.store_type IS NULL OR d.open_days IS NULL THEN '未分型'
            WHEN d.open_days <= 90 THEN CONCAT('新店·', d.store_type)
            ELSE CONCAT('老店·', d.store_type)
        END AS cell
        ,ROUND(w26.sale_amt / NULLIF(w26.biz_days, 0), 4) AS sale_day_avg_curr
        ,ROUND(w25.sale_amt / NULLIF(w25.biz_days, 0), 4) AS sale_day_avg_prev
        ,ROUND(w26.article_profit / NULLIF(w26.biz_days, 0), 4) AS article_profit_day_avg_curr
        ,ROUND(w25.article_profit / NULLIF(w25.biz_days, 0), 4) AS article_profit_day_avg_prev
        ,ROUND(w26.bf19_cust / NULLIF(w26.biz_days, 0), 4) AS bf19_cust_day_avg_curr
        ,ROUND(w26_d4.bf19_cust / NULLIF(w26_d4.biz_days, 0), 4) AS bf19_cust_day_avg_curr_d4
        ,ROUND(w25.bf19_cust / NULLIF(w25.biz_days, 0), 4) AS bf19_cust_day_avg_prev
        ,ROUND(w26.bf19_price_num / NULLIF(w26.bf19_cust, 0), 4) AS bf19_unit_price_curr
        ,CASE WHEN oa26.loss_net_profit IS NULL THEN NULL
              ELSE ROUND(oa26.loss_net_profit / NULLIF(oa26.loss_sale_days, 0), 4) END AS net_profit_day_avg_curr
        ,CASE
            WHEN oa26.stl_except_goods_amt IS NOT NULL AND p.month_cal_days > 0
            THEN ROUND(oa26.stl_except_goods_amt / p.month_cal_days, 4)
            ELSE NULL
        END AS breakeven_daily_curr
    FROM dim d
    INNER JOIN w26 ON d.store_id = w26.store_id
    LEFT JOIN w25 ON d.store_id = w25.store_id
    LEFT JOIN oa26 ON d.store_id = oa26.store_id
    LEFT JOIN w26_d4 ON d.store_id = w26_d4.store_id
    CROSS JOIN params p
    WHERE d.store_type IS NOT NULL AND d.open_days IS NOT NULL
),
city_bf19 AS (
    SELECT manage_area, city_name
        ,ROUND(AVG(bf19_cust_day_avg_curr), 4) AS city_bf19_mean_curr
    FROM base
    WHERE bf19_cust_day_avg_curr IS NOT NULL AND cell <> '未分型'
    GROUP BY manage_area, city_name
),
region_bf19 AS (
    SELECT manage_area
        ,ROUND(AVG(bf19_cust_day_avg_curr), 4) AS region_bf19_mean_curr
    FROM base
    WHERE bf19_cust_day_avg_curr IS NOT NULL AND cell <> '未分型'
    GROUP BY manage_area
)
SELECT b.store_id, b.store_name, b.manage_area, b.city_name, b.store_type, b.open_days
    ,b.supervisor_id, b.supervisor_name, b.franchisee_id, b.franchisee_name
    ,b.contract_franchisee_id, b.contract_franchisee_name
    ,b.zone_supper_id, b.zone_supper_manager, b.cell
    ,b.close_date, b.biz_days_curr
    ,b.sale_day_avg_curr, b.sale_day_avg_prev
    ,b.bf19_cust_day_avg_curr, b.bf19_cust_day_avg_curr_d4, b.bf19_cust_day_avg_prev
    ,b.bf19_unit_price_curr, b.net_profit_day_avg_curr
    ,b.breakeven_daily_curr
    ,CASE
        WHEN b.breakeven_daily_curr IS NOT NULL AND b.bf19_unit_price_curr IS NOT NULL AND b.bf19_unit_price_curr > 0
        THEN ROUND(b.breakeven_daily_curr / b.bf19_unit_price_curr, 4)
        ELSE NULL
    END AS qualified_bf19_curr
    ,CASE
        WHEN b.breakeven_daily_curr IS NOT NULL AND b.bf19_unit_price_curr IS NOT NULL AND b.bf19_unit_price_curr > 0
        THEN '盈亏平衡'
        ELSE '区域85'
    END AS traffic_path
    ,c.city_bf19_mean_curr
    ,r.region_bf19_mean_curr
FROM base b
LEFT JOIN city_bf19 c ON b.manage_area = c.manage_area AND b.city_name = c.city_name
LEFT JOIN region_bf19 r ON b.manage_area = r.manage_area
