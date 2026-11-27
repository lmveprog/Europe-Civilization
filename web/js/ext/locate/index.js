// Locate me: the visitor's position (browser geolocation; it never leaves the device) → the nearest municipality on
// the map, its card and a pin. A crosshair button beside the search box.
//   projection.json: the map's projection (pipeline/build/projection.py), loaded on the first click.
//   communes.json: the local units' centres in map units (x, y), loaded on the first click too.
const T = {
  label: "Locate me",
  title: "Locate me: open the card of the nearest place (your position stays on your device)",
  denied: "Location refused: allow it for this site in your browser",
  failed: "Could not find your position just now",
  outside: "You are off the map: the nearest place is ${km} km away",
  challenge: "Not during the daily challenge",
};
const MAX_KM = 30; // farther than this from every place centre: off the map
const SVG = `<svg class="icon" width="16" height="16" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><circle cx="12" cy="12" r="6.2" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="12" r="2.2" fill="currentColor"/><path d="M12 1.8v4M12 18.2v4M1.8 12h4M18.2 12h4" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>`;
const RAD = Math.PI / 180;

// lon/lat → map units, as core/geo.py MapProjection does (spherical; insets are plain lon/lat grids).
export function project(p, lon, lat) {
  for (const ins of p.insets || []) {
    if (lon >= ins.lon[0] && lon <= ins.lon[1] && lat >= ins.lat[0] && lat <= ins.lat[1]) {
      return [ins.ox + (lon - ins.lon[0]) * ins.kx, ins.oy + (ins.lat[1] - lat) * ins.ky];
    }
  }
  const R = p.radius_km;
  let X, Y;
  if (p.kind === "laea") {
    const lam = (lon - p.lon0) * RAD, phi = lat * RAD, s0 = Math.sin(p.lat0 * RAD), c0 = Math.cos(p.lat0 * RAD);
    const k = Math.sqrt(2 / Math.max(1e-12, 1 + s0 * Math.sin(phi) + c0 * Math.cos(phi) * Math.cos(lam)));
    X = R * k * Math.cos(phi) * Math.sin(lam);
    Y = R * k * (c0 * Math.sin(phi) - s0 * Math.cos(phi) * Math.cos(lam));
  } else { // albers
    const p1 = p.lat1 * RAD, p2 = p.lat2 * RAD, p0 = p.lat0 * RAD;
    const n = (Math.sin(p1) + Math.sin(p2)) / 2, c = Math.cos(p1) ** 2 + 2 * n * Math.sin(p1);
    const rho0 = (R * Math.sqrt(c - 2 * n * Math.sin(p0))) / n, rho = (R * Math.sqrt(c - 2 * n * Math.sin(lat * RAD))) / n;
    const th = n * (lon - p.lon0) * RAD;
    X = rho * Math.sin(th);
    Y = rho0 - rho * Math.cos(th);
  }
  return [(X - p.min_x) * p.scale + p.margin, (p.max_y - Y) * p.scale + p.margin];
}

// The communes.json row for map point (x, y), as an object, with its distance in map units. Rows are the local
// units' centres, so a large municipality's centre can be farther than a small neighbour's: each distance is divided
// by the unit's equal-area radius (area = population ÷ density, 1 km at least), and the smallest ratio wins.
export async function nearestPlace(app, x, y) {
  const d = await app.loadData("communes");
  if (!d?.rows?.length) return null;
  const col = (n) => d.columns.indexOf(n);
  const ix = col("x"), iy = col("y"), ipop = col("pop"), iden = col("density");
  const kmPerUnit = app.w?.raw?.km_per_unit || 1;
  let best = null, bs = Infinity, bd = 0;
  for (const r of d.rows) {
    const dist = Math.hypot(r[ix] - x, r[iy] - y);
    if (dist * kmPerUnit > 60) continue;
    const area = r[ipop] > 0 && r[iden] > 0 ? r[ipop] / r[iden] : 0;
    const s = dist / Math.max(Math.sqrt(area / Math.PI), 1) * kmPerUnit;
    if (s < bs) { bs = s; best = r; bd = dist; }
  }
  if (!best) { // off the map: the plain nearest, for the distance in the message
    for (const r of d.rows) {
      const dist = Math.hypot(r[ix] - x, r[iy] - y);
      if (!best || dist < bd) { best = r; bd = dist; }
    }
  }
  return best && { place: Object.fromEntries(d.columns.map((name, k) => [name, best[k]])), dist: bd };
}

export function install(app) {
  const search = document.querySelector("#topbar .search");
  if (!search || !("geolocation" in navigator)) return;
  document.getElementById("btn-locate")?.remove();
  const btn = document.createElement("button");
  btn.id = "btn-locate";
  btn.type = "button";
  btn.className = "btn btn-icon locate-btn";
  btn.title = T.title;
  btn.setAttribute("aria-label", T.label);
  btn.innerHTML = SVG;
  search.after(btn);
  const busy = (on) => { btn.classList.toggle("busy", on); btn.setAttribute("aria-busy", String(on)); };
  const kmPerUnit = () => app.w?.raw?.km_per_unit || 1;

  async function locate(lon, lat) {
    const p = await app.loadData("projection");
    if (!p) throw new Error("projection.json missing");
    const [x, y] = project(p, lon, lat);
    const hit = await nearestPlace(app, x, y);
    if (!hit) throw new Error("communes.json missing");
    const km = hit.dist * kmPerUnit();
    if (km > MAX_KM) return app.ui.toast(T.outside.replace("${km}", Math.round(km).toLocaleString()));
    if (app.mode) app.setMode(null);
    await app.showPlace(hit.place, { fly: true });
  }

  btn.addEventListener("click", () => {
    if (btn.classList.contains("busy")) return;
    if (app.mode === "challenge") return app.ui.toast(T.challenge);
    busy(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => locate(pos.coords.longitude, pos.coords.latitude)
        .catch((e) => { console.error("locate", e); app.ui.toast(T.failed); })
        .finally(() => busy(false)),
      (err) => { busy(false); app.ui.toast(err.code === 1 ? T.denied : T.failed); },
      { enableHighAccuracy: false, timeout: 15000, maximumAge: 600000 },
    );
  });
  app.locate = { project: (lon, lat) => app.loadData("projection").then((p) => project(p, lon, lat)), at: locate };
}
