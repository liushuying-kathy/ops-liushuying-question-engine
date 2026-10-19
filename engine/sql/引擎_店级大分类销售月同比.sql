-- 门店宽表 · 店×大分类 销售额月合计（T12 品类占比）

WITH params AS (
    SELECT DATE '2025-09-01' AS y25_start, DATE '2025-09-30' AS y25_end
        ,DATE '2026-09-01' AS y26_start, DATE '2026-09-30' AS y26_end
),
dim AS (
    SELECT TRIM(UPPER(CAST(d.sp_store_id AS STRING))) AS store_id
        ,CASE TRIM(d.manage_area_name)
            WHEN '粤西' THEN '粤西区'
            WHEN '粤东' THEN '粤东区'
            ELSE TRIM(d.manage_area_name)
        END AS manage_area
    FROM default_catalog.ads_business_analysis.operation_center_dim_store_profile_di d
    CROSS JOIN params p
    WHERE d.report_date = DATE '2026-09-30'
      AND d.sp_level = '1'
      AND TRIM(d.manage_area_name) NOT IN ('香港','澳门','香港区','澳门区')
),
base AS (
    SELECT
        d.manage_area
        ,w.category_name
        ,CASE
            WHEN w.report_date BETWEEN p.y25_start AND p.y25_end THEN '2025-09'
            WHEN w.report_date BETWEEN p.y26_start AND p.y26_end THEN '2026-09'
        END AS ym
        ,SUM(w.sale_amt_store_day_avg * w.store_business_day_cnt) AS sale_amt
    FROM default_catalog.ads_business_analysis.operation_center_wide_store_di w
    INNER JOIN dim d ON TRIM(UPPER(CAST(w.sp_store_id AS STRING))) = d.store_id
    CROSS JOIN params p
    WHERE w.store_agg_dim = '门店'
      AND w.category_tier = '大分类'
      AND COALESCE(w.store_business_day_cnt, 0) > 0
      AND (
          w.report_date BETWEEN p.y25_start AND p.y25_end
          OR w.report_date BETWEEN p.y26_start AND p.y26_end
      )
      AND w.category_name IN ('蔬菜类','猪肉类','水果类','水产类','冷藏及加工类','预制菜')
    GROUP BY d.manage_area, w.category_name, 3
)
SELECT manage_area, category_name, ym, sale_amt
FROM base
WHERE ym IS NOT NULL
ORDER BY manage_area, category_name, ym
