"""
Real data connectors for CASCADE.

Two credential-free sources, both fetched live and cached, each with a
committed real-data snapshot fallback so the repository always runs:

  EIAUraniumMarket - the U.S. fuel-cycle market, from EIA's published Uranium
      Marketing Annual data tables (no API key needed): real uranium price,
      enrichment services purchased (SWU) with U.S./foreign split, the average
      $/SWU price, and feed deliveries. Source: U.S. EIA, Form EIA-858.

  WikidataReactors - the operating nuclear reactor registry, via the live
      Wikidata SPARQL endpoint: real plant names, countries, and capacities.

What is real vs modelled: these connectors supply real market data and a real
reactor registry. Per-reactor *HALEU* loadings and the forward domestic
enrichment-capacity ramp are not published anywhere as data; they remain the
transparent, CSV-overrideable modelling layers in reactors.py / supply.py.
"""
from __future__ import annotations

import io
import json
import os
import re
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

try:
    import requests
except ImportError:                       # pragma: no cover
    requests = None

# unit conversions
U3O8_TO_U = 0.848                          # kg U per kg U3O8
LB_TO_KG = 0.45359237
LB_U3O8_TO_KGU = U3O8_TO_U * LB_TO_KG      # ~0.3847 kg U per lb U3O8

_UA = {"User-Agent": "CASCADE/0.1 (research)"}
_CACHE = os.path.join(os.path.dirname(__file__), "..", "outputs", ".cache")
_DATA = os.path.join(os.path.dirname(__file__), "data")


