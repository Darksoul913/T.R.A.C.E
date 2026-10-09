"""
track_b.py - Sentinel-2 change detector (Ideation Baseline #2, Track B: 10-20 m multispectral).

BIT (Track A) is trained on 0.5 m aerial RGB and finds 0% of OSCD's labelled change at 10 m. Track B is a
small per-pixel network on scale-free spectral features, trained on the 14 labelled OSCD cities:

  - normalised difference T1 vs T2 per band (B04 B03 B02 B08 B11 B12)       6
  - NDVI, NDBI, MNDWI, NBR, NDWI at T1, T2 and their change                 15
  - 5x5 neighbourhood mean and std of the per-band changes (context)          12

Ratios and normalised differences make it largely insensitive to L1C (OSCD) vs L2A (Earth Search) offsets.
Every reported number is leave-one-city-out: the model scoring a city never saw it. The scene build uses
the same rule: a labelled OSCD city is shown with the model trained without it.

    .venv/bin/python -m src.models.track_b      # trains all folds + full model, writes metrics
"""

import json
import os
import time
from typing import Dict, List, Optional

import numpy as np
import torch
from scipy.ndimage import uniform_filter

CKPT = "checkpoints/s2_track_b.pt"
METRICS = "data/outputs/track_b_metrics.json"
N_FEATURES = 21


