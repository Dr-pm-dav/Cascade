"""
Tails-assay economics.

The tails assay (how much U-235 is left in the depleted stream) is the central
economic lever in enrichment. A lower tails assay extracts more U-235 from each
kilogram of feed, so it needs less natural uranium but more separative work; a
higher tails assay does the reverse. The cost-minimising choice depends only on
the feed assay and the ratio of the uranium price to the SWU price.

This module turns that into analysis:
  - the cost-optimal tails for a given pair of prices,
  - the cost breakdown (feed vs SWU) for a product order,
  - the optimal-tails-versus-price-ratio curve,
  - a historical comparison of the cost-optimal tails against the tails the U.S.
    fleet appears to have actually operated at, both derived from real EIA data.

All relations build on the exact value-function physics in ``enrichment``.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import enrichment as E

NATURAL_U = E.NATURAL_U


def unit_cost(xw, xp, price_per_kgU, price_per_swu, xf=NATURAL_U):
    """Cost to produce 1 kg of product at tails ``xw`` (feed cost + SWU cost)."""
    return (E.feed_factor(xp, xf, xw) * price_per_kgU
            + E.swu_factor(xp, xf, xw) * price_per_swu)


def optimal_tails(price_per_kgU, price_per_swu, xf=NATURAL_U, xp=0.045, grid=4000):
    """Cost-optimal tails assay and the resulting unit product cost.

    Returns (tails_fraction, unit_cost). The optimum is only weakly dependent on
    the product assay ``xp``; it is driven by the feed assay and the price ratio.
    """
    xs = np.linspace(0.0003, xf * 0.97, grid)
    cost = unit_cost(xs, xp, price_per_kgU, price_per_swu, xf)
    i = int(np.argmin(cost))
    return float(xs[i]), float(cost[i])


def cost_breakdown(product_kg, xp, price_per_kgU, price_per_swu, xw, xf=NATURAL_U):
    """Feed and SWU quantities and costs for a product order at tails ``xw``."""
    ff = E.feed_factor(xp, xf, xw)
    sf = E.swu_factor(xp, xf, xw)
    feed_cost = ff * price_per_kgU * product_kg
    swu_cost = sf * price_per_swu * product_kg
    total = feed_cost + swu_cost
    return {
        "feed_kg": float(ff * product_kg),
        "swu": float(sf * product_kg),
        "feed_cost": float(feed_cost),
        "swu_cost": float(swu_cost),
        "total_cost": float(total),
        "unit_cost_per_kg": float(total / product_kg),
        "feed_cost_share": float(feed_cost / total) if total else float("nan"),
    }


def optimal_curve(price_ratios, xf=NATURAL_U, xp=0.045):
    """Cost-optimal tails as a function of the uranium/SWU price ratio.

    ``price_ratios`` are ($/kgU) / ($/SWU). Returns a DataFrame: ratio, tails.
    """
    rows = []
    for r in np.asarray(price_ratios, dtype="float64"):
        t, _ = optimal_tails(r, 1.0, xf=xf, xp=xp)   # only the ratio matters
        rows.append((float(r), t))
    return pd.DataFrame(rows, columns=["price_ratio_kgU_per_swu", "optimal_tails"])


def implied_operating_tails(feed_per_swu, xf=NATURAL_U, xp=0.045, grid=4000):
    """Tails assay reproducing an observed feed:SWU ratio (kg U per SWU).

    The feed:SWU ratio implied by real deliveries pins the operating tails for a
    given product assay. Sensitive to the assumed ``xp`` and to feed/SWU timing,
    so treat as an indicator, not a measurement.
    """
    xs = np.linspace(0.0010, 0.0030, grid)
    ratio = E.feed_factor(xp, xf, xs) / E.swu_factor(xp, xf, xs)
    return float(xs[int(np.argmin(np.abs(ratio - feed_per_swu)))])


def historical_tails(uranium_price_df, enrichment_df, xp=0.045):
    """Per-year cost-optimal tails (from EIA prices) vs implied operating tails.

    Inputs are the EIA connector frames. Returns a DataFrame: year,
    price_ratio, optimal_tails, implied_tails, feed_per_swu. Years require both a
    uranium price and an SWU price; implied_tails additionally needs feed and SWU
    quantities.
    """
    u = uranium_price_df[["year", "usd_per_kgU"]]
    e = enrichment_df[["year", "price_usd_swu", "feed_tU", "swu_total_m"]]
    m = u.merge(e, on="year", how="inner").dropna(subset=["usd_per_kgU", "price_usd_swu"])
    rows = []
    for _, r in m.iterrows():
        ratio = r["usd_per_kgU"] / r["price_usd_swu"]
        opt, _ = optimal_tails(r["usd_per_kgU"], r["price_usd_swu"], xp=xp)
        if pd.notna(r["feed_tU"]) and pd.notna(r["swu_total_m"]) and r["swu_total_m"] > 0:
            fps = (r["feed_tU"] * 1000.0) / (r["swu_total_m"] * 1e6)
            imp = implied_operating_tails(fps, xp=xp)
        else:
            fps, imp = np.nan, np.nan
        rows.append((int(r["year"]), float(ratio), opt, imp, fps))
    return pd.DataFrame(rows, columns=["year", "price_ratio", "optimal_tails",
                                       "implied_tails", "feed_per_swu"])
