"""Lenses = per-hex map overlays built from Eurostat's regional statistics, the local units' population and land cover.

Each hex of a map country is sampled at 7 points (world.py). A regional lens takes, for each hex, the mean of the
values of the regions under its 7 points (NUTS 3 figures; NUTS 2 figures for the rates Eurostat publishes only for
NUTS 2 regions), so a hex across a border blends both sides. Density spreads each local unit's 2021 census
population over the hexes (places.py) and divides by the hex's land area. Land lenses come from the hex's land-cover
samples.
"""

from __future__ import annotations

import math

from ..core.hexgrid import HexGrid
from ..core.geo import SCALE, MapProjection
from ..core.store import load_interim, write_web
from .yields import Stats

REQUIRES = ["_world", "_places", "eurostat", "canopy_eth", "ghsl_pop"]
PRODUCES = ["lenses.json", "_region_values", "timeline.json"]

GROUPS = [
    {"id": "people", "name": "People"},
    {"id": "prosperity", "name": "Prosperity"},
    {"id": "knowledge", "name": "Knowledge"},
    {"id": "climate", "name": "Climate"},
    {"id": "land", "name": "Land"},
]


def nice(v: float, up: bool) -> float:
    if v == 0:
        return 0
    mag = 10 ** (math.floor(math.log10(abs(v))) - 1)
    return round((math.ceil if up else math.floor)(v / mag) * mag, 10)


def percentile_domain(values: list, log: bool) -> list[float] | None:
    vals = sorted(v for v in values if v is not None and (v > 0 or not log))
    if not vals:
        return None
    lo, hi = vals[int(0.02 * (len(vals) - 1))], vals[int(0.98 * (len(vals) - 1))]
    lo, hi = nice(lo, False), nice(hi, True)
    return [lo, hi] if hi > lo else [lo, nice(vals[-1], True)]


DOMAIN_NOTE = " Colours span the 2nd to 98th percentile of hexes; values beyond take the end colour."