# ============================ EIA market data =============================
class EIAUraniumMarket:
    """Real U.S. uranium & enrichment market data (EIA Uranium Marketing Annual)."""

    BASE = "https://www.eia.gov/uranium/marketing/xls/"
    FILES = {
        "uranium_price": "umartableS1bfigureS2.xls",      # $/lb U3O8, weighted-avg
        "enrichment": "umartableS2figuresS3n4.xls",       # feed (Mlb) + SWU (M) + $/SWU
    }

    def __init__(self, *, offline=False, timeout=40, use_cache=True):
        self.offline = offline
        self.timeout = timeout
        self.use_cache = use_cache
        self.fetched_at = None
        self.source_url = self.BASE

    # ---- low level ----
    def _get(self, fname):
        os.makedirs(_CACHE, exist_ok=True)
        cpath = os.path.join(_CACHE, fname)
        if self.use_cache and os.path.exists(cpath):
            return open(cpath, "rb").read()
        if requests is None:
            raise RuntimeError("requests not installed; use from_snapshot()")
        r = requests.get(self.BASE + fname, headers=_UA, timeout=self.timeout)
        r.raise_for_status()
        if self.use_cache:
            open(cpath, "wb").write(r.content)
        self.fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return r.content

    @staticmethod
    def _year_rows(raw, cols):
        df = pd.read_excel(io.BytesIO(raw), header=None)
        rows = []
        for _, row in df.iterrows():
            try:
                y = int(row[0])
            except (ValueError, TypeError):
                continue
            if 1990 <= y <= 2035:
                rows.append([y] + [pd.to_numeric(row[c], errors="coerce") for c in cols])
        return rows, df

    # ---- public series ----
    def uranium_price(self):
        """DataFrame: year, usd_per_lb_u3o8, usd_per_kgU (weighted-average)."""
        rows, _ = self._year_rows(self._get(self.FILES["uranium_price"]), [1])
        df = pd.DataFrame(rows, columns=["year", "usd_per_lb_u3o8"])
        df["usd_per_kgU"] = df["usd_per_lb_u3o8"] / LB_U3O8_TO_KGU
        return df

    def enrichment(self):
        """DataFrame: year, feed_mlb_u3o8, swu_us_m, swu_foreign_m, swu_total_m,
        price_usd_swu, plus derived feed_tU and foreign_swu_share."""
        rows, _ = self._year_rows(self._get(self.FILES["enrichment"]), [1, 3, 4, 5, 6])
        df = pd.DataFrame(rows, columns=["year", "feed_mlb_u3o8", "swu_us_m",
                                         "swu_foreign_m", "swu_total_m", "price_usd_swu"])
        df["feed_tU"] = df["feed_mlb_u3o8"] * 1e6 * LB_U3O8_TO_KGU / 1000.0
        df["foreign_swu_share"] = df["swu_foreign_m"] / df["swu_total_m"]
        return df

    def report_meta(self):
        """Parse the report title / release date from the price table header."""
        raw = self._get(self.FILES["uranium_price"])
        head = pd.read_excel(io.BytesIO(raw), header=None, nrows=6)
        cells = [str(v) for v in head.values.ravel() if str(v) != "nan"]
        title = next((c for c in cells if "Uranium Marketing" in c), "EIA Uranium Marketing Annual")
        release = next((c for c in cells if "Release Date" in c), "")
        return {"title": title.strip(), "release": release.strip(),
                "source": "U.S. EIA, Form EIA-858 (Uranium Marketing Annual)",
                "url": self.BASE, "fetched_at": self.fetched_at}

    def latest(self):
        """Most-recent real values, as a flat dict."""
        up = self.uranium_price().dropna(subset=["usd_per_lb_u3o8"]).iloc[-1]
        en = self.enrichment().dropna(subset=["swu_total_m"]).iloc[-1]
        return {
            "year": int(en["year"]),
            "uranium_usd_per_lb_u3o8": float(up["usd_per_lb_u3o8"]),
            "uranium_usd_per_kgU": float(up["usd_per_kgU"]),
            "swu_usd": float(en["price_usd_swu"]) if pd.notna(en["price_usd_swu"]) else None,
            "swu_total_m": float(en["swu_total_m"]),
            "foreign_swu_share": float(en["foreign_swu_share"]),
            "feed_tU": float(en["feed_tU"]),
        }

    # ---- snapshot (committed real data, offline reproducibility) ----
    def to_snapshot(self, path=None):
        path = path or os.path.join(_DATA, "eia_snapshot.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        snap = {"meta": self.report_meta(),
                "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "uranium_price": self.uranium_price().to_dict(orient="list"),
                "enrichment": self.enrichment().to_dict(orient="list")}
        json.dump(snap, open(path, "w"), indent=2, default=str)
        return path

    @classmethod
    def from_snapshot(cls, path=None):
        path = path or os.path.join(_DATA, "eia_snapshot.json")
        snap = json.load(open(path))
        obj = cls(offline=True)
        obj._snap = snap
        obj.uranium_price = lambda: pd.DataFrame(snap["uranium_price"])      # type: ignore
        obj.enrichment = lambda: pd.DataFrame(snap["enrichment"])            # type: ignore
        obj.report_meta = lambda: snap["meta"]                              # type: ignore
        return obj


