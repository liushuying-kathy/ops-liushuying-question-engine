-- 问题引擎 · Hive 最小宽表草案 ① 店×日×中分类 KPI
-- 导出：starrocks-db MCP export_query → data/问题引擎/Hive_店日中级KPI_202509.csv
-- 真源：hive.dal_full_link.dal_manage_full_link_store_dc_article_info_di
-- 店维：hive.dim.dim_store_profile（inc_day 与 business_date 对齐）
-- 互映：data/问题引擎/店号互映_20260930.csv
--
-- 口径说明：
--   · 金额/量/件：店品日 SUM 后 rollup 到中分类（同窗店×日×中类一行）
--   · total_cust_counts 为品级客数 SUM，不可直接作中分类客单价分母（会重复计数）
--   · 客单价探针请用 DSL 订单明细或神策 mid_category；本表仅提供金额与销量腿
--   · business_flag='1'：营业店日（与商分全链路一致）
--
-- 参数：2026-09（可按月改 WHERE business_date）

WITH store_dim AS (
    SELECT
        TRIM(p.sp_store_id) AS store_id
        ,TRIM(p.manage_area_name) AS manage_area
        ,TRIM(p.sap_area_name) AS sap_area_name
        ,CAST(p.inc_day AS DATE) AS dim_day
    FROM hive.dim.dim_store_profile p
    WHERE p.sp_level = '1'
      AND TRIM(p.manage_area_name) NOT IN ('香港区', '澳门区', '香港', '澳门')
      AND p.inc_day >= '2026-09-01'
      AND p.inc_day <= '2026-09-30'
),

fl AS (
    SELECT
        TRIM(f.store_id) AS store_id
        ,f.business_date
        ,TRIM(f.second_category_id) AS mid_category_id
        ,TRIM(f.second_category_name) AS mid_category_name
        ,TRIM(f.first_category_name) AS big_category_name
        ,COALESCE(f.total_sale_amt, 0) AS total_sale_amt
        ,COALESCE(f.bf19_sale_amt, 0) AS bf19_sale_amt
        ,COALESCE(f.lp_sale_amt, 0) AS lp_sale_amt
        ,COALESCE(f.bf19_lp_sale_amt, 0) AS bf19_lp_sale_amt
        ,COALESCE(f.total_sale_qty, 0) AS total_sale_qty
        ,COALESCE(f.bf19_sale_qty, 0) AS bf19_sale_qty
        ,COALESCE(f.sale_piece_qty, 0) AS sale_piece_qty
        ,COALESCE(f.bf19_sale_piece_qty, 0) AS bf19_sale_piece_qty
        ,COALESCE(f.total_cust_counts, 0) AS total_cust_counts
        ,COALESCE(f.bf19_sale_custs, 0) AS bf19_sale_custs
        ,COALESCE(f.article_profit_amt, 0) AS article_profit_amt
        ,f.article_id
    FROM hive.dal_full_link.dal_manage_full_link_store_dc_article_info_di f
    WHERE f.business_date >= DATE '2026-09-01'
      AND f.business_date <= DATE '2026-09-30'
      AND COALESCE(f.business_flag, '1') = '1'
      AND f.second_category_id IS NOT NULL
      AND TRIM(f.second_category_name) <> ''
)

SELECT
    fl.business_date
    ,fl.store_id
    ,d.manage_area
    ,d.sap_area_name
    ,fl.mid_category_id
    ,fl.mid_category_name
    ,fl.big_category_name
    ,SUM(fl.total_sale_amt) AS total_sale_amt
    ,SUM(fl.bf19_sale_amt) AS bf19_sale_amt
    ,SUM(fl.lp_sale_amt) AS lp_sale_amt
    ,SUM(fl.bf19_lp_sale_amt) AS bf19_lp_sale_amt
    ,SUM(fl.total_sale_qty) AS total_sale_qty
    ,SUM(fl.bf19_sale_qty) AS bf19_sale_qty
    ,SUM(fl.sale_piece_qty) AS sale_piece_qty
    ,SUM(fl.bf19_sale_piece_qty) AS bf19_sale_piece_qty
    ,SUM(fl.article_profit_amt) AS article_profit_amt
    ,SUM(fl.total_cust_counts) AS total_cust_counts_sum
    ,SUM(fl.bf19_sale_custs) AS bf19_sale_custs_sum
    ,COUNT(DISTINCT fl.article_id) AS article_cnt
    ,CASE
        WHEN SUM(fl.total_sale_qty) > 0
        THEN SUM(fl.total_sale_amt) / SUM(fl.total_sale_qty)
    END AS avg_sale_price_by_qty
    ,CASE
        WHEN SUM(fl.bf19_sale_qty) > 0
        THEN SUM(fl.bf19_sale_amt) / SUM(fl.bf19_sale_qty)
    END AS bf19_avg_sale_price_by_qty
FROM fl
INNER JOIN store_dim d
    ON fl.store_id = d.store_id
   AND fl.business_date = d.dim_day
GROUP BY
    fl.business_date
    ,fl.store_id
    ,d.manage_area
    ,d.sap_area_name
    ,fl.mid_category_id
    ,fl.mid_category_name
    ,fl.big_category_name
ORDER BY
    fl.business_date
    ,d.manage_area
    ,fl.store_id
    ,fl.mid_category_name
