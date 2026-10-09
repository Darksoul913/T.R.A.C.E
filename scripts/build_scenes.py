"""Runs the full ChangeIntel pipeline per sector and writes web/scenes.json for the console.

For each sector: harmonise -> BIT inference (recall-first inside protected / water buffers) ->
vectorize -> OSM exposure -> GIS/SitRep exports; the unobservable (cloud / no data) layer; the naive
NDVI baseline vectorized the same way and checked against a reference (ground truth when the tile has
a usable one, otherwise the ChangeIntel detections); and, for sectors with a yearly Sentinel-2 series,
slow-creep and precursor detection.

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
import geopandas as gpd
import pandas as pd
from rasterio.features import geometry_mask, rasterize, shapes
from shapely.geometry import shape as to_geom
from rasterio.warp import transform_bounds
from shapely.affinity import affine_transform

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.data.geotiff_processor import GeoTIFFProcessor
from src.exporters.gis_export import GISExporter
from src.exporters.sitrep_pdf import SitRepGenerator
from src.geospatial.osm_overlay import OSMExposureOverlay
from src.geospatial.vectorizer import GeospatialVectorizer
from src.data.harmonise import align, apply_shift, correct_shift
from src.geospatial import creep as creep_mod
from src.geospatial.severity import MODES, PRIORITY, TYPE_WEIGHTS, SeverityScorer
from src.models.infer import DEFAULT_NORMALISATION, TiledInferenceEngine
from src.models.naive_baseline import NaiveBaselineComparator

OUT = ROOT / 'data/outputs'

# The only hand-written facts: what each tile is. Everything else is computed.
SECTORS = {
    'mumbai': {
        'label': 'Mumbai Eastern Suburbs · Chembur–Ghatkopar', 'place': 'Mumbai, Maharashtra', 'nav': 'Mumbai 2015–18',
        'sensor': 'Sentinel-2 MSI · 10 m', 'dates': ['30 Nov 2015', '19 Mar 2018'],
        'tile': 'data/geotiff/mumbai', 'out': 'mumbai_change_intelligence',
        # Geofabrik extract (data/raw is git-ignored); only needed to (re)build data/osm/mumbai.geojson
        'osm_pbf': 'data/raw/osm/western-zone-latest.osm.pbf',
        'default_mode': 'encroachment',   # years ΔT: planning / encroachment audit
    },
    'levir': {
        'label': 'Texas Urban Tile · LEVIR-CD', 'place': 'Houston, Texas',
        'sensor': 'Aerial ortho · 0.5 m', 'dates': ['T1 · pre-build', 'T2 · post-build'],
        'tile': 'data/geotiff/levir_test_2_0000_0000', 'out': 'levir_sample_test2',
        # LEVIR-CD ships without coordinates; dataset_builder places it at an example UTM origin
        'georeferenced': False,
        'default_mode': 'encroachment',
    },
    # Sentinel-2 L2A via scripts/fetch_s2.py (data/watch_areas.json): real SCL cloud mask + 2017-2025 series
    'mumbai_s2': {
        'label': 'Mumbai Eastern Suburbs · 2019 → 2025', 'place': 'Mumbai, Maharashtra', 'nav': 'Mumbai 2019–25',
        'sensor': 'Sentinel-2 L2A · 10 m', 'dates': None,          # read from data/geotiff/mumbai_s2_meta.json
        'tile': 'data/geotiff/mumbai_s2', 'out': 'mumbai_s2_change_intelligence',
        'osm_key': 'mumbai', 'osm_pbf': 'data/raw/osm/western-zone-latest.osm.pbf',
        'default_mode': 'encroachment', 'series': 'data/raw/s2/mumbai_s2',
    },
}
# The other OSCD cities (scripts/build_data.py writes their tiles); dates come from each city's dates.txt.
# No local OSM extract for these, so exposure falls back to Overpass (or "Not assessed" offline).
OSCD_IMAGES = ROOT / 'Onera Satellite Change Detection/images/Onera Satellite Change Detection dataset - Images'
OSCD_PLACES = {
    'abudhabi': 'Abu Dhabi, UAE', 'aguasclaras': 'Águas Claras, Brazil', 'beihai': 'Beihai, China',
    'beirut': 'Beirut, Lebanon', 'bercy': 'Bercy, Paris, France', 'bordeaux': 'Bordeaux, France',
    'brasilia': 'Brasília, Brazil', 'chongqing': 'Chongqing, China', 'cupertino': 'Cupertino, California',
    'dubai': 'Dubai, UAE', 'hongkong': 'Hong Kong', 'lasvegas': 'Las Vegas, Nevada', 'milano': 'Milan, Italy',
    'montpellier': 'Montpellier, France', 'nantes': 'Nantes, France', 'norcia': 'Norcia, Italy',
    'paris': 'Paris, France', 'pisa': 'Pisa, Italy', 'rennes': 'Rennes, France', 'rio': 'Rio de Janeiro, Brazil',
    'saclay_e': 'Saclay East, France', 'saclay_w': 'Saclay West, France', 'valencia': 'Valencia, Spain',
}
for _city, _place in OSCD_PLACES.items():
    if not (ROOT / f'data/geotiff/{_city}_t1_pre.tif').exists():
        continue   # not built yet: run scripts/build_data.py
    _d = dict(l.split(': ') for l in (OSCD_IMAGES / _city / 'dates.txt').read_text().split('\n') if ': ' in l)
    _dates = [pd.Timestamp(_d[k]).strftime('%-d %b %Y') for k in ('date_1', 'date_2')]
    SECTORS[_city] = {
        'label': f"{_place.split(',')[0]} · OSCD", 'place': _place,
        'nav': f"{_place.split(',')[0]} {_dates[0][-4:]}–{_dates[1][-2:]}",
        'sensor': 'Sentinel-2 MSI · 10 m', 'dates': _dates,
        'tile': f'data/geotiff/{_city}', 'out': f'{_city}_change_intelligence',
        'default_mode': 'encroachment',
    }
RECALL_FIRST_THRESHOLD = 0.35   # model probability needed inside protected / water buffers (0.5 elsewhere)
WATER_BUFFER_M = 50.0
NAIVE_THRESHOLD = 0.18     # same cutoff evaluate.py benchmarks the baseline with
MIN_OVERLAP = 0.2          # naive region is "confirmed" if >=20% of it lies on reference change


def jpeg_uri(bands):
    rgb = bands[:3].transpose(1, 2, 0) if bands.shape[0] == 3 and bands.dtype == np.uint8 \
        else GeoTIFFProcessor.to_uint8_rgb(GeoTIFFProcessor.percentile_stretch(bands[:3]))
    buf = io.BytesIO()
    Image.fromarray(rgb).save(buf, 'JPEG', quality=86)
    return 'data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode()


def unobservable_polygons(mask, tf, crs):
    """Cloud / shadow / nodata mask -> polygons with UTM area, in the raster CRS."""
    polys = [to_geom(g) for g, v in shapes(mask.astype(np.uint8), mask=mask, transform=tf) if v == 1]
    gdf = gpd.GeoDataFrame({'reason': ['cloud, shadow or no data'] * len(polys)}, geometry=polys, crs=crs)
    if len(gdf):
        gdf['area_sqm'] = gdf.to_crs(gdf.estimate_utm_crs()).area.round(1)
    return gdf


def recall_first_mask(bbox, tf, crs, shape_hw):
    """Protected land (parks, forests, ...) plus a WATER_BUFFER_M buffer around tidal water, mangroves, wetlands
    and lakes, rasterized to the tile. Ordinary nalas / drains are left out: in a city they would cover half the
    tile, which is no longer a protected zone but a lower threshold everywhere."""
    osm = OSMExposureOverlay.fetch_osm_features(list(bbox))
    if osm is None or not len(osm):
        return None
    utm = osm.estimate_utm_crs()
    zones = pd.concat([osm[osm.kind == 'protected'].to_crs(utm).geometry,
                       osm[(osm.kind == 'water') & osm.cls.isin(['tidal', 'wetland', 'waterbody'])].to_crs(utm).geometry.buffer(WATER_BUFFER_M)])
    zones = gpd.GeoSeries(zones, crs=utm).to_crs(crs)
    return rasterize(((g, 1) for g in zones if not g.is_empty), out_shape=shape_hw, transform=tf, dtype='uint8').astype(bool)


def sector_dates(cfg, tile):
    if cfg['dates']:
        return cfg['dates']
    meta = json.loads(pathlib.Path(f'{tile}_meta.json').read_text())['pair']
    fmt = lambda d: pd.Timestamp(d).strftime('%-d %b %Y')
    return [fmt(m['date']) for m in meta]


def creep_layer(cfg, tf, crs, protected, mode):
    """Slow creep + precursors over the sector's yearly series (src/geospatial/creep.py), as a GeoDataFrame
    shaped like the vectorizer's output, plus the years and per-polygon NDBI series."""
    base = ROOT / cfg['series']
    index = json.loads(pathlib.Path(f'{base}_series.json').read_text())
    refl, valid = [], []
    for e in index:
        with rasterio.open(f"{base}_series_{e['year']}_reflectance.tif") as s:
            refl.append(s.read())
        with rasterio.open(f"{base}_series_{e['year']}_scl.tif") as s:
            valid.append(~np.isin(s.read(1), GeoTIFFProcessor.SCL_UNOBSERVABLE))
    out = creep_mod.detect(np.stack(refl), np.stack(valid), protected)
    kinds = {'creep': ('Slow Built-up Creep', 'Built-up index rose steadily over {n} years (+{rise:.2f} trend) '
                                              'without any single year crossing the pairwise threshold.'),
             'cleared': ('Precursor: Cleared Plot', 'Vegetation cleared since {y0} with a small built-up rise: '
                                                     'a typical first step before construction.'),
             'track': ('Precursor: New Track', 'Thin cleared strip since {y0}: possible new access track.')}
    frames = []
    for k, (ctype, text) in kinds.items():
        g = GeospatialVectorizer().vectorize(out[k].astype(np.float32), tf, crs, mode=mode)
        if not len(g):
            continue
        g['change_type'], g['kind'] = ctype, k
        series = []
        for geom in g.geometry:
            m = ~geometry_mask([geom], out_shape=out[k].shape, transform=tf)
            series.append([round(float(v[m].mean()), 3) for v in out['ndbi']])
        g['ndbi_series'] = series
        g['summary'] = [text.format(n=len(index) - 1, rise=s[-1] - s[0], y0=index[0]['year']) for s in series]
        # magnitude = trend strength: a +0.2 NDBI rise over the series counts as full strength
        g['magnitude'] = [round(float(np.clip((s[-1] - s[0]) / 0.2, 0.5, 1.0)), 3) for s in series]
        for i, r in g.iterrows():
            sev = SeverityScorer.compute_all_modes(r.area_sqm, r.magnitude, ctype, pixel_area_sqm=r.pixel_area_sqm, primary_mode=mode)
            for c, v in sev.items():
                g.at[i, c] = v
        frames.append(g)
    gdf = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=crs) if frames else None
    if gdf is not None:
        gdf['feature_id'] = [f'CRP_{i:03d}' for i in range(1, len(gdf) + 1)]
    return gdf, [e['year'] for e in index]


