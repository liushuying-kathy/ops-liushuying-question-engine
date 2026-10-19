-- 店×中分类 9 月汇总（落盘用；与 fetch_hive_category_month_202509.py 一致）
SELECT
  TRIM(f.store_id) AS store_id,
  TRIM(p.manage_area_name) AS manage_area,
  TRIM(f.second_category_id) AS second_category_id,
  TRIM(f.second_category_name) AS mid_category_name,
  SUM(COALESCE(f.total_sale_amt, 0)) AS total_sale_amt
FROM hive.dal_full_link.dal_manage_full_link_store_dc_article_info_di f
INNER JOIN hive.dim.dim_store_profile p
  ON TRIM(f.store_id) = TRIM(p.sp_store_id)
WHERE f.business_date >= '2026-09-01'
  AND f.business_date <= '2026-09-30'
  AND p.sp_level = '1'
  AND TRIM(p.manage_area_name) NOT IN ('香港区', '澳门区', '香港', '澳门')
  AND f.second_category_name IS NOT NULL
  AND TRIM(f.second_category_name) <> ''
GROUP BY
  TRIM(f.store_id),
  TRIM(p.manage_area_name),
  TRIM(f.second_category_id),
  TRIM(f.second_category_name)
ORDER BY manage_area, store_id, mid_category_name