# ============================ Wikidata registry ===========================
class WikidataReactors:
    """Real operating-reactor registry via the live Wikidata SPARQL endpoint."""

    ENDPOINT = "https://query.wikidata.org/sparql"
    QUERY = """SELECT ?item ?itemLabel ?countryLabel ?cap WHERE {
      ?item wdt:P31 wd:Q134447 .
      OPTIONAL { ?item wdt:P17 ?country. }
      OPTIONAL { ?item wdt:P2109 ?cap. }
      SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
    }"""

    def __init__(self, *, timeout=90, retries=4):
        self.timeout = timeout
        self.retries = retries
        self.fetched_at = None
        self._df = None

    def fleet(self):
        """DataFrame: name, country, capacity_mw (nuclear power stations).

        Fetched once and cached on the instance; retries with backoff to ride
        out the endpoint's rate limiting.
        """
        if self._df is not None:
            return self._df
        if requests is None:
            raise RuntimeError("requests not installed; use from_snapshot()")
        last = None
        for attempt in range(self.retries):
            try:
                r = requests.get(self.ENDPOINT,
                                 params={"query": self.QUERY, "format": "json"},
                                 headers={**_UA, "Accept": "application/sparql-results+json"},
                                 timeout=self.timeout)
                if r.status_code == 429:
                    raise RuntimeError("429 rate limited")
                r.raise_for_status()
                self.fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
                rows = []
                for b in r.json()["results"]["bindings"]:
                    rows.append({
                        "name": b.get("itemLabel", {}).get("value"),
                        "country": b.get("countryLabel", {}).get("value"),
                        "capacity_mw": pd.to_numeric(b.get("cap", {}).get("value"), errors="coerce"),
                    })
                df = pd.DataFrame(rows).drop_duplicates(subset=["name"])
                self._df = df[df["name"].notna() & ~df["name"].str.startswith("Q")]
                return self._df
            except Exception as e:                       # noqa: BLE001
                last = e
                if attempt < self.retries - 1:
                    time.sleep(5 * (attempt + 1) ** 2)   # 5s, 20s, 45s
        raise RuntimeError(f"Wikidata fetch failed after {self.retries} tries: {last}")

    def summary(self):
        df = self.fleet()
        us = df[df["country"] == "United States"]
        return {"stations_total": int(len(df)),
                "countries": int(df["country"].nunique()),
                "capacity_gw_total": round(float(df["capacity_mw"].sum()) / 1000.0, 1),
                "us_stations": int(len(us)),
                "us_capacity_gw": round(float(us["capacity_mw"].sum()) / 1000.0, 1),
                "fetched_at": self.fetched_at}

    def to_snapshot(self, path=None):
        path = path or os.path.join(_DATA, "wikidata_snapshot.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        json.dump({"captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   "fleet": self.fleet().to_dict(orient="list")},
                  open(path, "w"), indent=2, default=str)
        return path

    @classmethod
    def from_snapshot(cls, path=None):
        path = path or os.path.join(_DATA, "wikidata_snapshot.json")
        snap = json.load(open(path))
        obj = cls()
        obj.fleet = lambda: pd.DataFrame(snap["fleet"])                      # type: ignore
        return obj


