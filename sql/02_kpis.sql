-- KPI tables behind the dashboard. Everything is pre-aggregated by (year, month, country) and (year, country).
-- country = 'All' is computed separately so distinct counts stay exact.
CREATE OR REPLACE TABLE top_countries AS
SELECT country FROM sales GROUP BY country ORDER BY SUM(revenue) DESC LIMIT 9;

CREATE OR REPLACE TABLE sales_c AS
SELECT s.*, CASE WHEN s.country IN (SELECT country FROM top_countries) THEN s.country ELSE 'Other countries' END AS country_g,
       strftime(invoice_date, '%Y-%m') AS ym, YEAR(invoice_date) AS yr
FROM sales s;

CREATE OR REPLACE TABLE returns_c AS
SELECT r.*, strftime(r.return_date, '%Y-%m') AS ym, YEAR(r.return_date) AS yr,
       COALESCE((SELECT ANY_VALUE(CASE WHEN s.country IN (SELECT country FROM top_countries) THEN s.country ELSE 'Other countries' END)
                 FROM sales s WHERE s.customer_id = r.customer_id), 'Other countries') AS country_g
FROM returns r;

-- monthly: one row per (ym, country) incl. 'All'
CREATE OR REPLACE TABLE monthly AS
WITH base AS (
    SELECT ym, country_g AS country, SUM(revenue) AS revenue, COUNT(DISTINCT invoice) AS orders,
           COUNT(DISTINCT customer_id) AS customers, SUM(quantity) AS units
    FROM sales_c GROUP BY ym, country_g
    UNION ALL
    SELECT ym, 'All', SUM(revenue), COUNT(DISTINCT invoice), COUNT(DISTINCT customer_id), SUM(quantity) FROM sales_c GROUP BY ym
),
ret AS (
    SELECT ym, country_g AS country, SUM(return_value) AS returns FROM returns_c GROUP BY ym, country_g
    UNION ALL
    SELECT ym, 'All', SUM(return_value) FROM returns_c GROUP BY ym
)
SELECT b.*, COALESCE(r.returns, 0) AS returns FROM base b LEFT JOIN ret r USING (ym, country) ORDER BY ym, country;

-- yearly KPIs incl. repeat-customer rate, for year in (2009, 2010, 2011, 'All') x country
CREATE OR REPLACE TABLE yearly AS
WITH keys AS (
    SELECT CAST(yr AS VARCHAR) AS yr, country_g AS country, customer_id, invoice, revenue FROM sales_c
    UNION ALL SELECT 'All', country_g, customer_id, invoice, revenue FROM sales_c
    UNION ALL SELECT CAST(yr AS VARCHAR), 'All', customer_id, invoice, revenue FROM sales_c
    UNION ALL SELECT 'All', 'All', customer_id, invoice, revenue FROM sales_c
),
per_cust AS (SELECT yr, country, customer_id, COUNT(DISTINCT invoice) AS n_orders FROM keys GROUP BY yr, country, customer_id)
SELECT yr, country, COUNT(*) AS customers, AVG(CASE WHEN n_orders > 1 THEN 1.0 ELSE 0 END) AS repeat_rate FROM per_cust GROUP BY yr, country;

-- top products and customers for every (year, country)
CREATE OR REPLACE TABLE top_products AS
WITH keys AS (
    SELECT CAST(yr AS VARCHAR) AS yr, country_g AS country, stock_code, revenue, quantity FROM sales_c
    UNION ALL SELECT 'All', country_g, stock_code, revenue, quantity FROM sales_c
    UNION ALL SELECT CAST(yr AS VARCHAR), 'All', stock_code, revenue, quantity FROM sales_c
    UNION ALL SELECT 'All', 'All', stock_code, revenue, quantity FROM sales_c
),
agg AS (SELECT yr, country, stock_code, SUM(revenue) AS revenue, SUM(quantity) AS units FROM keys GROUP BY ALL),
ranked AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY yr, country ORDER BY revenue DESC) AS rk FROM agg)
SELECT r.yr, r.country, r.rk, r.stock_code,
       (SELECT description FROM raw d WHERE d.stock_code = r.stock_code AND d.description IS NOT NULL
        GROUP BY description ORDER BY COUNT(*) DESC LIMIT 1) AS description,
       r.revenue, r.units
FROM ranked r WHERE rk <= 10 ORDER BY yr, country, rk;

CREATE OR REPLACE TABLE top_customers AS
WITH keys AS (
    SELECT CAST(yr AS VARCHAR) AS yr, country_g AS country, customer_id, revenue FROM sales_c
    UNION ALL SELECT 'All', country_g, customer_id, revenue FROM sales_c
    UNION ALL SELECT CAST(yr AS VARCHAR), 'All', customer_id, revenue FROM sales_c
    UNION ALL SELECT 'All', 'All', customer_id, revenue FROM sales_c
),
agg AS (SELECT yr, country, customer_id, SUM(revenue) AS revenue FROM keys GROUP BY ALL),
tot AS (SELECT yr, country, SUM(revenue) AS total FROM agg GROUP BY yr, country),
ranked AS (SELECT a.*, t.total, ROW_NUMBER() OVER (PARTITION BY a.yr, a.country ORDER BY a.revenue DESC) AS rk FROM agg a JOIN tot t USING (yr, country))
SELECT yr, country, rk, customer_id, revenue, revenue / total AS share FROM ranked WHERE rk <= 10 ORDER BY yr, country, rk;
