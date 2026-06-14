"""
Uranium enrichment physics - separative work and cascade mass balance.

This is the rigorous core of CASCADE. The functions implement the standard,
textbook ideal-cascade relations used throughout the civilian nuclear-fuel
industry to size enrichment demand: the separation potential (value) function
and the feed / tails / SWU mass balance for producing a given mass of enriched
product. These are economics-and-throughput relations (how much natural-uranium
feed and how many separative work units a reactor's fuel needs), not separation
technology.

Scope: deliberately limited to civilian low-enriched uranium and HALEU,
i.e. product assays up to 20% U-235. Requests above that raise - CASCADE models
the advanced-reactor fuel supply chain, nothing else.

Symbols (all assays are mass fractions of U-235):
    xp  product assay      xf  feed assay      xw  tails (waste) assay
    P   product mass       F   feed mass       W   tails mass
"""
from __future__ import annotations

import numpy as np

NATURAL_U = 0.00711       # natural uranium U-235 mass fraction
HALEU_MAX = 0.20          # civilian HALEU ceiling (20% U-235)
DEFAULT_TAILS = 0.0025    # 0.25% tails assay, a common operating point


def value_function(x):
    """Separation potential V(x) = (2x - 1) ln(x / (1 - x)).

    Dimensionless, non-negative, symmetric about x = 0.5 (where V = 0).
    Accepts scalars or arrays of mass fractions in (0, 1).
    """
    x = np.asarray(x, dtype="float64")
    if np.any((x <= 0) | (x >= 1)):
        raise ValueError("assays must be mass fractions strictly in (0, 1)")
    return (2.0 * x - 1.0) * np.log(x / (1.0 - x))


def feed_factor(xp, xf=NATURAL_U, xw=DEFAULT_TAILS):
    """Feed per unit product, F/P = (xp - xw) / (xf - xw)."""
    return (xp - xw) / (xf - xw)


def tails_factor(xp, xf=NATURAL_U, xw=DEFAULT_TAILS):
    """Tails per unit product, W/P = (xp - xf) / (xf - xw)."""
    return (xp - xf) / (xf - xw)


def swu_factor(xp, xf=NATURAL_U, xw=DEFAULT_TAILS):
    """Separative work per unit product (SWU per kg product).

    SWU/P = V(xp) + (W/P) V(xw) - (F/P) V(xf).
    """
    ff = feed_factor(xp, xf, xw)
    wf = tails_factor(xp, xf, xw)
    return value_function(xp) + wf * value_function(xw) - ff * value_function(xf)


def enrichment_requirements(product_kg, xp, xf=NATURAL_U, xw=DEFAULT_TAILS):
    """Feed, tails, and SWU needed to produce ``product_kg`` at assay ``xp``.

    Returns a dict with feed_kg, tails_kg, swu (kg-SWU), and the per-kg factors.
    Raises if ``xp`` exceeds the civilian HALEU ceiling (20% U-235).
    """
    if not (xf < xp <= HALEU_MAX):
        raise ValueError(
            f"product assay xp={xp:.4f} out of range: CASCADE is scoped to "
            f"civilian LEU/HALEU with feed < xp <= {HALEU_MAX:.2f} (<=20% U-235)"
        )
    if not (0 < xw < xf):
        raise ValueError("tails assay must satisfy 0 < xw < feed assay")
    ff = feed_factor(xp, xf, xw)
    wf = tails_factor(xp, xf, xw)
    sf = swu_factor(xp, xf, xw)
    return {
        "product_kg": float(product_kg),
        "feed_kg": float(product_kg * ff),
        "tails_kg": float(product_kg * wf),
        "swu": float(product_kg * sf),
        "feed_factor": float(ff),
        "swu_factor": float(sf),
    }


def optimal_tails(price_per_kg_feed, price_per_swu, xf=NATURAL_U):
    """Cost-optimal tails assay given feed and SWU unit prices.

    Solves dV/dx balance numerically over a plausible tails range; included
    because the tails choice is the central economic lever in enrichment and
    materially changes both feed and SWU demand. Returns the tails assay (mass
    fraction) minimising unit product cost.
    """
    xs = np.linspace(0.0005, xf * 0.95, 400)
    # unit product cost(xw) = feed_factor*price_feed + swu_factor*price_swu
    cost = (feed_factor(0.05, xf, xs) * price_per_kg_feed
            + swu_factor(0.05, xf, xs) * price_per_swu)
    return float(xs[int(np.argmin(cost))])
