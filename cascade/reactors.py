"""
Advanced-reactor fleet reference data.

A small, version-controlled table of U.S. advanced reactors and microreactors
that require HALEU, with approximate enrichment, first-core and annual-reload
HALEU masses, and target first-deployment years.

The masses and dates here are ILLUSTRATIVE planning placeholders at public
order-of-magnitude only - per-reactor HALEU loadings are not consistently
published and vary with design maturity. They exist so the model runs out of
the box; replace them with vetted figures via ``load_fleet(csv_path=...)``
before citing any result. The value of CASCADE is the enrichment physics and
the gap model, not these specific numbers.

Columns:
    name, developer, type, mwe, xp (product assay, mass fraction),
    first_core_haleu_t (tonnes), annual_reload_haleu_t, target_year
"""
from __future__ import annotations

import pandas as pd

# illustrative; see module docstring
_FLEET = [
    ("Natrium",   "TerraPower",   "Sodium fast",      345, 0.1975, 5.0, 1.2, 2030),
    ("Xe-100",    "X-energy",     "HTGR pebble TRISO",  80, 0.155,  2.5, 0.9, 2030),
    ("Hermes/KP-FHR", "Kairos",   "Fluoride salt TRISO", 35, 0.1975, 1.5, 0.6, 2031),
    ("Aurora",    "Oklo",         "Fast microreactor",  15, 0.1975, 1.0, 0.2, 2029),
    ("MMR",       "USNC",         "HTGR micro TRISO",    5, 0.1975, 0.5, 0.15, 2031),
    ("eVinci",    "Westinghouse", "Heat-pipe micro",     5, 0.150,  0.4, 0.12, 2032),
]

FLEET_COLUMNS = ["name", "developer", "type", "mwe", "xp",
                 "first_core_haleu_t", "annual_reload_haleu_t", "target_year"]


def load_fleet(csv_path: str | None = None) -> pd.DataFrame:
    """Return the advanced-reactor fleet table (or an override CSV)."""
    if csv_path:
        df = pd.read_csv(csv_path)
        missing = set(FLEET_COLUMNS) - set(df.columns)
        if missing:
            raise ValueError(f"override CSV missing columns: {sorted(missing)}")
        return df
    return pd.DataFrame(_FLEET, columns=FLEET_COLUMNS)
