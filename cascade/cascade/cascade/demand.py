"""
HALEU demand from the advanced-reactor deployment pipeline.

Translates the reactor fleet into an annual HALEU mass requirement (tonnes
U-235-bearing HALEU) and the corresponding separative-work demand (SWU),
using the enrichment physics in ``enrichment``. Each unit contributes its
first core in its deployment year, then annual reloads thereafter. A scenario
multiplier scales fleet build-out optimism; a uniform deployment delay shifts
every first core later (the dominant real-world uncertainty).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import enrichment
from .reactors import load_fleet


def annual_demand(fleet=None, *, start_year=2027, end_year=2040,
                  units_multiplier=1.0, delay_years=0, tails=enrichment.DEFAULT_TAILS):
    """Annual HALEU (tonnes) and SWU (kSWU) demand over a horizon.

    Returns a DataFrame: year, haleu_tonnes, swu_kswu.
    ``units_multiplier`` scales every reactor's masses (a proxy for how many
    units of each design deploy); ``delay_years`` shifts first cores later.
    """
    if fleet is None:
        fleet = load_fleet()
    years = np.arange(start_year, end_year + 1)
    haleu = np.zeros(len(years), dtype="float64")
    swu = np.zeros(len(years), dtype="float64")

    for _, r in fleet.iterrows():
        deploy = int(r["target_year"]) + int(delay_years)
        xp = float(r["xp"])
        sf = enrichment.swu_factor(xp, xw=tails)        # SWU per kg product
        for i, y in enumerate(years):
            mass_t = 0.0
            if y == deploy:
                mass_t += float(r["first_core_haleu_t"])
            if y > deploy:
                mass_t += float(r["annual_reload_haleu_t"])
            mass_t *= units_multiplier
            haleu[i] += mass_t
            swu[i] += sf * mass_t * 1000.0 / 1000.0   # SWU/kg * (t*1000 kg) -> SWU; /1000 -> kSWU
    return pd.DataFrame({"year": years, "haleu_tonnes": haleu, "swu_kswu": swu})


def cumulative_demand(demand: pd.DataFrame):
    """Add cumulative HALEU and SWU columns to a demand frame."""
    out = demand.copy()
    out["haleu_tonnes_cum"] = out["haleu_tonnes"].cumsum()
    out["swu_kswu_cum"] = out["swu_kswu"].cumsum()
    return out
