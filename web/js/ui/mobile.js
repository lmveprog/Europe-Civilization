// Phones and touch screens. The top bar on phones (css/style.css, max-width 700px) is two fixed
// rows instead of one sideways-scrolling strip: the map menu, a search button, Locate and a menu (the extension
// buttons, Share, Help, Almanac) on top, the national yields below. This wires what CSS cannot: the menu button and
// closing the menu, the search field's close button (the field opens over the first row while it has focus), the
// map menu, and on iOS, stopping Safari from zooming the page into a text field whose font is under 16 px.
import { icon } from "./icon.js";

const PHONE = "(max-width: 700px)";
const MENU_SVG = `<svg class="icon" width="18" height="18" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M4 6.5h16M4 12h16M4 17.5h16" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" fill="none"/></svg>`;
// The maps of the map menu: France and Europe.
const MAPS = [
  { id: "franceciv", label: "France", url: "https://mathieuastruc.com/franceciv/" },
  { id: "europeciv", label: "Europe", url: "https://mathieuastruc.com/europeciv/" },
];
const HERE = "europeciv";

export function initMobile({ app } = {}) {
  const phone = matchMedia(PHONE);
  preventIosInputZoom();
  const bar = document.getElementById("topbar");
  if (!bar) return;
  mapMenu(bar);

  // --- menu ------------------------------------------------------------------------------------------------------
  const menuBtn = document.getElementById("btn-menu");
  const menu = bar.querySelector(".tb-buttons");
  const help = document.getElementById("btn-help");
  if (help && !help.querySelector(".lbl")) help.insertAdjacentHTML("beforeend", `<span class="lbl lbl-menu">Help</span>`);
  if (menuBtn && menu) {
    menuBtn.innerHTML = MENU_SVG;
    const setOpen = (open) => {
      bar.classList.toggle("menu-open", open);
      menuBtn.setAttribute("aria-expanded", String(open));
    };
    menuBtn.addEventListener("click", () => setOpen(!bar.classList.contains("menu-open")));
    menu.addEventListener("click", (e) => { if (e.target.closest("button")) setOpen(false); });
    document.addEventListener("pointerdown", (e) => {
      if (bar.classList.contains("menu-open") && !e.target.closest(".tb-buttons, #btn-menu")) setOpen(false);
    }, true);
    document.addEventListener("keydown", (e) => {
      if (e.key !== "Escape" || !bar.classList.contains("menu-open")) return;
      e.stopPropagation();
      setOpen(false);
      menuBtn.focus();
    }, true);
    phone.addEventListener?.("change", () => setOpen(false));
  }

  // --- search ----------------------------------------------------------------------------------------------------
  const input = document.getElementById("search-input");
  const closeSearch = bar.querySelector(".search-close");
  if (input && closeSearch) {
    closeSearch.innerHTML = icon("close", null, { size: 12 });
    closeSearch.addEventListener("click", () => {
      if (input.value) {
        input.value = "";
        input.dispatchEvent(new Event("input"));
      }
      input.blur();
      closeSearch.blur();
    });
  }
  // The top bar changes height between one row and two: the map's visible area follows.
  phone.addEventListener?.("change", () => dispatchEvent(new Event("resize")));
  return app;
}

// The map menu: a <select> in the brand that names this map and opens the others.
function mapMenu(bar) {
  const brand = bar.querySelector(".brand");
  const text = brand?.querySelector(".brand-text");
  if (!brand || !text || brand.querySelector(".map-picker")) return;
  const sel = document.createElement("select");
  sel.className = "map-picker";
  sel.setAttribute("aria-label", "Switch map");
  sel.title = "Switch map";
  sel.innerHTML = MAPS.map((m) => `<option value="${m.id}"${m.id === HERE ? " selected" : ""}>${m.label}</option>`).join("");
  sel.addEventListener("change", () => {
    const m = MAPS.find((x) => x.id === sel.value);
    if (m && m.id !== HERE) location.href = m.url;
  });
  text.replaceWith(sel);
  // A <select> is as wide as its longest option: size it to the name it shows instead (a hidden copy measures it).
  const sizer = document.createElement("span");
  sizer.className = "brand-sizer";
  sizer.setAttribute("aria-hidden", "true");
  brand.appendChild(sizer);
  const fit = () => {
    sizer.textContent = sel.selectedOptions[0]?.textContent || "";
    const cs = getComputedStyle(sel);
    const pad = parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight) + parseFloat(cs.borderLeftWidth) * 2;
    sel.style.width = `${Math.ceil(sizer.getBoundingClientRect().width + pad + 2)}px`;
  };
  fit();
  addEventListener("resize", fit);
  document.fonts?.ready?.then(fit);
}

// Safari on iOS zooms the page into any focused text field or <select> whose font is under 16 px, and leaves it
// zoomed. maximum-scale=1 stops that; iOS still lets people pinch-zoom the page, so it is only added there.
export function preventIosInputZoom() {
  const ios = /iPhone|iPad|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  const meta = document.querySelector('meta[name="viewport"]');
  if (!ios || !meta || /maximum-scale/.test(meta.content)) return;
  meta.content += ", maximum-scale=1";
}
