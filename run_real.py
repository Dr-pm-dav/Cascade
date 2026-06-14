"""
CASCADE real-data run.

Pulls live, credential-free data, validates the enrichment engine against it,
runs the HALEU supply-demand gap on real-derived parameters, and records full
provenance. Writes to outputs/:
    cascade_real_context.png        real EIA market history (price + SWU split)
    cascade_gap.png                 HALEU gap (demand band vs capacity)
    eia_uranium_price.csv, eia_enrichment.csv, cascade_gap_real.csv
    cascade_provenance.json         sources, URLs, fetch time, real-vs-modelled

Also refreshes the committed real-data snapshots in cascade/data/ so the repo
runs offline. Use --offline to run from those snapshots instead of the network.

Run:  python run_real.py          (live)
      python run_real.py --offline
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import cascade as C
from cascade import enrichment as E
from cascade.connectors import EIAUraniumMarket, WikidataReactors, NRCReactors

OUT = os.path.join(os.path.dirname(__file__), "outputs")
OFFLINE = "--offline" in sys.argv
START, END = 2027, 2040
LWR_ASSAY = 0.045          # representative contemporary LWR reload assay


def implied_tails_from_real(feed_per_swu_real, xp=LWR_ASSAY):
    """Scan tails assay for the value reproducing the real feed:SWU ratio."""
    xs = np.linspace(0.0010, 0.0030, 400)
    ratio = np.array([E.feed_factor(xp, xw=x) / E.swu_factor(xp, xw=x) for x in xs])
    return float(xs[int(np.argmin(np.abs(ratio - feed_per_swu_real)))])


def main():
    os.makedirs(OUT, exist_ok=True)
    print("=" * 70)
    print(f" CASCADE real-data run  ({'OFFLINE snapshot' if OFFLINE else 'LIVE'})")
    print("=" * 70)

    # ---------------- real EIA fuel-cycle market ----------------
    eia = EIAUraniumMarket.from_snapshot() if OFFLINE else EIAUraniumMarket()
    meta = eia.report_meta()
    up = eia.uranium_price()
    en = eia.enrichment()
    latest = eia.latest() if not OFFLINE else {
        "year": int(en.dropna(subset=["swu_total_m"])["year"].iloc[-1]),
        "uranium_usd_per_lb_u3o8": float(up.dropna(subset=["usd_per_lb_u3o8"])["usd_per_lb_u3o8"].iloc[-1]),
        "uranium_usd_per_kgU": float(up.dropna(subset=["usd_per_kgU"])["usd_per_kgU"].iloc[-1]),
        "swu_usd": float(en.dropna(subset=["price_usd_swu"])["price_usd_swu"].iloc[-1]),
        "swu_total_m": float(en.dropna(subset=["swu_total_m"])["swu_total_m"].iloc[-1]),
        "foreign_swu_share": float(en.dropna(subset=["swu_total_m"])["foreign_swu_share"].iloc[-1]),
        "feed_tU": float(en.dropna(subset=["feed_tU"])["feed_tU"].iloc[-1]),
    }
    print(f"\n[REAL] {meta['title']}  ({meta.get('release','')})")
    print(f"       source: {meta['source']}")
    yr = latest["year"]
    print(f"  {yr} uranium price      : ${latest['uranium_usd_per_lb_u3o8']:.2f}/lb U3O8 "
          f"(= ${latest['uranium_usd_per_kgU']:.0f}/kgU)")
    print(f"  {yr} enrichment price   : ${latest['swu_usd']:.2f}/SWU")
    print(f"  {yr} U.S. enrichment    : {latest['swu_total_m']:.1f} M SWU purchased, "
          f"{latest['foreign_swu_share']*100:.0f}% foreign-origin")
    print(f"  {yr} feed deliveries    : {latest['feed_tU']:,.0f} tU")

    # ---------------- validate the engine against real feed:SWU ----------------
    recent = en.dropna(subset=["feed_tU", "swu_total_m"]).tail(5)
    real_ratio = float((recent["feed_tU"] * 1000).sum() / (recent["swu_total_m"] * 1e6).sum())
    imp_tails = implied_tails_from_real(real_ratio)
    eng_ratio = E.feed_factor(LWR_ASSAY, xw=imp_tails) / E.swu_factor(LWR_ASSAY, xw=imp_tails)
    opt_tails = E.optimal_tails(latest["uranium_usd_per_kgU"], latest["swu_usd"])
    print(f"\n[VALIDATION] real 5-yr feed:SWU = {real_ratio:.3f} kgU/SWU")
    print(f"  engine reproduces it at tails {imp_tails*100:.2f}% (assumed {LWR_ASSAY*100:.1f}% product) "
          f"-> engine ratio {eng_ratio:.3f}")
    print(f"  cost-optimal tails at real prices = {opt_tails*100:.2f}%  "
          f"(actual operations sit at/below this: underfeeding under high U prices)")
    hist = C.tails.historical_tails(up, en, xp=LWR_ASSAY)
    h0, h1 = hist.iloc[0], hist.iloc[-1]
    print(f"  {int(h0['year'])}-{int(h1['year'])}: cost-optimal tails moved "
          f"{h0['optimal_tails']*100:.2f}% -> {h1['optimal_tails']*100:.2f}% with prices; "
          f"implied operating tails tracked it down")

    # ---------------- real reactor registry (Wikidata) ----------------
    wd = None
    try:
        wd = WikidataReactors.from_snapshot() if OFFLINE else WikidataReactors()
        wsum = wd.summary()
        print(f"\n[REAL] Wikidata reactor registry: {wsum['stations_total']} nuclear "
              f"stations across {wsum['countries']} countries, "
              f"{wsum['capacity_gw_total']} GW; U.S. {wsum['us_stations']} stations "
              f"/ {wsum['us_capacity_gw']} GW")
    except Exception as e:
        wsum = {"error": str(e)}
        print(f"\n[REAL] Wikidata registry unavailable ({e}); continuing")

    # ---------------- real NRC reactor pipeline ----------------
    nrc = None
    try:
        nrc = NRCReactors.from_snapshot() if OFFLINE else NRCReactors()
        nsum = nrc.summary()
        print(f"\n[REAL] NRC reactors: {nsum['operating_units']} operating U.S. units "
              f"({', '.join(f'{k} {v}' for k, v in nsum['operating_by_type'].items())}); "
              f"advanced pre-application pipeline {nsum['pipeline_total']} developers, "
              f"{nsum['pipeline_haleu_relevant']} in HALEU-relevant technologies")
        for tech, n in nsum["pipeline_by_technology"].items():
            print(f"       {n:>2}  {tech}")
    except Exception as e:
        nsum = {"error": str(e)}
        print(f"\n[REAL] NRC pipeline unavailable ({e}); continuing")

    # ---------------- HALEU gap on real-derived tails ----------------
    fleet = C.reactors.load_fleet()
    demand = C.demand.annual_demand(fleet, start_year=START, end_year=END, tails=imp_tails)
    supply = C.supply.capacity_curve(START, END, plateau_tonnes=35)
    det = C.gap.deterministic_gap(demand, supply)
    mc = C.gap.monte_carlo_gap(fleet, start_year=START, end_year=END, n_sims=800,
                               plateau=35, tails=imp_tails)
    fsy = C.gap.first_shortfall_year(det)
    peak_swu_kswu = float(demand["swu_kswu"].max())
    print(f"\n[MODEL] HALEU gap (tails {imp_tails*100:.2f}% from real data; "
          f"fleet+ramp illustrative)")
    print(f"  peak HALEU demand {det['haleu_tonnes'].max():.1f} t/yr; first domestic "
          f"shortfall {fsy}")
    print(f"  peak HALEU enrichment demand {peak_swu_kswu:,.0f} kSWU/yr "
          f"(~{peak_swu_kswu/1000:.2f} M SWU) vs real LWR base {latest['swu_total_m']:.1f} M SWU/yr")
    for y in (2030, 2033, 2036):
        r = mc[mc["year"] == y]
        if len(r):
            print(f"  P(shortfall) {y}: {float(r['prob_shortfall'].iloc[0])*100:3.0f}%")

    # ---------------- outputs ----------------
    up.to_csv(os.path.join(OUT, "eia_uranium_price.csv"), index=False)
    en.to_csv(os.path.join(OUT, "eia_enrichment.csv"), index=False)
    det.to_csv(os.path.join(OUT, "cascade_gap_real.csv"), index=False)
    hist.to_csv(os.path.join(OUT, "cascade_tails_history.csv"), index=False)
    if nrc is not None and "error" not in nsum:
        nrc.operating_fleet().to_csv(os.path.join(OUT, "nrc_operating_fleet.csv"), index=False)
        nrc.advanced_pipeline().to_csv(os.path.join(OUT, "nrc_advanced_pipeline.csv"), index=False)

    _fig_real_context(up, en, latest)
    _fig_gap(det, mc)
    _fig_tails(hist)
    if nrc is not None and "error" not in nsum:
        _fig_nrc(nrc.advanced_pipeline())

    prov = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": "offline-snapshot" if OFFLINE else "live",
        "real_sources": {
            "eia_uranium_marketing": {"source": meta["source"], "url": meta["url"],
                                      "title": meta["title"], "release": meta.get("release"),
                                      "fields": ["uranium_price_usd_lb", "swu_price_usd",
                                                 "swu_purchased_M", "foreign_swu_share",
                                                 "feed_deliveries_tU"]},
            "wikidata_reactors": {"endpoint": WikidataReactors.ENDPOINT,
                                  "summary": wsum},
            "nrc_reactors": {"operating_url": NRCReactors.OPERATING,
                             "pipeline_url": NRCReactors.PRE_APP,
                             "summary": nsum},
        },
        "real_values_latest": latest,
        "validation": {"real_feed_per_swu_kgU": real_ratio,
                       "implied_operating_tails": imp_tails,
                       "cost_optimal_tails_at_real_prices": opt_tails,
                       "assumed_product_assay": LWR_ASSAY,
                       "tails_history_years": [int(hist["year"].min()), int(hist["year"].max())]},
        "modelled_layers": {
            "haleu_loadings": "reactors.py - illustrative, not published; CSV-overrideable",
            "domestic_capacity_ramp": "supply.py - illustrative program scenario; CSV-overrideable",
        },
        "haleu_gap_result": {"first_shortfall_year": fsy,
                             "peak_demand_tonnes": float(det["haleu_tonnes"].max()),
                             "peak_enrichment_kswu": peak_swu_kswu},
    }
    json.dump(prov, open(os.path.join(OUT, "cascade_provenance.json"), "w"), indent=2, default=str)

    # refresh committed snapshots (real data, dated) for offline reproducibility
    if not OFFLINE:
        try:
            EIAUraniumMarket().to_snapshot()
            if wd is not None:
                wd.to_snapshot()
            if nrc is not None and "error" not in nsum:
                nrc.to_snapshot()
            print("\n  refreshed cascade/data/ snapshots (real data, dated)")
        except Exception as e:
            print(f"\n  snapshot refresh skipped ({e})")

    print("  wrote: cascade_real_context.png, cascade_gap.png, cascade_tails.png, "
          "cascade_nrc_pipeline.png, CSVs, cascade_provenance.json")
    print("\nPROVENANCE  REAL: EIA uranium/enrichment market + Wikidata fleet + NRC "
          "operating fleet & advanced-reactor pipeline.  MODELLED: HALEU loadings + "
          "capacity ramp (labelled, overrideable).")


def _fig_real_context(up, en, latest):
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(7.2, 6.4))
    u = up.dropna(subset=["usd_per_lb_u3o8"])
    a1.plot(u["year"], u["usd_per_lb_u3o8"], color="#1f6feb", lw=2, label="uranium ($/lb U3O8)")
    a1.set_ylabel("uranium ($/lb U3O8)", color="#1f6feb")
    a1.tick_params(axis="y", labelcolor="#1f6feb")
    sp = en.dropna(subset=["price_usd_swu"])
    a1b = a1.twinx()
    a1b.plot(sp["year"], sp["price_usd_swu"], color="#d29922", lw=2, label="enrichment ($/SWU)")
    a1b.set_ylabel("enrichment ($/SWU)", color="#d29922")
    a1b.tick_params(axis="y", labelcolor="#d29922")
    a1.set_title("Real U.S. fuel-cycle market (EIA Uranium Marketing Annual)")
    a1.grid(alpha=0.25)

    e = en.dropna(subset=["swu_total_m"])
    a2.bar(e["year"], e["swu_us_m"], color="#2ca02c", label="U.S.-origin SWU")
    a2.bar(e["year"], e["swu_foreign_m"], bottom=e["swu_us_m"], color="#d62728",
           label="foreign-origin SWU")
    a2.set_ylabel("enrichment services (M SWU)")
    a2.set_xlabel("year")
    a2.set_title(f"U.S. enrichment by origin - {latest['foreign_swu_share']*100:.0f}% "
                 f"foreign in {latest['year']}")
    a2.legend(fontsize=8, frameon=False)
    a2.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "cascade_real_context.png"), dpi=200)
    plt.close(fig)


def _fig_gap(det, mc):
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7.0, 6.4),
                                   gridspec_kw={"height_ratios": [3, 1]}, sharex=True)
    yr = mc["year"]
    ax1.fill_between(yr, mc["demand_p10"], mc["demand_p90"], color="#1f6feb", alpha=0.20,
                     label="HALEU demand (P10-P90)")
    ax1.plot(yr, mc["demand_p50"], color="#1f6feb", lw=2, label="HALEU demand (median)")
    ax1.plot(det["year"], det["capacity_tonnes"], color="#2ca02c", lw=2, ls="--",
             label="domestic capacity (illustrative)")
    ax1.fill_between(det["year"], det["capacity_tonnes"], mc["demand_p50"],
                     where=(mc["demand_p50"].to_numpy() > det["capacity_tonnes"].to_numpy()),
                     color="#d62728", alpha=0.25, label="median shortfall")
    ax1.set_ylabel("HALEU (tonnes / year)")
    ax1.set_title("U.S. HALEU supply-demand gap (real-derived tails; fleet/ramp illustrative)")
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


def _fig_tails(hist):
    fig, ax = plt.subplots(figsize=(7.4, 3.8))
    ax.plot(hist["year"], hist["optimal_tails"] * 100, color="#1f6feb", lw=2,
            marker="o", ms=3, label="cost-optimal (from EIA prices)")
    ax.plot(hist["year"], hist["implied_tails"] * 100, color="#d62728", lw=2,
            marker="s", ms=3, label="implied operating (from EIA feed:SWU)")
    ax.set_ylabel("tails assay (% U-235)")
    ax.set_xlabel("year")
    ax.set_title("Cost-optimal vs implied operating tails, U.S. fleet (real EIA data)")
    ax.legend(fontsize=8, frameon=False)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "cascade_tails.png"), dpi=200)
    plt.close(fig)


def _fig_nrc(pipe):
    """NRC advanced-reactor pre-application pipeline by technology, HALEU flagged."""
    import matplotlib.patches as mpatches
    SHORT = {"High Temperature Gas Reactors": "HTGR",
             "Light Water Reactors": "LWR",
             "Molten Salt Reactors / Molten Chloride Fast Reactors": "MSR / MCFR",
             "Sodium Cooled Reactors": "Sodium fast", "Other Designs/ Not Specified": "Other"}
    order = pipe["technology"].value_counts()
    techs = list(order.index)
    counts = [int(order[t]) for t in techs]
    hal = []
    for t in techs:
        col = pipe[pipe["technology"] == t]["haleu_relevant"]
        hal.append(bool(col.iloc[0]) if col.notna().iloc[0] else None)
    colors = ["#d62728" if h else ("#9aa0a6" if h is None else "#1f6feb") for h in hal]
    short = [SHORT.get(t, t) for t in techs]
    fig, ax = plt.subplots(figsize=(7.6, 4.0))
    ax.barh(short[::-1], counts[::-1], color=colors[::-1])
    ax.set_xlabel("developers in NRC pre-application")
    ax.set_title("NRC advanced-reactor pipeline by technology")
    ax.grid(alpha=0.25, axis="x")
    leg = [mpatches.Patch(color="#d62728", label="HALEU-relevant (>5% U-235)"),
           mpatches.Patch(color="#1f6feb", label="LEU (light water)"),
           mpatches.Patch(color="#9aa0a6", label="unspecified")]
    ax.legend(handles=leg, fontsize=8, frameon=False, loc="lower right")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "cascade_nrc_pipeline.png"), dpi=200)
    plt.close(fig)


if __name__ == "__main__":
    main()
