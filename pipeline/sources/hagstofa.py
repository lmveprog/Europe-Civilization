"""Population of Iceland's municipalities on 1 January (Statistics Iceland, table MAN02005), for the local units GISCO
publishes without a population (LAU 2021 has none for Iceland).

The table follows today's municipalities; since 2021 several merged. Each merged municipality's population goes to its
largest 2021 unit (the town that gave it its name or seat), the units it absorbed get none."""

from __future__ import annotations

import json

from ..core.source import Source, SourceInfo

API = "https://px.hagstofa.is/pxen/api/v1/en/Ibuar/mannfjoldi/2_byggdir/sveitarfelog/MAN02005.px"
# LAU 2021 unit → today's municipality, where they differ (None: absorbed by a merger, its people counted in the unit
# named on the right-hand side of another entry).
LAU_TO_NOW = {
    "3711": "3716", "3710": None,                  # Stykkishólmur ← Stykkishólmsbær + Helgafellssveit (2022)
    "5604": "5613", "5612": None, "5611": None,    # Húnabyggð ← Blönduóssbær + Húnavatnshreppur (2022), Skagabyggð (2024)
    "5200": "5716", "5706": None,                  # Skagafjörður ← Sveitarfélagið Skagafjörður + Akrahreppur (2022)
    "6612": "6613", "6607": None,                  # Þingeyjarsveit ← Þingeyjarsveit + Skútustaðahreppur (2022)
    "6709": "6710", "6706": None,                  # Langanesbyggð ← Langanesbyggð + Svalbarðshreppur (2022)
    "4607": "4604", "4604": None,                  # Vesturbyggð ← Vesturbyggð + Tálknafjarðarhreppur (2024)
}


class Hagstofa(Source):
    info = SourceInfo(
        id="hagstofa",
        title="Population by municipality, 1 January (Statistics Iceland, MAN02005)",
        publisher="Statistics Iceland (Hagstofa Íslands)",
        homepage="https://px.hagstofa.is/pxen/pxweb/en/Ibuar/Ibuar__mannfjoldi__2_byggdir__sveitarfelog/MAN02005.px",
        license="CC BY 4.0",
        description="Residents of each of Iceland's municipalities on 1 January of the latest year, for the local "
        "units GISCO lists without a population. A municipality formed by a merger since 2021 is counted on its "
        "largest former unit.",
        used_for=["Population of Iceland's municipalities (density, search, place names)"],
    )

    def fetch(self, force=False):
        meta = json.loads(self.download(API, "MAN02005_meta.json", force=force).read_text())
        years = next(v for v in meta["variables"] if v["code"] == "Ár")["values"]
        query = {"query": [
            {"code": "Sveitarfélag", "selection": {"filter": "all", "values": ["*"]}},
            {"code": "Aldur", "selection": {"filter": "item", "values": ["-1"]}},
            {"code": "Ár", "selection": {"filter": "item", "values": [years[-1]]}},
            {"code": "Kyn", "selection": {"filter": "item", "values": ["0"]}},
        ], "response": {"format": "json-stat2"}}
        path = self.raw_dir / "MAN02005.json"
        if path.exists() and not force:
            return
        import urllib.request

        from ..core.fetch import USER_AGENT, record
        req = urllib.request.Request(API, data=json.dumps(query).encode(), method="POST",
                                     headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            body = r.read()
        json.loads(body)
        path.write_bytes(body)
        record(self.id, "MAN02005.json", API, f"POST: every municipality, all ages, both sexes, {years[-1]}")

    def process(self):
        d = json.loads((self.raw_dir / "MAN02005.json").read_text())
        dim = d["dimension"]["Sveitarfélag"]["category"]
        order = sorted(dim["index"], key=dim["index"].get)
        year = next(iter(d["dimension"]["Ár"]["category"]["index"]))
        now = {code: int(v) for code, v in zip(order, d["value"]) if v is not None and code != "9999"}
        print(f"    {len(now)} municipalities, {sum(now.values()):,} people on 1 January {year}")
        return {"vintage": f"Statistics Iceland, 1 January {year}", "_files": ["MAN02005.json"], "year": int(year),
                "municipalities": now, "lau_to_now": LAU_TO_NOW}
