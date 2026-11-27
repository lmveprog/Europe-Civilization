# Data contracts

The Python pipeline writes the JSON files in `web/data/`; the browser (`web/js`) and the challenge server
(`server/api.py`) read them. This document is the contract between the two sides: what each file contains, in which
units, and who reads it. Change a contract here first, then on both sides, and keep `pipeline check` passing.

europeciv is a port of usaciv (the United States), through its French port franceciv. The engine and the browser are
usaciv's, so many keys keep their original names even though the data is European. The table below says what they
mean here; the rest of the document uses the key names as they appear in the files.

## Inherited key names

| Key (as in the files) | Meaning in europeciv |
|---|---|
| `states`, `state` | The 38 countries of the map (27 EU members, Iceland, Liechtenstein, Norway, Switzerland, the Western Balkans, the United Kingdom). `state` in a row or site is a country code (Eurostat's: EL for Greece, UK for the United Kingdom). |
| `fips`, `abbr` | Both hold the country code: the NUTS 0 code (`EL` for Greece, `XK` for Kosovo). |
| `counties`, `county` | NUTS 3 regions (NUTS 2024), 1,265 of them. Bosnia and Herzegovina has no NUTS 3 level: its three NUTS 2 entities (`BA01`-`BA03`) stand in. |
| `geoid` | NUTS code of a region. |
| `cbsa` | The `id` of a cities.json city (an urban area), or `null`. |
| `metro` | City population of 250,000 or more. |
| `median_income` | Net disposable household income per inhabitant, in purchasing power standards (PPS), NUTS 2. It is a mean per inhabitant, not a median. `income_eur` is the same figure in euros. |
| `bachelors` | Share of people aged 25-64 with tertiary education (ISCED 5-8). |
| `employed` | Jobs counted at the place of work (Eurostat regional accounts), not employed residents. |
| Money keys (`gdp`, `gold`, `gdp_by_industry`, `gdp_per_capita`, …) | Euros, current prices, whole euros (not millions). |
| `usd` (lens and field `format`, yield `unit`) | Euros. The browser prints them with `€`. |
| `communes` (communes.json) | Local administrative units (LAU 2021: communes, Gemeinden, comuni…), plus GeoNames towns where GISCO has none. |
| `dep` (communes.json, defi.json) | Country code. |
| `aav` (communes.json) | The cities.json `id` of the unit's urban area, or `null`. |
| `naics` (districts.json) | NACE Rev. 2 codes (branches such as `K`, divisions such as `C29`). |
| `enplanements` (infrastructure.json) | Airport passengers, arrivals plus departures. |
| `interstate` (road class id) | Motorway. |
| `nlcd` (world.json `tables.cover`) | Internal land-cover group codes (numbered like the US NLCD classes) that the CORINE classes are mapped to. |
| `national` (citizens, districts, resources, wonders) | Europe: the whole map, or the cities that have the row (each file says which). |

Several inherited keys are kept for the browser but carry no European data. They are always `null` (or the constant
shown) and are listed in each file's section so nobody mistakes them for missing data.

## Conventions

* **Map units.** Every `x`, `y`, `width`, `height` and label size is in map units: a Lambert azimuthal equal-area
  projection centred on 52° N 10° E (the spherical form of EPSG:3035), multiplied by 2.5 and shifted so the top-left
  corner of the map is (0, 0) with y pointing **down**. One map unit is 0.4 km (world.json `km_per_unit`). The EU's
  outermost regions are drawn in insets with their own linear scale (world.json `insets[].km_per_unit`); a distance
  between an inset and the main map means nothing. See `pipeline/core/geo.py`.
* **Hex grid.** Pointy-top hexes in "odd-r" offset layout (odd rows shifted right), radius 25 map units (10 km, about
  17 km across, 260 km²). Cell (col, row) has its centre at `x = √3·r·(col + 0.5·(row & 1))`, `y = 1.5·r·row`.
  Neighbour order is E, SE, SW, W, NW, NE. `pipeline/core/hexgrid.py` and `web/js/hex.js` must stay identical.
* **Per-cell arrays** have length `grid.cols * grid.rows`; cell index = `row * cols + col`.
* **Land.** A cell belongs to a map country when world.json `owner[cell] >= 0`. Builders that need to know whether a
  cell is land of the map must use that test.
* **`null` means no data**, always. Never write `0` as a stand-in for unknown; a `0` is a real zero.
* **Shares** are 0..1 fractions unless a key says otherwise (world.json `pct` is the one exception: 0..100 integers).
* **Identifiers.** Country: NUTS 0 code. Region: NUTS 3 code. City: Urban Audit functional urban area code (`FR001F`)
  or `GN<geonameid>` for a GeoNames town. Local unit: `<country>_<national LAU code>` (`DE_09162000`) or
  `GN_<geonameid>`.
* **Order.** world.json `states` and states.json list the countries in the same order (alphabetical by English
  name); `owner` indexes into it. Rules that select things (districts, specialists, ports, wonders) are published
  inside the files as text, so the interface and the Almanac can quote them.
* **Icons.** Every `icon` id a file names (`l-*`, `y-*`, `r-*`, `d-*`) must exist in `web/js/icons.js`; a missing id
  draws an empty box. Citizen icons (`c-*`) are drawn by `web/js/render/art/people.js`.

## Pipeline

The flow is always source → interim → builder → `web/data`. Python is **standard library only**.

### Sources (`pipeline/sources/*.py`)

Discovered automatically: any `Source` subclass with `info = SourceInfo(id, title, publisher, homepage, license,
description, used_for)`. A source has two methods and knows nothing about hexes or the interface:

* A source that reads another one's interim lists it in a class attribute `after` (`process` runs those first):
  `gisco`, `eurostat`, `airports` and `ports` merge `uk_ons`, the United Kingdom rebuilt from the ONS, NRS, NISRA,
  CAA and DfT in their shapes (ITL 2025 regions recoded TL… → UK…, December 2022 wards as local units, Urban Audit
  2020 urban areas recoded …L3 → …F, Eurostat-keyed tables in euros and PPS). Eurostat's own pre-2020 UK rows are
  dropped first. Every approximation is listed in the `uk_ons` interim's `notes`.
* `fetch(force=False)` downloads raw files into `data/raw/<id>/` through `Source.download()` (or
  `download_prefix()` for the leading block of a big sorted file), which caches them and records url, sha256, size and
  retrieval time in `data/raw/<id>/manifest.json`. `Source.discard(rel_path)` forgets a bad cached file. All three
  wrap `core/fetch.py`. Under `--offline` (`fetch.OFFLINE`, `Source.offline`) sources skip discovery requests, use the
  newest cached data, and a download of a file that is not cached raises `OfflineError`. The two sources that read
  cloud-optimised GeoTIFFs by HTTP byte ranges (`corine_eu`, `climate_eu`) keep only what they reduce from them.
* `process()` returns a dict, saved as `data/interim/<id>.json` (payload `{name, processed, vintage, data, files}`).
  It may include `"vintage"` (a human string) and `"_files"` (the raw files it actually used, relative to
  `data/raw/<id>/`; the Almanac cites only those). Large rasters may be kept as binary side files in `data/interim/`
  (`corine_eu.bin`, `climate_*.bin`) named by the interim.

| Source id | Module | Data |
|---|---|---|
| `gisco` | gisco.py | NUTS 2024 regions, neighbouring countries, Urban Audit 2021 urban areas and core cities, LAU 2021 units with population and area |
| `eurostat` | eurostat.py | Regional tables: population by age, median age, GDP, value added and jobs by branch (NUTS 3); unemployment, employment rate, tertiary education, household income, life expectancy, poverty (NUTS 2); Urban Audit populations; national accounts for the countries |
| `urban_audit` | urban_audit.py | Urban Audit city statistics (age, origin, education, commute, labour) for urban areas and core cities |
| `sbs` | sbs.py | Structural business statistics: persons employed by NACE division, NUTS 2 |
| `geonames` | geonames.py | Places of 5,000+ inhabitants |
| `corine_eu` | corine_eu.py | OpenGeoHub 2018 land cover in CORINE classes, read by byte ranges, kept as a 480 m sample |
| `clc_dom` | clc_dom.py | CORINE Land Cover 2018 of the French outermost regions |
| `climate_eu` | climate_eu.py | ERA5/CHELSA monthly temperature and precipitation 2000-2019, reduced to decade grids during fetch |
| `etopo` | etopo.py | ETOPO1 relief and sea depth |
| `natural_earth` | natural_earth.py | Natural Earth 1:10m lakes, rivers and countries |
| `natural_earth_roads` | natural_earth.py | Natural Earth 1:10m roads and railways |
| `power_plants` | power_plants.py | powerplantmatching, plus the WRI database for Iceland and Cyprus |
| `airports`, `ports` | transport_hubs.py | Eurostat passengers (`avia_paoa`) and port tonnage (`mar_go_aa`), with OurAirports, Wikidata and UN/LOCODE positions |
| `unesco` | unesco.py | UNESCO World Heritage List |

### Builders (`pipeline/build/*.py`)

Discovered automatically: a module with `REQUIRES` (interims and web files it reads), `PRODUCES` (what it writes)
and `build()`, run in dependency order (`RUN_LAST = True` puts a builder at the end). Helpers without `build()`, such
as `yields.py`, are fine. `pipeline build` skips a builder whose outputs are newer than its `REQUIRES` and its code,
so a builder must list every file it reads.

| Builder | Writes |
|---|---|
| `world` | world.json, `_world` |
| `places` | `_places` |
| `cities` | cities.json, nation.json |
| `lenses` | lenses.json, `_region_values` |
| `states`, `counties`, `communes`, `citizens`, `districts`, `infrastructure`, `resources`, `wonders` | the file of the same name |
| `challenge` | defi.json |
| `catalog` (last) | sources.json |

Interims made by builders start with `_`:

* **`_world`** (world): `grid`, `projection` (`MapProjection` keyword arguments: `min_x`, `max_y`, `margin`, `scale`,
  `insets`), `owner`, `county`, `water`, `cover`, `pct` (as in world.json), `states` (country codes, world.json
  order), `counties` (NUTS 3 codes, world.json order), `county_state` (the country of each region),
  `county_samples` (per cell, the region index under each of the 7 sample points, sample 0 = centre, `-1` off any
  region; `[]` for cells that are not map land), `fuas` (urban area codes) and `fua_samples` (same layout, urban area
  indices), `clc` (per cell `{CORINE class: number of land-cover samples}`, `null` off the map's countries).
* **`_places`** (places): every local unit placed on the map, `columns` = `id, name, country, pop, area, x, y, cell,
  nuts3, fua` and `rows`; `hexpop` (population spread over the cells); `region_pop`, `fua_pop`, `fua_area`
  (2021 census sums per region and urban area); `fua_regions` (`{urban area: {region: population}}`); `city_fua`
  (core city code → the urban area that holds its point).
* **`_region_values`** (lenses): `{regions, values: {lens id: [value per region]}}`, so counties.json uses exactly the
  lens formulas.

### Checks

`uv run python -m pipeline check` validates the files. world, cities, states, nation, lenses and sources are
required (a missing one is a FAIL); resources and counties are validated when present. It then prints a data-quality
report and runs the **builder checks**: any module in `pipeline/build/` may define
`check(web_dir: Path) -> list[(level, message)]` with level `PASS`, `NOTE`, `WARN` or `FAIL`; `pipeline check`
discovers them, so a new builder never edits `pipeline/check.py`. Rules: read only `web_dir` (tests point it at a
small synthetic dataset); report a missing output as a `NOTE`; a check that raises counts as a FAIL. Validate the
file's shape against this document (keys, types, null rules, cells against world.json) and add a short coverage
summary. Today citizens, districts, infrastructure, resources and wonders have one.

## Files at a glance

| File | Builder | Size | Loaded by the browser |
|---|---|---|---|
| world.json | world | 3.1 MB | at start, required |
| cities.json | cities | 1.2 MB | at start, required |
| nation.json | cities | 4 kB | at start, required |
| states.json | states | 80 kB | at start (optional) |
| lenses.json | lenses | 8.5 MB | at start (optional) |
| resources.json | resources | 140 kB | at start (optional) |
| sources.json | catalog | 120 kB | at start (optional) |
| infrastructure.json | infrastructure | 390 kB | right after the first frame |
| wonders.json | wonders | 80 kB | right after the first frame |
| counties.json | counties | 230 kB | on demand (advisors, City View) |
| communes.json | communes | 9.2 MB | on demand (first keystroke in the search box, place card, challenge) |
| placenames/top.json, placenames/t*.json | placenames | 1.0 MB + 203 tiles of 2-160 kB | Places layer, when zoomed in |
| citizens.json | citizens | 1.0 MB | on demand (City View) |
| districts.json | districts | 0.9 MB | on demand (City View, banner badges, advisors) |
| timeline.json | lenses | 3.7 MB | on demand (the "Density since 1975" lens's slider) |
| projection.json | projection | 1 kB | on demand (Locate me) |
| defi.json | challenge | 390 kB | never: read by `server/api.py` only |

Optional site files (citizens, districts, infrastructure, wonders) share a header: `"version": 1`, `"vintage"` (a
string or `{part: string}`) and `"sources"` (sources.json ids, so the Almanac can cite them). A **site** (resource,
port, airport, wonder) has `x`, `y` = its true position, `cell` = a land cell of its country at or near that point,
`county` = the NUTS 3 code of that cell (or `null`), `cbsa` = the city whose footprint holds the cell (the most
populous if several; infrastructure also falls back to the urban area under most of the cell's sample points), and
`state` = a country code.

## world.json

The map: grid, terrain, countries, regions and rivers. Read by `web/js/world.js` (`prepareWorld`), the renderer
(`render/*`), the minimap and the Almanac.

```jsonc
{
  "version": 2,
  "grid": {"radius": 25.0, "cols": 244, "rows": 291},       // 71,004 cells
  "width": 10500.6, "height": 10863.5, "margin": 400.0,    // map units; margin = sea and neighbours around the map
  "km_per_unit": 0.4,
  "insets": [{"dep": "FRY1", "nuts": ["FRY1"], "name": "Guadeloupe", "lon": [-61.9, -60.95], "lat": [15.8, 16.55],
              "k": 1.0, "x": 2300, "y": 300, "frame": [2300, 300, 2613.9, 567.3], "km_per_unit": 0.4}],
  "owner":    [int],   // -1 water, -2 neighbouring country, >= 0 index into states
  "county":   [int],   // index into counties; -1 off the map's countries
  "elev":     [int],   // metres, see below
  "elev_max": [int],   // metres, highest land sample of the hex (0 for water); used for snow
  "water":    [int],   // 0 land, 1 ocean, 2 coast, 3 lake
  "relief":   [int],   // 0 flat, 1 hills, 2 mountains, 3 peaks; 0 for water
  "cover":    [int],   // land-cover id (tables.cover); 0 = none
  "pct": {"forest": [int], "crop": [int], "pasture": [int], "grass": [int], "shrub": [int], "wetland": [int],
          "developed": [int]},                              // 0..100, share of the hex's land samples
  "tables": {
    "water":  [{"id": 2, "name": "Coast", "color": "#2d6d97", "rule": "Sea next to a land hex, or shallower than 200 m (ETOPO1 mean)."}],
    "relief": [{"id": 0, "name": "Flat", "rule": "Elevation standard deviation inside the hex under 55 m."}],
    "cover":  [{"id": 1, "key": "forest_deciduous", "name": "Broadleaf forest", "color": "#4f7a35", "nlcd": [41], "rule": "…"}],
    "notes":  {"water": "…", "relief": "…", "cover": "…"}
  },
  "states":   [{"fips": "FR", "abbr": "FR", "name": "France", "region": "Western Europe"}],
  "counties": [{"geoid": "FR101", "name": "Paris"}],
  "rivers":   [{"name": "Danube", "rank": 2, "pts": [x0, y0, x1, y1, ...]}]
}
```

* **`insets`**: the outermost regions (Azores, Madeira, Canary Islands, Guadeloupe, Martinique, French Guiana,
  Réunion, Mayotte). `lon`/`lat` is the window drawn, `frame` = `[x0, y0, x1, y1]` in map units, `k` the scale
  relative to the main map, `dep` the inset id (its NUTS 2 code).
* **`owner`**: majority of 7 sample points (the centre and six points 60% of the way to the corners): a NUTS 3 region
  (hence a country), a neighbouring country (GISCO and Natural Earth outlines: United Kingdom, Turkey, Ukraine…),
  lake or sea; the centre breaks ties. Sea hexes whose ETOPO1 mean is above sea level and that are mostly surrounded
  by land become land; every city centre and every country gets at least its own hex. The water `rule` texts and
  `notes.water` say exactly how.
* **`county`**: the region under the centre sample when it lies in the cell's country, else the most common such
  sample. Every map-land cell has one.
* **`elev`**: land = mean of the hex's ETOPO1 samples at or above -100 m; sea = mean of its samples below sea level
  (its depth, <= 0); lake = `min(mean, 0)`; `-4000` where ETOPO1 has no sample.
* **`relief`**: from the standard deviation and mean of the land samples (thresholds in `tables.relief`). A hex whose
  lower 60% of samples is flat lowland (spread < 60 m, under 400 m) is eased one class (valley floors).
* **`cover`** ids are fixed: 0 none · 1 forest_deciduous · 2 forest_evergreen · 3 forest_mixed · 4 scrub ·
  5 grassland · 6 pasture · 7 cropland · 8 wetland · 9 urban · 10 barren · 11 ice. A hex is urban when built-up
  land (CORINE 111-133) is at least 30% of its land samples, else the largest group wins (`tables.cover[].rule` names
  the CORINE classes). About 400 samples per hex on an 800 m lattice. `nlcd`: the group codes of
  `sources/corine_eu.py`. `cover` and `pct` are 0 for water and neighbouring countries.
* **`rivers`**: Natural Earth 1:10m with its European supplement, clipped to the map; `rank` is Natural Earth's scale
  rank (1 = most important; up to 12 inside the map, up to 6 across neighbouring countries).

## cities.json

A list of cities sorted by population, descending (646 today). A city is either one of the 590 functional urban
areas of the Urban Audit 2021 (a core city and its commuting zone; `source: "urban_audit"`) or, in the countries the
Urban Audit does not cover (Western Balkans, Cyprus, Iceland, Liechtenstein), a GeoNames town of 50,000+ or
the capital (`source: "geonames"`). Read by the banners, city panel, search, City View, advisors and rankings; the
server reads `id` and `name`.

```jsonc
{
  "id": "FR001F", "name": "Paris", "full": "Paris functional urban area",
  "local_name": null,                 // the local name when the English one differs ("Milano" for Milan)
  "states": ["FR"],                   // always one country
  "metro": true, "capital": true, "national_capital": true,
  "centre": "Paris", "centre_code": "FR001C",   // core city name and Urban Audit code (null for GeoNames towns)
  "commune_population": 2187526, "commune_year": 2021,      // the core municipality
  "x": 3198.1, "y": 6705.2, "cell": 43749,
  "population": 13277552,
  "yields": {"food": 17553, "production": 859702, "gold": 854503430582, "science": 2071012, "culture": 515777},
  "jobs": {"agriculture": 17553, "manufacturing": 375531, "utilities": 70719, …},
  "employed": 7267979, "workplace_jobs": 7267979,
  "median_income": 26101, "income_eur": 29155,
  "unemployment": 0.087, "employment_rate": 0.7642, "poverty": 0.2072, "bachelors": 0.5727,
  "life_expectancy": 84.4, "median_age": 38.7, "seniors": 0.1667, "youth": 0.1769,
  "gdp": 854503430582, "gdp_year": 2023, "gdp_per_capita": 63976,
  "gdp_by_industry": {"agriculture": 1119787023, "manufacturing": 77804048318, …},
  "estimated": null,                  // Eurostat tables filled from a parent region, e.g. ["emp3", "gva3"]
  "growth": 0.0212, "growth_years": [2020, 2025],
  "counties": ["FR101", "FR102", "FR103", …],
  "land_km2": 18171.8,
  "pop_series": {"2014": 12829665, …, "2025": 13356530},
  "footprint": [42770, 42771, 42772, …],
  "ranks": {"population": 1, "gdp": 1, "gdp_per_capita": 46, "growth": 198,
            "food": 61, "production": 1, "gold": 1, "science": 1, "culture": 1},
  "peers": ["ES001F", "ES002F", "DE001F", "IT002F", "IT001F"],
  "source": "urban_audit",
  // always null or constant: band, communes (null), cross_border (false), and the economic keys listed below
}
```

* **Position.** `x`, `y` = the core city's point (GISCO; the GeoNames point for towns). `cell` = the land cell of the
  city's country under it, snapped to the nearest such cell when it is water or foreign, and moved up to 2 rings when
  a bigger city already holds it; banners anchor there. Cells are unique per city where possible.
* **Population.** Urban areas: the Urban Audit population of the area, latest year published (`urb_lpop1`), else the
  sum of its local units' 2021 census population. Towns: the GeoNames population. `commune_population` is the core
  municipality's 2021 census population; in Portugal, Ireland and Greece (whose local units are smaller than
  municipalities) and where no unit matches, the largest GeoNames place within 10 km, with `commune_year` null.
  GeoNames towns have `commune_year` null and `estimated` from their region.
* **Economy** (all `economy()` in `pipeline/build/yields.py`). A city takes each NUTS 3 region's totals in proportion
  to the share of the region's 2021 census population that lives in the urban area (a GeoNames town: its population
  over the region's). Rates published for NUTS 2 regions are population-weighted means of the parents of its regions.
  The economic fields, shared with states.json and nation.json `nation`:
  * `yields`: `food` = jobs in agriculture (NACE A); `production` = industry and construction (B-F); `gold` = GDP in
    euros; `science` = information and communication plus professional, scientific and support services (J, M, N);
    `culture` = arts, entertainment and other services (R-U). Jobs are Eurostat regional accounts
    (`nama_10r_3empers`, persons, place of work, self-employed included). nation.json `yields` defines them.
  * `jobs`: persons employed by branch: `agriculture` A, `manufacturing` C, `utilities` B-E minus C, `construction` F,
    `retail` G-I, `information` J, `finance` K, `real_estate` L, `professional` M-N, `public_admin` O-Q, `arts` R-U.
  * `employed` = `workplace_jobs` = total jobs at the place of work.
  * `median_income`, `income_eur`: see the inherited-names table (`nama_10r_2hhinc`, latest year).
  * `unemployment` (ILO, ages 15-74), `employment_rate` (ages 20-64), `poverty` (at risk of poverty or social
    exclusion), `bachelors`: 0..1 fractions from NUTS 2 tables (falling back to NUTS 1, then the country), latest year.
  * `life_expectancy`: years at birth (NUTS 2). `median_age`: population-weighted mean of the regions' median ages
    (null in nation.json). `seniors` (65+) and `youth` (under 15): fractions of the regions' population.
  * `gdp`: euros, `gdp_year` (Eurostat `nama_10r_3gdp`). `gdp_per_capita`: `gdp / population`, in euros (not adjusted
    for price levels; countries also have `gdp_pps_per_capita`).
    `gdp_by_industry`: GDP split by each branch's share of gross value added (`nama_10r_3gva`); keys `agriculture`,
    `manufacturing` (B-E), `construction`, `retail`, `information`, `finance`, `real_estate`, `professional`,
    `government` (O-Q), `arts`; a key is null when its value added is not published.
  * Always null: `median_rent`, `home_value`, `rent_burden`, `owners`, `second_homes`, `gdp_undisclosed`,
    `gdp_estimated`.
  * A total is null when any region it needs lacks the figure. Regional holes (Eurostat publishes some branches only
    for NUTS 2 or 1, Norway's newer regions, missing countries) are filled from the nearest ancestor: what its total
    leaves after its published regions, shared out by employment or population. `estimated` lists the Eurostat tables
    so filled for any of the city's regions (`pop3` population, `gdp3` GDP, `emp3` jobs, `gva3` value added).
* **Growth** (cities, states, nation): `population(year) / population(year − 5) − 1` from Eurostat populations on
  1 January (NUTS 3 regions apportioned for cities, the country's own figure for states), `growth_years =
  [2020, 2025]`, the end equal to nation.json `year`. `null` when the data is missing or the change exceeds ±15% (a
  break in the series, such as Albania's 2023 census).
* **`counties`**: the regions at least half of whose population lives in the urban area, or else the one with the
  most of its people (towns: the region they stand in). The economic figures use every region the area touches.
* **`land_km2`**: sum of the local units' areas (null for towns). **`pop_series`**: `{year: population}` of the
  apportioned regions, 2014 to the latest year (null for towns); its last value is not `population`, which comes from
  the Urban Audit.
* **`footprint`**: the cells that draw the urban area in the City View: cells where at least 4 of the 7 sample points
  fall in the area's outline, plus the city's own `cell` (never empty; a town has only its cell). A cell may belong to
  more than one footprint.
* **`ranks`**: rank among all cities, 1 = highest, for `population`, `gdp`, `gdp_per_capita`, `growth` and each yield; `null` where the value is null. **`peers`**: the 5 cities closest in
  population (by `|log(p / q)|`), nearest first.

## states.json

The 38 countries, in world.json `states` order. Read by the state panel, the country labels, rankings, advisors and
the server (`abbr`, `name`, `region`).

```jsonc
{
  "fips": "DE", "abbr": "DE", "name": "Germany", "region": "Central Europe",   // region: one of 5 parts of Europe
  "capital": "Berlin",                         // the capital's name (a string here, a boolean in cities.json)
  "membership": "EU",                          // EU | EFTA | Candidate | Potential candidate
  "population": 83577140, "gdp": 4219310000000, …,   // the economic fields of a city
  "growth": 0.0049, "growth_years": [2020, 2025],
  "pop_series": {"2014": 80767463, …, "2025": 83577140},
  "land_km2": 357202, "density": 234.0,        // sum of local-unit areas; population per km²
  "gdp_pps_per_capita": 46400,                 // GDP per inhabitant in PPS (€ at EU-average prices)
  "ranks": {"food": 7, "production": 1, "gold": 1, "science": 1, "culture": 1},
  "label": {"x": 4611.6, "y": 6112.5, "angle": 0.0, "size": 240.0},
  "land": {"forest": 0.32, "crop": 0.355, "pasture": 0.224, "grass": 0.037, "shrub": 0.002, "wetland": 0.003,
           "developed": 0.055},
  "energy": {"unit": "MW", "total": 98164, "by_type": {"nuclear": 0, "coal_plant": 37945, …},
             "sites": {"nuclear": 0, "coal_plant": 22, …},
             "note": "Only the power plants and wind or solar clusters mapped as resources, … not the country's total installed capacity."}
}
```

* The economic fields are those of a city, from the country's NUTS 0 rows (national accounts fill a missing NUTS 0
  row); `median_age` is the country's own median. `growth` is null for Albania (a census break), Bosnia and
  Herzegovina and Kosovo (no population series); `growth_years` is the same window everywhere, and `pipeline check`
  only requires a rate for Europe (nation.json). Countries
  without local units (Bosnia and Herzegovina, Montenegro, Kosovo) have null `land_km2` and `density`.
* **`ranks`**: per yield, 1..38, 1 = largest, null where the yield is null.
* **`label`**: suggested anchor for the country name: the hex farthest from the border (or one nearly as deep that
  fits a bigger name), `angle` in degrees clockwise (tilted along an elongated country only when that gives a much
  bigger name), `size` a font height in map units clamped to 14..240. Null for a country without hexes (none today).
  The browser may compute its own.
* **`land`**: mean of world.json `pct` over the country's cells with `cover > 0`, as 0..1 fractions.
* **`energy`**: MW summed from resources.json items of every `MW` type whose `state` is the country (`0` = no mapped
  site). It counts only the sites above each type's threshold, so it is **not** the country's installed capacity;
  `note` says so for the interface. `sites` = number of items per type. Null if resources.json was not built.

## nation.json

Europe as a whole, and the definitions the interface needs. Read by the top bar, the yield report and the Almanac.

```jsonc
{
  "vintage": "Eurostat regional statistics: population on 1 January 2025, GDP and jobs 2023",
  "year": 2025,                               // the population year; growth ends here
  "gdp_vintage": "Eurostat, GDP of NUTS 3 regions, 2023",
  "name": "Europe", "countries": 38,
  "nation": {"population": 477737293, "gdp": 18774044810000, …,     // the economic fields of a city
             "left_out": {"population": ["BA", "XK"], "jobs_total": ["XK"]},
             "growth": 0.0084, "growth_years": [2020, 2025], "pop_series": {"2014": 468573495, …}},
  "yields": [{"key": "food", "icon": "y-food", "label": "Food", "color": "#7fbf3f", "unit": "workers",
              "industries": ["agriculture"], "description": "Jobs in agriculture, forestry and fishing, …"}],
  "industries": {"agriculture": "Agriculture, forestry and fishing", …},           // labels of the jobs keys
  "gdp_industries": {"government": "Public administration, education, health and social work", …}
}
```

* `nation` sums the 38 countries, skipping a country that lacks a figure; `left_out` lists them per total. Rates are
  weighted by country population; `median_age` is null; there are no ranks. `pop_series` keeps only the years that
  every country with both growth populations publishes.
* `yields[].unit` is `workers` or `usd` (euros); `industries` lists the `jobs` keys a yield sums.

## lenses.json

Per-hex map overlays. Read by the lens dock and legend (`web/js/ui/lenses.js`, `world.js` `applyLens`) and the
advisors.

```jsonc
{
  "vintage": "Eurostat 2025, GISCO LAU 2021, land cover 2018",
  "groups": [{"id": "people", "name": "People"}, {"id": "prosperity", "name": "Prosperity"},
             {"id": "knowledge", "name": "Knowledge"},
             {"id": "climate", "name": "Climate"}, {"id": "land", "name": "Land"}],
  "lenses": [{
    "id": "income", "group": "prosperity", "name": "Household income", "icon": "l-income",
    "unit": "disposable income per inhabitant, PPS", "format": "usd", "scale": "linear",
    "domain": [11000, 28000], "ramp": ["#2e1a05", "…", "#fdf7da"], "higher_is": "good",
    "source": "eurostat", "description": "…",
    "values": [number | null]                  // per cell; null off the map's countries
  }]
}
```

* `note` (optional, `gdp_capita`, `warming` and `rain_change` today): a short caveat the legend always shows.
* `format`: `int`, `float`, `pct` (0..1; `growth` is signed), `usd` (euros), `years`, `celsius`, `dcelsius` (a
  temperature difference), `change` (a signed relative change), `metres` (one decimal and " m"). `pipeline check` also accepts `minutes` and
  `category` (integer indices into `categories: [{id, name, color}]`, with `ramp` = their colours and domain
  `[0, n − 1]`); no lens uses them today. `scale`: `linear` or `log`. `higher_is`: `good`, `bad` or `neutral`.
  `source`: a sources.json id. Keep `unit` a plain phrase: the legend prints numbers with short units only and the
  `unit` once underneath.
* `domain`: the 2nd and 98th percentiles of the hex values, rounded outward to two significant digits (values beyond
  take the end colour); land lenses `[0, 1]`; vineyard, olive and orchard lenses `[0, p98]`.
* **Regional lenses**: a region's value is its own NUTS 3 figure, or for rates published only for NUTS 2, its parent's
  (falling back to NUTS 1, then the country); a hex takes the plain mean of the non-null values of the regions under
  its 7 sample points, so a hex across a border blends both sides.

| id | group | format | Value |
|---|---|---|---|
| `density` | people | int, log | People per km² of land: each local unit's 2021 population on its hex (spread over the hexes within its radius when larger than a hex) ÷ the hex's land area. Bosnia and Herzegovina, Montenegro and Kosovo: their GeoNames settlements with the population GeoNames records |
| `growth` | people | pct | Population change 2020-2025, NUTS 3; null beyond ±15% |
| `age` | people | years | Median age, NUTS 3 |
| `seniors`, `youth` | people | pct | Share aged 65+ / under 15, NUTS 3 |
| `life_expectancy` | people | float | Years at birth, NUTS 2 |
| `gdp_capita` | prosperity | usd, log | GDP per inhabitant in PPS, NUTS 3 (has a `note`: GDP is counted where it is produced) |
| `income` | prosperity | usd | Household disposable income per inhabitant in PPS, NUTS 2 |
| `poverty` | prosperity | pct | At risk of poverty or social exclusion, NUTS 2 |
| `unemployment` | prosperity | pct | Unemployment rate 15-74, NUTS 2 |
| `employment` | prosperity | pct | Employment rate 20-64, NUTS 2 |
| `bachelors` | knowledge | pct | Tertiary education among 25-64, NUTS 2 |
| `forest`, `farmland`, `developed` | land | pct | Share of the hex's land samples (world.json `pct`: forest; crop + pasture; developed) |
| `vines`, `olives`, `orchards` | land | pct | Share of the hex's land in CORINE class 221, 223, 222 (`_world.clc`) |
| `temperature` | climate | celsius | Mean air temperature 2000-2019 (ERA5/CHELSA) |
| `warming` | climate | dcelsius | 2010-2019 mean minus 2000-2009 mean (has a `note`) |
| `rainfall` | climate | int, log | Yearly precipitation, mm, 2000-2018 (CHELSA) |
| `rain_change` | climate | change | Yearly precipitation 2010-2018 against 2000-2009 (has a `note`) |
| `forest_height` | land | metres | Mean canopy height at the hex's world.py land-cover points that fall in CORINE forest (311-313), at least 10, read on `canopy_eth` (ETH Zurich 2020, 1/32 overview, about 300 m); null elsewhere and in the insets |

Climate lenses sample the decade grids at the hex centre and six points around it; they are null in the Caribbean,
French Guiana and Indian Ocean insets, which the grids do not cover. The `life` group has no lens today.

## counties.json

One row per NUTS 3 region (world.json `counties` order), column-oriented. Loaded on demand by the advisors and the
City View (`app.loadCounties()`).

```jsonc
{
  "vintage": "Eurostat 2025 (GDP 2023)",
  "fields": [{"key": "population", "label": "Population", "format": "int", "unit": "people", "higher_is": "neutral",
              "source": "eurostat", "description": "Population on 1 January (Eurostat demo_r_pjanaggr3)."}],
  "columns": ["geoid", "name", "state", "population", "land_km2", "density", "gdp", "jobs", "growth", "median_age",
              "seniors", "youth", "gdp_capita", "income", "poverty", "unemployment", "employment", "bachelors",
              "life_expectancy", "forest", "crop", "pasture", "developed", "cbsa", "cell", "estimated"],
  "rows": [["DE212", "München (city)", "DE", 1505005, 311.4, 4833.0, 150229490000, 1203650, 0.014, 39.7, 0.1703,
            0.1338, 89900, 31800.0, 0.153, 0.03, 0.851, 0.474, 82.7, 0.173, 0.201, 0.102, 0.427, "DE003F", 45497, null]]
}
```

* `rows[i][j]` is column `columns[j]` of region i; `fields[j]` describes it (`fields[j].key == columns[j]`).
  `format` is a lens format, `text` or `km2`; `pct` values are 0..1 fractions.
* `population` (1 January), `gdp` (euros), `jobs` (place of work): the region's Eurostat figures, filled from a
  parent region when missing. `land_km2`: sum of its local units' areas; `density` = `population / land_km2`.
* `growth` … `life_expectancy` are the regional values of the lenses of the same meaning (`_region_values`; column
  `median_age` = lens `age`, `employment` = lens `employment`), so a region reads the same in both.
* `forest`, `crop`, `pasture`, `developed`: mean of world.json `pct` over the region's sample points, 0..1; null for a
  region no sample point hits.
* `cbsa`: the urban area (cities.json id) holding most of the region's people, or null. `cell`: the hex under the
  population-weighted centre of the region's local units, on its country's land (regions without local units: one of
  their own hexes; null if none). `estimated`: comma-separated Eurostat tables filled from a parent region (`"emp3,gdp3"`), or null.

## resources.json

Tile resources: the big power plants and wine regions. Read at start by the resource icons, the Almanac, the City
View and the energy advisor; states.json `energy` is summed from it.

```jsonc
{
  "types": [{"id": "nuclear", "name": "Nuclear plant", "category": "energy", "icon": "r-nuclear", "color": "#e8d44d",
             "unit": "MW", "description": "Every nuclear power plant in service; …", "source": "power_plants"}],
  "items": [{"type": "nuclear", "name": "Gravelines", "x": 3228.9, "y": 6100.4, "cell": 39846, "value": 5706,
             "detail": "6 reactors, in service since 1975", "state": "FR", "cbsa": "FR036F"}],
  "summary": {
    "note": "Totals of the mapped sites only (each type has its own threshold): …",
    "national": {"nuclear": {"count": 41, "value": 104044, "unit": "MW"}, "wine": {"count": 39, "value": null, "unit": "% of the land in vines"}},
    "states": {"AL": {"hydro": {"count": 2, "value": 1100, "unit": "MW"}}}
  }
}
```

* **Types**, in rank order: `nuclear`, `pumped_storage`, `tidal`, `hydro`, `coal_plant`, `gas_plant`, `geothermal`,
  `wind`, `solar`, `battery` (category `energy`, unit MW, source `power_plants`) and `wine` (category `agri`, source
  `corine_eu`). `pipeline check` also accepts the category `mineral`. Each `description` states the type's threshold.
* **Plants** of one kind in one hex make one item when they reach the type's threshold per hex; `x`, `y` = the largest
  unit's position, `value` = MW in service, `state` = the country holding most of the MW. **Wind, solar and battery**
  are clusters: all installations of the hex summed (offshore wind moved to the nearest coastal hex of its country),
  `x`, `y` = the hex centre. A plant filed in two national registers is kept once.
* **Vineyards**: hexes where vines (CORINE 221) are at least 12% of the land, thinned to one hex in four on a regular
  lattice; `value` is the vineyard share as a 0..1 fraction, `state` the hex's country.
* Items are sorted by type rank, then by value. `summary.national` has every type; `summary.states` has, per country
  with items, the types present. `value` sums the items' values, and is null for `wine` (shares do not add up).

## communes.json (lazy)

Every local administrative unit of the map's countries (LAU 2021, about 98,000), plus every GeoNames settlement of
Bosnia and Herzegovina, Montenegro and Kosovo, which have no units (about 28,000 towns, villages and hamlets, many
without a population): about 126,000 rows, sorted by country then name. Loaded on the first keystroke in the search
box; read by the place card, the challenge's home-town picker and the server (player home towns and teams). The
map's Places layer reads the lighter `placenames/` files built from it (below).

```jsonc
{"version": 1, "vintage": "GISCO LAU 2021 (census 2021), GeoNames",
 "columns": ["code", "name", "dep", "pop", "cell", "aav", "density", "region", "x", "y"],
 "rows": [["DE_09162000", "München", "DE", 1488202, 45497, "DE003F", 4779, "DE212", 4889, 6967],
          ["GN_3204541", "Banja Luka", "BA", 221106, 51135, null, null, "BA02", 6024, 7838]]}
```

* `code`: GISCO LAU id (`<country>_<national code>`) or `GN_<geonameid>`. `name`: as GISCO or GeoNames publish it.
  `dep`: country. `pop`: 2021 census population (null when not published). `cell`: the hex of the unit's point, or
  the nearest hex of its country within 6 rings (units farther away are left out). `aav`: the cities.json id of the
  urban area whose outline holds the point, or null. `density`: people per km², integer (null for GeoNames towns).
  `region`: NUTS 3 code. `x`, `y`: the unit's point in map units (integers, 400 m), where the Places layer writes its
  name. Belgian units of Brussels and Wallonia carry their French name (GISCO publishes the Dutch one).

## timeline.json (lazy)

The frames of a timeline lens (`lens.frames` in lenses.json: `{"file": "timeline", "years": [...], "frame": k}`):
`{"lens": "density_history", "years": [1975, 1980, …, 2020], "values": [[…], …]}`, one array of `n` hex values per
year (people per km² of land, from GHS-POP; null off the map's countries). The lens itself carries the last year's
values; the legend's slider loads this file and swaps in another year's array, on the same colour domain.

## projection.json (lazy)

How the browser turns a longitude and latitude into map units (`pipeline/build/projection.py`, read by
`web/js/ext/locate`): `kind` "laea", `lon0`, `lat0`, `radius_km` (spherical), `min_x`, `max_y` (km of the
projection at the map's top-left), `scale` (map units per km), `margin` (map units), and `insets`: each `{name, lon:
[w, e], lat: [s, n], ox, oy, kx, ky}`, a point inside the window going to `ox + (lon − w)·kx`, `oy + (n − lat)·ky`.

## placenames/ (lazy)

The names the map's Places layer writes (`pipeline/build/placenames.py`, from communes.json), cut so a phone loads
only what it shows. `placenames/top.json`: every place of `top_min` (4,000) people or more, plus `tile` (500 map
units) and `tiles`, the keys of the other files; loaded once the map is zoomed in. `placenames/t<col>_<row>.json`: the
smaller places whose point lies in that tile (col = ⌊x / tile⌋, row = ⌊y / tile⌋); loaded when the view is zoomed in
far enough to name places under `top_min` and the tile is on screen. Both have `columns` `["code", "name", "dep",
"pop", "x", "y"]` (`pop` 0 when unknown) and rows sorted by population, largest first.

## citizens.json (lazy)

Per city, the citizen mix of the City View's rows of person icons, built by `pipeline/build/citizens.py`. Figures are
rounded with the **largest-remainder** method so each row's figures add up exactly; the browser only draws icons.
Loaded on demand by the City View (and the advisors' explorer).

```jsonc
{
  "version": 1, "vintage": "Eurostat Urban Audit, latest year per city", "year": 2025,
  "years": {"workforce": [2023, 2023], "age": [2011, 2025], "commute": [2008, 2024], "education": [2011, 2025],
            "nativity": [2011, 2025]},                 // [first, last] year used per row
  "sources": ["urban_audit", "eurostat"],
  "figures": {"workforce": 20, "age": 10, "commute": 10},   // icons per row; education and nativity have none
  "rows": {"workforce": "Jobs by branch of activity", "age": "Residents by age group", …},
  "notes": {"all": "…", "workforce": "…", "age": "…", "commute": "…", "education": "…", "nativity": "…"},
  "groups": {"workforce": [{"key": "executive", "label": "Finance, insurance and real estate", "icon": "c-executive",
                            "lines": "cities.json jobs: finance + real_estate (NACE K, L)"}, …], …},
  "rule": {"specialist_high": 1.5, "specialist_low": 0.67, "min_share": 0.01, "max_high": 4, "max_low": 2, "text": "…"},
  "national": {"workforce": {…}, "age": {…}, …,      // rows, each with "cities" and "years"
               "specialists": [], "nativity_citizenship": {…}},
  "cities": {"FR001F": {
    "workforce": {"total": 7267977, "counts": {"executive": 434590, …}, "shares": {"executive": 0.06, …},
                  "figures": {"executive": 1, …}, "basis": "branch", "geo": "FR001F", "level": "fua", "year": 2023},
    "age": {"total": 13277552, "counts": {…}, "shares": {…}, "figures": {…}, "median": 37.9,
            "median_published": 37.0, "median_published_year": 2023, "geo": "FR001F", "level": "fua", "year": 2023},
    "commute": {"total": 6072300, "counts": {…}, "shares": {…}, "figures": {…}, "geo": "FR001F", "level": "fua",
                "year": 2020, "total_source": "EC1001V − EC1010V", "total_year": 2023, "published_sum": 100.1},
    "education": {"total": 6767193, "counts": {…}, "shares": {…}, "bachelors_plus": 0.515,
                  "geo": "FR001F", "level": "fua", "year": 2023},
    "nativity": {"total": 13277551, "counts": {…}, "shares": {…}, "foreign_born": 0.199, "born_in_state": 0.76,
                 "basis": "birthplace", "geo": "FR001F", "level": "fua", "year": 2023},
    "specialists": [{"row": "commute", "key": "transit", "share": 0.435, "national": 0.204, "ratio": 2.13}],
    "reliable": true
  }}
}
```

The category keys are usaciv's (the browser has a figure for each); here they mean:

| Row | Keys | Meaning | Data |
|---|---|---|---|
| workforce | `executive`, `engineer`, `scholar`, `healer`, `clerk`, `farmer`, `builder`, `maker` | Branches: K+L, J+M+N, R-U, O-Q, G-I, A, F, B-E | cities.json `jobs` (no occupation data exists for cities) |
| age | `child`, `young`, `midlife`, `elder` | Under 15, 15-34, 35-64, 65+ | Urban Audit `urb_lpop1` / `urb_cpop1` |
| commute | `drove_alone`, `transit`, `walk`, `other` | Car, public transport, on foot, bicycle or motorcycle | `urb_ltran` / `urb_ctran` mode shares × employed residents |
| education | `less_than_hs`, `high_school`, `bachelors` | ISCED 0-2, 3-4, 5-8, aged 25-64 | `urb_leduc` / `urb_ceduc` |
| nativity | `born_in_state`, `other_state`, `foreign_born` | Born in the country, in another EU country, outside the EU | `urb_lpopcb` / `urb_cpopcb` |

* Each Urban Audit row takes the urban area's figures (`geo` = the `…F` code, `level: "fua"`) when published, else
  the core city's (`…C`, `level: "city"`), from the latest year in which every category is published (`year`).
  `groups[].lines` names the exact indicators. Nativity falls back to citizenship (nationals, other EU citizens,
  non-EU citizens) where birthplace is not published; `basis` says which.
* `counts` are whole people summing to `total`; `shares` = count ÷ total (3 decimals); every category is present.
  `age.median` is interpolated within 5-year groups the same way everywhere; `median_published` is the statistical
  office's own figure when one exists within 2 years. A row Eurostat does not publish is `null`, never zeros; a city
  without any row, and every GeoNames town, is `null`. `reliable` is always `true`.
* `national` is Europe: per row, the sum of the cities that have it, with `cities` (how many) and `years`
  (`[first, last]`). Citizenship-basis city rows are compared with `national.nativity_citizenship`.
* `specialists`: categories whose share is at least 1.5× the European share (up to 4, strongest first) or at most
  0.67× (up to 2); categories under 1% both in the city and in Europe are skipped. Ratios use unrounded shares.

## districts.json (lazy)

Each city's industry specialisation as strategy-game districts, built by `pipeline/build/districts.py`. Loaded on
demand by the City View, the banner badges (`state.cityBadges`) and the advisors.

```jsonc
{
  "version": 1, "year": 2024, "sources": ["eurostat", "sbs"],
  "vintage": "Eurostat regional accounts 2023 (jobs by branch, NUTS 3) and structural business statistics 2024 (…)",
  "rule": {"min_lq": 1.25, "min_jobs": 1000, "min_share": 0.01, "specialty_lq": 3.0, "specialty_jobs": 1000,
           "max_per_city": 5, "harbor_needs_water": true, "harbor_needs_port": true, "aerodrome_needs_airport": true,
           "badge_lq": 6.0, "badge_share": 0.03, "text": "…(quote this in the UI)…", "county_note": "…"},
  "catalog": [{"id": "campus", "name": "Campus", "icon": "d-campus", "color": "#4a7bd0",
               "naics": ["J61", "J62", "J63", "M71", "M72"], "own": [],
               "sub": {"M72": "Research and development", "J62": "Software and IT services", …},
               "badge": {"id": "scientific", "label": "Knowledge city", "labels": {"M72": "Research city", …}},
               "description": "…", "caveat": "…"}],
  "industries": {"C29": {"title": "Cars and car parts", "eu_emp": 2335123}},
  "national": {"emp": 232915830, "avg_pay": null},
  "regions": {"DE21": "Oberbayern", "DE27": "Schwaben"},   // SBS regions (NUTS 2, or NUTS 1 / country) cities use
  "cities": {"DE003F": {
    "emp": 2061700, "avg_pay": null, "counties": [8, 8], "regions": ["DE21", "DE27"],
    "top": [{"naics": "J60", "emp": 3481, "lq": 3.29, "avg_pay": null, "oty_pct": null,
             "suppressed": 0, "lower_bound": false}],
    "districts": [{"id": "aerodrome", "lq": 3.16, "emp": 8791, "share": 0.0043, "avg_pay": null,
                   "sub": "H51", "sub_lq": 3.16, "sub_emp": 8791, "sub_lower_bound": false,
                   "via": "broad", "strength": 6010, "suppressed": 0, "lower_bound": false, "estimated": 0,
                   "site": "Munich Airport"}],
    "badge": {"id": "scientific", "label": "Knowledge city", "district": "campus", "basis": "eurostat",
              "text": "Campus: 1.9× the European share of jobs"}
  } | null},
  "counties": {"DE212": {"emp": 1203650, "districts": [["campus", 1.89, 105947], ["commercial_hub", 1.47, 40432], …]}}
}
```

| id | Summed codes (`naics`) | Specialities (`sub`) | Badge id |
|---|---|---|---|
| `campus` | J61, J62, J63, M71, M72 | R&D, software, data, telecoms, engineering | scientific |
| `commercial_hub` | K | K64 banking, K65 insurance, K66 funds and exchanges | commercial |
| `industrial_zone` | B, C | manufacturing and mining divisions (C10-C32, B05-B08) | industrial |
| `harbor` | H50, H52 | shipping, warehousing and cargo handling | maritime |
| `theater_square` | J58, J59, J60, R90, R91 | arts, film, broadcasting, publishing, museums | cultural |
| `entertainment_complex` | I55, R92, R93 | hotels, gambling, sports and amusement | entertainment |
| `aerodrome` | H51 | airlines | aviation |
| `government_plaza` | O-Q | none | governmental |
| `encampment` | none | none (no regional defence data: never appears) | militaristic |
| `aqueduct` | D, E | power and gas, water and waste | utility |

* **Jobs.** Whole branches (`K`, `C`, `O-Q` and the totals) come from the regional accounts (NUTS 3, place of work,
  self-employed included), apportioned to the city like cities.json. Divisions come from structural business
  statistics, published for NUTS 2 only: a division's jobs in a NUTS 3 region are its NUTS 2 region's jobs in that
  division shared out by the NUTS 3 region's jobs in the division's branch. Confidential figures are estimated from
  what the NUTS 1 or national total leaves; where nothing is left, they count as zero and the value is a lower bound.
  Switzerland, Liechtenstein, Albania, Bosnia and Herzegovina, Montenegro and Kosovo publish no SBS: their cities get
  only branch-based districts.
* **LQ** (location quotient) = (the city's jobs in the codes ÷ its total jobs) ÷ (the same ratio for Europe).
* **Rule** (also in `rule.text`): a district appears when its LQ ≥ 1.25 with ≥ 1,000 jobs or ≥ 1% of the city's jobs
  (`via: "broad"`), or when one of its specialities has LQ ≥ 3 with ≥ 1,000 jobs (`via: "specialty"`; `lq` may then be
  below 1.25). Harbor needs a port of infrastructure.json in or next to the urban area, Aerodrome an airport (without
  infrastructure.json, Harbor needs a footprint hex on or next to water or a river, and Aerodrome is not tested).
  Government plaza also needs 1.1× its country's own share outside national capitals (`lq_country`, only on that
  district). Districts are ranked by `strength` (jobs above the European norm, `emp − emp / lq`, or the speciality's
  if larger), five at most.
* **Badge**: the strongest district, unless a district or its speciality has LQ ≥ 6 with ≥ 3% of the city's jobs.
  Its label is the speciality's nickname when the speciality has LQ ≥ 3, else the district's ("Shipyard city" for
  C30 with a Harbor; "Capital city" for a Government plaza in a national capital). `badge.district` is always one of
  the city's `districts`. `null` when no district passes.
* District items: `share` = `emp` ÷ the city's jobs; `sub` = its strongest speciality with LQ > 1 and ≥ 1,000 jobs (or
  null); `suppressed` = member regions with a withheld or unpublished part; `lower_bound` = suppressed > 0 (show
  "≥"); `estimated` = member regions with an estimated part; `site` = the port or airport (Harbor, Aerodrome).
  `top`: up to 8 divisions (B-N, R) with ≥ 1,000 jobs and LQ > 1, by LQ. `counties` = `[regions, regions]` (both
  the number of the city's regions). A city is `null` when its regions have no jobs total (GeoNames towns in Bosnia
  and Herzegovina and Kosovo).
* `counties` (top level): every NUTS 3 region with a jobs total, `districts` as `[id, lq, emp]`, same rule, with the
  port or airport required in the region itself (`rule.county_note`).
* `industries`: every code used, `{title, eu_emp}` (European jobs). Always null: `avg_pay`, `oty_pct`. `own` is
  always `[]`.

## infrastructure.json (eager)

Tile improvements: roads and railways as links between neighbouring hexes, plus seaports and airports. Built by
`pipeline/build/infrastructure.py`; read by the map layers (`web/js/ext/layers`), rankings, the commerce advisor and
districts.json.

```jsonc
{
  "version": 1,
  "vintage": {"roads": "Natural Earth v5.1.2 (1:10m)", "rail": "Natural Earth v5.1.2 (1:10m)",
              "ports": "Eurostat mar_go_aa 2024–2025", "airports": "Eurostat avia_paoa 2024–2025"},
  "sources": ["natural_earth_roads", "ports", "airports", "geonames"],
  "rules": {"roads": "…", "rail": "…", "ports": "…", "airports": "…"},          // quotable selection rules
  "road_classes": [{"id": "interstate", "name": "Motorway"}, {"id": "major", "name": "Major road"}],
  "rail_tiers": [{"id": "main", "name": "Main line"}, {"id": "secondary", "name": "Secondary line"}],
  "hubs": {"L": "Large airport (10 million passengers or more)", "M": "…", "S": "…", "N": "Regional airport (under 500,000)"},
  "roads": [[3067, 3311, 1, "E69"]],      // [cell a, cell b, class index, route name or null]
  "rail":  [[8664, 8665, 1]],             // [cell a, cell b, tier index]
  "ports": [{"id": "NL_0NLRTM", "name": "Rotterdam", "type": "coastal", "rank": 1, "tons": 390170000,
             "imports": 285551000, "exports": 104619000, "year": 2025,
             "x": 3656.4, "y": 5886.8, "cell": 38392, "county": "NL366", "cbsa": "NL037F", "state": "NL",
             "domestic": null, "foreign": null}],
  "airports": [{"id": "CDG", "icao": "LFPG", "name": "Charles de Gaulle International Airport", "city": "Paris",
                "hub": "L", "enplanements": 72002540, "enplanements_prev": 70257116, "year": 2025,
                "x": 3246.2, "y": 6663.1, "cell": 43507, "county": "FR106", "cbsa": "FR001F", "state": "FR",
                "cargo_lbs": null}]
}
```

* **Links** join neighbouring cells, `a < b`, each pair once with its best class. Lines are sampled every 4 map units
  (1.6 km); a cell the line only clips at a corner is dropped; at least one end is map land and neither end is a
  neighbouring country; lines are cut at inset windows. Natural Earth is map art, not statistics (older alignments,
  part of the real network).
* **Road classes**: 0 = every road Natural Earth flags as an expressway; 1 = the other E-roads and highways of scale
  rank ≤ 7. Route name: the national number (`A6`), else the E-road (`E15`), else `Route <n>`; the lowest number wins
  on a shared link. **Rail tiers**: 0 = scale rank ≤ 5, 1 = 6-7.
* **Ports**: every Eurostat port with at least 500,000 tonnes in its country's latest complete year, ranked by
  tonnage (`rank`, 1 = largest). `tons` = gross weight handled, `imports` = unloaded, `exports` = loaded (tonnes, null
  when not published). `type`: `coastal`, or `inland` (Eurostat files it as inland, or no sea hex within 4 rings).
  Placed at the Wikidata place with its UN/LOCODE, else the UN/LOCODE coordinates, else the GeoNames town.
* **Airports**: every Eurostat airport with at least 50,000 passengers in the reference year (the year before for a
  country that reports late), sorted by passengers. `id` = IATA code (ICAO when there is none); `hub` follows
  passengers (L ≥ 10 million, M ≥ 2 million, S ≥ 500,000, N below); `enplanements_prev` = the year before (or null).
  Placed by ICAO code with OurAirports.
* A site's `cell` is land of its own country at its point, else the nearest within 2 hexes (4 next to another map
  country's land); a site without one (a small island) is left out. Always null: `domestic`, `foreign`, `cargo_lbs`.

## wonders.json (eager)

UNESCO World Heritage properties as wonders, built by `pipeline/build/wonders.py`. Read by the map layers, rankings
and the culture advisor.

```jsonc
{
  "version": 1,
  "vintage": {"unesco": "World Heritage List after the 2026 session (1,273 properties)"},
  "sources": ["unesco"],
  "rules": [{"id": "unesco", "kind": "landmark", "kinds": ["landmark", "natural"], "text": "…"}],
  "national": {"whs": 207, "whs_listed": 429,
               "park_visits": null, "park_visits_year": null, "museum_visits": null, "museum_visits_year": null},
  "wonders": [{"id": "whs-33", "key": "whs-33", "name": "Białowieża Forest", "short": "Białowieża",
               "kind": "natural", "rule": "unesco", "rank": 5,
               "metrics": {"inscribed": 1979, "whs_id": "33", "category": "Natural", "area_km2": 1418.8,
                           "in_danger": false, "states_parties": ["PL", "BY"], "visits": null},
               "x": 6938.7, "y": 5471.9, "cell": 35784, "cells": null,
               "county": "PL842", "cbsa": null, "state": "PL", "curated": false}]
}
```

* **Rule** (`rules[0].text`): every natural and mixed property, the cultural properties inscribed up to 1996, and for
  a country still without one its earliest inscription. A serial or transboundary property appears once, at its first
  component (by UNESCO reference number) on the land of one of its States Parties; properties off the map are left
  out. `rank`: by year of inscription, then UNESCO id.
* `kind`: `landmark` (cultural) or `natural` (natural and mixed), always one of its rule's `kinds`. `short`: a map
  label. `metrics.category`: UNESCO's category; `area_km2`: the property's area (null if not published);
  `states_parties`: only for transboundary properties (map country codes, ISO codes for the others).
* `cell`: one wonder per hex in rank order (a later one moves to the nearest free hex of its country within 2 rings;
  Malta, too small, keeps several on one); `x`, `y` stay the true position. `state_note` (optional, absent today)
  explains a site that lies in a country other than the inscribing one.
* `national.whs` = wonders on the map, `whs_listed` = properties listed for the map's countries. Always null or
  constant: `cells`, `metrics.visits`, the `national` visit keys, `curated` (false); `key` equals `id`.

## sources.json

The Almanac's bibliography, written last by `catalog`: one entry per source, `{id, title, publisher, homepage, license,
description, used_for, vintage, files: [{file, url, retrieved, sha256, bytes}]}`. `files` lists only the files the
latest `process()` used (`_files`) that are in the download manifest, or every manifest entry if the source did not
say. A file saved by `download_prefix()` has a `partial` note in the manifest; its `sha256` and `bytes` describe the
saved part. Read by the Almanac (`web/js/ui/pedia.js`); lens and resource `source` ids must exist here.

## defi.json (server only)

The pool of the daily challenge, built by `pipeline/build/challenge.py`. It is **not published** with the site (the
package step leaves it out); `server/api.py` reads it with communes.json, cities.json and states.json and draws each
day's places with a secret key.

```jsonc
{"version": 1, "start": "2026-11-26", "pattern": ["facile", "facile", "moyen", "moyen", "difficile"],
 "columns": ["code", "name", "dep", "pop", "x", "y"], "km_per_unit": 0.4,
 "tiers": {"facile": [["GN3089578", "Pabianice", "PL", 70542, 6210, 5890]], "moyen": [], "difficile": []}}
```

* Rows are GeoNames towns (`code` = `GN<geonameid>`, `dep` = country) whose name no city banner already shows, without
  digits in the name, outside the insets and on their own country's hexes. `x`, `y`: map units (rounded);
  km = units × `km_per_unit`.
* Tiers (the keys are part of the API: easy, medium, hard): `facile` 60,000 inhabitants or more, `moyen` 20,000 to
  59,999, `difficile` 8,000 to 19,999. Each tier is shuffled with a fixed seed.
* Each slot of `pattern` takes a row of its tier chosen by HMAC-SHA256 of the secret, the day, the slot and a counter,
  skipping places drawn in the previous 120 days. `start` is day 1 (days follow Europe/Paris time). A day's draw is
  stored on first use, so a new pool never changes a day already played.

## Browser side

* `web/js/main.js` loads world, cities and nation (required) and lenses, sources, resources and states (optional)
  before the first frame. They are `app.data.<name>` for the extensions (`web/js/ext/*`), with `app.data.sources = []`
  and an empty lens list when those files are missing.
* `app.loadData(name) → Promise<data | null>` loads `data/<name>.json` once (later calls return the same promise),
  sets `app.data[name]` and emits a `"data"` event `{name, data}`. An optional file is `undefined` until requested and
  `null` when missing (404) or invalid; every reader must handle `null`. infrastructure and wonders are requested
  right after the first frame; counties (`app.loadCounties()`), communes, citizens and districts only when something
  asks for them.
* URL hash keys that name data: `city` = a cities.json `id`, `state` = a country code (`abbr`), `lens` = a lens `id`.
* When renaming a field, update its readers: the advisors (`web/js/ext/advisors`) read every counties.json column,
  districts.json `cities` and `counties` and citizens.json `cities`; the City View (`web/js/ext/cityView`) reads
  citizens.json, districts.json and counties.json; the server reads communes.json `code`, `name`, `dep`,
  `aav`, cities.json `id`, `name`, states.json `abbr`, `name`, `region` and all of defi.json.
