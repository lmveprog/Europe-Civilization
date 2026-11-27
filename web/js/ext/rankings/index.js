// Rankings: the 38 countries ranked in every domain, a Civ "Demographics" screen docked beside the map.
//   top-bar button "Rankings", mode "rankings", link #rankings=<metric id>
//   domain tabs, then one metric at a time: a ranked table (click a row: select and fly to the country; hover: the
//   country lights up on the map), "Colour the map" turns the ranking into a lens, and the selected country's
//   placings across the whole domain (Civ's "rank N of 38").
import { css } from "../../color.js";
import { esc, int, money, pct, compact, dec } from "../../format.js";

const CSS_HREF = new URL("../../../css/rankings.css", import.meta.url).href;
const DOCK_W = 400;

const fin = (v) => typeof v === "number" && Number.isFinite(v);
const share = (st, k) => (st.land && fin(st.land[k]) ? st.land[k] : null);
const sum = (vals) => vals.reduce((a, b) => a + b, 0);
const mw = (v) => (!fin(v) ? "–" : v >= 10000 ? `${dec(v / 1000, v >= 1e5 ? 0 : 1)} GW` : `${int(v)} MW`);
const signed = (v) => (!fin(v) ? "–" : `${v >= 0 ? "+" : "−"}${dec(Math.abs(v * 100), 1)}%`);

