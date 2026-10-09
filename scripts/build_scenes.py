"""Runs the full T.R.A.C.E. (Terrain Analysis & Change Evaluation) pipeline per sector and writes web/scenes.json for the console.

For each sector: harmonise -> Scene Passport & Comparability Score (a low score tightens the threshold) ->
detection (Track A BIT / Track B Sentinel-2 network / event detector; recall-first inside protected and water
buffers) -> vectorize -> OSM exposure -> temporal context (change dating, persistence, seasonal check,
disaster recovery) -> GIS/SitRep exports; the unobservable (cloud / no data) layer; the naive NDVI baseline
vectorized the same way and checked against a reference (ground truth when the tile has a usable one,
otherwise the T.R.A.C.E. detections); and, for sectors with a yearly Sentinel-2 series, slow-creep and
precursor detection.

    .venv/bin/python scripts/build_scenes.py [sector ...]     # no names: every sector
"""
import base64
import io
import json
import math
import pathlib
import sys
from datetime import date

import numpy as np
import rasterio
from PIL import Image
from pyproj import Transformer
import geopandas as gpd
import pandas as pd
from rasterio.features import geometry_mask, rasterize, shapes
from shapely.geometry import box as box_geom, shape as to_geom
from shapely.strtree import STRtree
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
from src.geospatial import creep as creep_mod, events, passport, temporal
from src.geospatial.severity import MODES, PRIORITY, TYPE_WEIGHTS, SeverityScorer
from src.models import track_b
from src.models.infer import DEFAULT_NORMALISATION, TiledInferenceEngine
from src.models.naive_baseline import NaiveBaselineComparator

OUT = ROOT / 'data/outputs'
RAW_S2 = ROOT / 'data/raw/s2'


def fmt_date(d):
    d = pd.Timestamp(d)
    return f'{d.day} {d:%b %Y}'     # '%-d' is glibc-only


