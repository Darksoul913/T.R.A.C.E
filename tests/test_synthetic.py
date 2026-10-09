"""
Correctness check from the Ideation Baseline (§6): a synthetic pair with a known 100 x 100 px change
must give exactly one polygon whose area is 100·100·res² (±1%) with the right centroid.

    .venv/bin/python tests/test_synthetic.py
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import numpy as np
from rasterio.transform import from_origin
from rasterio.crs import CRS
from pyproj import Transformer

from src.geospatial.vectorizer import GeospatialVectorizer


def square_scene(transform, crs, res_m):
    prob = np.zeros((300, 300), np.float32)
    prob[100:200, 50:150] = 0.9
    gdf = GeospatialVectorizer().vectorize(prob, transform, crs)
    assert len(gdf) == 1, f"expected 1 polygon, got {len(gdf)}"
    r = gdf.iloc[0]
    expected = 100 * 100 * res_m ** 2
    assert abs(r.area_sqm - expected) / expected < 0.01, (r.area_sqm, expected)
    cx, cy = transform * (100, 150)                       # centre of cols 50-149, rows 100-199
    lon, lat = (cx, cy) if crs.is_geographic else Transformer.from_crs(crs, 4326, always_xy=True).transform(cx, cy)
    assert abs(r.centroid_lon - lon) < 1e-5 and abs(r.centroid_lat - lat) < 1e-5, (r.centroid_lon, lon, r.centroid_lat, lat)
    return r


def test_utm_10m():
    square_scene(from_origin(300000, 2110000, 10, 10), CRS.from_epsg(32643), 10)


def test_geographic():
    # ~10 m pixels near Mumbai in EPSG:4326; area must still come out right via local UTM
    dlon, dlat = 10 / (111320 * np.cos(np.radians(19.06))), 10 / 110574
    r = square_scene(from_origin(72.90, 19.10, dlon, dlat), CRS.from_epsg(4326), 10)
    assert abs(r.area_sqm - 1e6) / 1e6 < 0.01


def test_neighbours_keep_own_magnitude():
    # two polygons whose bounding boxes overlap must each report their own mean probability
    prob = np.zeros((200, 200), np.float32)
    prob[10:16, 10:100] = 0.95                             # L-shape whose bounding box ...
    prob[10:130, 94:100] = 0.95
    prob[30:110, 30:40] = 0.6                              # ... fully contains this separate bar
    gdf = GeospatialVectorizer().vectorize(prob, from_origin(300000, 2110000, 10, 10), CRS.from_epsg(32643))
    assert sorted(round(m, 2) for m in gdf.magnitude) == [0.6, 0.95], gdf.magnitude.tolist()


def test_resolution_aware_min_area():
    # min area is 4 px at any resolution: a 5x5 px blob is 6.25 m² at 0.5 m (the old fixed 25 m² floor dropped it)
    prob = np.zeros((100, 100), np.float32)
    prob[50:55, 50:55] = 0.9
    for res in (0.5, 10):
        assert len(GeospatialVectorizer().vectorize(prob, from_origin(300000, 2110000, res, res), CRS.from_epsg(32643))) == 1, res
    assert len(GeospatialVectorizer(min_area_px=30).vectorize(prob, from_origin(300000, 2110000, 0.5, 0.5), CRS.from_epsg(32643))) == 0


def test_jitter_sliver_dropped():
    prob = np.zeros((200, 200), np.float32)
    prob[100:102, 10:190] = 0.9                            # 2 px wide, 180 px long edge artefact
    prob[20:60, 20:60] = 0.9
    gdf = GeospatialVectorizer().vectorize(prob, from_origin(300000, 2110000, 10, 10), CRS.from_epsg(32643))
    assert len(gdf) == 1 and gdf.iloc[0].area_sqm > 150000, gdf[["area_sqm"]]


def test_recall_first_threshold_map():
    prob = np.zeros((100, 100), np.float32)
    prob[20:40, 20:40] = 0.4                               # weak signal
    tf, crs = from_origin(300000, 2110000, 10, 10), CRS.from_epsg(32643)
    assert len(GeospatialVectorizer().vectorize(prob, tf, crs)) == 0
    thr = np.full(prob.shape, 0.5, np.float32)
    thr[:50, :50] = 0.35                                   # protected zone: recall-first
    assert len(GeospatialVectorizer().vectorize(prob, tf, crs, threshold_map=thr)) == 1


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok ", name)
