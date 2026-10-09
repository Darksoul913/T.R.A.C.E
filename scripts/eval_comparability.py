"""Measures what the Comparability Score's threshold tightening (src/geospatial/passport.py) does on the labelled
OSCD cities: Track B pixel precision / recall / F1 against ground truth at the learned threshold and at the
tightened one, per low-comparability city and pooled. Writes data/outputs/comparability_tightening.json.

    .venv/bin/python scripts/eval_comparability.py      # after scripts/build_scenes.py (reads web/scenes.json)
"""
import json
import pathlib
import sys

import numpy as np
import rasterio

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src.data.geotiff_processor import GeoTIFFProcessor
from src.geospatial import passport
from src.models import track_b


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return {'precision': round(p, 4), 'recall': round(r, 4), 'f1_score': round(2 * p * r / (p + r), 4) if p + r else 0.0}


def main():
    scenes = json.loads((ROOT / 'web/scenes.json').read_text(encoding='utf-8'))
    cities, pooled = [], {'low': np.zeros((2, 3), int), 'all': np.zeros((2, 3), int)}
    for key, sc in scenes.items():
        if key == '_severity' or sc['detector']['track'] != 'B' or not sc.get('passport'):
            continue
        gt_path = ROOT / f'data/geotiff/{key}_ground_truth.tif'
        if not gt_path.exists():
            continue
        with rasterio.open(gt_path) as s:
            gt = s.read(1) > 0
        if not 0 < gt.mean() < 1:
            continue
        r1, r2 = GeoTIFFProcessor.load_reflectance(str(ROOT / f'data/geotiff/{key}'))
        prob, thr, _ = track_b.change_probability(r1, r2, holdout=key)   # the model that never saw this city
        score = sc['passport']['comparability']['score']
        counts = []
        for t in (thr, passport.tightened_threshold(thr, score)):
            pred = track_b.cleaned(prob >= t)
            counts.append([int((pred & gt).sum()), int((pred & ~gt).sum()), int((~pred & gt).sum())])
        counts = np.array(counts)
        pooled['all'] += counts
        if score < passport.LOW:
            pooled['low'] += counts
            cities.append({'city': key, 'comparability': score, 'threshold': round(float(thr), 4),
                           'tightened_threshold': passport.tightened_threshold(thr, score),
                           'learned': prf(*counts[0]), 'tightened': prf(*counts[1])})
    out = {'method': 'Track B leave-one-city-out model, cleaned masks, pixels vs OSCD ground truth; tightening applies '
                     f'below comparability {passport.LOW} (up to +{passport.MAX_TIGHTEN:.0%} at 0). Applied here to the whole '
                     'tile; the pipeline keeps recall-first zones at their own threshold, so the recall loss shown is an upper bound',
           'low_comparability_cities': cities,
           'pooled_low_comparability': {'learned': prf(*pooled['low'][0]), 'tightened': prf(*pooled['low'][1])},
           'pooled_all_labelled': {'learned': prf(*pooled['all'][0]), 'tightened': prf(*pooled['all'][1])}}
    (ROOT / 'data/outputs/comparability_tightening.json').write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == '__main__':
    main()
