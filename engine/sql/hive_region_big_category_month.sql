-- 管理区×大分类 9 月销售额（对账第二轨：Hive fl × 店维，不替代宽表 KPI）
-- 执行：starrocks-db MCP export_query → data/问题引擎/Hive_区域大分类月销_202509.csv
-- 店号互映：问题引擎/config/store_id_bridge.yaml
SELECT
  TRIM(p.manage_area_name) AS manage_area,
  TRIM(f.first_category_name) AS first_category_name,
  SUM(COALESCE(f.total_sale_amt, 0)) AS total_sale_amt
FROM hive.dal_full_link.dal_manage_full_link_store_dc_article_info_di f
INNER JOIN hive.dim.dim_store_profile p
  ON TRIM(f.store_id) = TRIM(p.sp_store_id)
WHERE f.business_date >= '2026-09-01'
  AND f.business_date <= '2026-09-30'
  AND p.sp_level = '1'
  AND TRIM(p.manage_area_name) NOT IN ('香港区', '澳门区', '香港', '澳门')
  AND f.first_category_name IS NOT NULL
  AND TRIM(f.first_category_name) <> ''
GROUP BY TRIM(p.manage_area_name), TRIM(f.first_category_name)
ORDER BY manage_area, first_category_name
