"""
CASCADE end-to-end demo (headless).

Runs the HALEU fuel-supply analysis on the illustrative fleet + capacity ramp,
prints a console report, and writes to outputs/:
    cascade_gap.png             demand band vs domestic capacity + shortfall prob
    cascade_gap_deterministic.csv
    cascade_gap_montecarlo.csv

The enrichment relations are exact; the fleet and capacity inputs are
clearly-labelled illustrative placeholders. Run:  python demo.py
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import cascade as C

OUT = os.path.join(os.path.dirname(__file__), "outputs")
START, END = 2027, 2040


def main():
    os.makedirs(OUT, exist_ok=True)
    pd.set_option("display.width", 100)

    print("=" * 64)
    print(" CASCADE - advanced-reactor HALEU fuel-supply analysis")
    print("=" * 64)

    # --- enrichment physics sanity (exact relations) ---
    for label, xp in [("LEU 4.4%", 0.044), ("HALEU 15.5%", 0.155), ("HALEU 19.75%", 0.1975)]:
        r = C.enrichment.enrichment_requirements(1.0, xp)
        print(f"  {label:13s}: {r['feed_factor']:6.2f} kg natural-U feed/kg, "
              f"{r['swu_factor']:6.2f} SWU/kg product")

    # --- demand from the reactor pipeline ---
    fleet = C.reactors.load_fleet()
    demand = C.demand.annual_demand(fleet, start_year=START, end_year=END)
    supply = C.supply.capacity_curve(START, END, plateau_tonnes=35)
    det = C.gap.deterministic_gap(demand, supply)

    peak_year = int(det.loc[det["haleu_tonnes"].idxmax(), "year"])
    fsy = C.gap.first_shortfall_year(det)
    peak_gap = float(det["gap_tonnes"].max())
    print(f"\n  fleet: {len(fleet)} HALEU-fueled designs")
    print(f"  peak annual HALEU demand: {det['haleu_tonnes'].max():.1f} t "
          f"in {peak_year}")
    print(f"  first year domestic capacity falls short (deterministic): {fsy}")
    print(f"  peak annual unmet HALEU (deterministic): {peak_gap:.1f} t")

    # --- Monte Carlo over deployment delays + capacity ramp ---
    mc = C.gap.monte_carlo_gap(fleet, start_year=START, end_year=END, n_sims=800,
                               plateau=35)
    det.to_csv(os.path.join(OUT, "cascade_gap_deterministic.csv"), index=False)
    mc.to_csv(os.path.join(OUT, "cascade_gap_montecarlo.csv"), index=False)

    for y in (2030, 2033, 2036):
        row = mc[mc["year"] == y]
        if len(row):
            print(f"  P(domestic shortfall) in {y}: "
                  f"{float(row['prob_shortfall'].iloc[0]) * 100:4.0f}%   "
                  f"median unmet {float(row['gap_p50'].iloc[0]):4.1f} t")

    # --- figure ---
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7.0, 6.4),
                                   gridspec_kw={"height_ratios": [3, 1]}, sharex=True)
    yr = mc["year"]
    ax1.fill_between(yr, mc["demand_p10"], mc["demand_p90"], color="#1f6feb",
                     alpha=0.20, label="HALEU demand (P10-P90)")
    ax1.plot(yr, mc["demand_p50"], color="#1f6feb", lw=2, label="HALEU demand (median)")
    ax1.plot(det["year"], det["capacity_tonnes"], color="#2ca02c", lw=2,
             ls="--", label="domestic capacity (illustrative)")
    ax1.fill_between(det["year"], det["capacity_tonnes"], mc["demand_p50"],
                     where=(mc["demand_p50"].to_numpy() > det["capacity_tonnes"].to_numpy()),
                     color="#d62728", alpha=0.25, label="median shortfall")
    ax1.set_ylabel("HALEU (tonnes / year)")
    ax1.set_title("U.S. HALEU supply-demand gap (illustrative inputs, exact enrichment physics)")
    ax1.legend(fontsize=8, frameon=False)
    ax1.grid(alpha=0.25)

    ax2.bar(yr, mc["prob_shortfall"] * 100, color="#d29922", width=0.7)
    ax2.set_ylabel("P(shortfall) %")
    ax2.set_xlabel("year")
    ax2.set_ylim(0, 100)
    ax2.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "cascade_gap.png"), dpi=200)
    plt.close(fig)

    print("\n  wrote: cascade_gap.png, cascade_gap_deterministic.csv, "
          "cascade_gap_montecarlo.csv")
    print("  NOTE: enrichment physics exact; fleet/capacity figures illustrative.")


if __name__ == "__main__":
    main()
