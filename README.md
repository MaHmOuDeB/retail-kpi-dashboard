# Retail KPI Dashboard

[![CI](https://github.com/MaHmOuDeB/retail-kpi-dashboard/actions/workflows/ci.yml/badge.svg)](https://github.com/MaHmOuDeB/retail-kpi-dashboard/actions/workflows/ci.yml)
![License](https://img.shields.io/badge/license-MIT-green)

An interactive sales dashboard for a UK online gift retailer, Dec 2009 to Dec 2011: revenue, orders, customers, average
order value, repeat-customer rate and return rate, filterable by country and year, with year-on-year change, top products,
top customers and a CSV export.

**[Open the live dashboard](https://mahmoudeb.github.io/retail-kpi-dashboard/)**

![Dashboard](docs/img/dashboard.png)

*Rebuilt in 2026 from my Master's project "Sales KPI Dashboard" (2023). The original was a Power BI file, which only opens
in Power BI Desktop on Windows. This version is a web page anyone can open, and the KPI logic is written in SQL.*

## What the data says

- **Revenue was flat year on year.** January to November 2011 revenue was £7.68M versus £7.68M in 2010 (-0.03%), with 2.8%
  fewer orders and a 2.8% higher average order value.
- **Returns grew.** On the same January to November months, cancelled value rose 29% and the return rate went from 2.9% to
  3.7% of sales. The data also ends nine days into December 2011, and in those nine days cancellations were £174k against £513k
  of sales (34%), which is why the full-year 2011 return rate reads 5.6%. The dashboard flags this on the card.
- **Strong seasonality.** The best month is November in both years (£1.16M in 2010, £1.14M in 2011).
- **Concentrated in one market and a few accounts.** The United Kingdom is 84% of revenue; the 10 largest customers are 16%.

## How it works

1. `sql/01_clean.sql` cleans the raw invoice lines: drops lines without a customer ID, separates cancellations, keeps real
   products only.
2. `sql/02_kpis.sql` pre-aggregates monthly and yearly KPIs, top products and top customers in DuckDB, once for every country
   and year, so distinct counts such as customers are exact for any filter.
3. `src/build_data.py` writes the result to `docs/data.json` (about 130 KB).
4. `docs/index.html` is a static page (Chart.js) that reads that file. There is no server and no build step, so it runs on
   GitHub Pages. It follows the system light or dark theme, works on a phone, and has keyboard focus styles and chart labels.
5. `tests/` checks that country figures add up to the total, that rankings are ordered and that rates are valid.

## KPI definitions

| KPI | Definition |
|---|---|
| Revenue | Quantity x unit price on real product lines (postage, fees and manual adjustments excluded) |
| Orders | Distinct invoices |
| Customers | Distinct registered customers who ordered in the period |
| Average order value | Revenue / orders |
| Repeat customers | Share of customers with more than one order in the period |
| Return rate | Value of cancelled invoices / sales value |
| Year-on-year change | 2011 versus 2010 for January to November, the months both years have in full |

## Limits

- 23% of invoice lines have no customer ID, so customer counts and repeat rates describe registered customers only.
- No cost data in the source, so there is no margin view (the original Power BI project had one).
- December 2009 and December 2011 are partial months.
- Returns are assigned to the country of the customer's orders.
- Customers can order from more than one country, so country customer counts are not strictly additive.

## Reproduce

```bash
make setup   # pip install -r requirements.txt
make data    # downloads UCI Online Retail II (45 MB) and converts it to Parquet
make build   # runs the SQL, rewrites docs/data.json
make serve   # http://localhost:8000
make test
```

Data: Chen, D. (2012). Online Retail II. UCI Machine Learning Repository, CC BY 4.0.