# The only hand-written facts: what each tile is. Everything else is computed.
OSCD_DATES = json.loads((ROOT / 'data/oscd_dates.json').read_text(encoding='utf-8'))   # from each OSCD city's dates.txt
SECTORS = {
    'mumbai': {
        'label': 'Mumbai Eastern Suburbs · Chembur–Ghatkopar', 'place': 'Mumbai, Maharashtra', 'nav': 'Mumbai 2015–18',
        'sensor': 'Sentinel-2 MSI · 10 m', 'iso_dates': OSCD_DATES['mumbai'],
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
    # Sentinel-2 L2A via scripts/fetch_s2.py (data/watch_areas.json): real SCL cloud mask + 2017-2026 series
    'mumbai_s2': {
        'label': 'Mumbai Eastern Suburbs · 2019 → 2025', 'place': 'Mumbai, Maharashtra', 'nav': 'Mumbai 2019–25',
        'sensor': 'Sentinel-2 L2A · 10 m', 'tile': 'data/geotiff/mumbai_s2', 'out': 'mumbai_s2_change_intelligence',
        'osm_key': 'mumbai', 'osm_pbf': 'data/raw/osm/western-zone-latest.osm.pbf',
        'default_mode': 'encroachment', 'series': 'data/raw/s2/mumbai_s2',
    },
}
# Disaster events (data/watch_areas.json entries with "event", fetched by scripts/fetch_s2.py): Sentinel-2
# before/after pair + a Copernicus EMS delineation rasterized as ground truth, scored by src/geospatial/events.py
for _area, _w in json.loads((ROOT / 'data/watch_areas.json').read_text(encoding='utf-8')).items():
    if 'event' in _w and (ROOT / f'data/geotiff/{_area}_t1_pre.tif').exists():
        SECTORS[_area] = {'label': _w['label'], 'place': _w['place'], 'nav': _w['label'].split(' · ')[0],
                          'sensor': 'Sentinel-2 L2A · 10 m', 'tile': f'data/geotiff/{_area}',
                          'out': f'{_area}_change_intelligence', 'default_mode': 'disaster',
                          'event': _w['event'], 'reference': _w['reference']}
# The other OSCD cities (scripts/build_data.py writes their tiles); dates come from each city's dates.txt.
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
    _txt = OSCD_IMAGES / _city / 'dates.txt'
    if _txt.exists():
        _d = dict(l.split(': ') for l in _txt.read_text(encoding='utf-8').split('\n') if ': ' in l)
        _iso = [pd.Timestamp(_d[k]).date().isoformat() for k in ('date_1', 'date_2')]
    else:
        _iso = OSCD_DATES[_city]      # the dataset folder is git-ignored; data/oscd_dates.json keeps its dates
    _dates = [fmt_date(d) for d in _iso]
    SECTORS[_city] = {
        'label': f"{_place.split(',')[0]} · OSCD", 'place': _place,
        'nav': f"{_place.split(',')[0]} {_dates[0][-4:]}–{_dates[1][-2:]}",
        'sensor': 'Sentinel-2 MSI · 10 m', 'iso_dates': _iso,
        'tile': f'data/geotiff/{_city}', 'out': f'{_city}_change_intelligence',
        'default_mode': 'encroachment',
    }
GEOFABRIK_INDEX = ROOT / 'data/raw/osm/geofabrik-index-v1.json'


def osm_extract_for(bounds):
    """Smallest downloaded Geofabrik extract whose region contains bounds (+~1 km), or None.
    Uses Geofabrik's index-v1.json; extracts live in data/raw/osm/ (git-ignored)."""
    if not GEOFABRIK_INDEX.exists():
        return None
    from shapely.geometry import box, shape as geom
    bb = box(bounds[0] - 0.01, bounds[1] - 0.01, bounds[2] + 0.01, bounds[3] + 0.01)
    found = [(geom(f['geometry']).area, ROOT / 'data/raw/osm' / f['properties']['urls']['pbf'].rsplit('/', 1)[1])
             for f in json.loads(GEOFABRIK_INDEX.read_text(encoding='utf-8'))['features']
             if f.get('geometry') and f['properties']['urls'].get('pbf') and geom(f['geometry']).contains(bb)]
    found = [(a, p) for a, p in found if p.exists()]
    return str(min(found)[1].relative_to(ROOT)) if found else None


RECALL_FIRST_FACTOR = 0.7      # detection threshold multiplier inside protected / water buffers (0.5 -> 0.35 for BIT)
TRACK_A_MAX_GSD = 2.0          # m; coarser imagery goes to Track B
_tb_metrics = json.loads((ROOT / track_b.METRICS).read_text(encoding='utf-8')) if (ROOT / track_b.METRICS).exists() else {}
TRACK_B_CITIES = {c['city'] for c in _tb_metrics.get('per_city', [])}
TRACK_B_SCORE = {'f1': _tb_metrics.get('pooled', {}).get('f1_score'), 'precision': _tb_metrics.get('pooled', {}).get('precision'),
                 'recall': _tb_metrics.get('pooled', {}).get('recall'), 'benchmark': 'OSCD, leave-one-city-out'}
_bench = json.loads((ROOT / 'data/outputs/benchmark_metrics.json').read_text(encoding='utf-8'))
TRACK_A_SCORE = {'f1': _bench['changeintel_ai_engine']['f1_score'], 'precision': _bench['changeintel_ai_engine']['precision'],
                 'recall': _bench['changeintel_ai_engine']['recall'], 'benchmark': 'LEVIR-CD test'}
WATER_BUFFER_M = 50.0
NAIVE_THRESHOLD = 0.18     # same cutoff evaluate.py benchmarks the baseline with
MIN_OVERLAP = 0.2          # naive region is "confirmed" if >=20% of it lies on reference change
USABLE_UNOBS = 0.25        # time-travel: a frame with more of the tile unobservable than this is not offered
FRAGMENT_RATIO = 5         # a polygon is a fragment of a same-type neighbour at least 5x its area ...
FRAGMENT_GAP_PX = 3        # ... within 3 px
FRAGMENT_MAX_PX = 30       # ... and tiny in absolute terms (0.3 ha at 10 m): a 50 ha burn patch is its own case
DUP_OVERLAP = 0.3          # a creep polygon >= 30 % covered by a pairwise detection is the same spot
PLACE_MAX_M = 5000
SOURCES = {   # (source, licence) per kind of input
    'oscd': ('Onera Satellite Change Detection dataset (Daudt et al., 2018), Sentinel-2 L1C',
             'Contains modified Copernicus Sentinel data; OSCD dataset terms apply'),
    'l2a': ('Sentinel-2 L2A cloud-optimised GeoTIFFs via Element 84 Earth Search STAC (AWS Open Data)',
            'Contains modified Copernicus Sentinel data (free, full and open Copernicus data policy)'),
    'levir': ('LEVIR-CD (Chen & Shi, 2020), Google Earth aerial imagery', 'Research use under the LEVIR-CD terms'),
}


def jpeg_uri(bands):
    rgb = bands[:3].transpose(1, 2, 0) if bands.shape[0] == 3 and bands.dtype == np.uint8 \
        else GeoTIFFProcessor.to_uint8_rgb(GeoTIFFProcessor.percentile_stretch(bands[:3]))
    buf = io.BytesIO()
    Image.fromarray(rgb).save(buf, 'JPEG', quality=86)
    return 'data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode()


def num(v, nd=3):
    """JSON-safe rounded float: None for None / NaN (NaN is not valid JSON)."""
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else round(float(v), nd)


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


def meta_for(tile):
    p = pathlib.Path(f'{tile}_meta.json')
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}


def pair_dates(cfg, tile):
    """ISO acquisition dates of the pair, or None (LEVIR-CD tiles carry none)."""
    if cfg.get('iso_dates'):
        return cfg['iso_dates']
    pair = meta_for(tile).get('pair')
    return [m['date'] for m in pair] if pair else None


def sector_dates(cfg, tile):
    iso = pair_dates(cfg, tile)
    return [fmt_date(d) for d in iso] if iso else cfg['dates']