# ============================ NRC reactor pipeline =========================
class NRCReactors:
    """Real U.S. reactor data from the NRC website (no API key needed).

    Two public datasets, fetched live and cached, with a committed snapshot:

      operating_fleet() - the licensed operating power-reactor fleet (the
          existing light-water base that runs on LEU, not HALEU).
          Source: NRC "List of Power Reactor Units".

      advanced_pipeline() - the advanced-reactor pre-application pipeline,
          grouped by reactor technology, which is the forward demand side.
          Source: NRC "Advanced Reactors - Who We're Working With",
          Pre-Application Activities.

    The IAEA PRIS database is the natural global-fleet source, but its pages
    return HTTP 503 to automated clients (a WAF block), so global fleet context
    is provided by the WikidataReactors connector instead (Wikidata reactor
    records draw substantially on IAEA / PRIS data).

    HALEU relevance: NRC groups pre-application projects by reactor technology
    but does not state fuel enrichment. The ``haleu_relevant`` flag here is
    CASCADE's own mapping from technology to the >5% U-235 fuel those concepts
    typically need (high-temperature gas, molten-salt, and sodium-cooled fast
    designs use HALEU; light-water designs use LEU). It is an analytical label,
    not an NRC statement.
    """

    OPERATING = "https://www.nrc.gov/reactors/operating/list-power-reactor-units.html"
    PRE_APP = ("https://www.nrc.gov/reactors/new-reactors/advanced/"
               "who-were-working-with/pre-application-activities.html")
    _BROWSER = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
    HALEU_TECH = {
        "High Temperature Gas Reactors": True,
        "Light Water Reactors": False,
        "Molten Salt Reactors / Molten Chloride Fast Reactors": True,
        "Sodium Cooled Reactors": True,
        "Other Designs/ Not Specified": None,
    }

    def __init__(self, *, timeout=45, use_cache=True):
        self.timeout = timeout
        self.use_cache = use_cache
        self.fetched_at = None
        self._fleet = None
        self._pipe = None

    # ---- low level ----
    def _html(self, url):
        os.makedirs(_CACHE, exist_ok=True)
        fname = url.rsplit("/", 1)[-1]
        cpath = os.path.join(_CACHE, fname)
        if self.use_cache and os.path.exists(cpath):
            return open(cpath, encoding="utf-8").read()
        if requests is None:
            raise RuntimeError("requests not installed; use from_snapshot()")
        r = requests.get(url, headers=self._BROWSER, timeout=self.timeout)
        r.raise_for_status()
        if self.use_cache:
            open(cpath, "w", encoding="utf-8").write(r.text)
        self.fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return r.text

    # ---- operating fleet ----
    def operating_fleet(self):
        """DataFrame: plant, docket, license, reactor_type, state, operator."""
        if self._fleet is not None:
            return self._fleet
        tab = max(pd.read_html(io.StringIO(self._html(self.OPERATING))),
                  key=lambda t: t.shape[0] * t.shape[1])
        tab.columns = ["plant_docket", "license", "reactor_type", "location",
                       "operator", "region"][:tab.shape[1]]
        rows = []
        for _, r in tab.iterrows():
            pdk = str(r["plant_docket"]).strip()
            m = re.search(r"(0\d{6,7})\s*$", pdk)
            docket = m.group(1) if m else ""
            plant = pdk[:pdk.rfind(docket)].strip() if docket else pdk
            loc = str(r.get("location", ""))
            sm = re.search(r",\s*([A-Z]{2})\b", loc)
            rows.append({"plant": plant, "docket": docket,
                         "license": str(r.get("license", "")).strip(),
                         "reactor_type": str(r.get("reactor_type", "")).strip(),
                         "state": sm.group(1) if sm else "",
                         "operator": str(r.get("operator", "")).strip()})
        df = pd.DataFrame(rows)
        self._fleet = df[df["plant"].str.len() > 0].reset_index(drop=True)
        return self._fleet

    # ---- advanced pre-application pipeline ----
    def advanced_pipeline(self):
        """DataFrame: developer, technology, haleu_relevant (NRC pre-application)."""
        if self._pipe is not None:
            return self._pipe
        tab = max(pd.read_html(io.StringIO(self._html(self.PRE_APP))),
                  key=lambda t: t.shape[0] * t.shape[1])
        rows = []
        for tech in tab.columns:
            tech_s = str(tech).strip()
            for v in tab[tech].dropna().astype(str):
                d = v.replace("*", "").strip()
                if len(d) <= 2 or "=" in d or d.lower().startswith("note"):
                    continue
                if "inactive project" in d.lower():
                    continue
                rows.append({"developer": d, "technology": tech_s,
                             "haleu_relevant": self.HALEU_TECH.get(tech_s)})
        self._pipe = pd.DataFrame(rows)
        return self._pipe

    def summary(self):
        fl = self.operating_fleet()
        pp = self.advanced_pipeline()
        haleu = pp[pp["haleu_relevant"] == True]            # noqa: E712
        return {
            "operating_units": int(len(fl)),
            "operating_by_type": {k: int(v) for k, v in
                                  fl["reactor_type"].value_counts().items()},
            "pipeline_total": int(len(pp)),
            "pipeline_by_technology": {k: int(v) for k, v in
                                       pp["technology"].value_counts().items()},
            "pipeline_haleu_relevant": int(len(haleu)),
            "fetched_at": self.fetched_at,
        }

    # ---- snapshot ----
    def to_snapshot(self, path=None):
        path = path or os.path.join(_DATA, "nrc_snapshot.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        json.dump({"captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   "operating_fleet": self.operating_fleet().to_dict(orient="list"),
                   "advanced_pipeline": self.advanced_pipeline().to_dict(orient="list")},
                  open(path, "w"), indent=2, default=str)
        return path

    @classmethod
    def from_snapshot(cls, path=None):
        path = path or os.path.join(_DATA, "nrc_snapshot.json")
        snap = json.load(open(path))
        obj = cls()
        obj._fleet = pd.DataFrame(snap["operating_fleet"])
        obj._pipe = pd.DataFrame(snap["advanced_pipeline"])
        obj.fetched_at = snap.get("captured_at")
        return obj
