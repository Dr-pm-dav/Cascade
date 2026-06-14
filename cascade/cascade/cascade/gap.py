"""
HALEU supply-demand gap.

Compares advanced-reactor HALEU demand against domestic enrichment capacity,
deterministically and under Monte Carlo uncertainty. The dominant real-world
uncertainties are reactor deployment slips and the pace of the domestic
capacity ramp, so those are the sampled variables. The output is the unmet-HALEU
trajectory (tonnes) with uncertainty bands and the probability of shortfall by
year - the strategic question for the advanced-reactor fuel supply chain.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .demand import annual_demand
from .supply import capacity_curve
from .reactors import load_fleet


def deterministic_gap(demand_df, supply_df):
    """Merge demand and capacity; return per-year balance and unmet gap."""
    m = demand_df.merge(supply_df, on="year", how="inner")
    m["balance_tonnes"] = m["capacity_tonnes"] - m["haleu_tonnes"]
    m["gap_tonnes"] = np.clip(m["haleu_tonnes"] - m["capacity_tonnes"], 0, None)
    m["gap_tonnes_cum"] = m["gap_tonnes"].cumsum()
    return m


def first_shortfall_year(gap_df, col="gap_tonnes"):
    """First year with a positive (unmet) gap, or None."""
    hit = gap_df[gap_df[col] > 1e-9]
    return int(hit["year"].iloc[0]) if len(hit) else None


def monte_carlo_gap(fleet=None, *, start_year=2027, end_year=2040, n_sims=600,
                    seed=0, delay_choices=(0, 1, 2, 3),
                    delay_probs=(0.35, 0.35, 0.20, 0.10),
                    units_mean=1.0, units_sd=0.25,
                    base_tonnes=0.9, ramp_mean=0.55, ramp_sd=0.15, plateau=None,
                    tails=None):
    """Monte Carlo HALEU unmet-gap trajectory.

    Each simulation samples independent per-reactor deployment delays, a
    fleet build-out multiplier, and a domestic capacity ramp rate. ``tails``
    (if given) sets the tails assay used in the SWU side of demand. Returns a
    DataFrame: year, demand_p10/50/90, gap_p10/50/90 (unmet tonnes),
    prob_shortfall (fraction of sims with unmet HALEU that year).
    """
    if fleet is None:
        fleet = load_fleet()
    rng = np.random.default_rng(seed)
    years = np.arange(start_year, end_year + 1)
    demand = np.zeros((n_sims, len(years)))
    gaps = np.zeros((n_sims, len(years)))
    dkw = {} if tails is None else {"tails": tails}

    for s in range(n_sims):
        f = fleet.copy()
        f["target_year"] = f["target_year"].to_numpy() + rng.choice(
            delay_choices, size=len(f), p=delay_probs)
        um = max(0.1, float(rng.normal(units_mean, units_sd)))
        d = annual_demand(f, start_year=start_year, end_year=end_year,
                          units_multiplier=um, **dkw)
        rr = max(0.1, float(rng.normal(ramp_mean, ramp_sd)))
        sup = capacity_curve(start_year, end_year, base_tonnes=base_tonnes,
                             ramp_rate=rr, plateau_tonnes=plateau)
        dem = d["haleu_tonnes"].to_numpy()
        demand[s] = dem
        gaps[s] = np.clip(dem - sup["capacity_tonnes"].to_numpy(), 0, None)

    dp = np.percentile(demand, [10, 50, 90], axis=0)
    gp = np.percentile(gaps, [10, 50, 90], axis=0)
    return pd.DataFrame({
        "year": years,
        "demand_p10": dp[0], "demand_p50": dp[1], "demand_p90": dp[2],
        "gap_p10": gp[0], "gap_p50": gp[1], "gap_p90": gp[2],
        "prob_shortfall": (gaps > 1e-9).mean(axis=0),
    })
