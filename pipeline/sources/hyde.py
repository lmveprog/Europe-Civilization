"""Population through history from HYDE 3.2.1 (History Database of the Global Environment, Klein Goldewijk et al.,
Utrecht University and PBL): people per 5-arc-minute cell (about 9 × 6 km in Europe) from 10,000 BC to 2017, modelled
from historical population estimates spread over the land that could feed them, then over towns and countryside.

The data sits in one 5.3 GB zip on the DANS data station (CC0), its entries compressed with Deflate64, which Python's
zipfile cannot read. fetch() reads the zip's central directory by byte ranges, downloads only the population-count
grids (popc_<year>.asc, about 9 MB each) of the years in YEARS, wraps each in a one-entry zip and lets the system's
`unzip` (Info-ZIP, which reads Deflate64) inflate it. Only the cells inside the map's windows are kept, as float32, in
data/raw/hyde/popc_<year>.bin; process() gathers them into data/interim/hyde.bin.
"""

from __future__ import annotations

import json
import os
import shutil
import struct
import subprocess
import tempfile
import urllib.request
from array import array

from ..core.fetch import USER_AGENT, record
from ..core.paths import INTERIM
from ..core.source import Source, SourceInfo

DATAFILE = "https://archaeology.datastations.nl/api/access/datafile/5490328"  # HYDE3_2_1-baseline.zip
PAGE = "https://doi.org/10.17026/dans-25g-gez3"
# Negative = BC. Every millennium from 4000 BC, then the centuries, then the steps of the last two hundred years.
YEARS = [-4000, -3000, -2000, -1000, 0, 500, 1000, 1200, 1300, 1400, 1500, 1600, 1700, 1800, 1850, 1900, 1950, 2000,
         2017]
CELL = 1 / 12  # 5 arc minutes; the grids are 4320 × 2160 from 180° W, 90° N
RASTER = "hyde.bin"


def windows() -> list[tuple[float, float, float, float]]:
    """(west, south, east, north) of the map's main box and of each inset's window."""
    from ..core.europe import INSETS

    out = [(-32.0, 26.0, 46.0, 72.0)]
    for d in INSETS:
        (w, e), (s, n) = d["lon"], d["lat"]
        out.append((w - 0.2, s - 0.2, e + 0.2, n + 0.2))
    return out


def label(year: int) -> str:
    return f"{-year}BC" if year < 0 else f"{year}AD"


