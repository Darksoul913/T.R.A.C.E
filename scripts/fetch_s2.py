"""Fetches Sentinel-2 L2A for the watch areas in data/watch_areas.json from Earth Search (public STAC, no key).

For each area it writes, on one 10 m UTM grid clipped to the bbox:
  - the change pair as {area}_t1_pre / _t2_post (display RGB, one stretch shared by both dates),
    {area}_t{1,2}_reflectance (B04 B03 B02 B08 B11 B12 x10000) and {area}_cloud_mask (SCL);
  - in data/raw/s2: a dry-season time series {area}_series_{year}_reflectance / _scl, indexed in
    {area}_series.json, and a seasonal no-change pair {area}_seasonal_* (post-monsoon vs dry season).

    .venv/bin/python scripts/fetch_s2.py [area ...]
"""
import json
import pathlib
import sys

import numpy as np
import rasterio
import requests
from rasterio.crs import CRS
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject, transform_bounds

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src.data.geotiff_processor import GeoTIFFProcessor

SCL_UNOBSERVABLE = GeoTIFFProcessor.SCL_UNOBSERVABLE

STAC = "https://earth-search.aws.element84.com/v1/search"
BANDS = ["red", "green", "blue", "nir", "swir16", "swir22"]     # = B04 B03 B02 B08 B11 B12, the reflectance order
OUT = ROOT / "data/geotiff"          # the change pair, read by build_scenes.py like any other sector
RAW = ROOT / "data/raw/s2"           # series + seasonal pair: analysis inputs only (git-ignored, ~30 MB)
RES = 10.0


def search(bbox, start, end, max_cloud, mgrs=None):
    body = {"collections": ["sentinel-2-l2a"], "bbox": bbox, "limit": 100,
            "datetime": f"{start}T00:00:00Z/{end}T23:59:59Z", "query": {"eo:cloud_cover": {"lt": max_cloud}}}
    items = requests.post(STAC, json=body, timeout=60).json().get("features", [])
    items = [i for i in items if not mgrs or i["properties"].get("grid:code") == mgrs]
    # least cloud first; for the same date prefer the newest processing baseline (consistent radiometry)
    return sorted(items, key=lambda i: (i["properties"]["eo:cloud_cover"], -float(i["properties"].get("s2:processing_baseline", 0))))


