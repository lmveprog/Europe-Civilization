"""Countries (the map's "states"): the same economic profile as a city (Eurostat), ranks, and a label anchor.

Also land-cover shares over the country's hexes and the MW of the power plants mapped in resources.json (only the
sites above each type's threshold, so not the country's total capacity).

Ranks are among the 37 countries of the map (1 = largest). The label anchor is the country's "pole of
inaccessibility" on the hex map (the hex farthest from the border, by hex steps, or one nearly as deep that fits a
bigger name), turned along the country's long axis when that helps, and sized to fit the run of its own hexes through
the anchor. `size` assumes ~0.6 em per character.
"""

from __future__ import annotations

import json
import math
from collections import deque

from ..core.europe import COUNTRIES, EFTA, EU
from ..core.hexgrid import HexGrid
from ..core.paths import WEB_DATA
from ..core.store import load_interim, write_web
from .yields import YIELDS, Stats, economy, growth_of, nuts2_rates, region_profile

REQUIRES = ["_world", "_places", "eurostat", "gisco", "worldbank", "resources.json"]
PRODUCES = ["states.json"]

MIN_LABEL_KM, MAX_LABEL_KM = 14.0, 240.0  # suggested font height range, map units


def national_extras(s: Stats, code: str) -> dict:
    """The country's share born abroad (2021 census), tourist nights per resident and R&D spending (share of GDP),
    from the same Eurostat tables as the lenses; null where Eurostat has no national figure."""
    series = s.t["born3"]["series"] if "born3" in s.t else {}
    born = next((v for k, v in series.items() if k.startswith("FOR|")), {})
    total = next((v for k, v in series.items() if k.startswith("TOTAL|")), {})
    f, t = born.get(code, {}).get("2021"), total.get(code, {}).get("2021")
    y, nights = s.latest("tourism3", "I551-I553", code) if "tourism3" in s.t else (None, None)
    pop = s.at("pop0", "TOTAL", code, str(y)) if y else None
    rd = s.latest("rd2", "TOTAL", code)[1] if "rd2" in s.t else None
    return {
        "born_abroad": round(f / t, 4) if f is not None and t else None,
        "tourist_nights": round(nights / pop, 2) if nights is not None and pop else None,
        "tourist_year": y if nights is not None and pop else None,
        "rd_gdp": round(rd / 100, 4) if rd is not None else None,
    }


def outline_areas(states: list[dict]) -> None:
    """Countries without local units (Bosnia and Herzegovina, Montenegro, Kosovo) have no summed LAU area: the area of
    their regions' GISCO outlines instead (equal-area projection), and the density that follows."""
    from ..core.geo import Laea

    laea = Laea()

    def ring_km2(ring):
        pts = [laea(lon, lat) for lon, lat in ring]
        return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]))) / 2

    nuts = load_interim("gisco")["nuts"]
    for st in states:
        if st.get("land_km2") is not None:
            continue
        regs = [n for n in nuts if n["country"] == st["abbr"] and n.get("rings")]
        if not regs:
            continue
        deepest = max(n["level"] for n in regs)
        st["land_km2"] = round(sum(ring_km2(r) for n in regs if n["level"] == deepest for r in n["rings"]))
        if st.get("population"):
            st["density"] = round(st["population"] / st["land_km2"], 1)


def world_bank_fill(states: list[dict]) -> None:
    """National World Bank figures where Eurostat has none (Bosnia and Herzegovina's population and age structure,
    land areas where there are no local units). Each country lists the fields filled this way in `worldbank`."""
    try:
        wb = load_interim("worldbank")["countries"]
    except FileNotFoundError:
        print("    worldbank not processed: Eurostat's blanks stay blank")
        return

    for st in states:
        row = wb.get(st["abbr"]) or {}
        filled = []

        def latest(key):
            ser = row.get(key) or {}
            y = max(ser, key=int) if ser else None
            return (int(y), ser[y]) if y else (None, None)

        if st.get("population") is None and row.get("population"):
            ser = row["population"]
            y, v = latest("population")
            st["population"] = round(v)
            st["pop_series"] = {k: round(x) for k, x in ser.items() if int(k) >= 2014}
            filled.append("population")
            if st.get("growth") is None and str(y - 5) in ser:
                g = v / ser[str(y - 5)] - 1
                if abs(g) <= 0.15:
                    st["growth"], st["growth_years"] = round(g, 4), [y - 5, y]
                    filled.append("growth")
            if st.get("gdp_per_capita") is None and st.get("gdp"):
                st["gdp_per_capita"] = round(st["gdp"] / st["population"])
        for key, field, scale, digits in (("life_expectancy", "life_expectancy", 1, 1), ("youth_pct", "youth", 0.01, 4),
                                          ("seniors_pct", "seniors", 0.01, 4)):
            if st.get(field) is None and row.get(key):
                st[field] = round(latest(key)[1] * scale, digits)
                filled.append(field)
        if st.get("density") is None and st.get("population") and st.get("land_km2"):
            st["density"] = round(st["population"] / st["land_km2"], 1)
            filled.append("density")
        if filled:
            st["worldbank"] = filled
    print(f"    World Bank fills: { {st['abbr']: st['worldbank'] for st in states if st.get('worldbank')} }")