class _Ranges:
    def __init__(self, url: str):
        self.url = url

    def get(self, a: int, b: int) -> bytes:
        req = urllib.request.Request(self.url, headers={"Range": f"bytes={a}-{b - 1}", "User-Agent": USER_AGENT})
        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, timeout=300) as r:
                    data = r.read()
                if len(data) == b - a:
                    return data
            except OSError:
                if attempt == 3:
                    raise
        raise OSError(f"short read {a}-{b} from {self.url}")

    def size(self) -> int:
        req = urllib.request.Request(self.url, headers={"Range": "bytes=0-0", "User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=120) as r:
            return int(r.headers["Content-Range"].rsplit("/", 1)[1])


def central_directory(rd: _Ranges) -> dict[str, dict]:
    size = rd.size()
    tail = rd.get(size - 65536, size)
    i = tail.rfind(b"PK\x05\x06")
    cd_size, cd_off = struct.unpack("<II", tail[i + 12:i + 20])
    j = tail.rfind(b"PK\x06\x07")
    if j >= 0:  # ZIP64 end of central directory
        z64 = struct.unpack("<Q", tail[j + 8:j + 16])[0]
        cd_size, cd_off = struct.unpack("<QQ", rd.get(z64 + 40, z64 + 56))
    cd = rd.get(cd_off, cd_off + cd_size)
    out, p = {}, 0
    while cd[p:p + 4] == b"PK\x01\x02":
        method, mtime, mdate, crc, csize, usize, nlen, xlen, clen = struct.unpack("<HHHIIIHHH", cd[p + 10:p + 34])
        lho = struct.unpack("<I", cd[p + 42:p + 46])[0]
        name = cd[p + 46:p + 46 + nlen].decode("utf-8", "replace")
        extra, q = cd[p + 46 + nlen:p + 46 + nlen + xlen], 0
        while q + 4 <= len(extra):
            hid, hl = struct.unpack("<HH", extra[q:q + 4])
            if hid == 1:  # ZIP64 sizes and offset, in this order, only for the fields set to 0xFFFFFFFF
                vals, k = extra[q + 4:q + 4 + hl], 0
                if usize == 0xFFFFFFFF:
                    usize, k = struct.unpack("<Q", vals[k:k + 8])[0], k + 8
                if csize == 0xFFFFFFFF:
                    csize, k = struct.unpack("<Q", vals[k:k + 8])[0], k + 8
                if lho == 0xFFFFFFFF:
                    lho = struct.unpack("<Q", vals[k:k + 8])[0]
            q += 4 + hl
        out[name] = {"method": method, "time": mtime, "date": mdate, "crc": crc, "csize": csize, "usize": usize,
                     "lho": lho}
        p += 46 + nlen + xlen + clen
    return out


def one_entry_zip(rd: _Ranges, name: str, e: dict) -> bytes:
    """The entry's compressed bytes, rewrapped as a zip of its own (no data descriptor, no ZIP64 fields)."""
    head = rd.get(e["lho"], e["lho"] + 30)
    nlen, xlen = struct.unpack("<HH", head[26:30])
    start = e["lho"] + 30 + nlen + xlen
    data = rd.get(start, start + e["csize"])
    bname = name.rsplit("/", 1)[-1].encode()
    local = struct.pack("<IHHHHHIIIHH", 0x04034B50, 21, 0, e["method"], e["time"], e["date"], e["crc"], e["csize"],
                        e["usize"], len(bname), 0) + bname
    central = struct.pack("<IHHHHHHIIIHHHHHII", 0x02014B50, 21, 21, 0, e["method"], e["time"], e["date"], e["crc"],
                          e["csize"], e["usize"], len(bname), 0, 0, 0, 0, 0, 0) + bname
    cd_off = len(local) + len(data)
    end = struct.pack("<IHHHHIIH", 0x06054B50, 0, 0, 1, 1, len(central), cd_off, 0)
    return local + data + central + end


def crop(text_lines, wins) -> list[dict]:
    """Read an ESRI ASCII grid line by line and keep each window's cells (float32, rows north to south)."""
    header = {}
    for _ in range(6):
        k, v = next(text_lines).split()
        header[k.lower()] = float(v)
    ncols, nrows = int(header["ncols"]), int(header["nrows"])
    x0, ytop, size, nodata = header["xllcorner"], header["yllcorner"] + nrows * header["cellsize"], header["cellsize"], header["nodata_value"]
    spans = []
    for w, s, e, n in wins:
        c0, c1 = max(0, int((w - x0) / size)), min(ncols, int((e - x0) / size) + 1)
        r0, r1 = max(0, int((ytop - n) / size)), min(nrows, int((ytop - s) / size) + 1)
        spans.append({"c0": c0, "c1": c1, "r0": r0, "r1": r1, "values": array("f")})
    for r, line in enumerate(text_lines):
        hits = [sp for sp in spans if sp["r0"] <= r < sp["r1"]]
        if not hits:
            if r > max(sp["r1"] for sp in spans):
                break
            continue
        vals = line.split()
        for sp in hits:
            for v in vals[sp["c0"]:sp["c1"]]:
                x = float(v)
                sp["values"].append(x if x > 0 and x != nodata else 0.0)
    return spans


class Hyde(Source):
    info = SourceInfo(
        id="hyde",
        title="HYDE 3.2.1: population from 10,000 BC to 2017, 5 arc minutes (Utrecht University, PBL)",
        publisher="Kees Klein Goldewijk, Utrecht University and PBL Netherlands Environmental Assessment Agency "
        "(Klein Goldewijk, Beusen, Doelman and Stehfest, Earth System Science Data, 2017)",
        homepage=PAGE,
        license="CC0 1.0",
        description="People per 5-arc-minute cell (about 9 × 6 km in Europe) at dates from 10,000 BC to 2017: "
        "historical population estimates for each country, spread over the land that could feed them, then split "
        "between towns and countryside. Estimates, more uncertain the further back they go. Read from the "
        "population-count grids (popc) of the years shown, cropped to the map.",
        used_for=["Lens \"Population since 4000 BC\""],
    )

    def fetch(self, force=False):
        if not shutil.which("unzip"):
            raise RuntimeError("hyde needs the system unzip (Info-ZIP reads Deflate64; Python's zipfile does not)")
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        todo = [y for y in YEARS if force or not (self.raw_dir / f"popc_{label(y)}.bin").exists()]
        if not todo:
            return
        rd = _Ranges(DATAFILE)
        cd = central_directory(rd)
        wins = windows()
        for y in todo:
            name = f"baseline/asc/{label(y)}_pop/popc_{label(y)}.asc"
            e = cd[name]
            blob = one_entry_zip(rd, name, e)
            with tempfile.TemporaryDirectory() as tmp:
                zpath = os.path.join(tmp, "one.zip")
                with open(zpath, "wb") as f:
                    f.write(blob)
                proc = subprocess.run(["unzip", "-p", zpath], capture_output=True, check=True)
            spans = crop(iter(proc.stdout.decode("ascii").splitlines()), wins)
            out = self.raw_dir / f"popc_{label(y)}.bin"
            meta = []
            with open(out.with_suffix(".tmp"), "wb") as f:
                off = 0
                for sp in spans:
                    f.write(sp["values"].tobytes())
                    meta.append({k: sp[k] for k in ("c0", "c1", "r0", "r1")} | {"offset": off})
                    off += len(sp["values"])
            os.replace(out.with_suffix(".tmp"), out)
            (self.raw_dir / f"popc_{label(y)}.json").write_text(json.dumps({"year": y, "windows": meta}))
            total = sum(sum(sp["values"]) for sp in spans)
            print(f"    {label(y)}: {e['csize'] / 1e6:.1f} MB read, {total / 1e6:.1f} M people in the windows", flush=True)
            record(self.id, out.name, DATAFILE, f"{name} of HYDE3_2_1-baseline.zip, cropped to the map, float32")

    def process(self):
        tiles, offset, files = [], 0, []
        INTERIM.mkdir(parents=True, exist_ok=True)
        tmp = INTERIM / f".{RASTER}.{os.getpid()}.tmp"
        with open(tmp, "wb") as f:
            for y in YEARS:
                path = self.raw_dir / f"popc_{label(y)}.bin"
                meta = json.loads(path.with_suffix(".json").read_text())
                data = path.read_bytes()
                f.write(data)
                tiles.append({"year": y, "offset": offset, "windows": meta["windows"]})
                offset += len(data) // 4
                files.append(path.name)
        os.replace(tmp, INTERIM / RASTER)
        print(f"    {len(tiles)} years → data/interim/{RASTER} ({offset * 4 / 1e6:.0f} MB)")
        return {"vintage": "HYDE 3.2.1", "_files": files, "raster": RASTER, "cell_deg": CELL, "west": -180.0,
                "north": 90.0, "years": YEARS, "grids": tiles}
