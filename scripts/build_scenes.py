"""Runs the full ChangeIntel pipeline per sector and writes web/scenes.json for the console.

For each sector: BIT inference -> vectorize -> OSM exposure -> GIS/SitRep exports,
plus the naive NDVI baseline vectorized the same way and checked against a reference
(ground truth when the tile has a usable one, otherwise the ChangeIntel detections).

    .venv/bin/python scripts/build_scenes.py
"""
import base64
import io
import json
import pathlib
import sys

import numpy as np
import rasterio
from PIL import Image
from pyproj import Transformer
from rasterio.features import geometry_mask
from rasterio.warp import transform_bounds
from shapely.affinity import affine_transform

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.data.geotiff_processor import GeoTIFFProcessor
from src.exporters.gis_export import GISExporter
from src.exporters.sitrep_pdf import SitRepGenerator
from src.geospatial.osm_overlay import OSMExposureOverlay
from src.geospatial.vectorizer import GeospatialVectorizer
from src.models.infer import TiledInferenceEngine
from src.models.naive_baseline import NaiveBaselineComparator

OUT = ROOT / 'data/outputs'

# The only hand-written facts: what each tile is. Everything else is computed.
SECTORS = {
    'mumbai': {
        'label': 'Mumbai Coastal & Mithi Basin', 'place': 'Mumbai, Maharashtra',
        'sensor': 'Sentinel-2 MSI · 10 m', 'dates': ['20 Nov 2015', '12 Apr 2017'],
        'tile': 'data/geotiff/mumbai', 'out': 'mumbai_change_intelligence',
    },
    'levir': {
        'label': 'Texas Urban Tile · LEVIR-CD', 'place': 'Houston, Texas',
        'sensor': 'Aerial ortho · 0.5 m', 'dates': ['T1 · pre-build', 'T2 · post-build'],
        'tile': 'data/geotiff/levir_test_2_0000_0000', 'out': 'levir_sample_test2',
    },
}
NAIVE_THRESHOLD = 0.18     # same cutoff evaluate.py benchmarks the baseline with
MIN_OVERLAP = 0.2          # naive region is "confirmed" if >=20% of it lies on reference change


def jpeg_uri(bands):
    rgb = bands[:3].transpose(1, 2, 0) if bands.shape[0] == 3 and bands.dtype == np.uint8 \
        else GeoTIFFProcessor.to_uint8_rgb(GeoTIFFProcessor.percentile_stretch(bands[:3]))
    buf = io.BytesIO()
    Image.fromarray(rgb).save(buf, 'JPEG', quality=86)
    return 'data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode()


