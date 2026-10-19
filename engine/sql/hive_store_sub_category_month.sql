-- 店×小分类 9 月销售额（Hive 主路径）
SELECT
  business_date,
  store_id,
  third_category_id,
  third_category_name AS sub_category_name,
  SUM(COALESCE(total_sale_amt, 0)) AS total_sale_amt
FROM hive.dal_full_link.dal_manage_full_link_store_dc_article_info_di
WHERE business_date >= '2026-09-01'
  AND business_date <= '2026-09-30'
  AND third_category_name IS NOT NULL
  AND TRIM(third_category_name) <> ''
GROUP BY
  business_date,
  store_id,
  third_category_id,
  third_category_name
