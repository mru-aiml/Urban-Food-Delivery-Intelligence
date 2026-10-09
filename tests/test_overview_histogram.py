"""Regression test for the production /api/overview broadcast error.

Uses the real dataset (data/zomato_cleaned.csv, 38,964 rows x 22 cols).
Verifies the delivery-time histogram:
  - does not raise an exception,
  - has exactly 20 bins and 21 edges,
  - bin counts sum to the number of valid observations,
  - matches the bins=20 reference result exactly.

Run: pytest tests/test_overview_histogram.py
"""
import numpy as np

from preprocessing.loader import load_raw
from preprocessing.cleaner import clean
from preprocessing.feature_engineering import engineer
from analytics.overview import overview_charts, overview_stats


def _load_df():
    raw, meta = load_raw()
    assert meta["rows"] == 38964, f"expected 38964 rows, got {meta['rows']}"
    assert meta["cols"] == 22, f"expected 22 cols, got {meta['cols']}"
    cdf, _ = clean(raw)
    edf, _ = engineer(cdf)
    return edf


def test_time_distribution_histogram():
    df = _load_df()
    s = df["_dtime"].dropna()
    n_valid = len(s)
    assert n_valid > 0

    charts = overview_charts(df)  # must not raise
    series = charts["time_distribution"]
    assert len(series) == 20

    values = [r["value"] for r in series]
    labels = [r["label"] for r in series]
    assert len(labels) == len(values)
    assert sum(values) == n_valid

    # identical to the bins=20 reference computation
    h_ref, e_ref = np.histogram(s, bins=20)
    assert len(e_ref) == 21
    assert values == [int(v) for v in h_ref]


def test_overview_kpis_unchanged():
    df = _load_df()
    k = overview_stats(df)
    assert k["total_orders"] == 38964
    assert k["avg_delivery_time"] == 26.58
    assert k["median_delivery_time"] == 26.0
    assert k["avg_distance"] == 9.77
    assert k["avg_rating"] == 4.63
    assert k["delayed_orders"] == 7048
    assert k["on_time_pct"] == 81.91
    assert k["avg_speed"] == 23.59
