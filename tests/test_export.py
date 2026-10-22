"""Tests for the site export (src/export_site.py).

Most tests read only committed files (docs/data.json and reports/site/retail.json), so they run in CI. The reversal tests run the
cleaning SQL on a few synthetic invoices. The last one re-runs the export and needs the local dataset (set DATA_DIR, default data/).
"""
import json
import os
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
from test_clean import row, run  # noqa: E402

from export_site import build_export, dump, largest_reversals, main, monthly_rows, yoy  # noqa: E402

DASHBOARD = json.loads((ROOT / "docs" / "data.json").read_text())
EXPORT_PATH = ROOT / "reports" / "site" / "retail.json"
DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))
if not DATA_DIR.is_absolute():
    DATA_DIR = ROOT / DATA_DIR
PARQUET, XLSX = DATA_DIR / "online_retail_ii.parquet", DATA_DIR / "online_retail_II.xlsx"
MONTHS = [f"{y}-{m:02d}" for y in (2009, 2010, 2011) for m in range(1, 13)][11:36]


@pytest.fixture(scope="module")
def export() -> dict:
    return json.loads(EXPORT_PATH.read_text())


@pytest.fixture(scope="module")
def monthly(export) -> list[dict]:
    return export["tables"]["monthly"]


def test_committed_export_round_trips():
    text = EXPORT_PATH.read_text()
    assert dump(json.loads(text)) == text


def test_dump_is_canonical():
    assert dump({"b": [1, 2], "a": "é"}) == '{\n "a": "é",\n "b": [\n  1,\n  2\n ]\n}\n'
    with pytest.raises(ValueError):
        dump({"x": float("nan")})


def test_meta(export):
    meta = export["_meta"]
    assert meta["schema"] == "retail/1" and meta["source"] == "retail" and meta["provenance"] == "public-data"
    assert meta["dataset"] == {"name": "UCI Online Retail II", "url": "https://archive.ics.uci.edu/dataset/502/online+retail+ii", "licence": "CC BY 4.0"}
    # the same workbook as the retention export: Task 7 records this hash
    assert meta["inputs"] == [{"path": "data/online_retail_II.xlsx", "rows": 1067371, "sha256": "bcbe73b35f5b7babf197fb0cb983a11f5d9ff929078d4aa53d171b1f2df2e980"}]
    assert "generated" not in json.dumps(meta).lower()


def test_monthly_has_25_months_and_marks_the_partial_one(monthly):
    assert [r["month"] for r in monthly] == MONTHS
    assert monthly[0]["month"] == "2009-12" and monthly[-1]["month"] == "2011-12"
    assert [r["month"] for r in monthly if r["partial"]] == ["2011-12"]
    assert all(set(r) == {"month", "sales_gbp_raw", "returns_gbp_raw", "sales_gbp_clean", "returns_gbp_clean", "partial"} for r in monthly)
    assert all(isinstance(r[k], int) for r in monthly for k in ("sales_gbp_raw", "returns_gbp_raw", "sales_gbp_clean", "returns_gbp_clean"))


def test_clean_months_equal_the_dashboard_data(monthly):
    """The cleaned series is the dashboard's 'All' row; GBP is rounded to whole pounds here, so the match is within half a pound."""
    dashboard = {r["ym"]: r for r in DASHBOARD["monthly"] if r["country"] == "All"}
    assert sorted(dashboard) == MONTHS
    for r in monthly:
        d = dashboard[r["month"]]
        assert abs(r["sales_gbp_clean"] - d["revenue"]) <= 0.5 + 0.01, r["month"]
        assert abs(r["returns_gbp_clean"] - d["returns"]) <= 0.5 + 0.01, r["month"]


def test_raw_is_at_least_clean_in_every_month(monthly):
    for r in monthly:
        assert r["sales_gbp_raw"] >= r["sales_gbp_clean"], r["month"]
        assert r["returns_gbp_raw"] >= r["returns_gbp_clean"], r["month"]