def scene_passport(cfg, tile, bounds, gsd, unobs_pct, shift, mode):
    """Scene Passport (#18) for the pair: identity, conditions, season and the Comparability Score."""
    kind = 'levir' if not cfg.get('georeferenced', True) else 'l2a' if 'L2A' in cfg['sensor'] else 'oscd'
    level = {'levir': 'Aerial RGB orthophoto', 'l2a': 'L2A surface reflectance', 'oscd': 'L1C top-of-atmosphere'}[kind]
    files = [f'{tile}_t1_pre.tif', f'{tile}_t2_post.tif', f'{tile}_t1_reflectance.tif', f'{tile}_t2_reflectance.tif']
    sums = {pathlib.Path(f).name: passport.sha256(f) for f in files if pathlib.Path(f).exists()}
    src, lic = SOURCES[kind]
    iso = pair_dates(cfg, tile)
    if not iso:
        return {'sensor': cfg['sensor'], 'processing_level': level, 'resolution_m': round(gsd, 2), 'source': src,
                'licence': lic, 'images': [], 'comparability': None, 'checksums': sums,
                'note': 'LEVIR-CD tiles carry no acquisition dates or coordinates: season, sun angle and comparability not assessed.'}
    lat, lon = (bounds[1] + bounds[3]) / 2, (bounds[0] + bounds[2]) / 2
    return passport.build([date.fromisoformat(d) for d in iso], lat, lon, cfg['sensor'], level, gsd, round(unobs_pct, 2),
                          list(shift), mode, scenes=meta_for(tile).get('pair'), source=src, licence=lic, checksums=sums)


def display_cutoffs(r1, r2):
    """The 2-98 % per-band stretch fetch_s2.py gave the pair's display images, so time-travel frames match them."""
    rgb = np.concatenate([r1[:3], r2[:3]], axis=2).astype(np.float32)
    return [(float(np.percentile(b, 2)), float(np.percentile(b, 98))) for b in rgb]


def frame_jpeg(refl, cuts, max_px=1600):
    rgb = np.stack([np.clip((refl[i].astype(np.float32) - lo) / max(hi - lo, 1e-6), 0, 1) for i, (lo, hi) in enumerate(cuts)])
    img = Image.fromarray((rgb.transpose(1, 2, 0) * 255).astype(np.uint8))
    if max(img.size) > max_px:
        img.thumbnail((max_px, max_px), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, 'JPEG', quality=82)
    return 'data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode()


