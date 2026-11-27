"""Population of Europe every five years since 1975 from the Global Human Settlement Layer (GHS-POP R2023A, European
Commission, Joint Research Centre): residents per 1 km cell, the census counts of each country spread over its built-up
areas as satellites saw them at each date.

The grid comes as 1000 km tiles (World Mollweide, ESRI:54009, 1 km cells, float64, LZW). fetch() downloads each tile
of each epoch that the map touches (its countries and the outermost regions' windows), sums its cells into 2 km blocks
and keeps them as zlib-compressed float32 in data/raw/ghsl_pop/E<year>_R<row>_C<col>.f32z (the 6 MB zips are not
kept). process() concatenates the blocks into data/interim/ghsl_pop.bin; the lens builder adds the blocks onto the hexes.
"""

from __future__ import annotations

import concurrent.futures
import io
import json
import math
import os
import urllib.error
import urllib.request
import zipfile
import zlib
from array import array

from ..core.cog import read_levels, tile_values
from ..core.fetch import USER_AGENT, record
from ..core.paths import INTERIM
from ..core.source import Source, SourceInfo

EPOCHS = list(range(1975, 2021, 5))  # 1975 … 2020: the epochs built from censuses (2025 and 2030 are projections)
URL = ("https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GHSL/GHS_POP_GLOBE_R2023A/GHS_POP_E{y}_GLOBE_R2023A_54009_1000/"
       "V1-0/tiles/GHS_POP_E{y}_GLOBE_R2023A_54009_1000_V1_0_R{r}_C{c}.zip")
PAGE = "https://human-settlement.emergency.copernicus.eu/ghs_pop2023.php"
X0, Y0, TILE_M, CELL_M = -18041000.0, 9000000.0, 1000000.0, 1000.0  # the tiling of the 1 km Mollweide grid
BLOCK = 2  # cells per block side: 2 km blocks
R_EARTH = 6378137.0
MAIN = ((-25.0, 45.0), (34.0, 71.5))  # lon, lat box of the main map; the insets add their own windows
RASTER = "ghsl_pop.bin"


def mollweide(lon: float, lat: float) -> tuple[float, float]:
    phi, lam = math.radians(lat), math.radians(lon)
    t = phi
    for _ in range(40):  # Newton on 2θ + sin 2θ = π sin φ
        d = 2 + 2 * math.cos(2 * t)
        if d < 1e-12:
            break
        step = (2 * t + math.sin(2 * t) - math.pi * math.sin(phi)) / d
        t -= step
        if abs(step) < 1e-12:
            break
    return 2 * math.sqrt(2) / math.pi * R_EARTH * lam * math.cos(t), math.sqrt(2) * R_EARTH * math.sin(t)


def mollweide_inverse(x: float, y: float) -> tuple[float, float]:
    t = math.asin(max(-1.0, min(1.0, y / (math.sqrt(2) * R_EARTH))))
    lat = math.asin(max(-1.0, min(1.0, (2 * t + math.sin(2 * t)) / math.pi)))
    lon = math.pi * x / (2 * math.sqrt(2) * R_EARTH * math.cos(t))
    return math.degrees(lon), math.degrees(lat)