def test_yoy_facts_equal_the_committed_table_to_4dp(export, monthly):
    facts = export["facts"]
    for kind in ("raw", "clean"):
        y = yoy(monthly, kind)
        assert set(y) == {"returns_growth", "return_rate_2010", "return_rate_2011", "revenue_growth"}
        assert facts[f"returns.yoy_growth_{kind}"]["value"] == round(y["returns_growth"], 4)
        assert facts[f"returns.rate_2010_{kind}"]["value"] == round(y["return_rate_2010"], 4)
        assert facts[f"returns.rate_2011_{kind}"]["value"] == round(y["return_rate_2011"], 4)
    assert facts["revenue.yoy_growth_clean"]["value"] == round(yoy(monthly, "clean")["revenue_growth"], 4)
    inflation = sum(r["sales_gbp_raw"] for r in monthly) / sum(r["sales_gbp_clean"] for r in monthly) - 1
    assert facts["revenue.inflation_share"]["value"] == round(inflation, 4)


def test_headline_anchors(export):
    f = export["facts"]
    assert round(f["returns.yoy_growth_raw"]["value"] * 100) == 29
    assert round(f["returns.yoy_growth_clean"]["value"] * 100) == 2


def test_verified_fact_values(export):
    f = export["facts"]
    assert {k: v["value"] for k, v in f.items()} == {
        "returns.yoy_growth_raw": 0.2903, "returns.yoy_growth_clean": 0.0239,
        "returns.rate_2010_clean": 0.0209, "returns.rate_2011_clean": 0.0217,
        "returns.rate_2010_raw": 0.0285, "returns.rate_2011_raw": 0.0368,
        "revenue.yoy_growth_clean": -0.0134, "revenue.inflation_share": 0.0239,
        "reversal.largest_gbp": 168470, "reversal.january_gbp": 77184,
    }


def test_fact_display(export):
    for name, fact in export["facts"].items():
        assert set(fact) <= {"value", "unit", "decimals", "label", "from", "scale"}, name
        if name.startswith("reversal."):
            assert (fact["unit"], fact["scale"], fact["decimals"]) == ("gbp", "k", 0), name
        else:
            assert fact["unit"] == "share" and "scale" not in fact, name
            assert fact["decimals"] == (1 if name.split(".")[1].startswith("rate_") else 0), name
        assert re.fullmatch(r"[a-z]+\.[a-z0-9_]+", name)


def test_largest_reversals_are_dates_and_values_only(export):
    rows = export["tables"]["largest_reversals"]
    assert rows == [{"date": "2011-12-09", "value_gbp": 168470}, {"date": "2011-01-18", "value_gbp": 77184}, {"date": "2011-06-10", "value_gbp": 38970}]
    f = export["facts"]
    assert f["reversal.largest_gbp"]["value"] == rows[0]["value_gbp"]
    assert f["reversal.january_gbp"]["value"] == rows[1]["value_gbp"] and rows[1]["date"].startswith("2011-01")


def test_no_customer_or_invoice_identifiers(export):
    def keys(node):
        if isinstance(node, dict):
            for k, v in node.items():
                yield k
                yield from keys(v)
        elif isinstance(node, list):
            for v in node:
                yield from keys(v)

    assert {k for k in keys(export) if "customer" in k or "invoice" in k} == set()


def test_build_export_has_no_timestamp_and_is_deterministic(export, monthly):
    reversals = export["tables"]["largest_reversals"]
    a = dump(build_export(monthly, reversals, "0" * 64, 5))
    assert a == dump(build_export(monthly, reversals, "0" * 64, 5))
    assert not re.search(r"\d{4}-\d{2}-\d{2}T|generated|timestamp", a)


# --- the reversal rule on synthetic invoices -------------------------------------------------------------------------------------------------


def test_reversal_within_24_hours_moves_value_from_clean_to_raw_only():
    con = run([
        row("A1", "10001", 100, "2011-01-18 10:00", price=2.0),  # 200 sold ...
        row("C2", "10001", -100, "2011-01-18 10:05", price=2.0),  # ... and cancelled 5 minutes later
        row("A3", "10002", 10, "2011-01-20 09:00", price=3.0),  # a normal sale of 30
        row("A4", "10003", 5, "2011-01-05 09:00", price=2.0),  # a genuine return later: stays in both
        row("C5", "10003", -5, "2011-01-25 09:00", price=2.0),
    ])
    jan = next(r for r in monthly_rows(con) if r["month"] == "2011-01")
    assert (jan["sales_gbp_raw"], jan["sales_gbp_clean"]) == (200 + 30 + 10, 30 + 10)
    assert (jan["returns_gbp_raw"], jan["returns_gbp_clean"]) == (200 + 10, 10)