def run_sector(key, cfg, engine):
    tile = ROOT / cfg['tile']
    with rasterio.open(f'{tile}_t1_pre.tif') as s:
        t1, tf, crs, shape = s.read(), s.transform, s.crs, (s.height, s.width)
        bounds = transform_bounds(crs, 'EPSG:4326', *s.bounds)
    with rasterio.open(f'{tile}_t2_post.tif') as s:
        t2 = s.read()
    gt = None
    gt_path = pathlib.Path(f'{tile}_ground_truth.tif')
    if gt_path.exists():
        with rasterio.open(gt_path) as s:
            g = s.read(1) > 0
        gt = g if 0 < g.mean() < 1 else None   # an all-0 / all-1 mask carries no information

    # ChangeIntel: the same chain web/app.py runs
    prob = engine.run_inference(t1, t2, normalize_radiometry=True)
    ai = GeospatialVectorizer().vectorize(prob, tf, crs, t1, t2)
    ai = OSMExposureOverlay.enrich_with_exposure(ai.to_crs(4326)).to_crs(crs) if len(ai) else ai
    GISExporter.export_all(ai, cfg['out'], str(OUT))
    sitrep = OUT / f'sitrep_{key}.pdf'
    SitRepGenerator.generate_report(ai.to_crs(4326), scene_name=cfg['label'], sensor_name=cfg['sensor'], output_path=str(sitrep))

    # Naive baseline, vectorized identically, then judged against the reference
    _, naive_mask = NaiveBaselineComparator.compute_naive_change(t1, t2, threshold=NAIVE_THRESHOLD)
    naive = GeospatialVectorizer().vectorize(naive_mask.astype(np.float32), tf, crs, t1, t2)
    ref = gt if gt is not None else prob >= 0.5
    ref_name = 'ground truth' if gt is not None else 'ChangeIntel detections'

    # geometry (raster CRS) -> percent of tile, the frame the console draws in
    inv = ~tf
    h, w = shape
    to_pct = [inv.a * 100 / w, inv.b * 100 / w, inv.d * 100 / h, inv.e * 100 / h, inv.c * 100 / w, inv.f * 100 / h]
    to_ll = Transformer.from_crs(crs, 4326, always_xy=True).transform

    def pct_ring(geom, tol=0.0):
        g = affine_transform(geom, to_pct)
        g = g.simplify(tol) if tol else g
        poly = max(g.geoms, key=lambda p: p.area) if g.geom_type == 'MultiPolygon' else g
        return [[round(x, 2), round(y, 2)] for x, y in poly.exterior.coords]

    feats = []
    for _, r in ai.iterrows():
        geom = r.geometry
        poly = max(geom.geoms, key=lambda p: p.area) if geom.geom_type == 'MultiPolygon' else geom
        c = affine_transform(geom.centroid, to_pct)
        feats.append({
            'id': r.feature_id, 'tier': r.severity_tier, 'type': r.change_type, 'summary': r.summary,
            'area_sqm': float(r.area_sqm), 'magnitude': float(r.magnitude), 'score': float(r.composite_score),
            'priority': r.action_priority, 'lat': float(r.centroid_lat), 'lon': float(r.centroid_lon),
            'exposure': r.get('civic_exposure'), 'violation': r.get('encroachment_violation'),
            'cx': round(c.x, 2), 'cy': round(c.y, 2), 'pts': pct_ring(geom),
            'ring': [[round(la, 6), round(lo, 6)] for lo, la in (to_ll(x, y) for x, y in poly.exterior.coords)],
        })

    naive_out, confirmed = [], 0
    for _, r in naive.iterrows():
        inside = ~geometry_mask([r.geometry], out_shape=shape, transform=tf)
        overlap = float(ref[inside].mean()) if inside.any() else 0.0
        if overlap >= MIN_OVERLAP:
            confirmed += 1
            continue
        naive_out.append({'type': r.change_type, 'area_sqm': float(r.area_sqm), 'overlap': round(overlap, 3),
                          'pts': pct_ring(r.geometry, tol=0.15)})
    naive_out.sort(key=lambda f: -f['area_sqm'])
    for i, f in enumerate(naive_out, 1):
        f['id'] = f'NFA_{i:03d}'

    print(f'[{key}] {len(feats)} ChangeIntel polygons · naive {len(naive)} regions, '
          f'{len(naive_out)} false alarms vs {ref_name}')
    return {
        **{k: cfg[k] for k in ('label', 'place', 'sensor', 'dates')},
        'bounds': {'w': bounds[0], 's': bounds[1], 'e': bounds[2], 'n': bounds[3]},
        'size': [w, h],
        'images': {'t1': jpeg_uri(t1), 't2': jpeg_uri(t2)},
        'features': feats,
        'naive': {
            'threshold': NAIVE_THRESHOLD, 'reference': ref_name,
            'regions': int(len(naive)), 'area_sqm': float(naive.area_sqm.sum()) if len(naive) else 0.0,
            'confirmed': confirmed, 'false_alarms': naive_out,
        },
        'files': {'geojson': f"{cfg['out']}.geojson", 'gpkg': f"{cfg['out']}.gpkg", 'sitrep': sitrep.name},
    }


if __name__ == '__main__':
    engine = TiledInferenceEngine()
    scenes = {k: run_sector(k, cfg, engine) for k, cfg in SECTORS.items()}
    (ROOT / 'web/scenes.json').write_text(json.dumps(scenes, ensure_ascii=False))
    print('Wrote web/scenes.json')