# id → (level, value function name, spec). Levels: "nuts3" (the region's own figure) or "nuts2" (its NUTS 2 parent's).
REGION_LENSES = {
    "growth": ("nuts3", {
        "group": "people", "name": "Growth", "icon": "l-growth",
        "format": "pct", "scale": "linear", "higher_is": "neutral",
        "ramp": ["#5b1a2a", "#a8434a", "#e0a08a", "#f2efe6", "#8fc1b5", "#2f7f86", "#123f52"],
        "source": "eurostat",
    }),
    "age": ("nuts3", {
        "group": "people", "name": "Median age", "icon": "l-age",
        "unit": "years", "format": "years", "scale": "linear", "higher_is": "neutral",
        "ramp": ["#00224e", "#35456c", "#666970", "#948e77", "#c8b866", "#fee838"], "source": "eurostat",
        "description": "Median age of the region's residents on 1 January (Eurostat demo_r_pjanind3, NUTS 3).",
    }),
    "seniors": ("nuts3", {
        "group": "people", "name": "Seniors", "icon": "l-age",
        "unit": "share aged 65 or over", "format": "pct", "scale": "linear", "higher_is": "neutral",
        "ramp": ["#0b1d3a", "#2d3f73", "#6a5a8e", "#a8738f", "#dc9a83", "#fbd8a5"], "source": "eurostat",
        "description": "Share of the region's residents aged 65 or over on 1 January (Eurostat demo_r_pjanaggr3, NUTS 3).",
    }),
    "youth": ("nuts3", {
        "group": "people", "name": "Children", "icon": "l-people",
        "unit": "share under 15", "format": "pct", "scale": "linear", "higher_is": "neutral",
        "ramp": ["#1a0b2e", "#3d1f5c", "#6b3f8a", "#a36cb0", "#d6a5cf", "#f6e3f1"], "source": "eurostat",
        "description": "Share of the region's residents under 15 on 1 January (Eurostat demo_r_pjanaggr3, NUTS 3).",
    }),
    "life_expectancy": ("nuts2", {
        "group": "people", "name": "Life expectancy", "icon": "l-amenities",
        "unit": "years at birth", "format": "float", "scale": "linear", "higher_is": "good",
        "ramp": ["#2b0f0e", "#6b2a1e", "#a85a2e", "#d39a4e", "#ead18a", "#f7f3d0"], "source": "eurostat",
        "description": "Life expectancy at birth, both sexes (Eurostat demo_r_mlifexp, NUTS 2, latest year published).",
    }),
    "gdp_capita": ("nuts3", {
        "group": "prosperity", "name": "GDP per person", "icon": "l-income",
        "unit": "€ per inhabitant, in purchasing power standards", "format": "usd", "scale": "log", "higher_is": "good",
        "ramp": ["#3a1c0b", "#7a4413", "#b8781f", "#e3b23c", "#f6e27f", "#fffbe0"], "source": "eurostat",
        "note": "GDP is counted where it is produced: regions with many commuters coming in (city centres, Luxembourg) "
                "look richer than their residents are.",
        "description": "Gross domestic product per inhabitant in purchasing power standards (PPS, EU27 = euros at "
                       "average EU prices), so price levels are comparable across countries (Eurostat nama_10r_3gdp, "
                       "NUTS 3). A region without a figure takes its larger region's; Iceland and Bosnia and "
                       "Herzegovina, which publish no regional figure, the national accounts' (nama_10_pc), and "
                       "Switzerland its PPS volume index times the EU level. Kosovo and Liechtenstein have none.",
    }),
    "income": ("nuts2", {
        "group": "prosperity", "name": "Household income", "icon": "l-income",
        "unit": "disposable income per inhabitant, PPS", "format": "usd", "scale": "linear", "higher_is": "good",
        "ramp": ["#2e1a05", "#6b3f0f", "#a8701e", "#d9a640", "#f2d886", "#fdf7da"], "source": "eurostat",
        "description": "Net disposable income of private households per inhabitant, in purchasing power standards "
                       "(Eurostat nama_10r_2hhinc, NUTS 2): what households have left to spend or save after taxes "
                       "and with social transfers. Iceland, Switzerland, Albania, Montenegro, North Macedonia, Serbia "
                       "and Kosovo publish no such account: their national figure is estimated from the EU-SILC "
                       "survey's mean income, times the median ratio between the two measures in the countries that "
                       "have both. Bosnia and Herzegovina and Liechtenstein have none.",
    }),
    "poverty": ("nuts2", {
        "group": "prosperity", "name": "Poverty", "icon": "l-poverty",
        "unit": "at risk of poverty or social exclusion", "format": "pct", "scale": "linear", "higher_is": "bad",
        "ramp": ["#03051a", "#4c1d4b", "#a11a5b", "#e83f3f", "#f69c73", "#faebdd"], "source": "eurostat",
        "description": "Share of people at risk of poverty or social exclusion (AROPE: below 60% of the national median "
                       "income, severely deprived, or in a household with very low work intensity), Eurostat "
                       "ilc_peps11n, NUTS 2. The poverty line is national, so the rate compares people with their own "
                       "country.",
    }),
    "unemployment": ("nuts2", {
        "group": "prosperity", "name": "Unemployment", "icon": "l-unemployment",
        "unit": "unemployed among the labour force aged 15-74", "format": "pct", "scale": "linear", "higher_is": "bad",
        "ramp": ["#0d1b2a", "#1b3a4b", "#3e5c76", "#8d6a9f", "#d17a8c", "#f6c5a0"], "source": "eurostat",
        "description": "Unemployment rate, ILO definition, ages 15-74 (Eurostat lfst_r_lfu3rt, labour force survey, "
                       "NUTS 2).",
    }),
    "employment": ("nuts2", {
        "group": "prosperity", "name": "Employment rate", "icon": "l-commute",
        "unit": "employed among people aged 20-64", "format": "pct", "scale": "linear", "higher_is": "good",
        "ramp": ["#1a1405", "#4a3a10", "#7f6a1f", "#b49d3a", "#dccd70", "#f7f2c4"], "source": "eurostat",
        "description": "Share of people aged 20-64 in employment (Eurostat lfst_r_lfe2emprt, NUTS 2).",
    }),
    "bachelors": ("nuts2", {
        "group": "knowledge", "name": "University degrees", "icon": "l-degrees",
        "unit": "share of 25-64 year-olds with tertiary education", "format": "pct", "scale": "linear",
        "higher_is": "good",
        "ramp": ["#08203e", "#0f4c81", "#2a7fc1", "#5fa8e0", "#a6d1f2", "#eaf5ff"], "source": "eurostat",
        "description": "Share of people aged 25-64 with tertiary education, ISCED levels 5-8 (Eurostat edat_lfse_04, "
                       "NUTS 2).",
    }),
}
LAND_LENSES = {
    "forest": (["forest"], {
        "name": "Forest", "icon": "l-forest",
        "ramp": ["#0b1f0f", "#14401c", "#1f6b2b", "#3a9443", "#7fc07a", "#d5efcd"],
        "description": "Share of the hex's land covered by broadleaf, coniferous or mixed forest (CORINE classes 311-313).",
    }),
    "farmland": (["crop", "pasture"], {
        "name": "Farmland", "icon": "l-farmland",
        "ramp": ["#141d05", "#2f4510", "#557019", "#84a02a", "#b8cf55", "#eef7b8"],
        "description": "Share of the hex's land in crops, vineyards, orchards, olive groves, pastures and mixed farming "
                       "(CORINE classes 211-244).",
    }),
    "developed": (["developed"], {
        "name": "Built-up", "icon": "l-developed",
        "ramp": ["#121218", "#2c2c3c", "#4b4b66", "#727294", "#a3a3c2", "#e2e2f0"],
        "description": "Share of the hex's land that is built up: urban fabric, industrial and commercial areas, "
                       "transport networks, construction sites (CORINE 111-133; green urban areas do not count).",
    }),
}
CLASS_LENSES = {
    "vines": ([221], "Vineyards", "#a33b5c", "Share of the hex's land in vineyards (CORINE class 221)."),
    "olives": ([223], "Olive groves", "#7d8c3a", "Share of the hex's land in olive groves (CORINE class 223)."),
    "orchards": ([222], "Orchards", "#b5652b", "Share of the hex's land in fruit trees and berry plantations (CORINE 222)."),
}


