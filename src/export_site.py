"""Write ``reports/site/retail.json``, the export the portfolio site reads: the returns series before and after the 24-hour reversal rule.

Run after ``make data`` (or point it at a folder that has the two data files)::

    make export                      # reads data/
    make export DATA_DIR=../elsewhere/data

The file holds monthly sales and returns twice, once with every invoice line (raw: ``sales_all`` and ``returns_all``) and once after the
rule in ``sql/01_clean.sql`` (clean: ``sales`` and ``returns``), plus the three largest reversed orders by date and value. It holds no
invoice numbers, no customer IDs and no generation time, and is written as canonical JSON, so two runs give the same bytes.
"""
from __future__ import annotations

import hashlib
import json
import platform
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "reports" / "site" / "retail.json"
EXPECTED_XLSX_SHA256 = "bcbe73b35f5b7babf197fb0cb983a11f5d9ff929078d4aa53d171b1f2df2e980"  # the workbook the retention export records too
FIRST_MONTH, LAST_MONTH = "2009-12", "2011-12"  # December 2011 is partial: the data ends on 9 Dec
MONTHS = [f"{y}-{m:02d}" for y in (2009, 2010, 2011) for m in range(1, 13)][11:36]
JAN_TO_NOV = {2010: [f"2010-{m:02d}" for m in range(1, 12)], 2011: [f"2011-{m:02d}" for m in range(1, 12)]}
GBP_KEYS = ("sales_gbp_raw", "returns_gbp_raw", "sales_gbp_clean", "returns_gbp_clean")


def dump(obj: dict) -> str:
    """Canonical JSON: sorted keys, one-space indent, no NaN, trailing newline."""
    return json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=False, allow_nan=False) + "\n"


def _by_month(con: duckdb.DuckDBPyConnection, table: str, date_col: str, value_col: str) -> dict[str, float]:
    sql = f"SELECT strftime({date_col}, '%Y-%m'), SUM({value_col}) FROM {table} GROUP BY 1"
    return {month: float(total) for month, total in con.execute(sql).fetchall()}


def monthly_rows(con: duckdb.DuckDBPyConnection) -> list[dict]:
    """One row per month, 2009-12 to 2011-12 (25), in whole pounds. A month with no invoices is 0, never missing."""
    series = {
        "sales_gbp_raw": _by_month(con, "sales_all", "invoice_date", "revenue"),
        "returns_gbp_raw": _by_month(con, "returns_all", "return_date", "return_value"),
        "sales_gbp_clean": _by_month(con, "sales", "invoice_date", "revenue"),
        "returns_gbp_clean": _by_month(con, "returns", "return_date", "return_value"),
    }
    return [{"month": m, **{k: int(round(series[k].get(m, 0.0))) for k in GBP_KEYS}, "partial": m == LAST_MONTH} for m in MONTHS]


def largest_reversals(con: duckdb.DuckDBPyConnection, n: int = 3) -> list[dict]:
    """The n reversed orders with the most value, largest first, as date (the day the order was placed) and whole pounds. No invoice numbers."""
    sql = """
        SELECT MIN(s.invoice_date) AS day, SUM(s.revenue) AS value
        FROM sales_all s
        WHERE EXISTS (SELECT 1 FROM reversed_pairs p WHERE p.order_invoice = s.invoice AND p.stock_code = s.stock_code)
        GROUP BY s.invoice
        ORDER BY value DESC, day, s.invoice
        LIMIT ?
    """
    return [{"date": day.isoformat(), "value_gbp": int(round(value))} for day, value in con.execute(sql, [n]).fetchall()]


def yoy(rows: list[dict], kind: str) -> dict:
    """January to November 2011 against the same months of 2010 (the months both years have in full). kind is "raw" or "clean"."""
    if kind not in ("raw", "clean"):
        raise ValueError(f"kind must be 'raw' or 'clean', not {kind!r}")
    by_month = {r["month"]: r for r in rows}

    def total(year: int, key: str) -> int:
        return sum(by_month[m][f"{key}_gbp_{kind}"] for m in JAN_TO_NOV[year])

    sales10, sales11, returns10, returns11 = total(2010, "sales"), total(2011, "sales"), total(2010, "returns"), total(2011, "returns")
    return {
        "returns_growth": returns11 / returns10 - 1,
        "return_rate_2010": returns10 / sales10,
        "return_rate_2011": returns11 / sales11,
        "revenue_growth": sales11 / sales10 - 1,
    }