def grid(bbox):
    """10 m UTM grid covering bbox [w, s, e, n]."""
    crs = CRS.from_epsg(32600 + int((bbox[0] + bbox[2]) / 2 + 180) // 6 + 1)
    w, s, e, n = transform_bounds("EPSG:4326", crs, *bbox)
    width, height = int(np.ceil((e - w) / RES)), int(np.ceil((n - s) / RES))
    return from_origin(w, n, RES, RES), crs, (height, width)


def read_asset(href, tf, crs, shape, resampling):
    out = np.zeros(shape, np.float32)
    with rasterio.open(href) as src:
        reproject(rasterio.band(src, 1), out, dst_transform=tf, dst_crs=crs, resampling=resampling, src_nodata=0, dst_nodata=0)
    return out


def boa_offset(item):
    """Reflectance offset still present in the item's DNs. L2A processing baseline >= 04.00 adds +1000 DN
    (offset -0.1), but Earth Search has already removed it from items flagged earthsearch:boa_offset_applied,
    even though their raster:bands still list -0.1, so applying it again would zero the visible bands."""
    p = item["properties"]
    if p.get("earthsearch:boa_offset_applied"):
        return 0.0
    return -0.1 if float(p.get("s2:processing_baseline", 0)) >= 4.0 else 0.0


def read_item(item, tf, crs, shape):
    """(6, H, W) uint16 reflectance x10000 (0 = nodata) and (H, W) SCL."""
    bands, offset = [], boa_offset(item)
    for b in BANDS:
        a = item["assets"][b]
        rb = (a.get("raster:bands") or [{}])[0]
        dn = read_asset(a["href"], tf, crs, shape, Resampling.bilinear)
        refl = dn * rb.get("scale", 1e-4) + offset
        bands.append(np.where(dn > 0, np.clip(refl * 10000, 1, 65535), 0).astype(np.uint16))
    scl = read_asset(item["assets"]["scl"]["href"], tf, crs, shape, Resampling.nearest).astype(np.uint8)
    return np.stack(bands), scl


def write(path, arr, tf, crs):
    GeoTIFFProcessor.write_geotiff(str(path), arr if arr.ndim == 3 else arr[None], tf, crs)


def best(cfg, start, end):
    items = search(cfg["bbox"], start, end, cfg["max_cloud"], cfg.get("mgrs"))
    if not items:
        raise SystemExit(f"no Sentinel-2 L2A scene under {cfg['max_cloud']}% cloud for {start}..{end}")
    return items[0]


def fetch_pair(area, cfg, windows, prefix, tf, crs, shape, out=OUT):
    stacks, meta = [], []
    for tag, (start, end) in zip(("t1", "t2"), windows):
        item = best(cfg, start, end)
        refl, scl = read_item(item, tf, crs, shape)
        write(out / f"{prefix}_{tag}_reflectance.tif", refl, tf, crs)
        write(out / f"{prefix}_{tag}_scl.tif", scl, tf, crs)
        stacks.append((refl, scl))
        meta.append({"id": item["id"], "date": item["properties"]["datetime"][:10],
                     "cloud": item["properties"]["eo:cloud_cover"]})
        print(f"  {prefix} {tag}: {item['id']} ({item['properties']['eo:cloud_cover']:.2f}% cloud)")
    # display RGB with ONE stretch for both dates, so brightness differences stay real
    rgb = np.concatenate([s[0][:3].astype(np.float32) for s in stacks], axis=2)
    disp = (GeoTIFFProcessor.percentile_stretch(rgb) * 255).astype(np.uint8)
    w = shape[1]
    write(out / f"{prefix}_t1_pre.tif", disp[:, :, :w], tf, crs)
    write(out / f"{prefix}_t2_post.tif", disp[:, :, w:], tf, crs)
    unobs = np.isin(stacks[0][1], SCL_UNOBSERVABLE) | np.isin(stacks[1][1], SCL_UNOBSERVABLE)
    write(out / f"{prefix}_cloud_mask.tif", unobs.astype(np.uint8), tf, crs)
    print(f"  {prefix}: {unobs.mean():.2%} unobservable per SCL")
    return meta


def fetch_series(area, cfg, tf, crs, shape):
    s = cfg["series"]
    index = []
    for year in s["years"]:
        m0, m1 = s["months"]
        try:
            item = best(cfg, f"{year}-{m0:02d}-01", f"{year}-{m1:02d}-28")
        except SystemExit as e:
            print(f"  series {year}: skipped ({e})")
            continue
        refl, scl = read_item(item, tf, crs, shape)
        write(RAW / f"{area}_series_{year}_reflectance.tif", refl, tf, crs)
        write(RAW / f"{area}_series_{year}_scl.tif", scl, tf, crs)
        index.append({"year": year, "id": item["id"], "date": item["properties"]["datetime"][:10],
                      "cloud": item["properties"]["eo:cloud_cover"]})
        print(f"  series {year}: {item['id']}")
    (RAW / f"{area}_series.json").write_text(json.dumps(index, indent=1))
    return index


def main(names):
    RAW.mkdir(parents=True, exist_ok=True)
    areas = json.loads((ROOT / "data/watch_areas.json").read_text())
    for area in names or areas:
        cfg = areas[area]
        tf, crs, shape = grid(cfg["bbox"])
        print(f"[{area}] {shape[1]}x{shape[0]} px at {RES:.0f} m, {crs}")
        meta = {"pair": fetch_pair(area, cfg, cfg["pair"], area, tf, crs, shape)}
        if "seasonal_pair" in cfg:
            meta["seasonal_pair"] = fetch_pair(area, cfg, cfg["seasonal_pair"], f"{area}_seasonal", tf, crs, shape, RAW)
        if "series" in cfg:
            meta["series"] = fetch_series(area, cfg, tf, crs, shape)
        (OUT / f"{area}_meta.json").write_text(json.dumps(meta, indent=1))


if __name__ == "__main__":
    assert boa_offset({"properties": {"earthsearch:boa_offset_applied": True, "s2:processing_baseline": "05.11"}}) == 0.0
    assert boa_offset({"properties": {"earthsearch:boa_offset_applied": False, "s2:processing_baseline": "05.11"}}) == -0.1
    assert boa_offset({"properties": {"s2:processing_baseline": "02.11"}}) == 0.0
    main(sys.argv[1:])
