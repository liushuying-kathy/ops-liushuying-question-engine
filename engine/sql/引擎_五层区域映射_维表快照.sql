-- 店 → 城市 → 省份 → 运营大区 → 管理区
-- 两个统计月末各拍一版。同比下钻不得用 2026-09-30 的组织替换 2025-09 的店归属。

WITH params AS (
    SELECT DATE '2026-09-30' AS snap_curr
        ,DATE '2025-09-30' AS snap_prev
)
SELECT d.report_date AS snapshot_date
    ,TRIM(UPPER(CAST(d.sp_store_id AS STRING))) AS store_id
    ,TRIM(d.city_description) AS city_name
    ,TRIM(d.pro_description) AS province_name
    ,TRIM(d.sap_area_name) AS opera_region
    ,CASE TRIM(d.manage_area_name)
        WHEN '粤西' THEN '粤西区'
        WHEN '粤东' THEN '粤东区'
        ELSE TRIM(d.manage_area_name)
    END AS manage_area
FROM default_catalog.ads_business_analysis.operation_center_dim_store_profile_di d
CROSS JOIN params p
WHERE d.sp_level = '1'
  AND d.report_date IN (p.snap_curr, p.snap_prev)
  AND TRIM(d.manage_area_name) NOT IN ('香港', '澳门', '香港区', '澳门区')
ORDER BY snapshot_date, manage_area, opera_region, province_name, city_name, store_id
