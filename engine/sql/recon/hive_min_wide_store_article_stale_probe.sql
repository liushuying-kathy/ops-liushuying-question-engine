-- 问题引擎 · Hive 最小宽表草案 ③ 店×品 滞销探针（M4 规则输入，非正式 ADS 叶子）
-- 导出：starrocks-db MCP export_query → data/问题引擎/Hive_店品滞销探针_202509.csv
-- 真源：hive.dal_full_link.dal_manage_full_link_store_dc_article_info_di
-- 引擎：thresholds.yaml stale_sku_days 拍板前仅作探针 CSV，不写判据
--
-- 规则（探针默认，可改 WHERE）：
--   · sale_days：月内 total_sale_qty > 0 的营业日天数
--   · last_sale_date：月内最后有销售日
--   · end_stock_qty_eom：月内最后营业日 end_stock_qty
--   · stale_candidate：sale_days = 0 AND end_stock_qty_eom > 0（整月无销但有期末库存）
--   · slow_sale_candidate：sale_days <= 3 AND end_stock_qty_eom > 0（低频动销+有库存，阈值待业务拍板）

WITH store_dim AS (
    SELECT
        TRIM(p.sp_store_id) AS store_id
        ,TRIM(p.manage_area_name) AS manage_area
        ,CAST(p.inc_day AS DATE) AS dim_day
    FROM hive.dim.dim_store_profile p
    WHERE p.sp_level = '1'
      AND TRIM(p.manage_area_name) NOT IN ('香港区', '澳门区', '香港', '澳门')
      AND p.inc_day >= '2026-09-01'
      AND p.inc_day <= '2026-09-30'
),

daily AS (
    SELECT
        TRIM(f.store_id) AS store_id
        ,f.business_date
        ,TRIM(f.article_id) AS article_id
        ,MAX(TRIM(f.article_name)) AS article_name
        ,TRIM(f.first_category_name) AS big_category_name
        ,TRIM(f.second_category_name) AS mid_category_name
        ,TRIM(f.third_category_name) AS sub_category_name
        ,SUM(COALESCE(f.total_sale_qty, 0)) AS total_sale_qty
        ,SUM(COALESCE(f.total_sale_amt, 0)) AS total_sale_amt
        ,SUM(COALESCE(f.end_stock_qty, 0)) AS end_stock_qty
        ,SUM(COALESCE(f.init_stock_qty, 0)) AS init_stock_qty
    FROM hive.dal_full_link.dal_manage_full_link_store_dc_article_info_di f
    INNER JOIN store_dim d
        ON TRIM(f.store_id) = d.store_id
       AND f.business_date = d.dim_day
    WHERE f.business_date >= DATE '2026-09-01'
      AND f.business_date <= DATE '2026-09-30'
      AND COALESCE(f.business_flag, '1') = '1'
      AND f.article_id IS NOT NULL
      AND TRIM(f.article_id) <> ''
    GROUP BY
        TRIM(f.store_id)
        ,f.business_date
        ,TRIM(f.article_id)
        ,TRIM(f.first_category_name)
        ,TRIM(f.second_category_name)
        ,TRIM(f.third_category_name)
),

monthly AS (
    SELECT
        store_id
        ,article_id
        ,MAX(article_name) AS article_name
        ,MAX(big_category_name) AS big_category_name
        ,MAX(mid_category_name) AS mid_category_name
        ,MAX(sub_category_name) AS sub_category_name
        ,SUM(total_sale_qty) AS sale_qty_month
        ,SUM(total_sale_amt) AS sale_amt_month
        ,SUM(CASE WHEN total_sale_qty > 0 THEN 1 ELSE 0 END) AS sale_days
        ,MAX(CASE WHEN total_sale_qty > 0 THEN business_date END) AS last_sale_date
        ,MAX_BY(end_stock_qty, business_date) AS end_stock_qty_eom
        ,MAX_BY(init_stock_qty, business_date) AS init_stock_qty_eom
    FROM daily
    GROUP BY
        store_id
        ,article_id
)

SELECT
    m.store_id
    ,d.manage_area
    ,m.article_id
    ,m.article_name
    ,m.big_category_name
    ,m.mid_category_name
    ,m.sub_category_name
    ,m.sale_qty_month
    ,m.sale_amt_month
    ,m.sale_days
    ,m.last_sale_date
    ,m.end_stock_qty_eom
    ,m.init_stock_qty_eom
    ,CASE
        WHEN m.sale_days = 0 AND COALESCE(m.end_stock_qty_eom, 0) > 0 THEN 1
        ELSE 0
    END AS stale_candidate
    ,CASE
        WHEN m.sale_days > 0
             AND m.sale_days <= 3
             AND COALESCE(m.end_stock_qty_eom, 0) > 0
        THEN 1
        ELSE 0
    END AS slow_sale_candidate
FROM monthly m
INNER JOIN (
    SELECT DISTINCT store_id, manage_area
    FROM store_dim
) d
    ON m.store_id = d.store_id
WHERE
    (
        m.sale_days = 0 AND COALESCE(m.end_stock_qty_eom, 0) > 0
    )
    OR (
        m.sale_days > 0
        AND m.sale_days <= 3
        AND COALESCE(m.end_stock_qty_eom, 0) > 0
    )
ORDER BY
    d.manage_area
    ,m.store_id
    ,m.sale_amt_month
    ,m.article_id