def run_sector(key, cfg, engine):
    tile = ROOT / cfg['tile']
    with rasterio.open(f'{tile}_t1_pre.tif') as s:
        t1, tf, crs, shape = s.read(), s.transform, s.crs, (s.height, s.width)
        bounds = transform_bounds(crs, 'EPSG:4326', *s.bounds)
    with rasterio.open(f'{tile}_t2_post.tif') as s:
        t2, meta2 = s.read(), {'transform': s.transform, 'crs': s.crs}
    gt = None
    gt_path = pathlib.Path(f'{tile}_ground_truth.tif')
    if gt_path.exists():
        with rasterio.open(gt_path) as s:
            g = s.read(1) > 0
        gt = g if 0 < g.mean() < 1 else None   # an all-0 / all-1 mask carries no information

    # Harmonise: T2 onto T1's grid, then register T1 onto T2 (outputs stay in the post-event frame);
    # the same shift goes to the reflectance stack
    meta1 = {'transform': tf, 'crs': crs}
    t2, aligned = align(t1, t2, meta1, meta2)
    refl = GeoTIFFProcessor.load_reflectance(str(tile))
    t1, shift = correct_shift(t2, t1)
    s1, s2 = (apply_shift(refl[0], shift), align(refl[0], refl[1], meta1, meta2)[0]) if refl else (t1, t2)

    georef = cfg.get('georeferenced', True)
    mode = cfg.get('default_mode', 'encroachment')
    osm_key = cfg.get('osm_key', key)
    snap = ROOT / f'data/osm/{osm_key}.geojson'
    if cfg.get('osm_pbf') and not snap.exists() and (ROOT / cfg['osm_pbf']).exists():
        pad = 0.01  # ~1 km, so assets just outside the tile still count
        OSMExposureOverlay.build_snapshot(str(ROOT / cfg['osm_pbf']),
                                          [bounds[0] - pad, bounds[1] - pad, bounds[2] + pad, bounds[3] + pad], str(snap))
    places_path = ROOT / f'data/osm/{osm_key}_places.json'
    if cfg.get('osm_pbf') and not places_path.exists() and (ROOT / cfg['osm_pbf']).exists():
        OSMExposureOverlay.build_gazetteer(str(ROOT / cfg['osm_pbf']), list(bounds), str(places_path))
    places = json.loads(places_path.read_text()) if places_path.exists() else []
    # recall-first: a lower detection threshold inside protected land and water buffers
    protected = recall_first_mask(bounds, tf, crs, shape) if georef else None
    thr_map = np.where(protected, RECALL_FIRST_THRESHOLD, 0.5).astype(np.float32) if protected is not None else None

    # ChangeIntel: the same chain web/app.py runs
    prob = engine.run_inference(t1, t2)
    # Unobservable = cloud / shadow (either date) + nodata. Never reported as "no change": masked out of
    # detection and published as its own layer.
    cloud = GeoTIFFProcessor.load_cloud_mask(str(tile))
    # no data from reflectance when available: the display stretch clips dark water to 0 in every band
    unobs = (s1 == 0).all(axis=0) | (s2 == 0).all(axis=0)
    if cloud is not None:
        unobs |= cloud
    prob[unobs] = 0.0
    ai = GeospatialVectorizer().vectorize(prob, tf, crs, s1, s2, mode=mode, threshold_map=thr_map)
    # pixel size in metres decides whether the 3-6 m DCPR nala setback is resolvable
    gsd = abs(tf.a) * (111320 * np.cos(np.radians((bounds[1] + bounds[3]) / 2)) if crs.is_geographic else 1)
    enrich = lambda g: OSMExposureOverlay.enrich_with_exposure(g.to_crs(4326), georeferenced=georef, gsd_m=gsd).to_crs(crs) if g is not None and len(g) else g
    ai = enrich(ai)
    creep_gdf, creep_years = creep_layer(cfg, tf, crs, protected, mode) if cfg.get('series') else (None, [])
    creep_gdf = enrich(creep_gdf)
    (OUT / f"{cfg['out']}.gpkg").unlink(missing_ok=True)   # drop stale layers
    GISExporter.export_all(ai, cfg['out'], str(OUT))
    unobs_gdf = unobservable_polygons(unobs, tf, crs)
    if len(unobs_gdf):
        GISExporter.export_geojson(unobs_gdf, str(OUT / f"{cfg['out']}_unobservable.geojson"))
        GISExporter.export_geopackage(unobs_gdf, str(OUT / f"{cfg['out']}.gpkg"), layer_name='unobservable')
    if creep_gdf is not None and len(creep_gdf):
        export = creep_gdf.assign(ndbi_series=creep_gdf.ndbi_series.map(json.dumps))
        GISExporter.export_geojson(export, str(OUT / f"{cfg['out']}_creep.geojson"))
        GISExporter.export_geopackage(export, str(OUT / f"{cfg['out']}.gpkg"), layer_name='creep_and_precursors')
    sitrep = OUT / f'sitrep_{key}.pdf'
    SitRepGenerator.generate_report(ai.to_crs(4326), scene_name=cfg['label'], sensor_name=cfg['sensor'], output_path=str(sitrep))

    # Naive baseline, vectorized identically, then judged against the reference
    _, naive_mask = NaiveBaselineComparator.compute_naive_change(s1, s2, threshold=NAIVE_THRESHOLD)
    naive = GeospatialVectorizer().vectorize(naive_mask.astype(np.float32), tf, crs, s1, s2)
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

    def feature_json(r):
        geom = r.geometry
        poly = max(geom.geoms, key=lambda p: p.area) if geom.geom_type == 'MultiPolygon' else geom
        c = affine_transform(geom.centroid, to_pct)
        return {
            'id': r.feature_id, 'tier': r.severity_tier, 'type': r.change_type, 'summary': r.summary,
            'area_sqm': float(r.area_sqm), 'magnitude': float(r.magnitude), 'score': float(r.composite_score),
            'priority': r.action_priority, 'lat': float(r.centroid_lat), 'lon': float(r.centroid_lon),
            # both severity modes, so the console can switch without a rebuild
            'tiers': {m: r[f'tier_{m}'] for m in MODES}, 'scores': {m: float(r[f'score_{m}']) for m in MODES},
            'parts': {'norm_area': float(r.norm_area), 'exposure': float(r.exposure_mult)},
            'exposure': r.get('civic_exposure'), 'violation': r.get('encroachment_violation'),
            'cx': round(c.x, 2), 'cy': round(c.y, 2), 'pts': pct_ring(geom),
            'ring': [[round(la, 6), round(lo, 6)] for lo, la in (to_ll(x, y) for x, y in poly.exterior.coords)],
        }

    feats = [feature_json(r) for _, r in ai.iterrows()]
    creep_feats = [{**feature_json(r), 'kind': r.kind, 'series': r.ndbi_series}
                   for _, r in creep_gdf.iterrows()] if creep_gdf is not None else []

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
          f'{len(naive_out)} false alarms vs {ref_name} · shift {shift} px · unobservable {unobs.mean():.2%}'
          + (f' · recall-first {protected.mean():.1%} of tile' if protected is not None else '')
          + (f' · creep/precursors {len(creep_feats)}' if cfg.get('series') else ''))
    return {
        **{k: cfg[k] for k in ('label', 'place', 'sensor')},
        'nav': cfg.get('nav'),
        'dates': sector_dates(cfg, tile),
        'recall_first_pct': round(float(protected.mean()) * 100, 1) if protected is not None else None,
        'creep': {'years': creep_years, 'features': creep_feats} if cfg.get('series') else None,
        'georeferenced': georef,
        'default_mode': mode,
        'places': places,
        'cloud_pct': round(float(cloud.mean()) * 100, 2) if cloud is not None else None,
        'unobservable': {'pct': round(float(unobs.mean()) * 100, 2),
                         'area_sqm': float(unobs_gdf.area_sqm.sum()) if len(unobs_gdf) else 0.0,
                         'polygons': [pct_ring(g, tol=0.1) for g in unobs_gdf.to_crs(crs).geometry]},
        'harmonise': {'aligned': aligned, 'shift_px': [round(shift[0], 2), round(shift[1], 2)],
                      'normalisation': DEFAULT_NORMALISATION},
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
    # severity model travels with the data so the console can explain every score
    scenes = {'_severity': {'weights': TYPE_WEIGHTS, 'priority': PRIORITY}, **scenes}
    (ROOT / 'web/scenes.json').write_text(json.dumps(scenes, ensure_ascii=False))
    print('Wrote web/scenes.json')
