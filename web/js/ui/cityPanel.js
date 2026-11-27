import { css } from "../color.js";
import { esc } from "../format.js";
import { isCapital } from "../world.js";
import { icon } from "./icon.js";
import { yieldGrid, amenities, industries, gdpRow, popLine, growthSpan, showPanel, hidePanel } from "./infoPanel.js";

/**
 * ctx: {w, nation, onClose, onPedia, onState(stateIndex)}
 */
export function openCityPanel(city, ctx) {
  const { w, nation } = ctx;
  const n = nation.nation;
  const owner = city.cell != null ? w.raw.owner[city.cell] : -1;
  const col = css(w.stateColor[owner] || [190, 190, 190]);

  // The city's states as links to their state panels.
  const states = (city.states || [])
    .map((abbr) => ({ abbr, i: w.raw.states.findIndex((s) => s.abbr === abbr) }))
    .map(({ abbr, i }) => (i >= 0 && ctx.onState
      ? `<button class="chip" data-state="${i}" title="Open ${esc(w.raw.states[i].name)}">${esc(abbr)}</button>`
      : `<span class="chip">${esc(abbr)}</span>`))
    .join("");

  const growth = growthSpan(city, n);

  showPanel({
    kind: "city",
    stripe: col,
    title: city.name,
    titleHtml: `${isCapital(city) ? `<span class="cap">${icon("capital", null, { size: 13, title: "National capital" })}</span> ` : ""}${esc(city.name)}`,
    sub: `${esc(city.full || "")}${states ? `<div class="chips">${states}</div>` : ""}`,
    headExtra: popLine(city, growth),
    sections: [
      { title: "Yields of the urban area", html: `<div class="yield-grid">${yieldGrid(nation, city.yields)}</div>` },
      { title: "Living standards in the urban area", html: amenities(city, n) + gdpRow(city) },
      { title: "Districts · where the area works", html: industries(city, nation) },
    ],
    foot: `This panel describes the functional urban area (the core city and its commuting zone), except its first line:
      ${city.centre ? `the municipality of ${esc(city.centre)}, whose card the search opens` : "the core city"}.
      Source: ${esc(nation.vintage)}${nation.gdp_vintage ? `; GDP: ${esc(nation.gdp_vintage)}` : ""}.
      Green ×N = this industry's share of jobs is N× its share across Europe.`,
    onClose: ctx.onClose,
    onPedia: ctx.onPedia,
    wire(panel) {
      panel.querySelectorAll("[data-state]").forEach((b) => (b.onclick = () => ctx.onState(+b.dataset.state)));
    },
  });
}

export const closeCityPanel = hidePanel;
