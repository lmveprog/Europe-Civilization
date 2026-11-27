// Touch screens have no hover, so a tap on the map shows what the hover tooltip would (a tile's terrain, region, lens
// value and resources, or a map site) in a card just above whatever covers the bottom of the map (the lens dock and
// legend, or a bottom sheet), out from under the finger. main.js decides when a tap reads a tile instead of opening
// a region; the card can still open it, or the city, in one more tap.
import { esc } from "../format.js";
import { icon } from "./icon.js";

const CLOSE = "Close";
const MOUSE_HINT = /^Click to open\b/; // the tooltip's last line for a mouse; the card's button replaces it

export function createTapCard({ onHide } = {}) {
  const el = document.createElement("div");
  el.id = "tap-card";
  el.className = "panel tap-card";
  el.hidden = true;
  el.setAttribute("role", "status");
  el.setAttribute("aria-live", "polite");
  document.body.appendChild(el);
  let action = null;

  el.addEventListener("click", (e) => {
    if (e.target.closest(".tc-close")) hide();
    else if (e.target.closest(".tc-open")) {
      const run = action;
      hide();
      run?.();
    }
  });

  // The card sits just above whatever covers the bottom of the map: the lens area's stack or a bottom sheet.
  function place() {
    const H = window.innerHeight;
    let edge = H;
    const consider = (c, anchored) => {
      if (c.hidden) return;
      const r = c.getBoundingClientRect();
      if (r.height > 0 && (!anchored || r.bottom >= H - 14) && r.top < edge) edge = r.top;
    };
    for (const c of document.querySelectorAll("#lens-area > *")) consider(c, false);
    for (const c of document.querySelectorAll("#city-panel, .app-dock")) consider(c, true);
    el.style.bottom = `${Math.round(H - edge + 8)}px`;
  }

  /**
   * html: the hover tooltip's content (ui/tooltip.js or a map layer's tooltip()), lines separated by <br>.
   * open: {label, run} for the button that opens the region or city, or null. key: the start of the line to put
   * first and larger (the lens value), or null.
   */
  function show(html, { open = null, key = null } = {}) {
    action = open?.run || null;
    el.innerHTML = `<div class="tc-body">${html}</div>
      <button type="button" class="icon-btn tc-close" aria-label="${CLOSE}">${icon("close", null, { size: 12 })}</button>
      ${open ? `<button type="button" class="tc-open">${esc(open.label)}</button>` : ""}`;
    const body = el.querySelector(".tc-body");
    const lines = [[]];
    for (const n of [...body.childNodes]) {
      if (n.nodeName === "BR") lines.push([]);
      else lines.at(-1).push(n);
    }
    body.textContent = "";
    for (const nodes of lines) {
      const text = nodes.map((n) => n.textContent).join("").trim();
      if (!nodes.length || MOUSE_HINT.test(text)) continue;
      const line = document.createElement("div");
      line.className = "tc-line";
      line.append(...nodes);
      if (key && text.includes(key)) {
        line.classList.add("tc-key");
        body.prepend(line);
      } else body.append(line);
    }
    el.hidden = false;
    place();
  }

  function hide() {
    if (el.hidden) return;
    el.hidden = true;
    el.innerHTML = "";
    action = null;
    onHide?.();
  }

  addEventListener("resize", hide);
  return { show, hide, get shown() { return !el.hidden; } };
}
