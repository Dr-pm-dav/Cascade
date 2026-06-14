"""Tails-economics tests."""
import numpy as np
import pandas as pd
import pytest

from cascade import tails as T
from cascade.connectors import LB_U3O8_TO_KGU


def test_optimal_tails_nearly_assay_independent():
    lo, _ = T.optimal_tails(137.0, 97.66, xp=0.044)
    hi, _ = T.optimal_tails(137.0, 97.66, xp=0.1975)
    assert lo == pytest.approx(hi, abs=2e-4)


def test_optimal_tails_falls_with_uranium_price():
    cheap_u, _ = T.optimal_tails(50.0, 100.0)    # cheap uranium -> strip less -> higher tails
    dear_u, _ = T.optimal_tails(250.0, 100.0)    # dear uranium  -> strip more -> lower tails
    assert cheap_u > dear_u


def test_cost_breakdown_consistency():
    cb = T.cost_breakdown(1000.0, 0.1975, 137.0, 97.66, 0.0020)
    assert cb["feed_cost"] + cb["swu_cost"] == pytest.approx(cb["total_cost"], rel=1e-9)
    assert 0.0 < cb["feed_cost_share"] < 1.0
    assert cb["unit_cost_per_kg"] == pytest.approx(cb["total_cost"] / 1000.0, rel=1e-9)


def test_optimal_curve_monotonic_non_increasing():
    curve = T.optimal_curve(np.linspace(0.5, 2.5, 12))
    t = curve["optimal_tails"].to_numpy()
    assert np.all(np.diff(t) <= 1e-6)


def test_historical_tails_shape_and_range():
    up = pd.DataFrame({"year": [2023, 2024],
                       "usd_per_lb_u3o8": [43.80, 52.71],
                       "usd_per_kgU": [43.80 / LB_U3O8_TO_KGU, 52.71 / LB_U3O8_TO_KGU]})
    en = pd.DataFrame({"year": [2023, 2024], "price_usd_swu": [106.97, 97.66],
                       "feed_tU": [13000.0, 16271.0], "swu_total_m": [15.2, 15.2]})
    h = T.historical_tails(up, en)
    assert list(h.columns) == ["year", "price_ratio", "optimal_tails",
                               "implied_tails", "feed_per_swu"]
    assert len(h) == 2
    assert (h["optimal_tails"].between(0.001, 0.004)).all()
