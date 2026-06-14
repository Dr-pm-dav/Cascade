"""Connector tests - conversions, tails economics, snapshot round-trip.

These run offline (no network). The live fetch paths are exercised by
run_real.py; unit tests stay deterministic and network-free.
"""
import json

import pytest

from cascade import enrichment as E
from cascade.connectors import (EIAUraniumMarket, WikidataReactors,
                                LB_U3O8_TO_KGU, U3O8_TO_U)


def test_conversion_constants():
    assert U3O8_TO_U == pytest.approx(0.848, abs=1e-3)
    # 1 lb U3O8 -> ~0.3847 kg U
    assert LB_U3O8_TO_KGU == pytest.approx(0.3847, abs=1e-3)


def test_optimal_tails_rises_with_swu_price():
    # cheap separative work -> strip harder (lower tails); expensive SWU -> higher tails
    cheap = E.optimal_tails(price_per_kg_feed=100, price_per_swu=30)
    dear = E.optimal_tails(price_per_kg_feed=100, price_per_swu=300)
    assert dear > cheap
    assert 0 < cheap < E.NATURAL_U and 0 < dear < E.NATURAL_U


def test_eia_snapshot_round_trip(tmp_path):
    snap = {
        "meta": {"title": "EIA Uranium Marketing Annual", "release": "Release Date: X",
                 "source": "U.S. EIA, Form EIA-858", "url": "https://www.eia.gov/uranium/marketing/xls/",
                 "fetched_at": None},
        "uranium_price": {"year": [2023, 2024], "usd_per_lb_u3o8": [43.80, 52.71],
                          "usd_per_kgU": [43.80 / LB_U3O8_TO_KGU, 52.71 / LB_U3O8_TO_KGU]},
        "enrichment": {"year": [2023, 2024], "feed_mlb_u3o8": [33.5, 42.3],
                       "swu_us_m": [4.3, 2.9], "swu_foreign_m": [10.9, 12.3],
                       "swu_total_m": [15.2, 15.2], "price_usd_swu": [106.97, 97.66],
                       "feed_tU": [0.0, 0.0], "foreign_swu_share": [0.717, 0.809]},
    }
    p = tmp_path / "eia.json"
    json.dump(snap, open(p, "w"))
    eia = EIAUraniumMarket.from_snapshot(str(p))
    up = eia.uranium_price()
    en = eia.enrichment()
    assert list(up.columns)[:2] == ["year", "usd_per_lb_u3o8"]
    assert float(up["usd_per_lb_u3o8"].iloc[-1]) == pytest.approx(52.71)
    assert float(en["price_usd_swu"].iloc[-1]) == pytest.approx(97.66)
    assert eia.report_meta()["source"].startswith("U.S. EIA")


def test_wikidata_snapshot_summary(tmp_path):
    snap = {"captured_at": None, "fleet": {
        "name": ["Surry", "Shearon Harris", "Some Plant"],
        "country": ["United States", "United States", "France"],
        "capacity_mw": [1695.0, 950.9, 1300.0]}}
    p = tmp_path / "wd.json"
    json.dump(snap, open(p, "w"))
    wd = WikidataReactors.from_snapshot(str(p))
    s = wd.summary()
    assert s["stations_total"] == 3
    assert s["us_stations"] == 2
    assert s["countries"] == 2
    assert s["us_capacity_gw"] == pytest.approx(round((1695.0 + 950.9) / 1000, 1), abs=1e-6)


# ---- NRC reactor pipeline connector ----
from cascade.connectors import NRCReactors


def test_nrc_haleu_tech_map():
    m = NRCReactors.HALEU_TECH
    assert m["High Temperature Gas Reactors"] is True
    assert m["Sodium Cooled Reactors"] is True
    assert m["Molten Salt Reactors / Molten Chloride Fast Reactors"] is True
    assert m["Light Water Reactors"] is False
    assert m["Other Designs/ Not Specified"] is None


def test_nrc_snapshot_round_trip(tmp_path):
    snap = {"captured_at": None,
            "operating_fleet": {"plant": ["Plant A", "Plant B"],
                                "docket": ["05000001", "05000002"],
                                "license": ["DPR-1", "NPF-2"],
                                "reactor_type": ["PWR", "BWR"],
                                "state": ["AL", "GA"], "operator": ["Op1", "Op2"]},
            "advanced_pipeline": {"developer": ["Dev HTGR", "Dev LWR"],
                                  "technology": ["High Temperature Gas Reactors",
                                                 "Light Water Reactors"],
                                  "haleu_relevant": [True, False]}}
    p = tmp_path / "nrc.json"
    json.dump(snap, open(p, "w"))
    nrc = NRCReactors.from_snapshot(str(p))
    assert list(nrc.operating_fleet()["reactor_type"]) == ["PWR", "BWR"]
    assert set(nrc.advanced_pipeline().columns) >= {"developer", "technology",
                                                    "haleu_relevant"}
    s = nrc.summary()
    assert s["operating_units"] == 2 and s["pipeline_haleu_relevant"] == 1


def test_nrc_committed_snapshot():
    """The committed real snapshot loads and is internally consistent."""
    nrc = NRCReactors.from_snapshot()
    fl = nrc.operating_fleet()
    assert len(fl) == 95
    assert set(fl["reactor_type"].unique()) <= {"PWR", "BWR"}
    pp = nrc.advanced_pipeline()
    assert len(pp) > 20
    haleu_tech = ("High Temperature Gas Reactors", "Sodium Cooled Reactors",
                  "Molten Salt Reactors / Molten Chloride Fast Reactors")
    for _, r in pp.iterrows():
        if r["technology"] in haleu_tech:
            assert r["haleu_relevant"] == True                  # noqa: E712
        elif r["technology"] == "Light Water Reactors":
            assert r["haleu_relevant"] == False                 # noqa: E712
    assert nrc.summary()["pipeline_haleu_relevant"] > 0
