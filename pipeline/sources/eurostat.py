"""Eurostat regional and city statistics, through the dissemination API (JSON-stat 2.0).

One file per table. Each table is reduced to {series key: {geo code: {year: value}}}, where the series key joins the
codes of the dimensions other than geo and time ("MIO_EUR|B-E"), and only the geographies of the map's countries are
kept (NUTS 0-3, cities and functional urban areas)."""

from __future__ import annotations

import itertools
import json
import urllib.parse

from ..core.europe import COUNTRIES, EXCLUDED_NUTS
from ..core.source import Source, SourceInfo

API = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{table}?format=JSON&lang=en&{query}"
SINCE = 2014

# id → (table, filters, description). Several values for one filter make several series.
TABLES = {
    "pop3": ("demo_r_pjanaggr3", {"sex": "T", "unit": "NR", "age": ["TOTAL", "Y_LT15", "Y15-64", "Y_GE65"]},
             "Population on 1 January by broad age group, NUTS 3"),
    "medage3": ("demo_r_pjanind3", {"indic_de": "MEDAGEPOP"}, "Median age of the population, NUTS 3"),
    "gdp3": ("nama_10r_3gdp", {"unit": ["MIO_EUR", "EUR_HAB", "PPS_EU27_2020_HAB"]},
             "Gross domestic product at current prices, NUTS 3"),
    "gva3": ("nama_10r_3gva", {"unit": "CP_MEUR", "nace_r2": ["TOTAL", "A", "B-E", "C", "F", "G-I", "J", "K", "L",
                                                               "M_N", "O-Q", "R-U"]},
             "Gross value added by branch (NACE A*10), NUTS 3"),
    "emp3": ("nama_10r_3empers", {"unit": "THS", "wstatus": "EMP", "nace_r2": ["TOTAL", "A", "B-E", "C", "F", "G-I",
                                                                               "J", "K", "L", "M_N", "O-Q", "R-U"]},
             "Employment (thousand persons) by branch, at the place of work, NUTS 3"),
    "unemp2": ("lfst_r_lfu3rt", {"sex": "T", "age": "Y15-74", "unit": "PC", "isced11": "TOTAL"},
               "Unemployment rate, ages 15-74, NUTS 2"),
    "emprate2": ("lfst_r_lfe2emprt", {"sex": "T", "age": "Y20-64", "unit": "PC"},
                 "Employment rate, ages 20-64, NUTS 2"),
    "tertiary2": ("edat_lfse_04", {"sex": "T", "age": "Y25-64", "isced11": "ED5-8", "unit": "PC"},
                  "Share of 25-64 year-olds with tertiary education (ISCED 5-8), NUTS 2"),
    "income2": ("nama_10r_2hhinc", {"unit": ["PPS_EU27_2020_HAB", "EUR_HAB"], "na_item": "B6N", "direct": "BAL"},
                "Net disposable income of households per inhabitant, NUTS 2"),
    "lifeexp2": ("demo_r_mlifexp", {"sex": "T", "age": "Y_LT1", "unit": "YR"},
                 "Life expectancy at birth, NUTS 2"),
    "arope2": ("ilc_peps11n", {"unit": "PC"}, "At-risk-of-poverty-or-social-exclusion rate, NUTS 2"),
    "born3": ("cens_21cob_r3", {"sex": "T", "age": "TOTAL", "unit": "NR", "c_birth": ["FOR", "TOTAL"]},
              "Population by country of birth (born abroad, total), 2021 census, NUTS 3"),
    "tourism3": ("tour_occ_nin2", {"c_resid": "TOTAL", "unit": "NR", "nace_r2": "I551-I553"},
                 "Nights spent at tourist accommodation (hotels, holiday homes, campsites), NUTS 3"),
    "rd2": ("rd_e_gerdreg", {"sectperf": "TOTAL", "unit": "PC_GDP"},
            "Gross domestic expenditure on research and development, % of GDP, NUTS 2"),
    "fua_pop": ("urb_lpop1", {"indic_ur": "DE1001V"}, "Population of functional urban areas (Urban Audit)"),
    "city_pop": ("urb_cpop1", {"indic_ur": "DE1001V"}, "Population of core cities (Urban Audit)"),
    "pop0": ("demo_pjan", {"sex": "T", "age": "TOTAL", "unit": "NR"}, "Population on 1 January, countries"),
    "gdp0": ("nama_10_gdp", {"unit": "CP_MEUR", "na_item": "B1GQ"}, "Gross domestic product at current prices, countries"),
    "emp0": ("nama_10_a10_e", {"unit": "THS_PER", "na_item": "EMP_DC", "nace_r2": ["TOTAL", "A", "B-E", "C", "F",
                                                                                "G-I", "J", "K", "L", "M_N", "O-Q",
                                                                                "R-U"]},
             "Employment (thousand persons) by branch, countries"),
    "gva0": ("nama_10_a10", {"unit": "CP_MEUR", "na_item": "B1G", "nace_r2": ["TOTAL", "A", "B-E", "C", "F", "G-I",
                                                                               "J", "K", "L", "M_N", "O-Q", "R-U"]},
             "Gross value added by branch, countries"),
    "gdppc0": ("nama_10_pc", {"unit": "CP_PPS_EU27_2020_HAB", "na_item": "B1GQ"},
               "GDP per inhabitant in purchasing power standards, countries"),
    "gdpidx0": ("prc_ppp_ind", {"na_item": "VI_PPS_EU27_2020_HAB", "ppp_cat": "GDP"},
                "GDP per inhabitant, volume index in PPS (EU27 = 100), countries"),
    "silc0": ("ilc_di03", {"statinfo": "MEAN_EI", "unit": "PPS", "age": "TOTAL", "sex": "T"},
              "Mean equivalised net income (EU-SILC survey), PPS, countries"),
}