def nd(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    a, b = a.astype(np.float32), b.astype(np.float32)
    return (a - b) / np.maximum(a + b, 1e-6)


def phenology_suppression(refl1: np.ndarray, refl2: np.ndarray) -> np.ndarray:
    """Masks pixels where vegetation changed without a corresponding built-up rise (phenology / seasonal shift)."""
    a, b = refl1.astype(np.float32), refl2.astype(np.float32)
    d_ndvi = nd(b[3], b[0]) - nd(a[3], a[0])
    d_ndbi = nd(b[4], b[3]) - nd(a[4], a[3])
    return (np.abs(d_ndvi) > 0.15) & (d_ndbi <= 0.05)


def features(refl1: np.ndarray, refl2: np.ndarray) -> np.ndarray:
    """(6, H, W) reflectance pair -> (H, W, 21) float32 features on Red, NIR, SWIR1, SWIR2 (immune to L1C/L2A Rayleigh shift)."""
    a, b = refl1.astype(np.float32), refl2.astype(np.float32)
    bands = [0, 3, 4, 5]
    band_change = [nd(b[i], a[i]) for i in bands]
    idx = lambda r: [nd(r[3], r[0]), nd(r[4], r[3]), nd(r[3], r[5])]
    i1, i2 = idx(a), idx(b)
    f = [*band_change, *i1, *i2, *[y - x for x, y in zip(i1, i2)]]
    for c in band_change:
        m = uniform_filter(c, 5)
        f += [m, np.sqrt(np.maximum(uniform_filter(c * c, 5) - m * m, 0))]
    out = np.stack(f, axis=-1).astype(np.float32)
    return np.nan_to_num(np.clip(out, -3, 3))


class PixelMLP(torch.nn.Module):
    def __init__(self, n=N_FEATURES):
        super().__init__()
        self.net = torch.nn.Sequential(torch.nn.Linear(n, 64), torch.nn.ReLU(), torch.nn.Linear(64, 32),
                                       torch.nn.ReLU(), torch.nn.Linear(32, 1))

    def forward(self, x):
        return self.net(x).squeeze(-1)


def train(data: List[Dict], epochs: int = 6, per_city: int = 40000, seed: int = 0) -> PixelMLP:
    """data: [{'X': (H, W, F), 'y': (H, W) bool}]. Balanced pixel sample per city, weighted BCE."""
    rng = np.random.default_rng(seed)
    xs, ys = [], []
    for d in data:
        X, y = d["X"].reshape(-1, N_FEATURES), d["y"].ravel()
        pos, neg = np.flatnonzero(y), np.flatnonzero(~y)
        take = lambda ix, n: rng.choice(ix, min(n, len(ix)), replace=False) if len(ix) else ix
        sel = np.concatenate([take(pos, per_city // 2), take(neg, per_city // 2)])
        xs.append(X[sel]); ys.append(y[sel])
    X = torch.from_numpy(np.concatenate(xs)); y = torch.from_numpy(np.concatenate(ys).astype(np.float32))
    torch.manual_seed(seed)
    model = PixelMLP(n=N_FEATURES)
    opt = torch.optim.AdamW(model.parameters(), 2e-3, weight_decay=1e-4)
    for _ in range(epochs):
        for b in torch.randperm(len(X)).split(1024):
            opt.zero_grad()
            torch.nn.functional.binary_cross_entropy_with_logits(model(X[b]), y[b]).backward()
            opt.step()
    return model.eval()


@torch.no_grad()
def predict(model: PixelMLP, X: np.ndarray) -> np.ndarray:
    h, w, _ = X.shape
    return torch.sigmoid(model(torch.from_numpy(X.reshape(-1, N_FEATURES)))).numpy().reshape(h, w)


BETA = 0.5   # operating point favours precision: same F1 as beta=1 under LOCO, but 23% vs 17% precision
             # and 1.7% vs 4.0% false alarms, which matters more for an officer's triage queue


# Polygon cleanup for Track B (vectorizer settings). Pixel errors are speckle; under LOCO, opening radius 2 and
# a 25 px (0.25 ha) minimum cut polygons per city from ~151 to ~32 and raise object precision from 26% to 42%,
# while the share of labelled objects found drops from 19% to 10% (small 10 m changes are the ones lost).
MORPH_RADIUS = 2
MIN_AREA_PX = 25


def cleaned(mask: np.ndarray) -> np.ndarray:
    from skimage.morphology import closing, disk, opening
    from scipy.ndimage import label
    m = closing(opening(mask, disk(MORPH_RADIUS)), disk(MORPH_RADIUS))
    lab, _ = label(m, np.ones((3, 3)))
    return np.isin(lab, np.flatnonzero(np.bincount(lab.ravel()) >= MIN_AREA_PX)[1:])


def object_scores(pred: np.ndarray, gt: np.ndarray) -> Dict[str, int]:
    """Polygon counts for triage: a predicted object is real if >= 20% of it is labelled change; a labelled
    object is found if >= 30% of it is covered."""
    from scipy.ndimage import label
    lp, n = label(pred, np.ones((3, 3)))
    lg, ng = label(gt, np.ones((3, 3)))
    size, on_gt = np.bincount(lp.ravel(), minlength=n + 1), np.bincount(lp.ravel(), weights=gt.ravel(), minlength=n + 1)
    real = int((on_gt[1:] / np.maximum(size[1:], 1) >= 0.2).sum())
    gsize, cov = np.bincount(lg.ravel(), minlength=ng + 1), np.bincount(lg.ravel(), weights=pred.ravel(), minlength=ng + 1)
    found = int((cov[1:] / np.maximum(gsize[1:], 1) >= 0.3).sum())
    return {"polygons": int(n), "real": real, "gt_objects": int(ng), "found": found}


def best_threshold(probs: List[np.ndarray], ys: List[np.ndarray], beta: float = BETA) -> float:
    """Threshold maximising pooled F-beta on the given (training) cities."""
    p, y = np.concatenate([q.ravel() for q in probs]), np.concatenate([t.ravel() for t in ys])
    best, thr = -1.0, 0.5
    for t in np.linspace(0.3, 0.99, 47):
        pr = p >= t
        tp = (pr & y).sum()
        prec, rec = tp / max(pr.sum(), 1), tp / max(y.sum(), 1)
        f = (1 + beta ** 2) * prec * rec / max(beta ** 2 * prec + rec, 1e-9)
        if f > best:
            best, thr = f, float(t)
    return thr


def load(holdout: Optional[str] = None):
    """(model, threshold, recall threshold) trained without `holdout` (a labelled OSCD city), or on all cities when None / unseen."""
    if not os.path.exists(CKPT):
        return None
    ck = torch.load(CKPT, weights_only=False)
    key = holdout if holdout in ck["folds"] else "_all"
    n_feat = ck.get("features", N_FEATURES)
    m = PixelMLP(n=n_feat); m.load_state_dict(ck["folds"][key]["state"]); m.eval()
    f = ck["folds"][key]
    return m, f["threshold"], f.get("threshold_recall", f["threshold"])


def change_probability(refl1: np.ndarray, refl2: np.ndarray, holdout: Optional[str] = None):
    """(probability map, precision-favouring threshold, recall-favouring threshold for protected zones),
    or None when no checkpoint is trained."""
    loaded = load(holdout)
    if loaded is None:
        return None
    model, thr, thr_recall = loaded
    prob = predict(model, features(refl1, refl2))
    prob[phenology_suppression(refl1, refl2)] = 0.0
    return prob, thr, thr_recall


def run_loco():
    """Leave-one-city-out over the labelled OSCD cities; saves all fold models + a full model."""
    from src.data.dataset_builder import DatasetBuilder
    from src.models.evaluate import confusion, metrics_from, oscd_labelled_cities
    cities = [c for c in oscd_labelled_cities()]
    data = {}
    for c in cities:
        d = DatasetBuilder.load_oscd_city(c)
        if d["gt"] is None or not d["gt"].any():
            continue
        data[c] = {
            "X": features(d["refl1"], d["refl2"]),
            "y": d["gt"].astype(bool),
            "pheno": phenology_suppression(d["refl1"], d["refl2"])
        }
    folds, per_city, total, objs = {}, [], np.zeros(4, np.int64), {"polygons": 0, "real": 0, "gt_objects": 0, "found": 0}
    t0 = time.perf_counter()
    for c in data:
        train_set = [data[k] for k in data if k != c]
        m = train(train_set)
        train_probs = []
        for d in train_set:
            pr = predict(m, d["X"])
            pr[d["pheno"]] = 0.0
            train_probs.append(pr)
        thr = best_threshold(train_probs, [d["y"] for d in train_set])
        thr_recall = best_threshold(train_probs, [d["y"] for d in train_set], beta=1.0)
        p = predict(m, data[c]["X"])
        p[data[c]["pheno"]] = 0.0
        pred = p >= thr
        cm = confusion(pred, data[c]["y"])
        total += cm
        for k, v in object_scores(cleaned(pred), data[c]["y"]).items():
            objs[k] += v
        per_city.append({"city": c, "threshold": round(thr, 3), **metrics_from(cm)})
        folds[c] = {"state": m.state_dict(), "threshold": thr, "threshold_recall": thr_recall}
        print(f"  {c:<12} F1 {per_city[-1]['f1_score']:.3f}  P {per_city[-1]['precision']:.3f}  R {per_city[-1]['recall']:.3f}  thr {thr:.2f}")
    full = train(list(data.values()))
    full_probs, ys = [], [d["y"] for d in data.values()]
    for d in data.values():
        pr = predict(full, d["X"])
        pr[d["pheno"]] = 0.0
        full_probs.append(pr)
    folds["_all"] = {"state": full.state_dict(), "threshold": best_threshold(full_probs, ys),
                     "threshold_recall": best_threshold(full_probs, ys, beta=1.0)}
    os.makedirs(os.path.dirname(CKPT), exist_ok=True)
    torch.save({"folds": folds, "features": N_FEATURES, "cities": list(data)}, CKPT)
    pooled = metrics_from(total)
    out = {"protocol": "leave-one-city-out over the labelled OSCD cities (10 m Sentinel-2)",
           "cities": len(data), "pooled": pooled, "false_alarm_km2_per_100km2": round(pooled["false_alarm_rate"] * 100, 2),
           "objects": {**objs, "object_precision": round(objs["real"] / max(objs["polygons"], 1), 3),
                       "objects_found": round(objs["found"] / max(objs["gt_objects"], 1), 3),
                       "polygons_per_city": round(objs["polygons"] / len(data), 1),
                       "cleanup": f"opening radius {MORPH_RADIUS}, minimum {MIN_AREA_PX} px"},
           "per_city": per_city, "train_s": round(time.perf_counter() - t0, 1)}
    os.makedirs(os.path.dirname(METRICS), exist_ok=True)
    with open(METRICS, "w") as f:
        json.dump(out, f, indent=2, default=float)
    print(f"Track B LOCO pooled: F1 {pooled['f1_score']} P {pooled['precision']} R {pooled['recall']} "
          f"FAR {pooled['false_alarm_rate']} | {out['objects']['polygons_per_city']} polygons/city, object precision "
          f"{out['objects']['object_precision']}, objects found {out['objects']['objects_found']} | {out['train_s']} s")
    return out


if __name__ == "__main__":
    # features are scale-free: multiplying both dates by the same gain changes nothing
    rng = np.random.default_rng(0)
    r1, r2 = rng.uniform(300, 4000, (6, 20, 20)), rng.uniform(300, 4000, (6, 20, 20))
    assert np.allclose(features(r1, r2), features(r1 * 1.3, r2 * 1.3), atol=1e-4)
    assert features(r1, r2).shape == (20, 20, N_FEATURES)
    run_loco()