# The United Kingdom's regional figures come from its own statistical offices (sources/uk_ons.py).
UK_NOTE = " United Kingdom: ONS, NRS and NISRA figures for its ITL regions."
UK_NOTES = {
    "income": " United Kingdom: gross disposable household income per head (ONS), a little above the net measure.",
    "poverty": " The United Kingdom publishes no regional rate on this definition: blank.",
    "unemployment": " United Kingdom: Annual Population Survey, ages 16 and over.",
    "employment": " United Kingdom: Annual Population Survey, ages 16-64.",
    "bachelors": " United Kingdom: Annual Population Survey, qualifications at level 4 or above, ages 16-64.",
    "life_expectancy": " United Kingdom: the mean of men's and women's life expectancy by local area (ONS).",
}


def build() -> None:
    world = load_interim("_world")
    places = load_interim("_places")
    s = Stats(world["counties"], places["region_pop"])
    grid = HexGrid(**world["grid"])
    owner = world["owner"]
    samples = world["county_samples"]
    regions = world["counties"]
    hex_area = 1.5 * math.sqrt(3) * (grid.radius / SCALE) ** 2

    def region_value(lid: str, g: str):
        if lid == "growth":
            a, b = s.value("pop3", "TOTAL", g, s.growth_from), s.value("pop3", "TOTAL", g, s.pop_year)
            v = b / a - 1 if a and b else None
            return v if v is None or abs(v) <= 0.15 else None
        if lid == "age":
            return s.latest("medage3", "MEDAGEPOP", g)[1]
        if lid in ("seniors", "youth"):
            part = s.value("pop3", "Y_GE65" if lid == "seniors" else "Y_LT15", g, s.pop_year)
            tot = s.value("pop3", "TOTAL", g, s.pop_year)
            return part / tot if part is not None and tot else None
        if lid == "gdp_capita":  # the region's own figure, else its larger region's, else the country's
            for geo in (g, g[:4], g[:3], g[:2]):
                v = s.at("gdp3", "PPS_EU27_2020_HAB", geo, s.gdp_year, 2)
                if v is not None:
                    return v
            return None
        table, code, scale = {
            "income": ("income2", "PPS_EU27_2020_HAB", 1), "poverty": ("arope2", "PC", 100),
            "unemployment": ("unemp2", "PC", 100), "employment": ("emprate2", "PC", 100),
            "bachelors": ("tertiary2", "ED5-8", 100), "life_expectancy": ("lifeexp2", "YR", 1),
        }[lid]
        for geo in (g[:4], g[:3], g[:2]):
            v = s.latest(table, code, geo)[1]
            if v is not None:
                return v / scale
        return None

    lenses = []
    # Density: local units' population per hex ÷ the hex's land area (share of its 7 samples on land). A hex of an
    # inset drawn at scale k covers 1/k² of a main-map hex's ground.
    proj = MapProjection(**world["projection"])
    hex_km2 = [hex_area] * grid.size
    for i in range(grid.size):
        if owner[i] >= 0:
            ins = proj.frame_of(*grid.center(*grid.col_row(i)))
            if ins is not None:
                hex_km2[i] = hex_area / ins.d["k"] ** 2
    land_km2 = [None] * grid.size
    for i, smp in enumerate(samples):
        if owner[i] >= 0:
            land_km2[i] = hex_km2[i] * (sum(1 for x in smp if x >= 0) or 7) / 7
    hexpop = places["hexpop"]
    density = [None] * grid.size
    for i in range(grid.size):
        if land_km2[i]:
            density[i] = round(hexpop[i] / land_km2[i], 2)
    lenses.append({
        "id": "density", "group": "people", "name": "Density", "icon": "l-people",
        "unit": "people / km²", "format": "int", "scale": "log",
        "ramp": ["#1b1035", "#4b2377", "#9a3b8a", "#e0645e", "#f9b24a", "#fff3a8"], "higher_is": "neutral",
        "source": "gisco",
        "description": "People per km² of land. Each local administrative unit's 2021 census population (GISCO LAU) is "
                       "placed on the hex of its centre, or spread evenly over the hexes within its own radius when "
                       "it is larger than a hex. Bosnia and Herzegovina, Montenegro and Kosovo have no local units: "
                       "their towns and villages are counted with the population GeoNames records for them, often "
                       "from an older census. Iceland's municipalities, which GISCO lists without a population, "
                       "take Statistics Iceland's latest figures." + DOMAIN_NOTE,
        "values": density, "domain": percentile_domain(density, True),
    })

    region_cache: dict = {}
    for lid, (level, spec) in REGION_LENSES.items():
        vals_by_region = [region_value(lid, g) for g in regions]
        region_cache[lid] = vals_by_region
        values = [None] * grid.size
        for i, smp in enumerate(samples):
            if owner[i] < 0:
                continue
            vs = [vals_by_region[k] for k in smp if k >= 0 and vals_by_region[k] is not None]
            if vs:
                values[i] = round(sum(vs) / len(vs), 4)
        spec = dict(spec)
        if lid == "growth":
            spec["unit"] = f"population change, {s.growth_from}-{s.pop_year}"
            spec["description"] = (f"Change in the region's population between 1 January {s.growth_from} and 1 January "
                                   f"{s.pop_year} (Eurostat demo_r_pjanaggr3, NUTS 3). A change beyond ±15% is a break "
                                   "in the series (a census revision), left blank.")
        log = spec["scale"] == "log"
        lenses.append({"id": lid, **spec, "description": spec["description"] + UK_NOTES.get(lid, UK_NOTE) + DOMAIN_NOTE,
                       "values": values,
                       "domain": percentile_domain(values, log)})

    pct = world["pct"]
    for lid, (keys, spec) in LAND_LENSES.items():
        values = [None] * grid.size
        for i in range(grid.size):
            if owner[i] >= 0 and world["cover"][i]:
                values[i] = round(sum(pct[k][i] for k in keys) / 100, 3)
        lenses.append({"id": lid, "group": "land", **spec, "unit": "share of the land", "format": "pct",
                       "scale": "linear", "higher_is": "neutral", "source": "corine_eu", "values": values,
                       "domain": [0, 1]})
    for lid, (codes, name, colour, desc) in CLASS_LENSES.items():
        values = [None] * grid.size
        for i, counts in enumerate(world["clc"]):
            if not counts or owner[i] < 0:
                continue
            land = sum(n for c, n in counts.items() if not str(c).startswith("5"))
            if land:
                values[i] = round(sum(counts.get(str(c), counts.get(c, 0)) for c in codes) / land, 3)
        dom = percentile_domain([v for v in values if v], False) or [0, 0.2]
        lenses.append({"id": lid, "group": "land", "name": name, "icon": "l-farmland", "unit": "share of the land",
                       "format": "pct", "scale": "linear", "higher_is": "neutral", "source": "corine_eu",
                       "ramp": ["#141414", "#2b2622", colour, "#e8d9c8"], "description": desc + DOMAIN_NOTE,
                       "values": values, "domain": [0, dom[1]]})

    lenses += density_history_lens(world, grid, proj, land_km2, lenses[0]["domain"])
    lenses += climate_lenses(world, grid)
    lenses += forest_height_lens(world, grid)
    write_web("lenses.json", {"vintage": f"Eurostat {s.pop_year}, GISCO LAU 2021, land cover 2018", "groups": GROUPS,
                              "lenses": lenses})
    save_region_values(world, region_cache)
    cover = {l["id"]: sum(1 for v in l["values"] if v is not None) for l in lenses}
    print(f"    {len(lenses)} lenses; hexes with a value: {cover}")


