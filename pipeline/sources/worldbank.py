"""World Development Indicators (World Bank): a few national figures for the countries Eurostat leaves blank, so a
country without a regional series still has a population and an age structure. Used only where Eurostat
has no figure (states.py), and named in the notes where it is."""

from __future__ import annotations

import json

from ..core.europe import COUNTRIES, ISO2
from ..core.source import Source, SourceInfo

API = "https://api.worldbank.org/v2/country/{iso}/indicator/{ind}?format=json&per_page=100&date=2010:2030"
INDICATORS = {
    "SP.POP.TOTL": "population",
    "SP.DYN.LE00.IN": "life_expectancy",
    "SP.POP.0014.TO.ZS": "youth_pct",
    "SP.POP.65UP.TO.ZS": "seniors_pct",
}
COUNTRIES_FILLED = ["BA", "XK", "ME", "AL", "MK", "RS", "LI"]  # the countries with gaps in Eurostat's tables


class WorldBank(Source):
    info = SourceInfo(
        id="worldbank",
        title="World Development Indicators (World Bank)",
        publisher="The World Bank",
        homepage="https://data.worldbank.org/",
        license="CC BY 4.0",
        description="National population, life expectancy and shares of under-15s and over-65s for the "
        "countries Eurostat publishes no figure for (chiefly Bosnia and Herzegovina and Kosovo). Used only to fill "
        "those blanks.",
        used_for=["Population, age structure and life expectancy of Bosnia and Herzegovina and Kosovo, where Eurostat "
                  "has none"],
    )

    def fetch(self, force=False):
        for code in COUNTRIES_FILLED:
            iso = ISO2[code]
            for ind in INDICATORS:
                self.download(API.format(iso=iso, ind=ind), f"{iso}_{ind}.json", force=force)

    def process(self):
        out, files = {}, []
        for code in COUNTRIES_FILLED:
            iso = ISO2[code]
            row = {}
            for ind, key in INDICATORS.items():
                name = f"{iso}_{ind}.json"
                payload = json.loads((self.raw_dir / name).read_text())
                obs = payload[1] if len(payload) > 1 and payload[1] else []
                series = {int(o["date"]): o["value"] for o in obs if o.get("value") is not None}
                if series:
                    row[key] = {str(y): v for y, v in sorted(series.items())}
                    files.append(name)
            out[code] = row
        assert set(out) <= set(COUNTRIES)
        print(f"    {sum(len(r) for r in out.values())} series for {', '.join(out)}")
        return {"vintage": "World Development Indicators", "_files": files, "countries": out}
