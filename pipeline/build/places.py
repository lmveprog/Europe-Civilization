"""The local units (LAU 2021 communes, plus GeoNames towns where GISCO has no LAU) placed on the map: each gets its
hex, its NUTS 3 region and its functional urban area. Also spreads their population over the hexes (a unit larger
than a hex is spread evenly over the land hexes of its country within its equal-area radius).

Interim "_places": what the cities, regions, lenses and search builders share."""

from __future__ import annotations

import math
from collections import Counter, defaultdict

from ..core.europe import COUNTRIES
from ..core.geo import SCALE, MapProjection, Shape, ShapeIndex
from ..core.hexgrid import HexGrid
from ..core.names import belgian_local
from ..core.store import load_interim, save_interim

REQUIRES = ["_world", "gisco", "geonames", "hagstofa"]
PRODUCES = ["_places"]

HEX_KM2 = None  # set from the grid


def nearest_own_cell(grid: HexGrid, owner: list, cell: int, state: int, max_rings: int = 6) -> int:
    """The cell itself if `state` owns it, else the nearest cell `state` owns within max_rings (or -1)."""
    if cell >= 0 and owner[cell] == state:
        return cell
    if cell < 0:
        return -1
    seen, frontier = {cell}, [cell]
    for _ in range(max_rings):
        nxt = []
        for c in frontier:
            for n in grid.neighbours(c):
                if n not in seen:
                    seen.add(n)
                    nxt.append(n)
        own = [n for n in nxt if owner[n] == state]
        if own:
            return own[0]
        frontier = nxt
    return -1


def iceland_units(rows: list[dict]) -> None:
    """GISCO's LAU 2021 has no population for Iceland: Statistics Iceland's figures for today's municipalities, a merged
    one on its largest former unit (sources/hagstofa.py)."""
    try:
        h = load_interim("hagstofa")
    except FileNotFoundError:
        print("    hagstofa not processed: Iceland's municipalities stay without population")
        return
    now, moved = h["municipalities"], h["lau_to_now"]
    n = 0
    for r in rows:
        if r["country"] != "IS" or r["pop"]:
            continue
        code = r["id"].split("_", 1)[1]
        target = moved.get(code, code)
        if target in now:
            r["pop"] = now[target]
            n += 1
    print(f"    Iceland: {n} municipalities given Statistics Iceland's {h['year']} population")