def _fact(value: float | int, unit: str, decimals: int, label: str, source: str, **extra) -> dict:
    return {"value": value, "unit": unit, "decimals": decimals, "label": label, "from": source, **extra}


def build_facts(rows: list[dict], reversals: list[dict]) -> dict:
    raw, clean = yoy(rows, "raw"), yoy(rows, "clean")
    inflation = sum(r["sales_gbp_raw"] for r in rows) / sum(r["sales_gbp_clean"] for r in rows) - 1
    window = "January to November 2011 against the same months of 2010"
    january = next(r for r in reversals if r["date"].startswith("2011-01"))
    return {
        "returns.yoy_growth_raw": _fact(round(raw["returns_growth"], 4), "share", 0, f"Growth in returns, {window}, without the 24-hour rule",
                                        "tables/monthly/returns_gbp_raw"),
        "returns.yoy_growth_clean": _fact(round(clean["returns_growth"], 4), "share", 0, f"Growth in returns, {window}, with the 24-hour rule",
                                          "tables/monthly/returns_gbp_clean"),
        "returns.rate_2010_clean": _fact(round(clean["return_rate_2010"], 4), "share", 1, "Returns as a share of sales, January to November 2010, with the rule",
                                         "tables/monthly/returns_gbp_clean"),
        "returns.rate_2011_clean": _fact(round(clean["return_rate_2011"], 4), "share", 1, "Returns as a share of sales, January to November 2011, with the rule",
                                         "tables/monthly/returns_gbp_clean"),
        "returns.rate_2010_raw": _fact(round(raw["return_rate_2010"], 4), "share", 1, "Returns as a share of sales, January to November 2010, without the rule",
                                       "tables/monthly/returns_gbp_raw"),
        "returns.rate_2011_raw": _fact(round(raw["return_rate_2011"], 4), "share", 1, "Returns as a share of sales, January to November 2011, without the rule",
                                       "tables/monthly/returns_gbp_raw"),
        "revenue.yoy_growth_clean": _fact(round(clean["revenue_growth"], 4), "share", 0, f"Growth in revenue, {window}, with the rule", "tables/monthly/sales_gbp_clean"),
        "revenue.inflation_share": _fact(round(inflation, 4), "share", 0, "How much the reversed orders inflate revenue over the whole period",
                                         "tables/monthly/sales_gbp_raw"),
        "reversal.largest_gbp": _fact(reversals[0]["value_gbp"], "gbp", 0, "Value of the largest reversed order", "tables/largest_reversals/0/value_gbp", scale="k"),
        "reversal.january_gbp": _fact(january["value_gbp"], "gbp", 0, "Value of the reversed order placed and cancelled in January 2011",
                                      f"tables/largest_reversals/{reversals.index(january)}/value_gbp", scale="k"),
    }


def build_export(rows: list[dict], reversals: list[dict], xlsx_sha256: str, raw_rows: int) -> dict:
    return {
        "_meta": {
            "schema": "retail/1", "source": "retail", "generator": "src/export_site.py",
            "inputs": [{"path": "data/online_retail_II.xlsx", "sha256": xlsx_sha256, "rows": raw_rows}],
            "engine": {"duckdb": duckdb.__version__, "python": ".".join(platform.python_version_tuple()[:2])},
            "dataset": {"name": "UCI Online Retail II", "url": "https://archive.ics.uci.edu/dataset/502/online+retail+ii", "licence": "CC BY 4.0"},
            "provenance": "public-data",
        },
        "facts": build_facts(rows, reversals),
        "tables": {"monthly": rows, "largest_reversals": reversals},
    }


def main(data_dir: Path = Path("data"), out: Path = OUT) -> None:
    data_dir = Path(data_dir).resolve()
    parquet, xlsx = data_dir / "online_retail_ii.parquet", data_dir / "online_retail_II.xlsx"
    digest = hashlib.sha256(xlsx.read_bytes()).hexdigest()
    if digest != EXPECTED_XLSX_SHA256:
        print(f"warning: {xlsx.name} has sha256 {digest}, expected {EXPECTED_XLSX_SHA256}; the export records the hash it saw", file=sys.stderr)
    con = duckdb.connect()
    con.execute("SET threads = 1")  # one thread, so ties and float sums never depend on scheduling
    con.execute((ROOT / "sql" / "01_clean.sql").read_text().replace("data/online_retail_ii.parquet", parquet.as_posix()))
    raw_rows = con.execute("SELECT COUNT(*) FROM raw").fetchone()[0]
    export = build_export(monthly_rows(con), largest_reversals(con), digest, raw_rows)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(dump(export))
    print(f"wrote {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data"))