// id, domain, label, short label, format(v), higher (is better: true | false | null = neutral), value(st, x), note
// x: {i (state index), cities, wonders, infra, res} — extra counts built from the other data files.
const METRICS = [
  // Yields: the five Civ yields of each country.
  { id: "gold", d: "yields", label: "Gold (GDP)", fmt: money, higher: true, v: (s) => s.yields?.gold, note: "Gross domestic product, current euros (Eurostat)." },
  { id: "production", d: "yields", label: "Production", fmt: compact, higher: true, v: (s) => s.yields?.production, note: "Jobs in industry and construction." },
  { id: "science", d: "yields", label: "Science", fmt: compact, higher: true, v: (s) => s.yields?.science, note: "Jobs in information, communication and professional, scientific and technical services." },
  { id: "culture", d: "yields", label: "Culture", fmt: compact, higher: true, v: (s) => s.yields?.culture, note: "Jobs in arts, entertainment, recreation and other services." },
  { id: "food", d: "yields", label: "Food", fmt: compact, higher: true, v: (s) => s.yields?.food, note: "Jobs in agriculture, forestry and fishing." },
  // Economy
  { id: "gdp_pps", d: "economy", label: "GDP per person", fmt: (v) => `${int(v)} PPS`, higher: true, v: (s) => s.gdp_pps_per_capita, note: "GDP per inhabitant in purchasing power standards (euros at EU-average prices), so price levels compare. Iceland, Bosnia and Herzegovina: national accounts; Switzerland: PPS volume index." },
  { id: "income", d: "economy", label: "Household income", fmt: (v) => `${int(v)} PPS`, higher: true, v: (s) => s.median_income, note: "Disposable household income per inhabitant, PPS (Eurostat, regional accounts). Iceland, Switzerland, Albania, Montenegro, North Macedonia, Serbia and Kosovo: estimated from the EU-SILC survey's mean income. United Kingdom: gross household income (ONS)." },
  { id: "employment", d: "economy", label: "Employment rate", fmt: (v) => pct(v, 1), higher: true, v: (s) => s.employment_rate, note: "Share of 20-64 year-olds in work (labour force survey)." },
  { id: "unemployment", d: "economy", label: "Unemployment", fmt: (v) => pct(v, 1), higher: false, v: (s) => s.unemployment, note: "Unemployment rate, ages 15-74 (labour force survey). Lowest first." },
  { id: "science_share", d: "economy", label: "Knowledge jobs", fmt: (v) => pct(v, 1), higher: true, v: (s) => (fin(s.yields?.science) && s.workplace_jobs ? s.yields.science / s.workplace_jobs : null), note: "Science-yield jobs as a share of all jobs." },
  { id: "industry_share", d: "economy", label: "Industrial jobs", fmt: (v) => pct(v, 1), higher: null, v: (s) => (fin(s.yields?.production) && s.workplace_jobs ? s.yields.production / s.workplace_jobs : null), note: "Industry and construction jobs as a share of all jobs." },
  // People
  { id: "population", d: "people", label: "Population", fmt: int, higher: null, wb: "population", v: (s) => s.population, note: "Residents on 1 January (Eurostat)." },
  { id: "growth", d: "people", label: "Growth", fmt: signed, higher: null, wb: "growth", v: (s) => s.growth, note: "Population change over five years; a census revision beyond ±15% is left blank." },
  { id: "life", d: "people", label: "Life expectancy", fmt: (v) => `${dec(v, 1)} yrs`, higher: true, wb: "life_expectancy", v: (s) => s.life_expectancy, note: "Life expectancy at birth." },
  { id: "age", d: "people", label: "Median age", fmt: (v) => `${dec(v, 1)} yrs`, higher: null, v: (s) => s.median_age, note: "Half the population is older, half younger." },
  { id: "youth", d: "people", label: "Children", fmt: (v) => pct(v, 1), higher: null, wb: "youth", v: (s) => s.youth, note: "Share of residents under 15." },
  { id: "density", d: "people", label: "Density", fmt: (v) => `${int(v)} /km²`, higher: null, wb: "density", v: (s) => s.density, note: "People per km² of land." },
  { id: "cities", d: "people", label: "Cities on the map", fmt: int, higher: null, v: (s, x) => x.cities.get(x.i) || 0, note: "Functional urban areas (or towns of 50,000+) drawn as cities." },
  // Society
  { id: "degrees", d: "society", label: "University degrees", fmt: (v) => pct(v, 1), higher: true, v: (s) => s.bachelors, note: "Share of 25-64 year-olds with tertiary education." },
  { id: "poverty", d: "society", label: "Poverty or exclusion", fmt: (v) => pct(v, 1), higher: false, v: (s) => s.poverty, note: "At risk of poverty or social exclusion (national poverty lines). Lowest first." },
  { id: "seniors", d: "society", label: "Seniors", fmt: (v) => pct(v, 1), higher: null, wb: "seniors", v: (s) => s.seniors, note: "Share of residents aged 65 or over." },
  // Land
  { id: "area", d: "land", label: "Area", fmt: (v) => `${int(v)} km²`, higher: null, v: (s) => s.land_km2, note: "Land area of the country's local units. Bosnia and Herzegovina, Montenegro and Kosovo have none: the area of their regions' outlines." },
  { id: "forest", d: "land", label: "Forest", fmt: (v) => pct(v, 0), higher: null, v: (s) => share(s, "forest"), note: "Share of the land under forest (CORINE classes)." },
  { id: "farmland", d: "land", label: "Farmland", fmt: (v) => pct(v, 0), higher: null, v: (s) => (share(s, "crop") != null ? share(s, "crop") + (share(s, "pasture") || 0) : null), note: "Share of the land in crops, vineyards, orchards and pastures." },
  { id: "forest_height", d: "land", label: "Forest height", fmt: (v) => `${dec(v, 1)} m`, higher: null, v: (s, x) => x.forestHeight.get(x.i) ?? null, note: "Mean canopy height of the country's forested hexes (ETH Zurich's 2020 map, learned from NASA's GEDI spaceborne LiDAR)." },
  { id: "builtup", d: "land", label: "Built-up land", fmt: (v) => pct(v, 1), higher: null, v: (s) => share(s, "developed"), note: "Share of the land that is built up." },
  // Energy (mapped sites only)
  { id: "power", d: "energy", label: "Power plants (mapped)", fmt: mw, higher: null, v: (s) => s.energy?.total, note: "Capacity of the plants on the map, each above its type's threshold: not the country's full capacity." },
  { id: "power_pc", d: "energy", label: "Power per person", fmt: (v) => `${int(v)} W`, higher: null, v: (s) => (fin(s.energy?.total) && s.population ? (s.energy.total * 1e6) / s.population : null), note: "Mapped capacity in watts per resident." },
  { id: "nuclear", d: "energy", label: "Nuclear", fmt: mw, higher: null, v: (s) => s.energy?.by_type?.nuclear || null, note: "Mapped nuclear capacity." },
  { id: "renewable", d: "energy", label: "Wind and solar", fmt: mw, higher: null, v: (s) => (s.energy ? (s.energy.by_type?.wind || 0) + (s.energy.by_type?.solar || 0) || null : null), note: "Mapped wind and solar clusters." },
  { id: "hydro", d: "energy", label: "Hydro", fmt: mw, higher: null, v: (s) => (s.energy ? (s.energy.by_type?.hydro || 0) + (s.energy.by_type?.pumped_storage || 0) || null : null), note: "Mapped hydro and pumped-storage capacity." },
  { id: "coal", d: "energy", label: "Coal", fmt: mw, higher: null, v: (s) => s.energy?.by_type?.coal_plant || null, note: "Mapped coal and lignite capacity still running." },
  // Heritage and hubs
  { id: "unesco", d: "heritage", label: "World Heritage sites", fmt: int, higher: null, v: (s, x) => x.wonders.get(x.i) || 0, note: "UNESCO World Heritage properties drawn as wonders (a selection: see the Almanac)." },
  { id: "air", d: "heritage", label: "Air passengers", fmt: compact, higher: null, v: (s, x) => x.air.get(x.i) || null, note: "Passengers of the country's airports on the map, latest year (Eurostat)." },
  { id: "ports", d: "heritage", label: "Port tonnage", fmt: (v) => `${compact(v)} t`, higher: null, v: (s, x) => x.ports.get(x.i) || null, note: "Goods handled by the country's ports on the map (Eurostat)." },
];
// Cities: the same idea for the 646 urban areas (top 50 shown). value(c) from cities.json.
const CITY_METRICS = [
  { id: "c_pop", label: "Population", fmt: int, higher: null, v: (c) => c.population, note: "People in the functional urban area (Eurostat Urban Audit; GeoNames for towns outside it)." },
  { id: "c_core", label: "Core city", fmt: int, higher: null, v: (c) => c.commune_population, note: "People in the core municipality itself (2021 census)." },
  { id: "c_gdp", label: "GDP", fmt: money, higher: true, v: (c) => c.gdp, note: "GDP of the urban area: its NUTS 3 regions' GDP shared out by population." },
  { id: "c_gdppc", label: "GDP per person", fmt: (v) => money(v), higher: true, v: (c) => (c.gdp && c.population ? c.gdp / c.population : null), note: "GDP ÷ population, current euros (not adjusted for price levels)." },
  { id: "c_growth", label: "Growth", fmt: signed, higher: null, v: (c) => c.growth, note: "Population change over five years." },
  { id: "c_science", label: "Science", fmt: compact, higher: true, v: (c) => c.yields?.science, note: "Jobs in information, communication and professional services." },
  { id: "c_production", label: "Production", fmt: compact, higher: true, v: (c) => c.yields?.production, note: "Jobs in industry and construction." },
  { id: "c_culture", label: "Culture", fmt: compact, higher: true, v: (c) => c.yields?.culture, note: "Jobs in arts, entertainment and other services." },
  { id: "c_degrees", label: "University degrees", fmt: (v) => pct(v, 1), higher: true, v: (c) => c.bachelors, note: "Share of 25-64 with tertiary education, NUTS 2 average." },
  { id: "c_unemp", label: "Unemployment", fmt: (v) => pct(v, 1), higher: false, v: (c) => c.unemployment, note: "Unemployment rate, NUTS 2 average. Lowest first." },
  { id: "c_life", label: "Life expectancy", fmt: (v) => `${dec(v, 1)} yrs`, higher: true, v: (c) => c.life_expectancy, note: "Life expectancy at birth, NUTS 2 average." },
];
const CITY_TOP = 50;
// A city figure built from regional tables Eurostat fills only for larger regions (cities.json `estimated`).
const ESTIMATED_FROM = { c_gdp: "gdp3", c_gdppc: "gdp3", c_science: "emp3", c_production: "emp3", c_culture: "emp3" };
const approx = (m, c) => !!ESTIMATED_FROM[m.id] && (c.estimated || []).includes(ESTIMATED_FROM[m.id]);

