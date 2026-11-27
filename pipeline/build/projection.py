"""projection.json: how the browser turns a longitude and latitude into map units, for "Locate me" (ext/locate).

The map's projection (core/geo.py MapProjection): spherical Lambert azimuthal equal-area centred at 52° N 10° E, km
scaled by `scale` from the corner (min_x, max_y) plus `margin`; points in an inset window go to their inset, a plain
lon/lat grid (`kx`, `ky` map units per degree from the window's north-west corner `ox`, `oy`)."""

from __future__ import annotations

from ..core.geo import INSET_PAD, R_EARTH_KM, Inset
from ..core.store import load_interim, write_web

REQUIRES = ["_world"]
PRODUCES = ["projection.json"]


def build() -> None:
    p = load_interim("_world")["projection"]
    insets = []
    for d in p.get("insets") or []:
        ins = Inset(d, p["scale"])
        insets.append({"name": d["name"], "lon": d["lon"], "lat": d["lat"], "ox": ins.ox, "oy": ins.oy,
                       "kx": round(ins.kx, 6), "ky": round(ins.ky, 6)})
    write_web("projection.json", {
        "kind": "laea", "lon0": 10.0, "lat0": 52.0, "radius_km": R_EARTH_KM,
        "min_x": p["min_x"], "max_y": p["max_y"], "margin": p["margin"], "scale": p["scale"],
        "inset_pad": INSET_PAD, "insets": insets,
    })
    print(f"    projection with {len(insets)} insets")
