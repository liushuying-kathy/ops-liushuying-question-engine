SELECT manage_area_name AS manage_area
    ,date_format(year_month, '%Y-%m') AS ym
    ,COUNT(*) AS store_cnt
    ,SUM(CASE WHEN is_bad_store = 1 THEN 1 ELSE 0 END) AS bad_store_cnt
    ,ROUND(SUM(CASE WHEN is_bad_store = 1 THEN 1 ELSE 0 END) * 1.0 / NULLIF(COUNT(*), 0), 6) AS bad_rate
FROM default_catalog.ads_business_analysis.operation_center_store_loss_profit_oa_mi
WHERE year_month IN (DATE '2025-09-01', DATE '2026-09-01')
  AND manage_area_name NOT IN ('香港区', '澳门区', '香港', '澳门')
  AND in_loss_scope = 1
GROUP BY manage_area_name, date_format(year_month, '%Y-%m')
ORDER BY manage_area, ym
