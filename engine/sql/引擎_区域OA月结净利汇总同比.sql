-- 区域×月 OA 月结净利汇总（非「税前利润达成」；仅供对照，不可作郑州阻断真源）

WITH params AS (
    SELECT DATE '2026-09-01' AS ym26, DATE '2025-09-01' AS ym25
)
SELECT
    CASE TRIM(o.manage_area_name) WHEN '粤西' THEN '粤西区' WHEN '粤东' THEN '粤东区' ELSE TRIM(o.manage_area_name) END AS manage_area
    ,CASE WHEN o.year_month = p.ym26 THEN '2026-09' WHEN o.year_month = p.ym25 THEN '2025-09' END AS ym
    ,SUM(o.stl_net_profit) AS stl_net_profit_sum
    ,SUM(o.stl_sale_amt) AS stl_sale_amt_sum
    ,SUM(o.stl_sale_days) AS stl_sale_days_sum
    ,COUNT(DISTINCT o.store_id) AS store_cnt
FROM default_catalog.ads_business_analysis.operation_center_store_loss_profit_oa_mi o
CROSS JOIN params p
WHERE o.year_month IN (p.ym26, p.ym25)
  AND TRIM(o.manage_area_name) NOT IN ('香港','澳门','香港区','澳门区')
GROUP BY 1, 2
ORDER BY manage_area, ym
