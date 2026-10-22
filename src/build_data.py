"""Run the SQL and write docs/data.json for the static dashboard.  python src/build_data.py [path/to/online_retail_ii.parquet]"""
import json
import os
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent


def rows_of(con, table):
    return con.execute(f"SELECT * FROM {table}").df().to_dict("records")


def clean(v):
    return round(v, 4) if isinstance(v, float) else v


def build(parquet="data/online_retail_ii.parquet"):
    """Run the SQL on the Parquet file and return the dashboard data as a dict (row order within a table is not guaranteed, see tests/test_export.py)."""
    con = duckdb.connect()
    sql_clean = (ROOT / "sql" / "01_clean.sql").read_text().replace("data/online_retail_ii.parquet", str(parquet))
    con.execute(sql_clean)
    con.execute((ROOT / "sql" / "02_kpis.sql").read_text())
    return {
        "meta": {"source": "UCI Online Retail II, 1 Dec 2009 to 9 Dec 2011", "first_month": "2009-12", "last_month": "2011-12",
                 "note": "December 2011 is a partial month (the data ends on 9 Dec)."},
        "monthly": [{k: clean(v) for k, v in r.items()} for r in rows_of(con, "monthly")],
        "yearly": [{k: clean(v) for k, v in r.items()} for r in rows_of(con, "yearly")],
        "top_products": [{k: clean(v) for k, v in r.items()} for r in rows_of(con, "top_products")],
        "top_customers": [{k: clean(v) for k, v in r.items()} for r in rows_of(con, "top_customers")],
        "countries": ["All"] + [r[0] for r in con.execute("SELECT country FROM top_countries").fetchall()] + ["Other countries"],
    }


if __name__ == "__main__":
    os.chdir(ROOT)
    out = build(sys.argv[1] if len(sys.argv) > 1 else "data/online_retail_ii.parquet")
    Path("docs/data.json").write_text(json.dumps(out, separators=(",", ":"), default=str))
    print({k: (len(v) if isinstance(v, list) else v) for k, v in out.items() if k != "meta"}, f"{Path('docs/data.json').stat().st_size/1024:.0f} KB")
