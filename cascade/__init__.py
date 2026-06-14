"""
CASCADE - advanced-reactor HALEU fuel-supply analytics.

Models the high-assay low-enriched uranium (HALEU) supply chain for the U.S.
advanced-reactor build-out: rigorous enrichment physics (separative work and
cascade mass balance), HALEU/SWU demand from the reactor deployment pipeline,
a domestic enrichment-capacity ramp, and the supply-demand gap under Monte
Carlo uncertainty.

Scope is civilian LEU/HALEU (<=20% U-235). The enrichment relations are exact;
the fleet and capacity figures are clearly-labelled illustrative placeholders
with CSV overrides. See README.md.

Public surface:
    enrichment   value_function, feed/tails/swu_factor, enrichment_requirements
    reactors     load_fleet
    demand       annual_demand, cumulative_demand
    supply       capacity_curve
    gap          deterministic_gap, monte_carlo_gap, first_shortfall_year
    connectors   EIAUraniumMarket, WikidataReactors, NRCReactors  (real data)
    tails        optimal_tails, cost_breakdown, optimal_curve, historical_tails
"""
from . import connectors, demand, enrichment, gap, reactors, supply, tails

__all__ = ["enrichment", "reactors", "demand", "supply", "gap", "connectors", "tails"]
__version__ = "0.3.0"