def mapped_geo(code: str) -> bool:
    return code[:2] in COUNTRIES and not code.startswith(EXCLUDED_NUTS)


def parse(d: dict) -> dict:
    """JSON-stat 2.0 → {series key: {geo: {year: value}}} for the map's geographies."""
    dims, size = d["id"], d["size"]
    stride = [1] * len(dims)
    for k in range(len(dims) - 2, -1, -1):
        stride[k] = stride[k + 1] * size[k + 1]
    cats = {dim: sorted(d["dimension"][dim]["category"]["index"].items(), key=lambda t: t[1]) for dim in dims}
    geo_dim = "geo" if "geo" in dims else "cities"  # the Urban Audit tables call it "cities"
    other = [dim for dim in dims if dim not in (geo_dim, "time", "freq")]
    out: dict = {}
    values = d["value"]
    if isinstance(values, list):
        values = {str(i): v for i, v in enumerate(values) if v is not None}

    def walk(k, offset, key):
        if k == len(other):
            series = out.setdefault("|".join(key), {})
            gi, ti = dims.index(geo_dim), dims.index("time")
            for geo, g in cats[geo_dim]:
                if not mapped_geo(geo):
                    continue
                row = {}
                for year, t in cats["time"]:
                    v = values.get(str(offset + g * stride[gi] + t * stride[ti]))
                    if v is not None:
                        row[year] = v
                if row:
                    series[geo] = row
            return
        dim = other[k]
        for code, i in cats[dim]:
            walk(k + 1, offset + i * stride[dims.index(dim)], key + [code])

    walk(0, 0, [])
    return out


class Eurostat(Source):
    after = ("uk_ons",)
    info = SourceInfo(
        id="eurostat",
        title="Eurostat regional and city statistics",
        publisher="Eurostat (European Commission), from the national statistical institutes",
        homepage="https://ec.europa.eu/eurostat/web/regions/database",
        license="Free reuse (Eurostat reuse policy, CC BY 4.0)",
        description="Population, age, GDP, value added and employment by branch of the NUTS 3 regions; unemployment, "
        "employment, degrees, household income, life expectancy and poverty of the NUTS 2 regions; population of the "
        "functional urban areas and core cities (Urban Audit). Read through Eurostat's dissemination API, since "
        + str(SINCE) + ". Tables: " + ", ".join(sorted({t for t, _, _ in TABLES.values()})) + ".",
        used_for=["Population, GDP and jobs of cities, countries and regions", "Yields (Gold, Production, Science…)",
                  "Socio-economic lenses"],
    )

    def _requests(self, key, table, filters):
        """One request per combination of the list-valued filters (the API refuses large extractions)."""
        lists = [(k, v) for k, v in filters.items() if isinstance(v, list)]
        fixed = [(k, v) for k, v in filters.items() if not isinstance(v, list)]
        for combo in itertools.product(*[v for _, v in lists]):
            q = [("sinceTimePeriod", str(SINCE))] + fixed + [(k, x) for (k, _), x in zip(lists, combo)]
            name = "_".join([key] + [x.replace("/", "-") for x in combo]) + ".json"
            yield API.format(table=table, query=urllib.parse.urlencode(q)), name

    def fetch(self, force=False):
        for key, (table, filters, _) in TABLES.items():
            for url, name in self._requests(key, table, filters):
                self.download(url, name, force=force)

    def process(self):
        tables = {}
        files = []
        for key, (table, filters, label) in TABLES.items():
            series, d = {}, {}
            for _, name in self._requests(key, table, filters):
                d = json.loads((self.raw_dir / name).read_text())
                series.update(parse(d))
                files.append(name)
            n = sum(len(s) for s in series.values())
            last = max((y for s in series.values() for row in s.values() for y in row), default=None)
            print(f"    {key:9s} {table:18s} {len(series)} series, {n} geo rows, latest {last}")
            tables[key] = {"table": table, "label": label, "updated": d.get("updated"), "series": series}
        # The United Kingdom left Eurostat's regional tables in 2020: the ONS figures in the same series
        # (sources/uk_ons.py), when that source has been processed.
        # Eurostat's own UK rows stop in 2018-2020 on NUTS 2016 codes: dropped, so no stale figure shows as current.
        from .gisco import uk_part
        uk = uk_part()
        if uk:
            for t in tables.values():
                for rows in t["series"].values():
                    for geo in [g for g in rows if g.startswith("UK")]:
                        del rows[geo]
        for key, by_series in (uk or {}).get("tables", {}).items():
            if key not in tables:
                continue
            for skey, rows in by_series.items():
                tables[key]["series"].setdefault(skey, {}).update(rows)
        if uk:
            print(f"    + United Kingdom (ONS) in {sorted(k for k in uk.get('tables', {}) if k in tables)}")
        return {
            "vintage": "Eurostat, " + ", ".join(sorted({t["updated"][:10] for t in tables.values() if t.get("updated")})[-1:]),
            "_files": files,
            "tables": tables,
        }
