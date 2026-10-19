SELECT
  TRIM(UPPER(CAST(sp_store_id AS STRING))) AS sp_store_id,
  TRIM(CAST(sp_store_id AS STRING)) AS sp_store_id_raw,
  TRIM(CAST(sp_store_id AS STRING)) AS hive_store_id,
  TRIM(CAST(sp_store_id AS STRING)) AS sensors_store_key,
  TRIM(manage_area_name) AS manage_area,
  TRIM(sap_area_name) AS sap_area_name,
  TRIM(CAST(city_description AS STRING)) AS city_description
FROM default_catalog.ads_business_analysis.operation_center_dim_store_profile_di
WHERE report_date = '2026-09-30'
  AND sp_level = '1'
  AND manage_area_name NOT IN ('香港区', '澳门区', '香港', '澳门')
  AND sp_store_id IS NOT NULL
  AND TRIM(CAST(sp_store_id AS STRING)) <> ''