def tile_of(x: float, y: float) -> tuple[int, int]:
    return int((Y0 - y) // TILE_M) + 1, int((x - X0) // TILE_M) + 1


def wanted_tiles() -> list[tuple[int, int]]:
    from ..core.europe import INSETS

    out = set()
    boxes = [MAIN] + [(tuple(d["lon"]), tuple(d["lat"])) for d in INSETS]
    for (lo0, lo1), (la0, la1) in boxes:
        n = max(20, int(max(lo1 - lo0, la1 - la0) * 10))
        for i in range(n + 1):
            for j in range(n + 1):
                out.add(tile_of(*mollweide(lo0 + (lo1 - lo0) * i / n, la0 + (la1 - la0) * j / n)))
    return sorted(out)


def _name(y: int, r: int, c: int) -> str:
    return f"E{y}_R{r}_C{c}.f32z"


def _one(job: tuple[str, int, int, int]) -> tuple[str, str]:
    """Download one tile of one epoch, sum it into 2 km blocks, write the compressed blocks. Runs in a worker process."""
    raw_dir, y, r, c = job
    path = os.path.join(raw_dir, _name(y, r, c))
    url = URL.format(y=y, r=r, c=c)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    blob = b""
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                blob = resp.read()
            break
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return _name(y, r, c), "missing"
            if attempt == 3:
                raise
        except OSError:
            if attempt == 3:
                raise
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        tif = z.read(next(n for n in z.namelist() if n.endswith(".tif")))
    lv = read_levels(lambda o, n: tif[o:o + n])[0]
    assert lv.scale[0] == CELL_M and lv.width == lv.height == 1000, (lv.scale, lv.width)
    side = lv.width // BLOCK
    out = array("f", bytes(4 * side * side))
    for k, (o, n) in enumerate(zip(lv.offsets, lv.counts)):
        if not n:
            continue
        vals = tile_values(lv, tif[o:o + n])
        tx, ty = (k % lv.tiles_across) * lv.tile_w, (k // lv.tiles_across) * lv.tile_h
        for rr in range(lv.tile_h):
            py = ty + rr
            if py >= lv.height:
                break
            row = (py // BLOCK) * side
            base = rr * lv.tile_w
            for cc in range(min(lv.tile_w, lv.width - tx)):
                v = vals[base + cc]
                if v > 0:
                    out[row + (tx + cc) // BLOCK] += v
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(zlib.compress(out.tobytes(), 6))
    os.replace(tmp, path)
    return _name(y, r, c), f"{sum(out) / 1e6:.1f} M people"


class GhslPop(Source):
    info = SourceInfo(
        id="ghsl_pop",
        title="GHS-POP R2023A: population grid 1975-2020, 1 km (European Commission, JRC)",
        publisher="European Commission, Joint Research Centre (Global Human Settlement Layer)",
        homepage=PAGE,
        license="CC BY 4.0",
        description="Residents per 1 km cell every five years from 1975 to 2020: each country's census counts, spread "
        "over the built-up areas the Landsat and Sentinel-2 archives show at each date (Schiavina, Freire, Carioli and "
        "MacManus, 2023). Read from the 1000 km Mollweide tiles that the map touches, summed into 2 km blocks.",
        used_for=["Lens \"Density since 1975\""],
    )

    def fetch(self, force=False):
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        missing_path = self.raw_dir / "missing.json"
        missing = set(json.loads(missing_path.read_text())) if missing_path.exists() and not force else set()
        tiles = wanted_tiles()
        jobs = [(str(self.raw_dir), y, r, c) for y in EPOCHS for r, c in tiles
                if _name(y, r, c) not in missing and (force or not (self.raw_dir / _name(y, r, c)).exists())]
        print(f"    {len(tiles)} tiles × {len(EPOCHS)} epochs; {len(jobs)} to fetch", flush=True)
        with concurrent.futures.ProcessPoolExecutor(max_workers=min(8, os.cpu_count() or 4)) as pool:
            for k, (name, what) in enumerate(pool.map(_one, jobs), 1):
                print(f"    {k}/{len(jobs)} {name}: {what}", flush=True)
                if what == "missing":
                    missing.add(name)
        missing_path.write_text(json.dumps(sorted(missing)))
        for y in EPOCHS:
            for r, c in tiles:
                if (self.raw_dir / _name(y, r, c)).exists():
                    record(self.id, _name(y, r, c), URL.format(y=y, r=r, c=c),
                           "the tile's 1 km cells summed into 2 km blocks, float32, zlib")

    def process(self):
        side = 1000 // BLOCK
        tiles, offset = [], 0
        INTERIM.mkdir(parents=True, exist_ok=True)
        tmp = INTERIM / f".{RASTER}.{os.getpid()}.tmp"
        files = []
        with open(tmp, "wb") as f:
            for r, c in wanted_tiles():
                blobs = {}
                for y in EPOCHS:
                    p = self.raw_dir / _name(y, r, c)
                    if p.exists():
                        blobs[y] = p.read_bytes()
                if not blobs:
                    continue
                parts = {}
                for y, b in blobs.items():
                    f.write(b)
                    parts[str(y)] = [offset, len(b)]
                    offset += len(b)
                    files.append(_name(y, r, c))
                tiles.append({"row": r, "col": c, "x0": X0 + (c - 1) * TILE_M, "y0": Y0 - (r - 1) * TILE_M,
                              "epochs": parts})
        os.replace(tmp, INTERIM / RASTER)
        print(f"    {len(tiles)} tiles, {len(files)} tile-epochs → data/interim/{RASTER} ({offset / 1e6:.0f} MB)")
        return {
            "vintage": "GHS-POP R2023A, 1975-2020",
            "_files": files,
            "raster": RASTER, "epochs": EPOCHS, "block_m": CELL_M * BLOCK, "side": side, "radius": R_EARTH,
            # each tile: its Mollweide corner (west, north, metres) and per epoch [offset, length] of its zlib blob of
            # side × side float32 block sums (people), rows north to south
            "tiles": tiles,
        }