// How the coloured map's legend writes each metric: [lens format, unit].
const LENS_FMT = {
  gold: ["usd", "€"], production: ["float", "jobs"], science: ["float", "jobs"], culture: ["float", "jobs"], food: ["float", "jobs"],
  gdp_pps: ["float", "PPS"], income: ["float", "PPS"], employment: ["pct", ""], unemployment: ["pct", ""],
  science_share: ["pct", ""], industry_share: ["pct", ""], population: ["float", "people"], growth: ["change", ""],
  life: ["years", ""], age: ["years", ""], youth: ["pct", ""], density: ["int", "people / km²"], cities: ["float", "cities"],
  degrees: ["pct", ""], poverty: ["pct", ""], seniors: ["pct", ""], area: ["float", "km²"], forest: ["pct", ""],
  farmland: ["pct", ""], forest_height: ["metres", ""], builtup: ["pct", ""], power: ["float", "MW"], power_pc: ["float", "W per person"],
  nuclear: ["float", "MW"], renewable: ["float", "MW"], hydro: ["float", "MW"], coal: ["float", "MW"],
  unesco: ["float", "sites"], air: ["float", "passengers"], ports: ["float", "t"],
};
const DOMAINS = [
  { id: "yields", label: "Yields" }, { id: "economy", label: "Economy" }, { id: "people", label: "People" },
  { id: "society", label: "Society" }, { id: "land", label: "Land" }, { id: "energy", label: "Energy" },
  { id: "heritage", label: "Heritage & hubs" },
];
const RAMP_GOOD = ["#3a1c0b", "#7a4413", "#b8781f", "#e3b23c", "#f6e27f", "#fffbe0"];
const RAMP_BAD = ["#fffbe0", "#f6c89a", "#e8875c", "#c24a3d", "#7d1f2b", "#3a0b14"];
const RAMP_NEUTRAL = ["#0b1d3a", "#1f4a73", "#3f7fa3", "#78b3b8", "#bfe0c7", "#f3f7d8"];

