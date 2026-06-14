"""
Domestic HALEU enrichment-capacity supply.

A transparent ramp model for U.S. domestic HALEU output capacity (tonnes per
year). The reference trajectory starts from a small demonstration-scale output
and grows as new cascades come online under the DOE HALEU Availability Program,
optionally toward a plateau.

Numbers are ILLUSTRATIVE planning placeholders (demonstration-scale output in
the low single-digit tonnes/yr, scaling later this decade). Replace with vetted
program figures via ``capacity_curve(csv_path=...)``. SWU-side capacity is
derived from the HALEU tonnage at a reference product assay so demand and
supply can be compared in either unit.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import enrichment


def capacity_curve(start_year=2027, end_year=2040, *, base_tonnes=0.9,
                   start_ramp_year=2028, ramp_rate=0.55, plateau_tonnes=None,
                   ref_assay=0.1975, csv_path=None):
    """Annual domestic HALEU output capacity (tonnes) and SWU-equivalent (kSWU).

    Exponential ramp from ``base_tonnes`` beginning ``start_ramp_year`` at
    ``ramp_rate`` per year, optionally capped at ``plateau_tonnes``. With
    ``csv_path`` an override table (columns: year, haleu_tonnes) is used
    directly. Returns DataFrame: year, capacity_tonnes, capacity_kswu.
    """
    if csv_path:
        df = pd.read_csv(csv_path)
        years = df["year"].to_numpy()
        cap = df["haleu_tonnes"].to_numpy(dtype="float64")
    else:
        years = np.arange(start_year, end_year + 1)
        cap = np.full(len(years), base_tonnes, dtype="float64")
        for i, y in enumerate(years):
            if y >= start_ramp_year:
                cap[i] = base_tonnes * (1 + ramp_rate) ** (y - start_ramp_year)
        if plateau_tonnes is not None:
            cap = np.minimum(cap, plateau_tonnes)

    sf = enrichment.swu_factor(ref_assay)              # SWU per kg at ref assay
    cap_kswu = sf * cap * 1000.0 / 1000.0              # tonnes->kg->SWU->kSWU
    return pd.DataFrame({"year": years, "capacity_tonnes": cap,
                         "capacity_kswu": cap_kswu})
