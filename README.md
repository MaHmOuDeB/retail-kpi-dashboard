# Retail KPI Dashboard

An interactive sales dashboard for a UK online gift retailer (Dec 2009 to Dec 2011): revenue, orders, customers,
average order value, repeat-customer rate and return rate, filterable by country and year, with top products and
top customers. **Live demo:** _(added after publishing)_

Rebuilt in 2026 from my Master's project *Sales KPI Dashboard* (2023, Power BI). The original was a Power BI file, which
only opens in Power BI Desktop on Windows. This version is a web page anyone can open, with the KPI logic written in SQL.

## How it works

1. `sql/01_clean.sql` cleans the raw invoice lines (drops lines without a customer ID, separates cancellations, keeps
   real products only).
2. `sql/02_kpis.sql` pre-aggregates monthly and yearly KPIs, top products and top customers in DuckDB, once for every
   country and year, so distinct counts such as customers are exact for any filter.
3. `src/build_data.py` writes the result to `docs/data.json` (about 130 KB).
4. `docs/index.html` is a static page (Chart.js) that reads that file. No server is needed, so it runs on GitHub Pages.
5. `tests/` checks that country figures add up to the total, that rankings are ordered, and that rates are valid.

## KPI definitions

| KPI | Definition |
|---|---|
| Revenue | Quantity x unit price on real product lines (postage, fees and manual adjustments excluded) |
| Orders | Distinct invoices |
| Customers | Distinct registered customers who ordered in the period |
| Average order value | Revenue / orders |
| Repeat customers | Share of customers with more than one order in the period |
| Return rate | Value of cancelled invoices / sales value |

## Limits

- 23% of invoice lines have no customer ID, so customer counts and repeat rates describe registered customers only.
- No cost data in the source, so there is no margin view (the original Power BI project had one).
- December 2009 and December 2011 are partial months.
- Returns are assigned to the country of the customer's orders.
- Customers can order from more than one country, so country customer counts are not strictly additive.

## Run it

```bash
pip install -r requirements.txt
python src/prepare.py            # download the data first (UCI Online Retail II), converts it to Parquet
python src/build_data.py         # rebuilds docs/data.json
python -m http.server -d docs    # open http://localhost:8000
pytest
```

Data: Chen, D. (2012). Online Retail II [Dataset]. UCI Machine Learning Repository (CC BY 4.0).
