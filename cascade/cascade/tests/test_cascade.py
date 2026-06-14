"""CASCADE contract tests - enrichment physics and the gap pipeline."""
import numpy as np
import pytest

import cascade as C
from cascade import enrichment as E


# ------------------------------ enrichment ---------------------------------
def test_value_function_zero_at_half_and_symmetric():
    assert E.value_function(0.5) == pytest.approx(0.0, abs=1e-9)
    assert E.value_function(0.05) == pytest.approx(E.value_function(0.95), rel=1e-9)


def test_value_function_rejects_bad_assay():
    with pytest.raises(ValueError):
        E.value_function(0.0)
    with pytest.raises(ValueError):
        E.value_function(1.0)


def test_mass_balance_feed_equals_product_plus_tails():
    r = E.enrichment_requirements(10.0, 0.05)
    assert r["feed_kg"] == pytest.approx(r["product_kg"] + r["tails_kg"], rel=1e-9)
    # feed_factor = 1 + tails_factor
    assert E.feed_factor(0.05) == pytest.approx(1 + E.tails_factor(0.05), rel=1e-9)


def test_swu_factor_known_magnitudes():
    # 4.4% LEU at 0.25% tails is the textbook ~6.7 SWU/kg case
    assert 6.0 < E.swu_factor(0.044) < 7.5
    # 19.75% HALEU is far more SWU-intensive
    assert 35.0 < E.swu_factor(0.1975) < 50.0


def test_swu_and_feed_increase_with_assay():
    assays = [0.02, 0.05, 0.10, 0.1975]
    swu = [E.swu_factor(a) for a in assays]
    feed = [E.feed_factor(a) for a in assays]
    assert all(swu[i] < swu[i + 1] for i in range(len(swu) - 1))
    assert all(feed[i] < feed[i + 1] for i in range(len(feed) - 1))


def test_haleu_ceiling_enforced():
    with pytest.raises(ValueError):
        E.enrichment_requirements(1.0, 0.90)        # weapons-grade -> refused
    with pytest.raises(ValueError):
        E.enrichment_requirements(1.0, 0.25)        # above 20% HALEU ceiling


def test_tails_must_be_below_feed():
    with pytest.raises(ValueError):
        E.enrichment_requirements(1.0, 0.05, xw=0.01)   # tails > natural feed


# -------------------------------- demand -----------------------------------
def test_demand_shape_and_scaling():
    d1 = C.demand.annual_demand(start_year=2027, end_year=2040, units_multiplier=1.0)
    d2 = C.demand.annual_demand(start_year=2027, end_year=2040, units_multiplier=2.0)
    assert list(d1.columns) == ["year", "haleu_tonnes", "swu_kswu"]
    assert (d1["haleu_tonnes"] >= 0).all()
    # demand scales linearly with the units multiplier
    assert d2["haleu_tonnes"].sum() == pytest.approx(2 * d1["haleu_tonnes"].sum(), rel=1e-9)


def test_delay_shifts_demand_later():
    base = C.demand.annual_demand(start_year=2027, end_year=2040, delay_years=0)
    delayed = C.demand.annual_demand(start_year=2027, end_year=2040, delay_years=3)
    # cumulative demand by mid-horizon is lower when deployment slips
    assert delayed["haleu_tonnes"].cumsum().iloc[5] <= base["haleu_tonnes"].cumsum().iloc[5]


# -------------------------------- supply -----------------------------------
def test_capacity_monotonic_nondecreasing():
    cap = C.supply.capacity_curve(2027, 2040)["capacity_tonnes"].to_numpy()
    assert np.all(np.diff(cap) >= -1e-9)


# --------------------------------- gap -------------------------------------
def test_deterministic_gap_definition():
    d = C.demand.annual_demand(start_year=2027, end_year=2040)
    s = C.supply.capacity_curve(2027, 2040)
    g = C.gap.deterministic_gap(d, s)
    expected = np.clip(g["haleu_tonnes"] - g["capacity_tonnes"], 0, None)
    assert np.allclose(g["gap_tonnes"], expected)


def test_monte_carlo_bands_ordered_and_probabilities_valid():
    mc = C.gap.monte_carlo_gap(start_year=2027, end_year=2040, n_sims=200, seed=1)
    assert (mc["gap_p10"] <= mc["gap_p50"] + 1e-9).all()
    assert (mc["gap_p50"] <= mc["gap_p90"] + 1e-9).all()
    assert mc["prob_shortfall"].between(0, 1).all()
