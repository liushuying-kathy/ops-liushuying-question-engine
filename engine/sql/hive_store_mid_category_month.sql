-- 店×中分类 9 月销售额（Hive 主路径，经 starrocks-db MCP 或数仓调度执行）
-- 表：hive.dal_full_link.dal_manage_full_link_store_dc_article_info_di
-- 备：hive.dal_bi_rpt.sale_store_goods_daily_fact ⋈ hive.dim.dim_goods_information_have_pt
SELECT
  business_date,
  store_id,
  second_category_id,
  second_category_name AS mid_category_name,
  SUM(COALESCE(total_sale_amt, 0)) AS total_sale_amt
FROM hive.dal_full_link.dal_manage_full_link_store_dc_article_info_di
WHERE business_date >= '2026-09-01'
  AND business_date <= '2026-09-30'
  AND second_category_name IS NOT NULL
  AND TRIM(second_category_name) <> ''
GROUP BY
  business_date,
  store_id,
  second_category_id,
  second_category_name