def label_anchor(grid: HexGrid, owner: list[int], s: int, name: str) -> dict | None:
    """{x, y, angle, size} for state index `s`, or None if it owns no hex (e.g. DC).

    angle: degrees, clockwise on screen (y down), in (-90, 90]. size: suggested font height in map km.
    """
    cells = [i for i, o in enumerate(owner) if o == s]
    if not cells:
        return None
    # Multi-source BFS from the border hexes inward.
    dist = {}
    queue = deque()
    for c in cells:
        nb = grid.neighbours(c)
        if len(nb) < 6 or any(owner[n] != s for n in nb):
            dist[c] = 0
            queue.append(c)
    while queue:
        c = queue.popleft()
        for n in grid.neighbours(c):
            if owner[n] == s and n not in dist:
                dist[n] = dist[c] + 1
                queue.append(n)
    pts = {c: grid.center(*grid.col_row(c)) for c in cells}
    mx = sum(p[0] for p in pts.values()) / len(cells)
    my = sum(p[1] for p in pts.values()) / len(cells)

    # Principal axis of the hex centres. Labels stay horizontal unless tilting them
    # along a clearly elongated state (at most 45°) allows a much bigger name.
    sxx = sum((p[0] - mx) ** 2 for p in pts.values())
    syy = sum((p[1] - my) ** 2 for p in pts.values())
    sxy = sum((p[0] - mx) * (p[1] - my) for p in pts.values())
    theta = 0.5 * math.atan2(2 * sxy, sxx - syy)  # (-90°, 90°], clockwise on screen
    angles = [0.0] + ([theta] if 1 <= abs(math.degrees(theta)) <= 45 else [])
    step = grid.radius / 4

    def reach(x: float, y: float, ux: float, uy: float) -> float:
        """Distance (km) from (x, y) along (ux, uy) before leaving the state's hexes."""
        t = 0.0
        while True:
            c = grid.cell_at(x + (t + step) * ux, y + (t + step) * uy)
            if c < 0 or owner[c] != s:
                return t + step / 2
            t += step

    def fit(c: int, t: float) -> float:
        """Font height (km) for a label centred on hex c at angle t: ~0.6 em per character
        over 90% of the local run through c, and no taller than 80% of the local breadth.
        The run is then re-measured along the label's top and bottom edges (twice), so the
        whole box, not just its centre line, stays inside the state."""
        (x, y), ux, uy = pts[c], math.cos(t), math.sin(t)
        across = 2 * min(reach(x, y, -uy, ux), reach(x, y, uy, -ux))
        h, offsets = 0.8 * across, [0.0]
        for _ in range(3):
            along = min(
                2 * min(reach(x - o * uy, y + o * ux, ux, uy), reach(x - o * uy, y + o * ux, -ux, -uy))
                for o in offsets
            )
            h = min(h, 0.9 * along / (0.6 * max(len(name), 4)))
            offsets = [0.0, h / 2, -h / 2]
        return h

    # Candidates: the pole of inaccessibility and hexes nearly as deep; pick the one (and angle)
    # that fits the biggest label, a tilted label only if it is 25% bigger than a flat one.
    far = max(dist.values())
    best = None
    for c in cells:
        if dist[c] < far - 1:
            continue
        for t in angles:
            size = fit(c, t) / (1.25 if t else 1.0)
            score = (round(size), -math.hypot(pts[c][0] - mx, pts[c][1] - my))
            if best is None or score > best[0]:
                best = (score, c, t, size * (1.25 if t else 1.0))
    _, pole, angle, size = best
    px, py = pts[pole]
    return {
        "x": round(px, 1),
        "y": round(py, 1),
        "angle": round(math.degrees(angle), 1),
        "size": round(max(MIN_LABEL_KM, min(MAX_LABEL_KM, size)), 1),
    }


PCT_KEYS = ["forest", "crop", "pasture", "grass", "shrub", "wetland", "developed"]
ENERGY_NOTE = ("Only the power plants and wind or solar clusters mapped as resources, each above its type's threshold, "
               "are counted: this is not the country's total installed capacity.")


