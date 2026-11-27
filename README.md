# Europe-Civilization

**Europe as a Civilization-style strategy map, built entirely from open data.**

**[Play it at mathieuastruc.com/europeciv](https://mathieuastruc.com/europeciv/)** · [Announcement on X](https://x.com/matheusnpu/status/2126047439274516570)

![The map of Europe: hex terrain, cities with their yield banners, resources and wonders](docs/images/europe.jpg)

The 27 EU member states, Iceland, Liechtenstein, Norway, Switzerland, the six Western Balkan countries and the United
Kingdom, drawn as the map of a turn-based strategy game. Every hex, city banner and number comes from public
statistics: Eurostat, the UK's statistical offices, Copernicus, UNESCO and other open sources, each cited in the
in-game Almanac.

It is a viewer, not a game: you explore Europe the way you would explore a Civilization map. It is a port of
Andrej Karpathy's [usaciv](https://karpathy.ai/usaciv/) (MIT), through its French version
[franceciv](https://mathieuastruc.com/franceciv/). The engine, the rendering and the interface come from usaciv; the
data pipeline is rebuilt for Europe. This is a first version and it is actively maintained.

## What you can do

- **Explore the map.** About 71,000 hexes of 10 km radius, 19,400 of them on the 38 countries: forests, farmland,
  heath and maquis, snowy Alps and Pyrenees, wetlands and towns, with rivers, lakes, named seas and mountain ranges,
  roads, railways, 341 airports and 370 ports. The EU's outermost regions (Azores, Madeira, Canary Islands,
  Guadeloupe, Martinique, French Guiana, Réunion, Mayotte) sit in insets.
- **Visit 734 cities.** Eurostat's functional urban areas (a core city and its commuting zone; the UK's from the 2020
  edition), plus towns of 50,000+ where the Urban Audit has none. Each has its yields (Food, Production, Gold, Science, Culture), a city view with its
  districts (its real industrial specialisation) and its citizens (age, education, origins, commuting).
- **Rank the countries.** The Rankings screen orders the 38 countries in 35 measures across seven domains (yields,
  economy, people, society, land, energy, heritage) and 734 cities in 11 more, and can colour the map by any of them.