def test_reversal_that_crosses_midnight_is_still_a_reversal():
    con = run([row("A1", "10001", 10, "2011-02-28 23:30", price=4.0), row("C2", "10001", -10, "2011-03-01 08:00", price=4.0)])
    rows = {r["month"]: r for r in monthly_rows(con)}
    assert (rows["2011-02"]["sales_gbp_raw"], rows["2011-02"]["sales_gbp_clean"]) == (40, 0)
    assert (rows["2011-03"]["returns_gbp_raw"], rows["2011-03"]["returns_gbp_clean"]) == (40, 0)


def test_cancellation_after_more_than_24_hours_is_not_a_reversal():
    con = run([row("A1", "10001", 10, "2011-02-27 08:00", price=4.0), row("C2", "10001", -10, "2011-02-28 09:00", price=4.0)])
    feb = next(r for r in monthly_rows(con) if r["month"] == "2011-02")
    assert (feb["sales_gbp_raw"], feb["sales_gbp_clean"], feb["returns_gbp_raw"], feb["returns_gbp_clean"]) == (40, 40, 40, 40)


def test_monthly_rows_always_has_the_25_months_and_flags_only_december_2011():
    rows = monthly_rows(run([row("A1", "10001", 1, "2010-06-01 10:00", price=5.0)]))
    assert [r["month"] for r in rows] == MONTHS
    assert [r["month"] for r in rows if r["partial"]] == ["2011-12"]
    assert next(r for r in rows if r["month"] == "2010-06")["sales_gbp_clean"] == 5
    assert next(r for r in rows if r["month"] == "2010-07") == {"month": "2010-07", "sales_gbp_raw": 0, "returns_gbp_raw": 0, "sales_gbp_clean": 0, "returns_gbp_clean": 0, "partial": False}


def test_largest_reversals_lists_dates_and_values_largest_first():
    con = run([
        row("A1", "10001", 10, "2011-01-18 10:00", price=2.0), row("C1", "10001", -10, "2011-01-18 11:00", price=2.0),
        row("A2", "10002", 100, "2011-12-09 10:00", price=2.0), row("C2", "10002", -100, "2011-12-09 11:00", price=2.0),
        row("A3", "10003", 50, "2011-03-01 10:00", price=2.0), row("C3", "10003", -50, "2011-03-02 09:00", price=2.0),
        row("A4", "10004", 1, "2011-04-01 10:00", price=2.0), row("C4", "10004", -1, "2011-04-01 11:00", price=2.0),
    ])
    assert largest_reversals(con) == [
        {"date": "2011-12-09", "value_gbp": 200}, {"date": "2011-03-01", "value_gbp": 100}, {"date": "2011-01-18", "value_gbp": 20}]


def test_yoy_on_a_small_table():
    rows = [{"month": m, "sales_gbp_raw": 120, "returns_gbp_raw": 12, "sales_gbp_clean": 100, "returns_gbp_clean": 10, "partial": False} for m in MONTHS]
    for r in rows:
        if r["month"].startswith("2011") and r["month"] != "2011-12":
            r.update(sales_gbp_raw=240, returns_gbp_raw=24, sales_gbp_clean=110, returns_gbp_clean=11)
    raw, clean = yoy(rows, "raw"), yoy(rows, "clean")
    assert raw == pytest.approx({"returns_growth": 1.0, "return_rate_2010": 0.1, "return_rate_2011": 0.1, "revenue_growth": 1.0})
    assert clean == pytest.approx({"returns_growth": 0.1, "return_rate_2010": 0.1, "return_rate_2011": 0.1, "revenue_growth": 0.1})


@pytest.mark.skipif(not (PARQUET.exists() and XLSX.exists()), reason="needs the local dataset (make data, or set DATA_DIR)")
def test_export_twice_is_byte_identical(tmp_path):
    first, second = tmp_path / "a.json", tmp_path / "b.json"
    main(DATA_DIR, first)
    main(DATA_DIR, second)
    assert first.read_bytes() == second.read_bytes()
    assert first.read_text() == EXPORT_PATH.read_text()