def heat_uri(prob, thr, max_px=1600):
    """Changed pixels (probability above the threshold in force there) as a 16-level palette PNG: the console
    clips it to the selected polygon to show where inside it the change is strongest."""
    lvl = np.clip((prob - thr) / np.maximum(1 - thr, 1e-6), 0, 1)
    idx = np.where(prob >= thr, 1 + np.round(lvl * 14), 0).astype(np.uint8)
    step = math.ceil(max(idx.shape) / max_px)
    idx = idx[::step, ::step]
    img = Image.frombytes('P', idx.shape[::-1], idx.tobytes())
    ramp = [(255, 196 + (246 - 196) * k // 14, 61 + (200 - 61) * k // 14) for k in range(15)]   # amber -> pale gold
    img.putpalette([0, 0, 0] + [c for rgb in ramp for c in rgb])
    buf = io.BytesIO()
    img.save(buf, 'PNG', transparency=bytes([0] + [110 + 125 * k // 14 for k in range(15)]), optimize=True)
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()


def labels_for(gdf, tf, shape):
    if gdf is None or not len(gdf):
        return None
    return rasterize(((g, i + 1) for i, g in enumerate(gdf.geometry)), out_shape=shape, transform=tf, dtype='int32')


def read_frame(base, tag):
    with rasterio.open(f'{base}_{tag}_reflectance.tif') as s:
        refl = s.read()
    with rasterio.open(f'{base}_{tag}_scl.tif') as s:
        ok = ~np.isin(s.read(1), GeoTIFFProcessor.SCL_UNOBSERVABLE)
    return refl, ok


def series_context(cfg, tf, shape, layers, iso, cuts):
    """Encroachment time travel (#47) over the yearly series: frames + per-polygon change dating, persistence
    and seasonal check (#19). layers: {'pair': gdf, 'creep': gdf}."""
    base = ROOT / cfg['series']
    index_path = pathlib.Path(f'{base}_series.json')
    if not index_path.exists():
        return None, {}
    index = json.loads(index_path.read_text(encoding='utf-8'))
    frames, stack, valid = [], [], []
    for e in index:
        refl, ok = read_frame(base, f"series_{e['year']}")
        unob = float(1 - ok.mean())
        usable = unob <= USABLE_UNOBS
        frames.append({'date': e['date'], 'label': str(e['year']), 'id': e['id'], 'unobservable': round(unob, 4),
                       'usable': usable, 'sun_elevation': num(e.get('sun_elevation'), 1), 'img': frame_jpeg(refl, cuts) if usable else None})
        stack.append(temporal.indices(refl))
        valid.append(ok)
    seasonal = None
    if pathlib.Path(f'{base}_seasonal_t1_reflectance.tif').exists():
        seasonal = [read_frame(f'{base}_seasonal', t) for t in ('t1', 't2')]
        seasonal = [(temporal.indices(r), ok) for r, ok in seasonal]
    ds = [date.fromisoformat(f['date']) for f in frames]
    near = lambda d: int(np.argmin([abs((x - date.fromisoformat(d)).days) for x in ds]))
    t1_i, t2_i = near(iso[0]), near(iso[1])
    ctx = {}
    for name, gdf in layers.items():
        labels = labels_for(gdf, tf, shape)
        if labels is None:
            continue
        n = len(gdf)
        need = {}
        for i, r in enumerate(gdf.itertuples()):
            ix, sign = temporal.index_for(r.change_type, {'ndbi': getattr(r, 'd_ndbi', None), 'ndvi': getattr(r, 'd_ndvi', None),
                                                         'mndwi': getattr(r, 'd_mndwi', None), 'nbr': getattr(r, 'd_nbr', None)})
            need.setdefault(ix, []).append((i, sign))
        for ix, members in need.items():
            vals = temporal.label_values(stack, valid, labels, n, ix)
            swing = None
            if seasonal:
                (a, oka), (b, okb) = seasonal
                m1, _ = temporal.polygon_means(labels, n, a[ix], oka)
                m2, _ = temporal.polygon_means(labels, n, b[ix], okb)
                swing = np.abs(m2 - m1)
            for i, sign in members:
                v = vals[i][0]
                a_, b_ = (0, len(v) - 1) if name == 'creep' else (t1_i, t2_i)
                sw = None if swing is None or np.isnan(swing[i]) else float(swing[i])
                c = temporal.date_change(v, a_, b_, ix, sign, sw)
                if name == 'creep':
                    c.pop('seasonal', None)   # the creep test already demands a steady rise across same-season images
                ctx[gdf.feature_id.iloc[i]] = {**c, 'index': ix, 'direction': sign, 'values': v, 'pair_frames': [a_, b_]}
    return {'kind': 'series', 'frames': frames, 'pair_frames': [t1_i, t2_i]}, ctx


def recovery_context(key, cfg, tf, shape, gdf, s1, s2, iso, cuts):
    """Disaster time travel (#47): pre-event, post-event and recovery revisits, with per-polygon recovery."""
    index_path = RAW_S2 / f'{key}_recovery.json'
    if not index_path.exists() or gdf is None or not len(gdf):
        return None, {}
    index = json.loads(index_path.read_text(encoding='utf-8'))
    tile = ROOT / cfg['tile']
    pair_ok = []
    for t in ('t1', 't2'):
        with rasterio.open(f'{tile}_{t}_scl.tif') as s:
            pair_ok.append(~np.isin(s.read(1), GeoTIFFProcessor.SCL_UNOBSERVABLE))
    meta = meta_for(tile).get('pair', [{}, {}])
    frames = [{'date': iso[0], 'label': 'Before', 'role': 'pre', 'id': meta[0].get('id'), 'usable': True, 'img': None,
               'unobservable': round(float(1 - pair_ok[0].mean()), 4)},
              {'date': iso[1], 'label': 'After', 'role': 'post', 'id': meta[1].get('id'), 'usable': True, 'img': None,
               'unobservable': round(float(1 - pair_ok[1].mean()), 4)}]
    stack, valid = [temporal.indices(s1), temporal.indices(s2)], pair_ok
    for e in index:
        refl, ok = read_frame(RAW_S2 / key, f"recovery_{e['i']}")
        unob = float(1 - ok.mean())
        usable = unob <= USABLE_UNOBS
        frames.append({'date': e['date'], 'label': fmt_date(e['date']), 'role': 'revisit', 'id': e['id'], 'usable': usable,
                       'unobservable': round(unob, 4), 'img': frame_jpeg(refl, cuts) if usable else None})
        stack.append(temporal.indices(refl))
        valid.append(ok if usable else np.zeros_like(ok))
    ix = 'mndwi' if cfg['event'] == 'flood' else 'nbr'
    labels = labels_for(gdf, tf, shape)
    vals = temporal.label_values(stack, valid, labels, len(gdf), ix, threshold=0.0 if cfg['event'] == 'flood' else None)
    ctx = {}
    for i, fid in enumerate(gdf.feature_id):
        v, share = vals[i]
        ctx[fid] = {'assessed': True, 'index': ix, 'values': v, 'recovery': temporal.recovery(cfg['event'], v, share or [None] * len(v))}
    return {'kind': 'recovery', 'frames': frames, 'pair_frames': [0, 1]}, ctx


def mark_redundant(ai, creep_gdf, px):
    """#46 de-duplication: tiny same-type fragments beside a larger polygon (part_of) and creep polygons on a
    spot that is already a pairwise case (dup_of)."""
    part_of, dup_of = {}, {}
    if ai is not None and len(ai) > 1:
        geoms, areas, types, ids = list(ai.geometry), ai.area_sqm.values, ai.change_type.values, list(ai.feature_id)
        tiny = ai.pixel_area_sqm.values * FRAGMENT_MAX_PX
        tree = STRtree(geoms)
        for i, g in enumerate(geoms):
            if areas[i] > tiny[i]:
                continue
            big = [j for j in tree.query(g.buffer(FRAGMENT_GAP_PX * px)) if j != i and types[j] == types[i]
                   and areas[j] >= FRAGMENT_RATIO * areas[i]]
            if big:
                part_of[ids[i]] = ids[max(big, key=lambda j: areas[j])]
        for k in list(part_of):            # point every fragment at the root of its chain
            while part_of[k] in part_of:
                part_of[k] = part_of[part_of[k]]
    if creep_gdf is not None and len(creep_gdf) and ai is not None and len(ai):
        tree = STRtree(list(ai.geometry))
        for cid, g in zip(creep_gdf.feature_id, creep_gdf.geometry):
            hit = [j for j in tree.query(g) if ai.geometry.iloc[j].intersection(g).area >= DUP_OVERLAP * g.area]
            if hit:
                dup_of[cid] = ai.feature_id.iloc[hit[0]]
    return part_of, dup_of


def nearest_place(lat, lon, places):
    if not places or lat is None:
        return None
    pl = np.radians([[p['lat'], p['lon']] for p in places])
    la, lo = math.radians(lat), math.radians(lon)
    h = np.sin((pl[:, 0] - la) / 2) ** 2 + math.cos(la) * np.cos(pl[:, 0]) * np.sin((pl[:, 1] - lo) / 2) ** 2
    d = 2 * 6371000 * np.arcsin(np.sqrt(h))
    i = int(np.argmin(d))
    if d[i] > PLACE_MAX_M:
        return None
    p = places[i]
    return {'name': p['name'], 'name_mr': p.get('name_mr'), 'name_hi': p.get('name_hi'), 'kind': p['kind'], 'dist_m': int(round(d[i], -1))}


def creep_layer(cfg, tf, crs, protected, mode):
    """Slow creep + precursors over the sector's yearly series (src/geospatial/creep.py), as a GeoDataFrame
    shaped like the vectorizer's output, plus the years and per-polygon NDBI series."""
    base = ROOT / cfg['series']
    index_path = pathlib.Path(f'{base}_series.json')
    if not index_path.exists():
        print(f'  no yearly series at {index_path.relative_to(ROOT)}: run scripts/fetch_s2.py; creep layer skipped')
        return None, []
    index = json.loads(index_path.read_text(encoding='utf-8'))
    refl, valid = [], []
    for e in index:
        r, ok = read_frame(base, f"series_{e['year']}")
        refl.append(r)
        valid.append(ok)
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
        # magnitude = strength of the signal that defined the polygon, 0.5 at its rule's threshold:
        # creep by its NDBI rise (CUM_RISE 0.10 -> 0.5, +0.20 -> 1), precursors by their NDVI loss (0.15 -> 0.5)
        if k == 'creep':
            g['magnitude'] = [round(float(np.clip((s[-1] - s[0]) / (2 * creep_mod.CUM_RISE), 0, 1)), 3) for s in series]
        else:
            drops = []
            for geom in g.geometry:
                m = ~geometry_mask([geom], out_shape=out[k].shape, transform=tf)
                drops.append(float(out['ndvi'][0][m].mean() - out['ndvi'][-1][m].mean()))
            g['magnitude'] = [round(float(np.clip(d / (2 * creep_mod.CLEAR_NDVI_DROP), 0, 1)), 3) for d in drops]
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
    if georef and not cfg.get('osm_pbf'):
        cfg = {**cfg, 'osm_pbf': osm_extract_for(bounds)}
    if cfg.get('osm_pbf') and not snap.exists() and (ROOT / cfg['osm_pbf']).exists():
        pad = 0.01  # ~1 km, so assets just outside the tile still count
        OSMExposureOverlay.build_snapshot(str(ROOT / cfg['osm_pbf']),
                                          [bounds[0] - pad, bounds[1] - pad, bounds[2] + pad, bounds[3] + pad], str(snap))
    places_path = ROOT / f'data/osm/{osm_key}_places.json'
    if cfg.get('osm_pbf') and not places_path.exists() and (ROOT / cfg['osm_pbf']).exists():
        OSMExposureOverlay.build_gazetteer(str(ROOT / cfg['osm_pbf']), list(bounds), str(places_path))
    places = json.loads(places_path.read_text(encoding='utf-8')) if places_path.exists() else []
    # recall-first: a lower detection threshold inside protected land and water buffers
    protected = recall_first_mask(bounds, tf, crs, shape) if georef else None
    # pixel size in metres: routes the detector and decides whether the 3-6 m DCPR nala setback is resolvable
    gsd = abs(tf.a) * (111320 * np.cos(np.radians((bounds[1] + bounds[3]) / 2)) if crs.is_geographic else 1)

    # Unobservable = cloud / shadow (either date) + nodata. Never reported as "no change": masked out of
    # detection and published as its own layer.
    cloud = GeoTIFFProcessor.load_cloud_mask(str(tile))
    # no data from reflectance when available: the display stretch clips dark water to 0 in every band
    unobs = (s1 == 0).all(axis=0) | (s2 == 0).all(axis=0)
    if cloud is not None:
        unobs |= cloud
    # Scene Passport (#18) before detection: a low Comparability Score tightens the learned detectors' threshold
    pp = scene_passport(cfg, tile, bounds, gsd, float(unobs.mean()) * 100, shift, mode)
    comp = (pp.get('comparability') or {}).get('score')

    # Two-track routing (Ideation Baseline #2): BIT for <= 2 m imagery, Track B for 10-20 m multispectral.
    # A labelled OSCD city is scored by the Track B model trained without it (leave-one-city-out).
    tb = track_b.change_probability(s1, s2, holdout=key) if gsd > TRACK_A_MAX_GSD and refl and not cfg.get('event') else None
    if cfg.get('event'):
        prob, thr = events.SCORERS[cfg['event']](s1, s2), 0.5
        thr_recall = thr
        detector = {'track': 'E', 'name': {'flood': 'Event detector · new water (MNDWI > 0)',
                                           'wildfire': 'Event detector · burn severity (dNBR ≥ 0.27)'}[cfg['event']],
                    'held_out': True, 'benchmark': cfg['reference']['source']}
    elif tb is not None:
        prob, thr, thr_recall = tb
        detector = {'track': 'B', 'name': 'Track B · Sentinel-2 spectral network', **TRACK_B_SCORE,
                    'object_precision': _tb_metrics.get('objects', {}).get('object_precision'),
                    'held_out': key in TRACK_B_CITIES}
    else:
        prob, thr = engine.run_inference(t1, t2), 0.5
        thr_recall = thr * RECALL_FIRST_FACTOR
        detector = {'track': 'A', 'name': 'Track A · BIT (0.5 m aerial)', **TRACK_A_SCORE, 'held_out': False,
                    'out_of_domain': gsd > TRACK_A_MAX_GSD}
    detector['threshold_base'] = round(float(thr), 4)
    # event detectors keep their fixed literature thresholds; recall-first zones keep theirs too, because a miss
    # inside a protected buffer costs more than a false alarm there (data/outputs/comparability_tightening.json)
    if detector['track'] != 'E':
        thr = passport.tightened_threshold(thr, comp)
    detector['threshold'], detector['threshold_recall'] = round(float(thr), 4), round(float(thr_recall), 4)
    # recall-first: a lower threshold inside protected land and water buffers
    # (Track B: its measured recall-favouring F1 threshold; BIT: 0.7x of 0.5)
    thr_map = np.where(protected, thr_recall, thr).astype(np.float32) if protected is not None else None
    prob[unobs] = 0.0
    vec = GeospatialVectorizer(prob_threshold=thr, morphology_radius=track_b.MORPH_RADIUS, min_area_px=track_b.MIN_AREA_PX) \
        if detector['track'] == 'B' else GeospatialVectorizer(prob_threshold=thr)
    ai = vec.vectorize(prob, tf, crs, s1, s2, mode=mode,
                                                            threshold_map=None if cfg.get('event') else thr_map)
    if cfg.get('event') and len(ai):
        # the detector already decided the event type; describe each polygon from the same index and re-score
        ctype = events.EVENT_TYPES[cfg['event']]
        for i, r in ai.iterrows():
            m = ~geometry_mask([r.geometry], out_shape=shape, transform=tf)
            ai.at[i, 'change_type'], ai.at[i, 'summary'] = ctype, events.describe(cfg['event'], s1, s2, m)
            for c, v in SeverityScorer.compute_all_modes(r.area_sqm, r.magnitude, ctype, pixel_area_sqm=r.pixel_area_sqm,
                                                         primary_mode=mode).items():
                ai.at[i, c] = v
    enrich = lambda g: OSMExposureOverlay.enrich_with_exposure(g.to_crs(4326), georeferenced=georef, gsd_m=gsd).to_crs(crs) if g is not None and len(g) else g
    ai = enrich(ai)
    creep_gdf, creep_years = creep_layer(cfg, tf, crs, protected, mode) if cfg.get('series') else (None, [])
    creep_gdf = enrich(creep_gdf)

    # Temporal context (#19) and time-travel frames (#47) where dated imagery beyond the pair exists
    iso = pair_dates(cfg, tile)
    timeline, tctx = None, {}
    if refl and iso:
        cuts = display_cutoffs(s1, s2)
        if cfg.get('series'):
            timeline, tctx = series_context(cfg, tf, shape, {'pair': ai, 'creep': creep_gdf}, iso, cuts)
        elif cfg.get('event'):
            timeline, tctx = recovery_context(key, cfg, tf, shape, ai, s1, s2, iso, cuts)
    if timeline:
        fr = timeline['frames']
        label = lambda i: fr[i]['date'] if i is not None else None
        for g in (ai, creep_gdf):
            if g is None or not len(g):
                continue
            ctxs = [tctx.get(f, {}) for f in g.feature_id]
            g['first_seen'] = [label(c.get('first_seen')) if c.get('assessed') and 'first_seen' in c else None for c in ctxs]
            g['persistence'] = [f"{c['persist'][0]}/{c['persist'][1]} later images" if c.get('persist') and c['persist'][1] else None for c in ctxs]
            g['seasonal_check'] = [(c.get('seasonal') or {}).get('verdict') for c in ctxs]
            g['recovery'] = [(c.get('recovery') or {}).get('status') for c in ctxs]
    if comp is not None and len(ai):
        ai['comparability'] = comp

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
    # Naive baseline, vectorized identically, then judged against the reference
    _, naive_mask = NaiveBaselineComparator.compute_naive_change(s1, s2, threshold=NAIVE_THRESHOLD)
    naive = GeospatialVectorizer().vectorize(naive_mask.astype(np.float32), tf, crs, s1, s2)
    ref = gt if gt is not None else prob >= thr
    ref_name = 'ground truth' if gt is not None else 'T.R.A.C.E. detections'

    # Event validation against the Copernicus EMS delineation, on final polygons, where EMS mapped and both
    # images are observable. Track B and naive NDVI are scored the same way for comparison.
    event_validation, reference = None, None
    if cfg.get('event') and gt is not None:
        with rasterio.open(f'{tile}_reference_aoi.tif') as s:
            scope = (s.read(1) > 0) & ~unobs
        as_mask = lambda g: ~geometry_mask(list(g.geometry), out_shape=shape, transform=tf) if len(g) else np.zeros(shape, bool)
        tbp = track_b.change_probability(s1, s2)
        event_validation = {'reference': cfg['reference']['source'], 'scope_km2': round(float(scope.sum()) * gsd * gsd / 1e6, 1),
                            'changeintel': events.validate(as_mask(ai), gt, scope),
                            'track_b_urban': events.validate(track_b.cleaned(tbp[0] >= tbp[1]), gt, scope) if tbp else None,
                            'naive_ndvi': events.validate(naive_mask.astype(bool), gt, scope)}
        ref_path = ROOT / cfg['reference']['event']
        if ref_path.exists():
            ref_gdf = gpd.read_file(ref_path).to_crs(crs)
        else:   # data/raw is git-ignored; the committed ground truth is the same EMS delineation rasterized on this grid
            ref_gdf = gpd.GeoDataFrame(geometry=[to_geom(g) for g, v in shapes(gt.astype(np.uint8), mask=gt, transform=tf) if v == 1], crs=crs)
        reference = {'source': cfg['reference']['source'], 'polygons': []}
        detector['f1'] = event_validation['changeintel']['f1_score']
        print(f"  [{key}] vs EMS: F1 {event_validation['changeintel']['f1_score']} "
              f"P {event_validation['changeintel']['precision']} R {event_validation['changeintel']['recall']}")

    sitrep = OUT / f'sitrep_{key}.pdf'
    note = (f"Detector: {detector['name']}" + (f", F1 {detector['f1']:.0%} on {detector['benchmark']}." if detector.get('f1') is not None
                                                else f", validated against {detector['benchmark']}."))
    limits = []
    if pp.get('comparability'):
        c = pp['comparability']
        limits.append(f"Image comparability {c['score']}/100 ({c['band'].lower()}); biggest factor: {c['factors'][0]['detail']}."
                      + (f" Detection threshold raised from {detector['threshold_base']} to {detector['threshold']} outside protected zones."
                         if detector['threshold'] != detector['threshold_base'] else ''))
    elif pp.get('note'):
        limits.append(pp['note'])
    limits.append(f"Change dated from {sum(1 for f in timeline['frames'] if f['usable'])} dated images ({timeline['frames'][0]['date']} to "
                  f"{timeline['frames'][-1]['date']})." if timeline else "Change dated only to the window between the two images: no yearly series stored for this area.")
    limits.append("OpenStreetMap exposure and buffer checks are screening only, not legal boundaries; verify against revenue, FTL and "
                  "Development Plan records before any notice." if georef else "Tile is not georeferenced: exposure and buffer checks not assessed.")
    SitRepGenerator.generate_report(ai.to_crs(4326), scene_name=cfg['label'], sensor_name=cfg['sensor'], output_path=str(sitrep),
                                    event=cfg.get('event') or 'encroachment', detector_note=note,
                                    unobservable_pct=float(unobs.mean()) * 100, limitations=limits)

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

    part_of, dup_of = mark_redundant(ai, creep_gdf, abs(tf.a))
    zone_of = {}     # share of each polygon inside the recall-first (protected / water buffer) zone
    for g in (ai, creep_gdf):
        labels = labels_for(g, tf, shape) if protected is not None else None
        if labels is not None:
            share, _ = temporal.polygon_means(labels, len(g), protected.astype(np.float32), np.ones(shape, bool))
            zone_of.update({fid: 0.0 if np.isnan(v) else float(v) for fid, v in zip(g.feature_id, share)})

    def near_unobs(geom, pad=5):
        """Share of the polygon's surroundings (bbox + pad px) that is unobservable."""
        c0, r1 = inv * (geom.bounds[0], geom.bounds[1])
        c1, r0 = inv * (geom.bounds[2], geom.bounds[3])
        r0, r1 = sorted((r0, r1))
        c0, c1 = sorted((c0, c1))
        win = unobs[max(0, int(r0) - pad):min(h, int(r1) + pad + 1), max(0, int(c0) - pad):min(w, int(c1) + pad + 1)]
        return round(float(win.mean()), 3) if win.size else 0.0

    def feature_json(r):
        geom = r.geometry
        poly = max(geom.geoms, key=lambda p: p.area) if geom.geom_type == 'MultiPolygon' else geom
        c = affine_transform(geom.centroid, to_pct)
        z = zone_of.get(r.feature_id, 0.0)
        lat, lon = num(r.centroid_lat, 6), num(r.centroid_lon, 6)
        t = tctx.get(r.feature_id)
        return {
            'id': r.feature_id, 'tier': r.severity_tier, 'type': r.change_type, 'summary': r.summary,
            'area_sqm': float(r.area_sqm), 'magnitude': float(r.magnitude), 'score': float(r.composite_score),
            'priority': r.action_priority, 'lat': lat, 'lon': lon,
            # both severity modes, so the console can switch without a rebuild
            'tiers': {m: r[f'tier_{m}'] for m in MODES}, 'scores': {m: float(r[f'score_{m}']) for m in MODES},
            'parts': {'norm_area': float(r.norm_area), 'exposure': float(r.exposure_mult)},
            'exposure': r.get('civic_exposure'), 'violation': r.get('encroachment_violation'),
            # case facts for the Change-to-Action Card and the copilot
            'idx': {k: num(r.get(k)) for k in ('d_ndvi', 'd_mndwi', 'd_ndbi', 'd_nbr') if num(r.get(k)) is not None},
            # the cut-off this polygon's signal was held to: creep magnitude is trend strength, 0.5 = creep_mod.CUM_RISE
            'thr': (0.5 * (creep_mod.RECALL_FACTOR if z >= 0.5 else 1.0)) if 'kind' in r.index
                   else float(thr_recall if z >= 0.5 else thr),
            'zone': round(z, 2), 'near_unobs': near_unobs(geom),
            'place': nearest_place(lat, lon, places) if georef else None,
            'part_of': part_of.get(r.feature_id), 'dup_of': dup_of.get(r.feature_id),
            'temporal': t,
            'cx': round(c.x, 2), 'cy': round(c.y, 2), 'pts': pct_ring(geom),
            'ring': [[round(la, 6), round(lo, 6)] for lo, la in (to_ll(x, y) for x, y in poly.exterior.coords)],
        }

    feats = [feature_json(r) for _, r in ai.iterrows()]
    if reference is not None:
        clip = box_geom(*rasterio.transform.array_bounds(h, w, tf))
        for g in ref_gdf.geometry.intersection(clip).simplify(gsd * 2):
            for part in (getattr(g, 'geoms', None) or [g]):
                if part.geom_type == 'Polygon' and part.area > 4 * gsd * gsd:
                    reference['polygons'].append(pct_ring(part))
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

    print(f'[{key}] {len(feats)} T.R.A.C.E. polygons · naive {len(naive)} regions, '
          f'{len(naive_out)} false alarms vs {ref_name} · shift {shift} px · unobservable {unobs.mean():.2%}'
          + (f' · recall-first {protected.mean():.1%} of tile' if protected is not None else '')
          + (f' · creep/precursors {len(creep_feats)}' if cfg.get('series') else '')
          + (f' · comparability {comp}' if comp is not None else '')
          + (f" · {sum(1 for f in timeline['frames'] if f['usable'])} time-travel frames" if timeline else ''))
    return {
        **{k: cfg[k] for k in ('label', 'place', 'sensor')},
        'nav': cfg.get('nav'),
        'dates': sector_dates(cfg, tile),
        'iso_dates': iso,
        'recall_first_pct': round(float(protected.mean()) * 100, 1) if protected is not None else None,
        'creep': {'years': creep_years, 'features': creep_feats} if cfg.get('series') else None,
        'georeferenced': georef,
        'default_mode': mode,
        'places': places,
        'cloud_pct': round(float(cloud.mean()) * 100, 2) if cloud is not None else None,
        'unobservable': {'pct': round(float(unobs.mean()) * 100, 2),
                         'area_sqm': float(unobs_gdf.area_sqm.sum()) if len(unobs_gdf) else 0.0,
                         'polygons': [pct_ring(g, tol=0.1) for g in unobs_gdf.to_crs(crs).geometry]},
        'detector': detector,
        'passport': pp,
        'timeline': timeline,
        'heat': heat_uri(prob, thr_map if thr_map is not None else np.float32(thr)),
        'event': cfg.get('event'),
        'event_validation': event_validation,
        'reference': reference,
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
    only = sys.argv[1:]
    path = ROOT / 'web/scenes.json'
    # a partial rebuild keeps the other sectors from the last full run
    scenes = json.loads(path.read_text(encoding='utf-8')) if only and path.exists() else {}
    scenes.pop('_severity', None)
    for k, cfg in SECTORS.items():
        if not only or k in only:
            scenes[k] = run_sector(k, cfg, engine)
    # sector order follows SECTORS; the severity model travels with the data so the console can explain every score
    scenes = {'_severity': {'weights': TYPE_WEIGHTS, 'priority': PRIORITY}, **{k: scenes[k] for k in SECTORS if k in scenes}}
    path.write_text(json.dumps(scenes, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    print('Wrote web/scenes.json')
