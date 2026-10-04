"""Consistency checks on the data behind the dashboard (docs/data.json)."""
import json
from pathlib import Path

D = json.loads((Path(__file__).resolve().parent.parent / "docs" / "data.json").read_text())


def test_country_revenue_adds_up_to_all_for_every_month():
    for ym in {r["ym"] for r in D["monthly"]}:
        parts = sum(r["revenue"] for r in D["monthly"] if r["ym"] == ym and r["country"] != "All")
        total = next(r["revenue"] for r in D["monthly"] if r["ym"] == ym and r["country"] == "All")
        assert abs(parts - total) < 1.0, ym


def test_orders_add_up_to_all():
    assert sum(r["orders"] for r in D["monthly"] if r["country"] == "All") == sum(r["orders"] for r in D["monthly"] if r["country"] != "All")


def test_repeat_rate_is_a_share():
    assert all(0 <= r["repeat_rate"] <= 1 for r in D["yearly"])


def test_top_lists_are_ranked_and_complete():
    for key in ("top_products", "top_customers"):
        groups = {}
        for r in D[key]:
            groups.setdefault((r["yr"], r["country"]), []).append(r)
        for rows in groups.values():
            revs = [r["revenue"] for r in sorted(rows, key=lambda r: r["rk"])]
            assert revs == sorted(revs, reverse=True) and len(rows) <= 10
