// The Almanac: what every number means and exactly where it comes from.
import { resolveTables } from "../terrain.js";
import { esc, kmPerUnit } from "../format.js";
import { parseHex, luminance } from "../color.js";
import { icon, glyph } from "./icon.js";

const COVER_ICON = { forest_deciduous: "l-forest", forest_evergreen: "l-forest", forest_mixed: "l-forest", cropland: "l-farmland", pasture: "l-farmland", urban: "l-developed" };
// Glyph colour that reads on a resource medallion (dark on light faces such as nuclear yellow or silver).
const inkOn = (hex) => {
  try { return /^#[0-9a-f]{6}$/i.test(hex || "") && luminance(parseHex(hex)) > 0.4 ? "#1c1710" : "#f8f0d8"; } catch { return "#f8f0d8"; }
};
const CATEGORY = { energy: "Energy", mineral: "Minerals", agri: "Agriculture" };
// Page ids stay as they are (other modules open pages by id); LABEL is what the reader sees.
const LABEL = { States: "Countries" };
const enNum = (v) => (typeof v === "number" ? v.toLocaleString("en-GB") : String(v));

export function initPedia(data) {
  const modal = document.getElementById("pedia");
  const card = modal.querySelector(".modal-card");
  const nav = document.getElementById("pedia-nav");
  const body = document.getElementById("pedia-body");
  const srcName = (id) => data.sources?.find((s) => s.id === id)?.title || id || "";
  let restoreFocus = null;

  const h2 = (ic, fb, text) => `<h2>${icon(ic, fb, { size: 24 })}<span>${esc(text)}</span></h2>`;
  const insets = (data.world.insets || []).map((x) => x.name).filter(Boolean);

  const pages = {
    "About this map": () => `
      ${h2("pedia", null, "About this map")}
      <p>This is the real Europe, drawn like a strategy game: 38 countries, the 27 members of the European Union, Iceland,
      Liechtenstein, Norway, Switzerland, the six Western Balkan countries and the United Kingdom. Nothing is invented:
      every tile, city and number comes from public data, listed under <i>Sources</i>.</p>
      <h4>How it's built</h4>
      <p>Europe is projected (Lambert azimuthal equal-area, centred like EPSG:3035) and cut into ${data.world.grid.cols}×${data.world.grid.rows}
      hexes, each about ${enNum(Math.round(data.world.grid.radius * 2 * kmPerUnit(data.world) * 10) / 10)} km corner to corner. Each hex belongs to the
      country and the NUTS 3 region that cover most of its 7 sample points. Terrain comes from elevation samples inside each hex.
      ${insets.length ? `The EU's outermost regions (${esc(insets.join(", "))}) are drawn in insets on the open sea, each at its own scale.` : ""}</p>
      <p><b>Cities</b> are Eurostat's functional urban areas (Urban Audit 2021: a city and its commuting zone), named after
      and placed at their core city. Where the Urban Audit has none (the Western Balkans, Cyprus, Iceland, Liechtenstein),
      towns of 50,000+ people from GeoNames stand in. Their numbers cover the whole urban area, not just the core city.</p>
      <h4>Controls</h4>
      <p>Drag or arrow keys / WASD to pan · scroll, +/– or double-click to zoom · click a city or a country to open it ·
      / or ⌘K to search places, cities and countries · L to cycle lenses · R to show or hide resources · ? for all shortcuts · Esc to close.</p>
      <p>The address bar always holds a link to what you're looking at (lens, selection and view); use <i>Share</i> to copy it
      or to download a picture.</p>
      <p class="muted">A map by <a href="https://mathieuastruc.com/" target="_blank" rel="noopener">Mathieu Astruc</a>, based on <a href="https://karpathy.ai/usaciv/" target="_blank" rel="noopener">usaciv</a> by Andrej Karpathy, MIT licence.</p>`,
    Yields: () => `
      ${h2("y-production", null, "Yields")}
      <p>Civilization's yields mapped onto real measures. Job-based yields count the jobs in an industry where the work is
      done (Eurostat regional accounts, self-employed included). <b>Gold is GDP</b>: output per year in euros, counted where
      the work is done.</p>
      <table>${data.nation.yields.map((y) => `<tr><td class="ic" style="color:${esc(y.color)}">${glyph(y, 26)}</td><td><b style="color:${esc(y.color)}">${esc(y.label)}${y.key === "gold" ? " (GDP)" : ""}</b><br>${esc(y.description)}</td></tr>`).join("")}</table>
      <h4>Living standards</h4>
      <p>Unemployment = unemployed ÷ labour force aged 15–74 (Eurostat Labour Force Survey). Disposable income = net
      disposable income of private households per inhabitant, in purchasing power standards (PPS: euros at EU-average
      prices, so it compares across countries). At risk of poverty or social exclusion = share of
      people below 60% of their country's median income, severely deprived, or in a household with very low work intensity.
      Eurostat publishes these rates for NUTS 2 regions: a city shows the population-weighted mean of its regions'.</p>`,
    States: () => `
      ${h2("terrain", null, "Countries")}
      <p>Click any land hex without a city to open its country. A country's numbers are its own totals and rates from the
      same tables as the cities (${esc(data.nation.vintage)}${data.nation.gdp_vintage ? `; GDP: ${esc(data.nation.gdp_vintage)}` : ""}),
      not the sum of its cities, so rural areas count too.</p>
      <p><b>Ranks</b> ("#3 of 38") compare the mapped countries; 1 is the largest. The outermost regions drawn in insets count
      with their country (Portugal, Spain or France).</p>
      <p>Each urban area is listed under its country, with its whole-area numbers.</p>
      ${data.states ? "" : `<p class="muted">This data build has no states.json, so country panels show names and cities only.</p>`}`,
    Terrain: () => {
      const t = data.w?.tables || resolveTables(data.world.tables);
      const hasCover = Array.isArray(data.world.cover);
      const row = (x) => `<tr><td class="nm">${x.color ? `<span class="swatch" style="background:${esc(x.color)}"></span>` : ""}${
        COVER_ICON[x.key] ? icon(COVER_ICON[x.key], "", { size: 15 }) + " " : ""}<b>${esc(x.name)}</b></td><td>${esc(x.rule || "")}</td></tr>`;
      return `
      ${h2("terrain", null, "Terrain")}
      <p>Each hex averages the ETOPO1 elevation samples inside it. Relief comes from the mean elevation and roughness
      (standard deviation) of those samples; shading comes from elevation differences with neighbouring hexes, lit from the
      north-west.</p>
      <h4>${icon("l-forest", null, { size: 16 })} Land cover</h4>
      ${hasCover
        ? `<p>The base colour of each hex is its dominant land-cover group: the largest group among the land samples inside it
           (CORINE land-cover classes, OpenGeoHub). Small symbols show the mix: trees scale with the forest share, and fields,
           reeds, shrubs and grass tufts mark farmland, wetland, heath and scrub, and grassland.</p>
           <table>${t.cover.filter((x) => x.id > 0).map(row).join("")}</table>`
        : `<p class="muted">This data build has no land-cover layer yet; land is coloured by elevation.</p>`}
      <h4>Relief</h4>
      <table>${t.relief.map(row).join("")}</table>
      <h4>${icon("r-hydro", null, { size: 16 })} Water</h4>
      <table>${t.water.filter((x) => x.id > 0).map(row).join("")}</table>
      <h4>Beyond the borders</h4>
      <p class="muted">Neighbouring countries (Ukraine, Belarus, Moldova, Russia, Turkey, North Africa, and
      microstates such as Andorra, Monaco and San Marino) are drawn under a light fog: they are shown for context and not
      mapped in detail.</p>`;
    },
    Lenses: () => `
      ${h2("layers", null, "Lenses")}
      <p>Lenses recolour the map by one measure, built from regional statistics (${esc(data.lenses.vintage)}). Each hex is
      sampled at 7 points. A regional lens takes the mean of the values of the regions under those points (NUTS 3 figures,
      or NUTS 2 for the rates Eurostat publishes only for NUTS 2 regions), so a hex across a border blends both sides.
      Density spreads each municipality's 2021 census population over the hexes and divides by the hex's land area; land
      lenses come from the hex's land-cover samples.</p>
      <p>The legend shows how many hexes fall at each value. Hover or drag on it to show only that range on the map.</p>
      ${(data.lenses.groups || [{ id: null, name: "" }]).map((g) => {
        const ls = data.lenses.lenses.filter((l) => !g.id || l.group === g.id);
        if (!ls.length) return "";
        return `${g.name ? `<h3 class="grp">${icon(`g-${g.id}`, "", { size: 16 })} ${esc(g.name)}</h3>` : ""}${ls.map((l) => `
          <div class="lens-entry"><div class="le-ic">${glyph(l, 26)}</div><div>
          <h4>${esc(l.name)}</h4><p>${esc(l.description)}<br>
          <i class="le-ramp" style="background:linear-gradient(90deg, ${(l.ramp || []).map(esc).join(",")})"></i>
          <span class="muted">Scale: ${esc(l.scale)}, ${l.domain[0].toLocaleString("en-GB")}–${l.domain[1].toLocaleString("en-GB")} ${esc(l.unit)}${
            l.higher_is === "good" ? " · higher is better" : l.higher_is === "bad" ? " · higher is worse" : ""}${l.source ? " · " + esc(srcName(l.source)) : ""}</span></p></div></div>`).join("")}`;
      }).join("")}`,
    Resources: () => {
      const r = data.resources;
      if (!r?.types?.length) return `${h2("resources", null, "Resources")}<p class="muted">This data build has no resources layer.</p>`;
      const count = new Map();
      for (const it of r.items || []) count.set(it.type, (count.get(it.type) || 0) + 1);
      const cats = [...new Set(r.types.map((t) => t.category || "other"))];
      return `
      ${h2("resources", null, "Resources")}
      <p>Resources mark the biggest power plants, mines and fields on the tiles where they are.
      Only meaningful sites are shown: each type's threshold is in its description. When zoomed out, a hex shows its
      highest-ranked resource; zoom in to see more. Press <b>R</b> to show or hide them.</p>
      ${cats.map((c) => `<h4>${esc(CATEGORY[c] || c)}</h4><table class="res-table">
        <tr><th></th><th>Type</th><th>What counts</th><th>Sites</th></tr>
        ${r.types.filter((t) => (t.category || "other") === c).map((t) => `<tr>
          <td class="ic"><span class="res-ic" style="background:${esc(t.color || "#24384f")};color:${inkOn(t.color)}">${glyph(t, 20)}</span></td>
          <td class="nm"><b>${esc(t.name)}</b>${t.unit ? `<br><span class="muted">value in ${esc(t.unit)}</span>` : ""}</td>
          <td>${esc(t.description || "")}<br><span class="muted">Source: ${esc(srcName(t.source))}</span></td>
          <td class="num">${count.get(t.id) || 0}</td></tr>`).join("")}</table>`).join("")}`;
    },
    Sources: () => `
      ${h2("pedia", null, "Sources")}
      ${data.sources.map((s) => `
        <h4>${esc(s.title)}</h4>
        <p>${esc(s.description)}<br>
        <span class="muted">${esc(s.publisher)} · ${esc(s.license)}${s.vintage ? " · " + esc(s.vintage) : ""} ·
        <a href="${esc(s.homepage)}" target="_blank" rel="noopener">homepage</a></span></p>
        <table>${(s.files || []).map((f) => `<tr><td><code>${esc(f.url)}</code></td><td class="muted" style="white-space:nowrap">${esc((f.retrieved || "").slice(0, 10))}<br>${((f.bytes || 0) / 1e6).toFixed(1)} MB</td></tr>`).join("")}</table>`).join("")}`,
  };

  const show = (name) => {
    if (!pages[name]) name = "About this map";
    body.innerHTML = pages[name]();
    body.scrollTop = 0;
    nav.querySelectorAll("button").forEach((b) => {
      const on = b.dataset.page === name;
      b.classList.toggle("active", on);
      b.setAttribute("aria-current", on ? "page" : "false");
    });
  };
  nav.innerHTML = `<div class="hd">Almanac</div>` + Object.keys(pages).map((p) => `<button data-page="${esc(p)}">${esc(LABEL[p] || p)}</button>`).join("");
  nav.onclick = (e) => {
    const b = e.target.closest("button[data-page]");
    if (b) show(b.dataset.page);
  };
  const close = () => {
    if (modal.hidden) return;
    modal.hidden = true;
    if (restoreFocus && document.contains(restoreFocus)) restoreFocus.focus();
    restoreFocus = null;
  };
  modal.onclick = (e) => {
    if (e.target === modal || e.target.closest("[data-close]")) close();
  };
  // Keep Tab inside the dialog.
  modal.addEventListener("keydown", (e) => {
    if (e.key !== "Tab") return;
    const f = [...card.querySelectorAll("button, a[href], [tabindex]:not([tabindex='-1'])")].filter((x) => x.offsetParent);
    if (!f.length) return;
    const first = f[0], last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  });

  return {
    open(page = "About this map") {
      if (modal.hidden) restoreFocus = document.activeElement;
      show(page);
      modal.hidden = false;
      (nav.querySelector("button.active") || card.querySelector("[data-close]"))?.focus();
    },
    close,
    get isOpen() {
      return !modal.hidden;
    },
  };
}
