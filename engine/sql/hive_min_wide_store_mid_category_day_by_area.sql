-- A1 分片导出模板：每次只跑一个管理区，避免 export_query max_rows=100000 截断
-- 用法：将下方 __MANAGE_AREA__ 替换为 粤西区、粤东区、华东区…（共 13 区 + 运营中心直管）
-- 导出：每区一个 CSV → data/问题引擎/_scratch/a1_by_area/Hive_店日中级KPI_202509_粤西区.csv
-- 合并：问题引擎/scripts/concat_hive_a1_by_area.py（导出后运行）
--
-- MCP 提示：若 WITH CTE 报 400，用 SELECT * FROM ( ... 本文件去掉注释后的 SELECT ... ) t

WITH store_dim AS (
    SELECT
        TRIM(p.sp_store_id) AS store_id
        ,TRIM(p.manage_area_name) AS manage_area
        ,TRIM(p.sap_area_name) AS sap_area_name
        ,CAST(p.inc_day AS DATE) AS dim_day
    FROM hive.dim.dim_store_profile p
    WHERE p.sp_level = '1'
      AND TRIM(p.manage_area_name) = '__MANAGE_AREA__'
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
    ,CASE WHEN SUM(fl.total_sale_qty) > 0 THEN SUM(fl.total_sale_amt) / SUM(fl.total_sale_qty) END AS avg_sale_price_by_qty
    ,CASE WHEN SUM(fl.bf19_sale_qty) > 0 THEN SUM(fl.bf19_sale_amt) / SUM(fl.bf19_sale_qty) END AS bf19_avg_sale_price_by_qty
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