def land_shares(world: dict, s: int) -> dict | None:
    """Mean world `pct` (0..100) over the state's cells with land-cover samples, as 0..1 fractions."""
    pct, cover, owner = world.get("pct"), world.get("cover"), world["owner"]
    if not pct or not cover:
        return None
    cells = [i for i, o in enumerate(owner) if o == s and cover[i]]
    if not cells:
        return None
    return {k: round(sum(pct[k][i] for i in cells) / len(cells) / 100, 3) for k in PCT_KEYS}


def energy_by_state() -> dict[str, dict] | None:
    """abbr → {unit, total, by_type, sites, note} summed from resources.json items of every MW type
    (states without a mapped site get zeros under "", the default row); None if resources.json is not built."""
    path = WEB_DATA / "resources.json"
    if not path.exists():
        return None
    res = json.loads(path.read_text())
    mw_types = [t["id"] for t in res["types"] if t["unit"] == "MW"]
    mw: dict[str, dict] = {}
    sites: dict[str, dict] = {}
    for it in res["items"]:
        if it["type"] in mw_types and it.get("state"):
            mw.setdefault(it["state"], dict.fromkeys(mw_types, 0))[it["type"]] += it["value"] or 0
            sites.setdefault(it["state"], dict.fromkeys(mw_types, 0))[it["type"]] += 1
    out = {}
    for abbr in ["", *mw]:
        by_type = {k: round(v) for k, v in mw.get(abbr, dict.fromkeys(mw_types, 0)).items()}
        out[abbr] = {"unit": "MW", "total": sum(by_type.values()), "by_type": by_type,
                     "sites": sites.get(abbr, dict.fromkeys(mw_types, 0)), "note": ENERGY_NOTE}
    return out


def build() -> None:
    world = load_interim("_world")
    places = load_interim("_places")
    s = Stats(world["counties"], places["region_pop"])
    grid = HexGrid(**world["grid"])
    owner = world["owner"]
    energy = energy_by_state()
    if energy is None:
        print("    resources.json not built yet: energy left null")
    local = {n["code"]: n["name"] for n in load_interim("gisco")["nuts"] if n["level"] == 0}  # Latin-script local name
    area: dict = {}
    units: dict = {}  # local administrative units (LAU 2021; the UK's wards), GeoNames towns left out
    for u in places["rows"]:
        if u[4]:
            area[u[2]] = area.get(u[2], 0.0) + u[4]
        if not str(u[0]).startswith("GN_"):
            units[u[2]] = units.get(u[2], 0) + 1
    states = []
    for i, code in enumerate(world["states"]):
        name, capital, region = COUNTRIES[code]
        p = region_profile(s, code)
        rates = nuts2_rates(s, code)
        econ = economy(p, rates, s, median_age=s.latest("medage3", "MEDAGEPOP", code)[1])
        g, years = growth_of(p, s)
        states.append({
            "fips": code,
            "abbr": code,
            "name": name,
            "local_name": local.get(code) if local.get(code) != name else None,  # Deutschland, Suomi/Finland, Elláda
            "region": region,
            "capital": capital,
            "membership": ("EU" if code in EU else "EFTA" if code in EFTA else "Left the EU in 2020" if code == "UK"
                           else "Candidate" if code != "XK" else "Potential candidate"),
            **econ,
            "growth": g,
            "growth_years": years,
            "pop_series": p["series"] or None,
            "land_km2": round(area[code]) if area.get(code) else None,
            "municipalities": units.get(code),
            **national_extras(s, code),
            "density": round(econ["population"] / area[code], 1) if econ.get("population") and area.get(code) else None,
            # GDP per inhabitant in purchasing power standards (euros at EU-average prices): comparable across countries
            "gdp_pps_per_capita": s.latest("gdp3", "PPS_EU27_2020_HAB", code)[1],
            "ranks": {},
            "label": label_anchor(grid, owner, i, name),
            "land": land_shares(world, i),
            "energy": dict(energy.get(code) or energy[""]) if energy is not None else None,
        })
    outline_areas(states)
    world_bank_fill(states)
    for key in [y["key"] for y in YIELDS]:
        ranked = sorted((st for st in states if st["yields"][key] is not None), key=lambda st: -st["yields"][key])
        for r, st in enumerate(ranked, 1):
            st["ranks"][key] = r
        for st in states:
            st["ranks"].setdefault(key, None)
    write_web("states.json", states)
    missing = {k: [st["abbr"] for st in states if st.get(k) is None] for k in ("population", "gdp", "unemployment")}
    print(f"    {len(states)} countries; missing: {missing}")