function ensureCss() {
  if (document.getElementById("rankings-css")) return;
  const l = document.createElement("link");
  l.id = "rankings-css";
  l.rel = "stylesheet";
  l.href = CSS_HREF;
  document.head.appendChild(l);
}

export function install(app) {
  ensureCss();
  let metricId = "gold", cityMetricId = "c_pop", scope = "countries", root = null, prevLens = null, mapLens = null, extra = null;
  const states = () => app.data.states || [];
  const worldStates = () => app.w.raw.states;

  // Counts by country index from the other files (cities now; wonders, airports, ports once loaded).
  function extras() {
    const idx = new Map(worldStates().map((s, i) => [s.abbr, i]));
    const count = (items, key = () => 1) => {
      const m = new Map();
      for (const it of items || []) {
        const i = idx.get(it.state ?? it.states?.[0]);
        if (i == null) continue;
        const v = key(it);
        if (fin(v)) m.set(i, (m.get(i) || 0) + v);
      }
      return m;
    };
    // mean of a lens over each country's hexes that have a value
    const lensMean = (id) => {
      const lens = app.data.lenses?.lenses?.find((l) => l.id === id);
      const owner = app.w.raw.owner, acc = new Map(), m = new Map();
      lens?.values.forEach((v, c) => {
        if (!fin(v) || owner[c] < 0) return;
        const a = acc.get(owner[c]) || [0, 0];
        a[0] += v;
        a[1] += 1;
        acc.set(owner[c], a);
      });
      for (const [i, [total, n]] of acc) m.set(i, total / n);
      return m;
    };
    const infra = app.data.infrastructure;
    return {
      forestHeight: lensMean("forest_height"),
      cities: count(app.data.cities, () => 1),
      wonders: count(app.data.wonders?.wonders),
      air: count(infra?.airports, (a) => a.enplanements),
      ports: count(infra?.ports, (p) => p.tons),
    };
  }
  const metric = (id) => METRICS.find((m) => m.id === id) || METRICS[0];
  function rows(m) {
    extra ??= extras();
    const out = [];
    states().forEach((s, i) => {
      const v = m.v(s, { ...extra, i });
      if (fin(v)) out.push({ i, s, v });
    });
    out.sort((a, b) => (m.higher === false ? a.v - b.v : b.v - a.v));
    out.forEach((r, k) => (r.rank = k + 1));
    return out;
  }
  const rankOf = (m, i) => rows(m).find((r) => r.i === i) || null;
  const cityMetric = (id) => CITY_METRICS.find((m) => m.id === id) || CITY_METRICS[0];
  function cityRows(m) {
    const out = [];
    for (const c of app.data.cities || []) {
      const v = m.v(c);
      if (fin(v)) out.push({ c, v });
    }
    out.sort((a, b) => (m.higher === false ? a.v - b.v : b.v - a.v));
    out.forEach((r, k) => (r.rank = k + 1));
    return out;
  }

  // --- top-bar button and mode -------------------------------------------------------------------------------------
  const btn = app.ui.addTopButton({
    id: "btn-rankings", label: "Rankings", title: "Rankings: the countries ranked in every domain",
    onClick: () => (app.mode === "rankings" ? app.setMode(null) : app.setMode("rankings", { metric: scope === "cities" ? cityMetricId : metricId })),
  });
  if (btn) {
    btn.innerHTML = `<svg class="icon" width="16" height="16" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M9 5h6v16H9zM2.5 11h5.5v10H2.5zM16 8.5h5.5V21H16z" fill="currentColor"/></svg><span class="lbl">Rankings</span>`;
    btn.setAttribute("aria-pressed", "false");
  }
  app.on("mode", ({ name }) => btn?.setAttribute("aria-pressed", String(name === "rankings")));

  app.registerMode("rankings", {
    enter(p = {}) {
      if (p.metric?.startsWith?.("c_")) { scope = "cities"; cityMetricId = cityMetric(p.metric).id; }
      else if (p.metric) { scope = "countries"; metricId = metric(p.metric).id; }
      prevLens = app.state.lens || null;
      const dock = app.ui.dock("left", { width: DOCK_W, label: "Rankings" });
      dock.innerHTML = "";
      dock.classList.add("rk-dock");
      root = document.createElement("div");
      root.className = "rk-root";
      dock.appendChild(root);
      wire(root);
      render();
      // Wonders, airports and ports feed the heritage tab; they may still be on their way.
      for (const name of ["wonders", "infrastructure"]) {
        if (app.data[name] === undefined) app.loadData?.(name).then(() => { extra = null; if (app.mode === "rankings") render(); });
      }
    },
    exit() {
      if (mapLens && app.state.lens === mapLens) app.setLens(prevLens);
      mapLens = null;
      app.setHighlight(null);
      app.ui.undock("left");
      root = null;
    },
  });
  app.on("select", () => { if (app.mode === "rankings") render(); });

  app.hash.register("rankings", {
    get: () => (app.mode === "rankings" ? (scope === "cities" ? cityMetricId : metricId) : null),
    set(v) {
      if (v != null) {
        if (v.startsWith("c_")) { scope = "cities"; cityMetricId = cityMetric(v).id; } else { scope = "countries"; metricId = metric(v).id; }
        if (app.mode !== "rankings") app.setMode("rankings", { metric: scope === "cities" ? cityMetricId : metricId });
        else render();
      } else if (app.mode === "rankings") app.setMode(null);
    },
  });

  function pick(id) {
    metricId = metric(id).id;
    if (mapLens && app.state.lens === mapLens) colourMap(); // keep the map in step with the table
    render();
    app.hash.update?.();
  }

  // --- the map coloured by the current ranking ----------------------------------------------------------------------
  function colourMap() {
    const m = metric(metricId), rs = rows(m);
    const byIndex = new Map(rs.map((r) => [r.i, r.v]));
    const owner = app.w.raw.owner, n = owner.length;
    const values = new Array(n).fill(null);
    for (let c = 0; c < n; c++) if (owner[c] >= 0 && byIndex.has(owner[c])) values[c] = byIndex.get(owner[c]);
    const vals = rs.map((r) => r.v);
    const lo = Math.min(...vals), hi = Math.max(...vals);
    const log = lo > 0 && hi / lo > 50;
    const [format, unit] = LENS_FMT[m.id] || ["float", ""];
    mapLens = {
      id: `rank-${m.id}`, group: "rankings", name: `${m.label} by country`, icon: "l-people", unit,
      format, scale: log ? "log" : "linear", domain: [lo, hi === lo ? lo + 1 : hi],
      ramp: m.higher === true ? RAMP_GOOD : m.higher === false ? RAMP_BAD : RAMP_NEUTRAL, higher_is: m.higher === true ? "good" : m.higher === false ? "bad" : "neutral",
      source: "eurostat", description: `${m.note} Each country is coloured by its value.`, values,
    };
    app.setLens(mapLens);
    render();
  }

  // --- rendering ---------------------------------------------------------------------------------------------------
  function render() {
    if (!root) return;
    if (scope === "cities") return renderCities();
    const m = metric(metricId);
    const rs = rows(m);
    const max = Math.max(...rs.map((r) => Math.abs(r.v)), 1e-9);
    const sel = app.state.selectedState;
    const selIdx = sel == null ? -1 : typeof sel === "number" ? sel : worldStates().findIndex((s) => s.abbr === sel || s.fips === sel);
    const colour = (i) => css(app.w.stateColor?.[i] || [190, 190, 190]);
    const missing = states().length - rs.length;
    const lensOn = mapLens && app.state.lens === mapLens;
    root.innerHTML = `
      <header class="rk-head">
        <div class="rk-titles"><h2>Rankings</h2></div>
        ${scopeSwitch()}
        <button type="button" class="icon-btn rk-close" aria-label="Close the rankings (Esc)" title="Close (Esc)"><svg width="12" height="12" viewBox="0 0 24 24" aria-hidden="true"><path d="M5.5 5.5L18.5 18.5M18.5 5.5L5.5 18.5" fill="none" stroke="currentColor" stroke-width="3.2" stroke-linecap="round"/></svg></button>
      </header>
      <nav class="rk-domains" role="tablist" aria-label="Domains">${DOMAINS.map((d) => `<button type="button" role="tab" data-domain="${d.id}" aria-selected="${d.id === m.d}">${esc(d.label)}</button>`).join("")}</nav>
      <div class="rk-metrics">${METRICS.filter((x) => x.d === m.d).map((x) => `<button type="button" data-metric="${x.id}" aria-pressed="${x.id === m.id}">${esc(x.label)}</button>`).join("")}</div>
      ${selIdx >= 0 ? placings(m.d, selIdx) : ""}
      <div class="rk-bar">
        <p class="rk-note">${esc(m.note)}${wbNote(m)}${missing > 0 ? ` <span class="muted">${missing} countr${missing === 1 ? "y has" : "ies have"} no figure.</span>` : ""}</p>
        <button type="button" class="rk-colour${lensOn ? " on" : ""}" aria-pressed="${!!lensOn}">${lensOn ? "Map coloured" : "Colour the map"}</button>
      </div>
      <ol class="rk-table">${rs.map((r) => `
        <li><button type="button" class="rk-row${r.i === selIdx ? " sel" : ""}${r.rank <= 3 ? ` top top${r.rank}` : ""}" data-i="${r.i}">
          <span class="rk-rank">${r.rank}</span>
          <span class="rk-sw" style="background:${colour(r.i)}"></span>
          <span class="rk-name">${esc(r.s.name)}</span>
          <span class="rk-val">${esc(m.fmt(r.v))}</span>
          <span class="rk-meter"><i style="width:${Math.max(2, (Math.abs(r.v) / max) * 100).toFixed(1)}%"></i></span>
        </button></li>`).join("")}
      </ol>
      <p class="rk-foot muted">${states().length} countries: the EU, Iceland, Liechtenstein, Norway, Switzerland and the Western Balkans. Click a country to fly to it; the Almanac gives every source.</p>`;
  }

  // Countries whose figure for this metric comes from the World Bank (states.json `worldbank`: Eurostat has none).
  function wbNote(m) {
    if (!m.wb) return "";
    const names = states().filter((st) => st.worldbank?.includes(m.wb)).map((st) => st.name);
    return names.length ? ` ${names.join(", ")}: World Bank.` : "";
  }

  function scopeSwitch() {
    return `<div class="rk-scope" role="tablist" aria-label="Rank">${[["countries", `Countries`], ["cities", `Cities`]].map(([k, l]) =>
      `<button type="button" role="tab" data-scope="${k}" aria-selected="${scope === k}">${l}</button>`).join("")}</div>`;
  }

  function renderCities() {
    const m = cityMetric(cityMetricId);
    const rs = cityRows(m);
    const top = rs.slice(0, CITY_TOP);
    const max = Math.max(...top.map((r) => Math.abs(r.v)), 1e-9);
    const sel = app.state.selectedCity;
    const selRow = sel ? rs.find((r) => r.c === sel) : null;
    const name = (st) => worldStates().find((s) => s.abbr === st)?.name || st;
    const colour = (st) => {
      const i = worldStates().findIndex((s) => s.abbr === st);
      return css(app.w.stateColor?.[i] || [190, 190, 190]);
    };
    root.innerHTML = `
      <header class="rk-head">
        <div class="rk-titles"><h2>Rankings</h2></div>
        ${scopeSwitch()}
        <button type="button" class="icon-btn rk-close" aria-label="Close the rankings (Esc)" title="Close (Esc)"><svg width="12" height="12" viewBox="0 0 24 24" aria-hidden="true"><path d="M5.5 5.5L18.5 18.5M18.5 5.5L5.5 18.5" fill="none" stroke="currentColor" stroke-width="3.2" stroke-linecap="round"/></svg></button>
      </header>
      <div class="rk-metrics rk-city-metrics">${CITY_METRICS.map((x) => `<button type="button" data-cmetric="${x.id}" aria-pressed="${x.id === m.id}">${esc(x.label)}</button>`).join("")}</div>
      ${selRow ? `<section class="rk-placings"><h3>${esc(sel.name)} <span class="muted">is #${selRow.rank} of ${rs.length} for ${esc(m.label.toLowerCase())}: ${esc(m.fmt(selRow.v))}</span></h3></section>` : ""}
      <div class="rk-bar"><p class="rk-note">${esc(m.note)} <span class="muted">Top ${top.length} of ${rs.length} cities.</span></p></div>
      <ol class="rk-table">${top.map((r) => `
        <li><button type="button" class="rk-row${r.c === sel ? " sel" : ""}${r.rank <= 3 ? ` top top${r.rank}` : ""}" data-city="${esc(r.c.id)}">
          <span class="rk-rank">${r.rank}</span>
          <span class="rk-sw" style="background:${colour(r.c.states?.[0])}" title="${esc(name(r.c.states?.[0]))}"></span>
          <span class="rk-name">${esc(r.c.name)} <small class="muted">${esc(name(r.c.states?.[0]))}</small></span>
          <span class="rk-val"${approx(m, r.c) ? ` title="Estimated: Eurostat does not publish this for the city's regions, so it is shared out from a larger region"` : ""}>${approx(m, r.c) ? "≈ " : ""}${esc(m.fmt(r.v))}</span>
          <span class="rk-meter"><i style="width:${Math.max(2, (Math.abs(r.v) / max) * 100).toFixed(1)}%"></i></span>
        </button></li>`).join("")}
      </ol>
      <p class="rk-foot muted">≈ estimated from a larger region. Cities are Eurostat's functional urban areas (a core city and its commuting zone). Click one to fly to it.</p>`;
  }

  // The selected country's placings in the current domain, Civ-style: "rank 3 of 38".
  function placings(domain, i) {
    const s = states()[i];
    if (!s) return "";
    const items = METRICS.filter((x) => x.d === domain).map((x) => {
      const r = rankOf(x, i);
      const n = rows(x).length;
      return r ? `<button type="button" class="rk-place${r.rank <= 3 ? ` top${r.rank}` : ""}" data-metric="${x.id}" title="${esc(x.label)}: ${esc(x.fmt(r.v))}"><b>#${r.rank}</b><span>${esc(x.label)}</span><small>of ${n}</small></button>` : "";
    }).join("");
    return `<section class="rk-placings"><h3>${esc(s.name)} <span class="muted">in ${esc(DOMAINS.find((d) => d.id === domain)?.label || "")}</span></h3><div class="rk-places">${items}</div></section>`;
  }

  function wire(el) {
    el.addEventListener("click", (e) => {
      const t = e.target.closest("button");
      if (!t) return;
      if (t.classList.contains("rk-close")) return app.setMode(null);
      if (t.dataset.scope) {
        scope = t.dataset.scope;
        if (scope === "cities" && mapLens && app.state.lens === mapLens) { app.setLens(prevLens); mapLens = null; }
        render();
        return app.hash.update?.();
      }
      if (t.dataset.cmetric) { cityMetricId = cityMetric(t.dataset.cmetric).id; render(); return app.hash.update?.(); }
      if (t.dataset.city) {
        const c = (app.data.cities || []).find((x) => x.id === t.dataset.city);
        if (c) app.selectCity(c, { fly: true });
        return;
      }
      if (t.dataset.domain) return pick(METRICS.find((x) => x.d === t.dataset.domain)?.id);
      if (t.dataset.metric) return pick(t.dataset.metric);
      if (t.classList.contains("rk-colour")) {
        if (mapLens && app.state.lens === mapLens) { app.setLens(prevLens); mapLens = null; render(); } else colourMap();
        return;
      }
      if (t.dataset.i != null) {
        const i = +t.dataset.i;
        app.selectState(i, { fly: true });
      }
    });
    el.addEventListener("pointerover", (e) => {
      const t = e.target.closest(".rk-row");
      app.setHighlight(t && t.dataset.i != null ? { states: new Set([+t.dataset.i]) } : null);
    });
    el.addEventListener("pointerleave", () => app.setHighlight(null));
  }

  app.rankings = { metrics: METRICS, rows: (id) => rows(metric(id)), open: (id) => app.setMode("rankings", { metric: id || metricId }) };
}