def build() -> None:
    world = load_interim("_world")
    gisco = load_interim("gisco")
    geonames = load_interim("geonames")
    grid = HexGrid(**world["grid"])
    proj = MapProjection(**world["projection"])
    owner, county = world["owner"], world["county"]
    state_k = {c: k for k, c in enumerate(world["states"])}
    region_k = {g: k for k, g in enumerate(world["counties"])}
    region_state = world["county_state"]
    nuts3 = {n["code"]: n for n in gisco["nuts"] if n.get("county")}
    county_idx = ShapeIndex([Shape([[proj(lon, lat) for lon, lat in r] for r in nuts3[g]["rings"]])
                             for g in world["counties"]], cell_km=60)
    fuas = {f["code"]: f for f in gisco["fuas"]}
    fua_codes = world["fuas"]
    fua_idx = ShapeIndex([Shape([[proj(lon, lat) for lon, lat in r] for r in fuas[c]["rings"]]) for c in fua_codes],
                         cell_km=60)
    hex_km2 = 1.5 * math.sqrt(3) * (grid.radius / SCALE) ** 2

    cols = gisco["lau"]["columns"]
    rows = [dict(zip(cols, r)) for r in gisco["lau"]["rows"]]
    lau_countries = {r["country"] for r in rows}
    iceland_units(rows)
    # Countries without local units (Bosnia and Herzegovina, Montenegro, Kosovo): every GeoNames settlement.
    for p in geonames["settlements"]:
        if p["country"] in lau_countries:
            continue
        rows.append({"id": f"GN_{p['id']}", "country": p["country"], "name": p["name"], "pop": p["pop"] or None,
                     "area": None, "lon": p["lon"], "lat": p["lat"], "geonames": True})

    out = []
    renamed: list = []
    off_map = Counter()
    hexpop = [0.0] * grid.size
    for r in rows:
        if r["country"] not in state_k:
            continue
        st = state_k[r["country"]]
        x, y = proj(r["lon"], r["lat"])
        cell0 = grid.cell_at(x, y)
        cell = nearest_own_cell(grid, owner, cell0, st)
        if cell < 0:
            off_map[r["country"]] += 1
            continue
        reg = county_idx.locate(x, y)
        if reg < 0 or region_state[reg] != r["country"]:
            reg = county[cell] if county[cell] >= 0 and region_state[county[cell]] == r["country"] else reg
        fua = fua_idx.locate(x, y)
        g3 = world["counties"][reg] if reg >= 0 else None
        name = belgian_local(r["name"], g3) if r["country"] == "BE" else r["name"]
        if name != r["name"] and r["country"] == "BE":
            renamed.append(f"{r['name']}→{name}")
        out.append([r["id"], name, r["country"], r["pop"], r["area"], round(x, 1), round(y, 1), cell,
                    world["counties"][reg] if reg >= 0 else None, fua_codes[fua] if fua >= 0 else None])
        pop = r["pop"] or 0
        if not pop:
            continue
        area = r["area"] or 0
        ins = proj.frame_of(x, y)
        k = ins.d["k"] if ins is not None else 1.0  # an inset drawn at scale k: a hex covers 1/k² of the ground
        if area <= hex_km2 / k ** 2:
            hexpop[cell] += pop
            continue
        rad = math.sqrt(area / math.pi) * SCALE * k  # equal-area radius, map units
        cx, cy = grid.center(*grid.col_row(cell))
        cells = []
        c0, r0 = grid.col_row(cell)
        span = int(rad / (grid.radius * 1.5)) + 2
        for dr in range(-span, span + 1):
            for dc in range(-span, span + 1):
                cc, rr = c0 + dc, r0 + dr
                if 0 <= cc < grid.cols and 0 <= rr < grid.rows:
                    k = grid.index(cc, rr)
                    hx, hy = grid.center(cc, rr)
                    if owner[k] == st and math.hypot(hx - x, hy - y) <= rad:
                        cells.append(k)
        if not cells:
            cells = [cell]
        for k in cells:
            hexpop[k] += pop / len(cells)

    print(f"    {len(renamed)} Walloon and Brussels municipalities given their French name: {renamed[:12]}")
    # Population of each (region, urban area) pair, and of each region and urban area, from the local units.
    by_region: Counter = Counter()
    by_fua: Counter = Counter()
    pair: dict = defaultdict(Counter)
    area_fua: Counter = Counter()
    for _, _, _, pop, area, _, _, _, reg, fua in out:
        if reg:
            by_region[reg] += pop or 0
        if fua:
            by_fua[fua] += pop or 0
            area_fua[fua] += area or 0
            if reg:
                pair[fua][reg] += pop or 0
    print(f"    {len(out)} local units placed ({sum(1 for o in out if o[0].startswith('GN_'))} GeoNames towns); "
          f"{sum(1 for o in out if not o[8])} without a region; off the map: {dict(off_map)}")
    print(f"    {sum(1 for o in out if o[9])} units in {len(by_fua)} urban areas; "
          f"map population {sum(o[3] or 0 for o in out):,.0f}")
    # Each Urban Audit core city in the urban area whose outline holds its point (GISCO's own city → FUA codes are
    # shuffled for some countries: its "Trondheim" points at Bergen's area).
    city_fua, fixed = {}, []
    for c in gisco["cities"]:
        if c["country"] not in state_k:
            continue
        k = fua_idx.locate(*proj(c["lon"], c["lat"]))
        city_fua[c["code"]] = fua_codes[k] if k >= 0 else c["fua"]
        if k >= 0 and c["fua"] and fua_codes[k] != c["fua"]:
            fixed.append(f"{c['name']} {c['fua']}→{fua_codes[k]}")
    print(f"    {len(fixed)} core cities moved to the urban area holding them: {fixed[:10]}")
    save_interim("_places", {
        "city_fua": city_fua,
        "columns": ["id", "name", "country", "pop", "area", "x", "y", "cell", "nuts3", "fua"],
        "rows": out,
        "hexpop": [round(v) for v in hexpop],
        "region_pop": dict(by_region),
        "fua_pop": dict(by_fua),
        "fua_area": {k: round(v, 1) for k, v in area_fua.items()},
        "fua_regions": {f: dict(c) for f, c in pair.items()},
    })
