SELECT 'operation_center_wide_store_di' AS tbl, COUNT(*) AS cnt
FROM default_catalog.ads_business_analysis.operation_center_wide_store_di

UNION ALL
SELECT 'operation_center_wide_daily', COUNT(*)
FROM default_catalog.ads_business_analysis.operation_center_wide_daily

UNION ALL
SELECT 'operation_center_dim_store_profile_di', COUNT(*)
FROM default_catalog.ads_business_analysis.operation_center_dim_store_profile_di

UNION ALL
SELECT 'operation_center_store_loss_profit_oa_mi', COUNT(*)
FROM default_catalog.ads_business_analysis.operation_center_store_loss_profit_oa_mi

UNION ALL
SELECT 'operation_resource_store_layer_list', COUNT(*)
FROM default_catalog.ads_business_analysis.operation_resource_store_layer_list

UNION ALL
SELECT 'operation_center_store_allowance_di', COUNT(*)
FROM default_catalog.ads_business_analysis.operation_center_store_allowance_di

UNION ALL
SELECT 'operation_center_legacy_store_bad_rate_mtd_di', COUNT(*)
FROM default_catalog.ads_business_analysis.operation_center_legacy_store_bad_rate_mtd_di

UNION ALL
SELECT 'operation_center_dim_store_change_info_da', COUNT(*)
FROM default_catalog.ads_business_analysis.operation_center_dim_store_change_info_da

UNION ALL
SELECT 'operation_center_store_category_price_strategy_di', COUNT(*)
FROM default_catalog.ads_business_analysis.operation_center_store_category_price_strategy_di

UNION ALL
SELECT 'operation_center_store_promotion_cost_bearer_di', COUNT(*)
FROM default_catalog.ads_business_analysis.operation_center_store_promotion_cost_bearer_di

UNION ALL
SELECT 'operation_center_goods_dim', COUNT(*)
FROM default_catalog.ads_business_analysis.operation_center_goods_dim

UNION ALL
SELECT 'operation_center_process_daily', COUNT(*)
FROM default_catalog.ads_business_analysis.operation_center_process_daily

UNION ALL
SELECT 'operation_center_store_daily', COUNT(*)
FROM default_catalog.ads_business_analysis.operation_center_store_daily

UNION ALL
SELECT 'operation_center_wide_v6', COUNT(*)
FROM default_catalog.ads_business_analysis.operation_center_wide_v6

UNION ALL
SELECT 'operation_center_store_midcategory_must_order_di', COUNT(*)
FROM default_catalog.ads_business_analysis.operation_center_store_midcategory_must_order_di

UNION ALL
SELECT 'tmp_store_article_TOBpromotion', COUNT(*)
FROM default_catalog.ads_business_analysis.tmp_store_article_TOBpromotion

UNION ALL
SELECT 'product_center_business_v3_info_di', COUNT(*)
FROM default_catalog.ads_business_analysis.product_center_business_v3_info_di

UNION ALL
SELECT 'article_price_index_info_di', COUNT(*)
FROM default_catalog.ads_business_analysis.article_price_index_info_di

UNION ALL
SELECT 'operation_center_online_omni_weekly_mtd_di', COUNT(*)
FROM default_catalog.ads_business_analysis.operation_center_online_omni_weekly_mtd_di

UNION ALL
SELECT 'operation_center_new_store_90d_weekly_store_di', COUNT(*)
FROM default_catalog.ads_business_analysis.operation_center_new_store_90d_weekly_store_di

UNION ALL
SELECT 'operation_center_closure_weekly_store_di', COUNT(*)
FROM default_catalog.ads_business_analysis.operation_center_closure_weekly_store_di