- **Switch lenses.** 24 map overlays: density, growth, median age, life expectancy, GDP per person, household income,
  poverty, unemployment, university degrees, forest, farmland, vineyards, olive groves, temperature, warming,
  rainfall and more, including forest height from spaceborne LiDAR (ETH Zurich's canopy height map, learned from
  NASA's GEDI measurements).
- **Watch fifty years go by.** The "Density since 1975" lens has a year slider and a Play button: the population
  every five years from 1975 to 2020 (the European Commission's Global Human Settlement Layer), on one colour scale.
  Madrid's region grows by about 70% while inland Spain, the Alentejo, eastern Germany, the Baltics and Bulgaria
  lose people.
- **Read the council of advisors.** Economy, prosperity, energy, people, knowledge, culture and land dashboards, and an
  explorer that charts any column of the countries, cities and 1,447 regions.
- **Read every name.** The 98,000 local administrative units (communes, Gemeinden, comuni…), the UK's 8,500 wards and
  the 28,000 towns and villages of Bosnia and Herzegovina, Montenegro and Kosovo are named on the map as you zoom in,
  from the largest towns down to the smallest village. Search finds any of them, by local name too.
- **Find yourself.** The crosshair beside the search box asks your browser for your position, which stays on your
  device, and opens the card of the municipality you are in.
- **Play the daily challenge.** Five places a day, the same for everyone, thirty seconds each: click where you think
  they are. Rankings by player, city, country and part of Europe.

## Run it locally

You need [uv](https://docs.astral.sh/uv/) (it installs Python 3.11+ for you). Nothing else.

```bash
git clone https://github.com/lmveprog/Europe-Civilization.git
cd Europe-Civilization
uv run python -m pipeline serve          # http://127.0.0.1:8765
```

The built data is in the repository, so the map, cities, lenses, rankings and advisors run as is. `web/` is a
self-contained static site (ES modules and Canvas 2D, no framework, no build step). The daily challenge also needs
its pool of places, which the repository leaves out like the live site does: `uv run python -m pipeline all` builds it.

## Rebuild the data

```bash
uv run python -m pipeline all            # download every source, rebuild every file, check them
uv run python -m pipeline build lenses   # or rebuild one file
uv run python -m pipeline check          # consistency checks on web/data
uv run python -m unittest discover tests
```

A full rebuild downloads a few gigabytes and takes about an hour (most of it is the 2000-2019 climate series).
If your network intercepts TLS, set `SSL_CERT_FILE` to your system's certificate bundle; if it resets TLS over IPv6,
set `PIPELINE_IPV4=1`. The pipeline uses only Python's standard library.

In the browser, `web/dev/smoke.html?d=1456x838&quick` drives the whole app (zoom, selection, city views, lenses,
advisors, rankings, search, daily challenge) and reports any error; run it before sending a change.

## How it works

The flow is always **source → interim → builder → web/data**:

- `pipeline/sources/` downloads each source once (cached, with a provenance manifest) and tidies it into
  `data/interim/`.
- `pipeline/build/` puts those data on the hex grid and writes the JSON files in `web/data/` that the browser reads.
- `pipeline/check.py` and each builder's `check()` validate those files against
  [docs/DATA_CONTRACTS.md](docs/DATA_CONTRACTS.md).
- `server/api.py` is the daily challenge's server (standard library and SQLite).

The map uses a Lambert azimuthal equal-area projection centred on 52° N 10° E (the spherical form of EPSG:3035).
A city's GDP and jobs are its NUTS 3 regions' figures shared out by the share of their population living in the urban
area; rates published only for NUTS 2 regions (unemployment, income, poverty, degrees) are population-weighted means.
Where Eurostat leaves a region blank, the figure is filled from the larger region that has it and flagged as an
estimate. Countries outside the EU's regional accounts get national estimates: GDP per person from the national
accounts (or, for Switzerland, the PPS volume index), household income from the EU-SILC survey's mean income scaled to
the regional-accounts measure. Bosnia and Herzegovina's population and age structure and Kosovo's age structure, which
Eurostat does not publish, come from the World Bank; the population of Iceland's municipalities, missing from the LAU
file, from Statistics Iceland.

| Part | Where |
|---|---|
| Data sources (one module each) | `pipeline/sources/` |
| Builders (one per web/data file) | `pipeline/build/` |
| Map geometry, Europe settings, file readers | `pipeline/core/` |
| Browser app | `web/js/` (`main.js`, `render/`, `ui/`, `ext/` for city view, advisors, rankings, layers, challenge) |
| Data files read by the browser | `web/data/` |
| Daily challenge server | `server/` |
| Tests | `tests/`, `web/dev/smoke.html` |

## Data sources

| Data | Source | Licence |
|---|---|---|
| Regions, countries, urban areas, local units | Eurostat GISCO (NUTS 2024, Urban Audit 2021, LAU 2021) | Eurostat reuse policy; boundaries © EuroGeographics |
| Population, GDP, jobs, income, education, health | Eurostat regional and city statistics | CC BY 4.0 |
| Land cover 2018 (CORINE classes) | OpenGeoHub EcoDataCube, from Copernicus CORINE and LUCAS | CC BY 4.0 |
| Land cover of the French overseas regions | CORINE Land Cover 2018 (SDES, IGN) | Licence Ouverte 2.0 |
| Climate 2000-2019 | ERA5 (Copernicus) and CHELSA, via EcoDataCube | CC BY 4.0 |
| Forest height 2020 | ETH Zurich global canopy height map (from NASA GEDI LiDAR and Sentinel-2) | CC BY 4.0 |
| Elevation and sea depth | NOAA ETOPO1 | Public domain |
| Rivers, lakes, roads, railways | Natural Earth | Public domain |
| Power plants | powerplantmatching (PyPSA), WRI Global Power Plant Database | CC BY 4.0 |
| World Heritage sites | UNESCO open data | CC BY-SA 4.0 |
| Airports | Eurostat passenger statistics, OurAirports | CC BY 4.0, public domain |
| Towns and place names | GeoNames | CC BY 4.0 |
| Population every five years, 1975-2020 | GHS-POP R2023A, Global Human Settlement Layer (European Commission, JRC) | CC BY 4.0 |
| Population of Iceland's municipalities | Statistics Iceland | CC BY 4.0 |
| Population and age of Bosnia and Herzegovina and Kosovo | World Bank, World Development Indicators | CC BY 4.0 |
| United Kingdom: ITL regions, wards and census population, regional accounts, jobs, labour force, life expectancy | ONS, National Records of Scotland, NISRA | Open Government Licence v3.0 |
| United Kingdom: airports, ports | Civil Aviation Authority, Department for Transport | Open Government Licence v3.0 |

The Almanac (top right in the app) lists every file used, with its URL, date and checksum.

## FAQ

**Where do the United Kingdom's figures come from?** The UK left the EU in 2020 and Eurostat's regional tables stop
there, so its regions, wards and statistics come from the UK's own offices (ONS, National Records of Scotland, NISRA),
converted to euros and PPS at Eurostat's rates. A few measures differ slightly: household income is gross rather than
net, the labour-force rates use UK age bands, and no regional poverty rate exists. The Almanac lists every
approximation.

**Why two populations for a city?** The banner shows the core municipality (Paris: 2.2 million); the panel adds the
functional urban area, the city and its commuting zone (Paris: 13.3 million), which is what Eurostat compares across
countries.

**How recent is the data?** Population on 1 January 2025; GDP and jobs 2023; local units from the 2021 census; land
cover 2018; climate 2000-2019. Each figure's year is in the Almanac.

**Why are the hexes bigger than in franceciv?** Europe is seven times the area of France; 17 km hexes keep the map
fluid, phones included, with the same detail per region and city.

## Contributing

Issues and pull requests are welcome. Keep changes focused, run the tests and the smoke page, and describe what you
changed and why. New data must come from an open source with a licence that allows reuse, and its figures must be
traceable in the Almanac.

## Security

The site is static. The only server part is the daily challenge: bound to 127.0.0.1 behind a reverse proxy, with an
origin check, per-address rate limits and a small request size limit. Players have a nickname and a random token,
nothing else (no e-mail, no password). The server's secret key and database never leave the server. To report a
vulnerability, see [SECURITY.md](SECURITY.md).

## Credits and licence

Code under the MIT licence (see [LICENSE](LICENSE)): the original engine and art are © Andrej Karpathy (usaciv), the
Europe adaptation © the europeciv contributors. The data keep their own licences (above). UK data: contains public
sector information licensed under the Open Government Licence v3.0; UK boundaries contain OS data © Crown copyright and
database right, and Land & Property Services (Northern Ireland) data.
