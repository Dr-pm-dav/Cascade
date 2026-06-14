"""
CASCADE console - the shippable HALEU fuel-supply tool.

Four tabs, one scenario sidebar:
  1. HALEU gap          deployment / ramp / tails sliders, demand band vs
                        domestic capacity, shortfall probability, MC table.
  2. Real market (EIA)  live or snapshot uranium & enrichment data, the
                        81%-foreign reliance, and the engine validation.
  3. Enrichment calc    feed / tails / SWU for any product mass and assay
                        (civilian <=20% U-235, enforced).
  4. Reactor registry   real operating fleet from Wikidata.

Run:  streamlit run app/streamlit_app.py

The enrichment physics is exact. Market data and the reactor registry are real
(EIA Form EIA-858; Wikidata). The HALEU fleet loadings and the domestic
capacity ramp are clearly-labelled illustrative layers; override them in code.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import streamlit as st

# make the repo root importable when launched as `streamlit run app/streamlit_app.py`
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cascade as C
from cascade import enrichment as E
from cascade.connectors import EIAUraniumMarket, WikidataReactors

st.set_page_config(page_title="CASCADE console", page_icon="*", layout="wide")

DELAY_SCENARIOS = {
    "Optimistic": (0.50, 0.30, 0.15, 0.05),
    "Base": (0.35, 0.35, 0.20, 0.10),
    "Pessimistic": (0.15, 0.30, 0.30, 0.25),
}


# ----------------------------- cached compute -----------------------------
@st.cache_data(show_spinner=False)
def load_eia(live: bool):
    eia = EIAUraniumMarket() if live else EIAUraniumMarket.from_snapshot()
    return eia.uranium_price(), eia.enrichment(), eia.latest(), eia.report_meta()


@st.cache_data(show_spinner=False)
def load_wikidata(live: bool):
    wd = WikidataReactors() if live else WikidataReactors.from_snapshot()
    return wd.fleet(), wd.summary()


def implied_tails(real_ratio: float, xp: float = 0.045) -> float:
    xs = np.linspace(0.0010, 0.0030, 400)
    r = np.array([E.feed_factor(xp, xw=x) / E.swu_factor(xp, xw=x) for x in xs])
    return float(xs[int(np.argmin(np.abs(r - real_ratio)))])


@st.cache_data(show_spinner=False)
def run_gap(start, end, units_mean, delay_probs, ramp_mean, plateau, tails, n_sims):
    fleet = C.reactors.load_fleet()
    demand = C.demand.annual_demand(fleet, start_year=start, end_year=end, tails=tails)
    supply = C.supply.capacity_curve(start, end, plateau_tonnes=plateau)
    det = C.gap.deterministic_gap(demand, supply)
    mc = C.gap.monte_carlo_gap(fleet, start_year=start, end_year=end, n_sims=n_sims,
                               units_mean=units_mean, delay_probs=delay_probs,
                               ramp_mean=ramp_mean, plateau=plateau, tails=tails)
    return fleet, det, mc


# -------------------------------- sidebar ---------------------------------
st.sidebar.title("CASCADE")
st.sidebar.caption("Advanced-reactor HALEU fuel-supply analytics")
live = st.sidebar.checkbox("Fetch live data (EIA + Wikidata)", value=False,
                           help="Off uses committed real-data snapshots (no network).")

st.sidebar.subheader("Scenario")
yr0, yr1 = st.sidebar.slider("Horizon", 2027, 2050, (2027, 2040))
units_mean = st.sidebar.slider("Fleet build-out multiplier", 0.5, 2.5, 1.0, 0.1,
                               help="Scales every reactor's HALEU mass.")
scen = st.sidebar.selectbox("Deployment slip profile", list(DELAY_SCENARIOS), index=1)
ramp_mean = st.sidebar.slider("Domestic capacity ramp rate / yr", 0.2, 1.0, 0.55, 0.05)
plateau = st.sidebar.slider("Capacity plateau (t/yr)", 10, 80, 35, 5)
n_sims = st.sidebar.slider("Monte Carlo runs", 200, 1500, 800, 100)

# load real data (drives the tails options + market tab)
try:
    up, en, latest, meta = load_eia(live)
    eia_ok = True
except Exception as e:  # noqa: BLE001
    eia_ok = False
    eia_err = str(e)

st.sidebar.subheader("Tails assay")
if eia_ok:
    recent = en.dropna(subset=["feed_tU", "swu_total_m"]).tail(5)
    real_ratio = float((recent["feed_tU"] * 1000).sum() / (recent["swu_total_m"] * 1e6).sum())
    eia_tails = implied_tails(real_ratio)
    opt_tails = E.optimal_tails(latest["uranium_usd_per_kgU"], latest["swu_usd"])
    tails_mode = st.sidebar.radio(
        "Source",
        [f"EIA-derived ({eia_tails*100:.2f}%)",
         f"Cost-optimal at live prices ({opt_tails*100:.2f}%)",
         "Manual"])
    if tails_mode.startswith("EIA"):
        tails = eia_tails
    elif tails_mode.startswith("Cost"):
        tails = opt_tails
    else:
        tails = st.sidebar.slider("Manual tails (%)", 0.05, 0.30, 0.25, 0.01) / 100.0
else:
    tails = st.sidebar.slider("Manual tails (%)", 0.05, 0.30, 0.25, 0.01) / 100.0

fleet, det, mc = run_gap(yr0, yr1, units_mean, DELAY_SCENARIOS[scen],
                         ramp_mean, plateau, tails, n_sims)

st.title("CASCADE console")
st.caption("Exact enrichment physics; real EIA + Wikidata data; illustrative, "
           "overrideable HALEU fleet and capacity ramp.")

tab_gap, tab_mkt, tab_tails, tab_calc, tab_reg = st.tabs(
    ["HALEU gap", "Real market (EIA)", "Tails economics", "Enrichment calculator",
     "Reactor registry"])


# ------------------------------- gap tab ----------------------------------
with tab_gap:
    fsy = C.gap.first_shortfall_year(det)
    peak_t = float(det["haleu_tonnes"].max())
    peak_kswu = float(C.demand.annual_demand(fleet, start_year=yr0, end_year=yr1,
                                             tails=tails)["swu_kswu"].max())
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("First domestic shortfall", fsy if fsy else "none")
    c2.metric("Peak HALEU demand", f"{peak_t:.1f} t/yr")
    c3.metric("Peak enrichment", f"{peak_kswu:,.0f} kSWU/yr")
    pk = mc.loc[mc["prob_shortfall"].idxmax()]
    c4.metric("Max shortfall prob", f"{pk['prob_shortfall']*100:.0f}%",
              f"in {int(pk['year'])}")

    fig, (a1, a2) = plt.subplots(2, 1, figsize=(8, 5.2),
                                 gridspec_kw={"height_ratios": [3, 1]}, sharex=True)
    a1.fill_between(mc["year"], mc["demand_p10"], mc["demand_p90"], color="#1f6feb",
                    alpha=0.20, label="HALEU demand (P10-P90)")
    a1.plot(mc["year"], mc["demand_p50"], color="#1f6feb", lw=2, label="demand (median)")
    a1.plot(det["year"], det["capacity_tonnes"], color="#2ca02c", lw=2, ls="--",
            label="domestic capacity (illustrative)")
    a1.fill_between(det["year"], det["capacity_tonnes"], mc["demand_p50"],
                    where=(mc["demand_p50"].to_numpy() > det["capacity_tonnes"].to_numpy()),
                    color="#d62728", alpha=0.25, label="median shortfall")
    a1.set_ylabel("HALEU (t / yr)")
    a1.legend(fontsize=8, frameon=False)
    a1.grid(alpha=0.25)
    a2.bar(mc["year"], mc["prob_shortfall"] * 100, color="#d29922", width=0.7)
    a2.set_ylabel("P(short) %")
    a2.set_ylim(0, 100)
    a2.set_xlabel("year")
    a2.grid(alpha=0.25)
    fig.tight_layout()
    st.pyplot(fig)
    st.caption(f"Tails assay {tails*100:.2f}%. Demand uncertainty from per-reactor "
               f"deployment slips ({scen.lower()}) and capacity-ramp spread.")

    st.dataframe(mc.round(2), width="stretch", hide_index=True)
    with st.expander("Illustrative HALEU fleet (override via load_fleet(csv_path=...))"):
        st.dataframe(fleet, width="stretch", hide_index=True)


# ----------------------------- market tab ---------------------------------
with tab_mkt:
    if not eia_ok:
        st.error(f"EIA data unavailable: {eia_err}")
    else:
        st.subheader(f"Real U.S. fuel-cycle market - {meta.get('title','EIA')}")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric(f"Uranium ({latest['year']})", f"${latest['uranium_usd_per_lb_u3o8']:.2f}/lb",
                  f"${latest['uranium_usd_per_kgU']:.0f}/kgU")
        m2.metric("Enrichment price", f"${latest['swu_usd']:.2f}/SWU")
        m3.metric("U.S. enrichment", f"{latest['swu_total_m']:.1f} M SWU")
        m4.metric("Foreign-origin", f"{latest['foreign_swu_share']*100:.0f}%")

        fig2, (b1, b2) = plt.subplots(2, 1, figsize=(8, 5.4))
        u = up.dropna(subset=["usd_per_lb_u3o8"])
        b1.plot(u["year"], u["usd_per_lb_u3o8"], color="#1f6feb", lw=2)
        b1.set_ylabel("uranium ($/lb U3O8)", color="#1f6feb")
        b1.tick_params(axis="y", labelcolor="#1f6feb")
        sp = en.dropna(subset=["price_usd_swu"])
        b1b = b1.twinx()
        b1b.plot(sp["year"], sp["price_usd_swu"], color="#d29922", lw=2)
        b1b.set_ylabel("enrichment ($/SWU)", color="#d29922")
        b1b.tick_params(axis="y", labelcolor="#d29922")
        b1.set_title("Prices")
        b1.grid(alpha=0.25)
        e2 = en.dropna(subset=["swu_total_m"])
        b2.bar(e2["year"], e2["swu_us_m"], color="#2ca02c", label="U.S.-origin")
        b2.bar(e2["year"], e2["swu_foreign_m"], bottom=e2["swu_us_m"], color="#d62728",
               label="foreign-origin")
        b2.set_ylabel("enrichment (M SWU)")
        b2.set_xlabel("year")
        b2.set_title("Enrichment services by origin")
        b2.legend(fontsize=8, frameon=False)
        b2.grid(alpha=0.25)
        fig2.tight_layout()
        st.pyplot(fig2)

        st.markdown(
            f"**Engine validation.** Real 5-year feed:SWU ratio is "
            f"`{real_ratio:.3f}` kg U/SWU. The enrichment engine reproduces it at "
            f"a **{eia_tails*100:.2f}%** tails assay (4.5% product); the cost-optimal "
            f"tails at current prices is **{opt_tails*100:.2f}%**. Operating at or "
            f"below cost-optimal is the industry's underfeeding under high uranium "
            f"prices, recovered here from first principles.")
        st.caption(f"Source: {meta.get('source','EIA Form EIA-858')}. {meta.get('url','')}")


# ----------------------------- tails tab ----------------------------------
with tab_tails:
    st.subheader("Tails-assay economics")
    st.caption("The cost-minimising tails assay is set by the uranium/SWU price "
               "ratio. Lower tails means less natural-uranium feed but more SWU.")
    default_pf = round(float(latest["uranium_usd_per_kgU"]), 1) if eia_ok else 137.0
    default_ps = round(float(latest["swu_usd"]), 1) if eia_ok else 98.0
    t1, t2, t3 = st.columns(3)
    pf = t1.number_input("Uranium price ($/kgU)", 20.0, 500.0, default_pf, 1.0)
    ps = t2.number_input("SWU price ($/SWU)", 30.0, 300.0, default_ps, 1.0)
    order_t = t3.number_input("HALEU order (t at 19.75%)", 0.1, 50.0, 5.0, 0.5)

    opt, _unit = C.tails.optimal_tails(pf, ps)
    cb = C.tails.cost_breakdown(order_t * 1000, 0.1975, pf, ps, opt)
    o1, o2, o3, o4 = st.columns(4)
    o1.metric("Cost-optimal tails", f"{opt*100:.3f}%")
    o2.metric("Feed for order", f"{cb['feed_kg']/1000:,.0f} tU")
    o3.metric("SWU for order", f"{cb['swu']/1000:,.0f} kSWU")
    o4.metric("Order cost", f"${cb['total_cost']/1e6:,.1f} M",
              f"feed {cb['feed_cost_share']*100:.0f}% / SWU {(1-cb['feed_cost_share'])*100:.0f}%")

    xs = np.linspace(0.0005, 0.0060, 200)
    cost_curve = [C.tails.unit_cost(x, 0.1975, pf, ps) for x in xs]
    figt, (ta, tb) = plt.subplots(1, 2, figsize=(9.2, 3.4))
    ta.plot(xs * 100, cost_curve, color="#1f6feb", lw=2)
    ta.axvline(opt * 100, color="#d62728", ls="--", lw=1, label=f"optimal {opt*100:.2f}%")
    ta.set_xlabel("tails assay (% U-235)")
    ta.set_ylabel("$ / kg HALEU")
    ta.set_title("Unit cost vs tails (current prices)")
    ta.legend(fontsize=8, frameon=False)
    ta.grid(alpha=0.25)
    if eia_ok:
        hist = C.tails.historical_tails(up, en)
        tb.plot(hist["year"], hist["optimal_tails"] * 100, color="#1f6feb", lw=2,
                marker="o", ms=3, label="cost-optimal")
        tb.plot(hist["year"], hist["implied_tails"] * 100, color="#d62728", lw=2,
                marker="s", ms=3, label="implied operating")
        tb.set_xlabel("year")
        tb.set_ylabel("tails (% U-235)")
        tb.set_title("U.S. fleet, real EIA history")
        tb.legend(fontsize=8, frameon=False)
        tb.grid(alpha=0.25)
    figt.tight_layout()
    st.pyplot(figt)
    st.caption("Cost-optimal tails is nearly independent of product assay. The "
               "implied operating series is an indicator only (feed-delivery vs "
               "SWU-purchase timing, ~81% foreign enrichment, assumed 4.5% assay).")


# -------------------------- enrichment calc tab ---------------------------
with tab_calc:
    st.subheader("Enrichment requirements")
    st.caption("Feed, tails, and separative work for a HALEU/LEU product order.")
    d1, d2, d3 = st.columns(3)
    mass = d1.number_input("Product mass (kg)", 1.0, 1e6, 1000.0, 100.0)
    xp_pct = d2.number_input("Product assay (% U-235)", 1.0, 20.0, 19.75, 0.25)
    xw_pct = d3.number_input("Tails assay (% U-235)", 0.05, 0.70, 0.25, 0.01)
    try:
        r = E.enrichment_requirements(mass, xp_pct / 100.0, xw=xw_pct / 100.0)
        q1, q2, q3 = st.columns(3)
        q1.metric("Natural-U feed", f"{r['feed_kg']:,.0f} kg", f"{r['feed_factor']:.1f} kg/kg")
        q2.metric("Depleted tails", f"{r['tails_kg']:,.0f} kg")
        q3.metric("Separative work", f"{r['swu']:,.0f} SWU", f"{r['swu_factor']:.1f} SWU/kg")

        assays = np.linspace(0.01, 0.20, 60)
        swu_curve = [E.swu_factor(a, xw=xw_pct / 100.0) for a in assays]
        figc, axc = plt.subplots(figsize=(7, 3.2))
        axc.plot(assays * 100, swu_curve, color="#1f6feb", lw=2)
        axc.axvline(xp_pct, color="#d62728", ls="--", lw=1)
        axc.set_xlabel("product assay (% U-235)")
        axc.set_ylabel("SWU per kg product")
        axc.set_title("Separative work intensity vs assay")
        axc.grid(alpha=0.25)
        st.pyplot(figc)
    except ValueError as ex:
        st.error(str(ex))


# ------------------------- reactor registry tab ---------------------------
with tab_reg:
    st.subheader("Operating nuclear reactor registry (Wikidata)")
    try:
        wfleet, wsum = load_wikidata(live)
        g1, g2, g3, g4 = st.columns(4)
        g1.metric("Stations", wsum["stations_total"])
        g2.metric("Countries", wsum["countries"])
        g3.metric("Capacity", f"{wsum['capacity_gw_total']:.0f} GW")
        g4.metric("U.S.", f"{wsum['us_stations']} / {wsum['us_capacity_gw']:.0f} GW")
        top = wfleet.dropna(subset=["capacity_mw"]).sort_values(
            "capacity_mw", ascending=False).head(20)
        st.dataframe(top, width="stretch", hide_index=True)
        st.caption("Real registry of the operating fleet. The advanced-reactor "
                   "HALEU pipeline driving demand is the illustrative overlay in "
                   "the HALEU gap tab (not yet a public structured feed).")
    except Exception as e:  # noqa: BLE001
        st.error(f"Wikidata registry unavailable: {e}")