def density_history_lens(world: dict, grid: HexGrid, proj, land_km2: list, domain) -> list[dict]:
    """Density every five years since 1975 from GHS-POP (ghsl_pop): each 2 km block of the grid goes to the hex under
    its centre (a coastal block in a sea hex to the nearest land hex); the hex's people ÷ its land area. The lens shows the last epoch; timeline.json holds every epoch, on
    the density lens's colour scale. Empty if the source has not been processed."""
    import zlib
    from array import array

    from ..core.paths import INTERIM
    from ..sources.ghsl_pop import mollweide_inverse
    from .world import FOREIGN

    try:
        g = load_interim("ghsl_pop")
    except FileNotFoundError:
        print("    ghsl_pop not processed: no density timeline")
        return []
    epochs = g["epochs"]
    blob = (INTERIM / g["raster"]).read_bytes()
    owner = world["owner"]
    side, step = g["side"], g["block_m"]
    people = {y: [0.0] * grid.size for y in epochs}
    for t in g["tiles"]:
        grids = {}
        for y, (off, n) in t["epochs"].items():
            a = array("f")
            a.frombytes(zlib.decompress(blob[off:off + n]))
            grids[int(y)] = a
        for k in range(side * side):
            if not any(a[k] > 0 for a in grids.values()):
                continue
            lon, lat = mollweide_inverse(t["x0"] + (k % side + 0.5) * step, t["y0"] - (k // side + 0.5) * step)
            if not (-180 <= lon <= 180):
                continue
            x, y = proj(lon, lat)
            c = grid.cell_at(x, y)
            if c < 0 or owner[c] == FOREIGN:
                continue
            if owner[c] < 0:  # a coastal block whose centre is in a sea hex: the nearest land hex of a map country
                near = [(math.dist((x, y), grid.center(*grid.col_row(j))), j) for j in grid.neighbours(c) if owner[j] >= 0]
                if not near:
                    continue
                c = min(near)[1]
            for yr, a in grids.items():
                people[yr][c] += a[k]
    frames = [[round(people[y][i] / land_km2[i], 2) if land_km2[i] else None for i in range(grid.size)]
              for y in epochs]
    totals = {y: round(sum(people[y])) for y in epochs}
    print(f"    density timeline: people on the map's hexes by epoch {totals}")
    write_web("timeline.json", {"lens": "density_history", "years": epochs, "values": frames})
    return [{
        "id": "density_history", "group": "people", "name": f"Density since {epochs[0]}", "icon": "l-people",
        "unit": "people / km²", "format": "int", "scale": "log",
        "ramp": ["#1b1035", "#4b2377", "#9a3b8a", "#e0645e", "#f9b24a", "#fff3a8"], "higher_is": "neutral",
        "source": "ghsl_pop",
        "description": f"People per km² of land every five years from {epochs[0]} to {epochs[-1]}: drag the slider or "
        "press Play. From the European Commission's Global Human Settlement Layer (GHS-POP R2023A), which spreads "
        "each country's census counts over the built-up areas that Landsat and Sentinel-2 saw at each date, on a "
        "1 km grid. From 1975 to 2020 the Madrid region grows by about 70% and Ireland's east by two thirds, while "
        "Castile and León, Extremadura and the Alentejo lose 10 to 15%, Saxony-Anhalt and Thuringia nearly a "
        "quarter, Latvia a quarter and Bulgaria a fifth. Same colours for every year, those of the Density lens.",
        "frames": {"file": "timeline", "years": epochs, "frame": len(epochs) - 1},
        "values": frames[-1], "domain": domain,
    }]


def save_region_values(world, cache):
    """The regional values the lenses used, for counties.json (the same formulas)."""
    from ..core.store import save_interim
    save_interim("_region_values", {"regions": world["counties"], "values": cache})


def forest_height_lens(world: dict, grid: HexGrid) -> list[dict]:
    """Forest height from the canopy_eth raster (ETH's GEDI-trained canopy height map, 1/32 overview): the mean
    height at the hex's land-cover points (world.py's lattice) that fall in CORINE forest, 10 of them at least.
    Empty if the source has not been processed."""
    from ..core.geo import Laea3035, MapProjection
    from ..core.paths import INTERIM
    from .world import HEX_RADIUS_KM, NLCD_STEP_KM, hex_lattice

    try:
        eth = load_interim("canopy_eth")
    except FileNotFoundError:
        print("    canopy_eth not processed: no forest height lens")
        return []
    clc = load_interim("corine_eu")
    raster = (INTERIM / clc["raster"]).read_bytes()
    rw, rh, px, rx0, ry0 = clc["width"], clc["height"], clc["pixel"], clc["x0"], clc["y0"]
    forest = {int(v) for v, c in clc["values"].items() if c in (311, 312, 313)}
    canopy = (INTERIM / eth["raster"]).read_bytes()
    tiles = {(round(t["west"]), round(t["north"])): t for t in eth["tiles"]}
    proj = MapProjection(**world["projection"])
    laea = Laea3035()
    owner = world["owner"]
    lattice = hex_lattice(HEX_RADIUS_KM, NLCD_STEP_KM)
    values = [None] * grid.size
    for i, counts in enumerate(world["clc"]):
        if owner[i] < 0 or not counts or not any(counts.get(str(c), counts.get(c, 0)) for c in (311, 312, 313)):
            continue
        cx, cy = grid.center(*grid.col_row(i))
        if proj.frame_of(cx, cy) is not None:
            continue  # the outermost regions are not on the CORINE raster
        n = total = 0
        for ox, oy in lattice:
            lon, lat = proj.inverse(cx + ox, cy + oy)
            X, Y = laea(lon, lat)
            c, r = int((X - rx0) / px), int((ry0 - Y) / px)
            if not (0 <= c < rw and 0 <= r < rh) or raster[r * rw + c] not in forest:
                continue
            t = tiles.get((math.floor(lon / 3) * 3, math.floor(lat / 3) * 3 + 3))
            if t is None:
                continue
            tc, tr = int((lon - t["west"]) / t["deg"]), int((t["north"] - lat) / t["deg"])
            if 0 <= tc < t["width"] and 0 <= tr < t["height"]:
                v = canopy[t["offset"] + tr * t["width"] + tc]
                if v != eth["nodata"]:
                    n += 1
                    total += v
        if n >= 10:
            values[i] = round(total / n, 1)
    return [{
        "id": "forest_height", "group": "land", "name": "Forest height", "icon": "l-forest",
        "unit": "m, mean height of the forests", "format": "metres", "scale": "linear", "higher_is": "neutral",
        "ramp": ["#10180c", "#22381a", "#2f5a26", "#3f8236", "#6fb15a", "#c6e8a8"],
        "source": "canopy_eth",
        "description": "Mean canopy height of the hex's forests (CORINE classes 311 to 313), from ETH Zurich's 2020 "
        "map of the world's canopy height: a deep network learned the heights NASA's GEDI LiDAR measured from the "
        "International Space Station, then estimated them everywhere from Sentinel-2 images at 10 m. Read here at "
        "about 300 m, at the hex's forest land-cover points (10 at least). The Alpine and Dinaric forests of "
        "Switzerland, Slovenia and Austria average 25 m, Finland's and Norway's boreal forests 13 m, Iberian "
        "woodland 10 to 11 m. The outermost regions are not covered."
        + DOMAIN_NOTE,
        "values": values, "domain": percentile_domain(values, False),
    }]


def climate_lenses(world: dict, grid: HexGrid) -> list[dict]:
    """Temperature, warming, rainfall and rainfall change from the climate_eu decade grids (EPSG:3035): each hex of a
    map country takes the mean of the grid points inside it (or the point nearest its centre). Empty if the source
    has not been processed."""
    from array import array

    from ..core.geo import Laea3035, MapProjection
    from ..core.paths import INTERIM

    try:
        clim = load_interim("climate_eu")["grids"]
    except FileNotFoundError:
        print("    climate_eu not processed: no climate lenses")
        return []
    proj = MapProjection(**world["projection"])
    laea = Laea3035()
    owner = world["owner"]
    rasters = {}
    for key, g in clim.items():
        a = array("f")
        a.frombytes((INTERIM / g["raster"]).read_bytes())
        rasters[key] = (g, a)
    offsets = [(0.0, 0.0)] + [(dx * 9.0, dy * 9.0) for dx, dy in ((1, 0), (-1, 0), (0.5, 0.87), (-0.5, 0.87),
                                                                    (0.5, -0.87), (-0.5, -0.87))]

    def hex_values(key):
        g, a = rasters[key]
        out = [None] * grid.size
        for i in range(grid.size):
            if owner[i] < 0:
                continue
            cx, cy = grid.center(*grid.col_row(i))
            if proj.frame_of(cx, cy) is not None and proj.frame_of(cx, cy).d["dep"].startswith("FRY"):
                continue  # the grids stop at Europe: not the Caribbean, Guiana or the Indian Ocean
            vals = []
            for ox, oy in offsets:
                lon, lat = proj.inverse(cx + ox, cy + oy)
                X, Y = laea(lon, lat)
                c, r = int((X - g["x0"]) / g["step"] + 0.5), int((g["y0"] - Y) / g["step"] + 0.5)
                if 0 <= c < g["width"] and 0 <= r < g["height"]:
                    v = a[r * g["width"] + c]
                    if v == v:
                        vals.append(v)
            if vals:
                out[i] = sum(vals) / len(vals)
        return out

    t0, t1 = hex_values("t_2000s"), hex_values("t_2010s")
    p0, p1 = hex_values("p_2000s"), hex_values("p_2010s")
    yt0, yt1 = clim["t_2000s"]["years"], clim["t_2010s"]["years"]
    yp0, yp1 = clim["p_2000s"]["years"], clim["p_2010s"]["years"]
    n0, n1 = yp0[1] - yp0[0] + 1, yp1[1] - yp1[0] + 1
    temp = [round((a + b) / 2, 2) if a is not None and b is not None else None for a, b in zip(t0, t1)]
    warm = [round(b - a, 2) if a is not None and b is not None else None for a, b in zip(t0, t1)]
    rain = [round((a * n0 + b * n1) / (n0 + n1)) if a is not None and b is not None else None for a, b in zip(p0, p1)]
    rchg = [round(b / a - 1, 4) if a and b is not None else None for a, b in zip(p0, p1)]
    src = "climate_eu"
    note_short = (f"One decade ({yt1[0]}-{yt1[1]}) against the one before ({yt0[0]}-{yt0[1]}): over so short a span, "
                  "a few unusual years weigh on the difference.")
    lenses = [
        {"id": "temperature", "group": "climate", "name": "Temperature", "icon": "l-temperature",
         "unit": f"°C, yearly mean {yt0[0]}-{yt1[1]}", "format": "celsius", "scale": "linear", "higher_is": "neutral",
         "ramp": ["#2b3a8c", "#4f7cc2", "#9cc5dd", "#f2e6b6", "#f0a35c", "#c8452c", "#7a1420"], "source": src,
         "description": f"Mean air temperature at 2 m over {yt0[0]}-{yt1[1]} (ERA5 reanalysis downscaled to 1 km with "
                        "CHELSA, sampled every 5 km): relief first, then latitude and the sea.",
         "values": temp},
        {"id": "warming", "group": "climate", "name": "Warming", "icon": "l-warming",
         "unit": f"°C warmer in {yt1[0]}-{yt1[1]} than in {yt0[0]}-{yt0[1]}", "format": "dcelsius", "scale": "linear",
         "higher_is": "bad", "ramp": ["#2f6fa8", "#a7c7dc", "#fbe3b0", "#f6b26b", "#e8783f", "#c8452c", "#8e1c24"],
         "source": src, "note": note_short,
         "description": f"Change in the mean temperature between {yt0[0]}-{yt0[1]} and {yt1[0]}-{yt1[1]} (ERA5/CHELSA). "
                        "A thirty-year comparison would be steadier; this is what the 1 km monthly series allows.",
         "values": warm},
        {"id": "rainfall", "group": "climate", "name": "Rainfall", "icon": "l-rain",
         "unit": f"mm a year, {yp0[0]}-{yp1[1]}", "format": "int", "scale": "log", "higher_is": "neutral",
         "ramp": ["#f4ecd6", "#cfe0d8", "#8fc1cf", "#4f8fbf", "#2b5ea8", "#1b2f73"], "source": src,
         "description": f"Yearly precipitation (rain and snow) averaged over {yp0[0]}-{yp1[1]} (CHELSA, 1 km, read at "
                        "about 8 km): from the soaked western slopes (Norway's coast, the Alps, the Dinaric Alps) to the "
                        "dry south-east of Spain.",
         "values": rain},
        {"id": "rain_change", "group": "climate", "name": "Rainfall change", "icon": "l-rain",
         "unit": f"change in yearly rainfall, {yp1[0]}-{yp1[1]} vs {yp0[0]}-{yp0[1]}", "format": "change",
         "scale": "linear", "higher_is": "neutral",
         "ramp": ["#8c510a", "#d8b365", "#f6e8c3", "#f5f5f5", "#c7eae5", "#5ab4ac", "#01665e"], "source": src,
         "note": "Rainfall varies a lot from year to year: a decade-to-decade change mixes trend and chance.",
         "description": f"Yearly precipitation in {yp1[0]}-{yp1[1]} compared with {yp0[0]}-{yp0[1]} (CHELSA).",
         "values": rchg},
    ]
    for l in lenses:
        l["domain"] = percentile_domain(l["values"], l["scale"] == "log")
        l["description"] += DOMAIN_NOTE
    return lenses
