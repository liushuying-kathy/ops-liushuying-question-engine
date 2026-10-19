-- 管理区域 × 大分类 · 2026-09 对 2025-09
-- 19点前销售、来客、重量、均价、促销折扣、时段折扣

WITH params AS (
    SELECT
        DATE '2025-09-01' AS ly_start
        ,DATE '2025-09-30' AS ly_end
        ,DATE '2026-09-01' AS cur_start
        ,DATE '2026-09-30' AS cur_end
),
base AS (
    SELECT
        w.store_agg_name AS manage_area
        ,CASE
            WHEN w.report_date BETWEEN p.cur_start AND p.cur_end THEN '2026-09'
            WHEN w.report_date BETWEEN p.ly_start AND p.ly_end THEN '2025-09'
        END AS ym
        ,CASE
            WHEN w.category_tier = '门店' AND w.category_name = '门店' THEN '全店'
            WHEN w.category_tier = '大分类' THEN w.category_name
        END AS category_name
        ,SUM(w.bf19_sale_amt_store_day_avg * w.store_business_day_cnt) AS bf19_sale_wtd
        ,SUM(w.sale_amt_store_day_avg * w.store_business_day_cnt) AS sale_wtd
        ,SUM(w.bf19_cust_num_store_day_avg * w.store_business_day_cnt) AS bf19_cust_wtd
        ,SUM(w.bf19_sales_weight_store_day_avg * w.store_business_day_cnt) AS bf19_wt_wtd
        ,SUM(w.promo_discount_rate * w.lp_sale_amt_store_day_avg * w.store_business_day_cnt) AS promo_wtd
        ,SUM(w.hour_discount_rate * w.lp_sale_amt_store_day_avg * w.store_business_day_cnt) AS hour_wtd
        ,SUM(w.lp_sale_amt_store_day_avg * w.store_business_day_cnt) AS lp_wtd
        ,SUM(w.store_business_day_cnt) AS biz_days
    FROM default_catalog.ads_business_analysis.operation_center_wide_store_di w
    CROSS JOIN params p
    WHERE w.store_agg_dim = '管理区域'
      AND w.store_agg_name IN (
          '粤西区','粤东区','华东区','成都区','重庆区','西安区','南京区','合肥区','天津区','郑州区','武汉区','长沙区'
      )
      AND COALESCE(w.store_business_day_cnt, 0) > 0
      AND (
          (w.category_tier = '门店' AND w.category_name = '门店')
          OR (
              w.category_tier = '大分类'
              AND w.category_name IN ('蔬菜类','猪肉类','水果类','水产类','冷藏及加工类','预制菜')
          )
      )
      AND (
          w.report_date BETWEEN p.ly_start AND p.ly_end
          OR w.report_date BETWEEN p.cur_start AND p.cur_end
      )
    GROUP BY 1, 2, 3
)
SELECT
    manage_area
    ,category_name
    ,ym
    ,ROUND(bf19_sale_wtd / NULLIF(biz_days, 0), 2) AS bf19_sale_day_avg
    ,ROUND(sale_wtd / NULLIF(biz_days, 0), 2) AS sale_day_avg
    ,ROUND(bf19_cust_wtd / NULLIF(biz_days, 0), 2) AS bf19_cust_day_avg
    ,ROUND(bf19_wt_wtd / NULLIF(biz_days, 0), 3) AS bf19_weight_day_avg
    ,ROUND(bf19_wt_wtd / NULLIF(bf19_cust_wtd, 0), 4) AS basket_weight
    ,ROUND(bf19_sale_wtd / NULLIF(bf19_wt_wtd, 0), 3) AS bf19_avg_price
    ,ROUND(bf19_sale_wtd / NULLIF(bf19_cust_wtd, 0), 3) AS bf19_unit_price
    ,ROUND(promo_wtd / NULLIF(lp_wtd, 0), 4) AS promo_discount_rate
    ,ROUND(hour_wtd / NULLIF(lp_wtd, 0), 4) AS hour_discount_rate
    ,biz_days
FROM base
WHERE category_name IS NOT NULL
  AND ym IS NOT NULL
ORDER BY manage_area, category_name, ym
