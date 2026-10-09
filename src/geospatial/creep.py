"""
creep.py - Missed-encroachment defence (Ideation Baseline #12).

A pairwise detector compares two dates; encroachment that creeps in a little every year never crosses
its threshold between any two consecutive images. Over a yearly series this module flags:

1. Slow built-up creep : NDBI rises steadily (robust Theil-Sen trend) to a cumulative gain above the pair
                         threshold, while no single year-to-year step does.
2. Precursors          : cleared plots (vegetation removed, built-up index up but still below the
                         built-up threshold) and new tracks (thin, linear cleared strips).
3. Recall-first zones  : inside protected / water buffers every threshold is lowered.

Pixels that are unobservable (SCL cloud / shadow / no data) in any year are excluded, not assumed stable.
"""

from itertools import combinations
from typing import Dict, Optional

import numpy as np
from scipy.ndimage import label
from skimage.morphology import skeletonize

PAIR_RISE = 0.10          # a single-step NDBI rise the pairwise rules call built-up (spectral_indices.NDBI_RISE)
CUM_RISE = 0.10           # cumulative trend rise that counts as creep
POSITIVE_STEPS = 0.6      # share of year-to-year steps that must be rises (steady, not one jump + noise)
RECALL_FACTOR = 0.5       # thresholds are multiplied by this inside protected / water buffers
CLEAR_NDVI_DROP = 0.15
TRACK_MIN_LEN_PX = 15
TRACK_THINNESS = 0.25     # skeleton length / area: a w-px-wide strip is ~1/w, a square plot ~0.06


def nd(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    a, b = a.astype(np.float32), b.astype(np.float32)
    return (a - b) / np.maximum(a + b, 1e-6)


def theil_sen(series: np.ndarray) -> np.ndarray:
    """Per-pixel median of pairwise slopes, (T, H, W) -> (H, W) per time step."""
    slopes = [(series[j] - series[i]) / (j - i) for i, j in combinations(range(series.shape[0]), 2)]
    return np.median(np.stack(slopes), axis=0)


def detect(refl: np.ndarray, valid: np.ndarray, protected: Optional[np.ndarray] = None) -> Dict[str, np.ndarray]:
    """refl: (T, 6, H, W) yearly reflectance (B04 B03 B02 B08 B11 B12), valid: (T, H, W) observable.
    Returns boolean masks creep / cleared / track / unobservable plus per-year NDBI and NDVI."""
    ndbi = np.stack([nd(r[4], r[3]) for r in refl])
    ndvi = np.stack([nd(r[3], r[0]) for r in refl])
    observable = valid.all(axis=0)
    scale = np.where(protected, RECALL_FACTOR, 1.0) if protected is not None else 1.0
    steps = np.diff(ndbi, axis=0)
    trend = theil_sen(ndbi) * (ndbi.shape[0] - 1)
    creep = (observable & (trend >= CUM_RISE * scale) & (steps.max(axis=0) < PAIR_RISE)
             & ((steps > 0).mean(axis=0) >= POSITIVE_STEPS))

    d_ndvi, d_ndbi = ndvi[-1] - ndvi[0], ndbi[-1] - ndbi[0]
    cleared = observable & ~creep & (d_ndvi <= -CLEAR_NDVI_DROP * scale) & (d_ndbi > 0.02) & (d_ndbi < PAIR_RISE)
    track = np.zeros_like(cleared)
    lab, n = label(cleared)
    for i in range(1, n + 1):
        comp = lab == i
        length = skeletonize(comp).sum()
        if length >= TRACK_MIN_LEN_PX and length / comp.sum() >= TRACK_THINNESS:
            track |= comp
    return {"creep": creep, "cleared": cleared & ~track, "track": track, "unobservable": ~observable,
            "ndbi": ndbi, "ndvi": ndvi}


if __name__ == "__main__":
    T, H, W = 7, 60, 60
    rng = np.random.default_rng(0)
    base = np.array([800, 900, 700, 3000, 1800, 1000], np.float32)[:, None, None] * np.ones((6, H, W), np.float32)
    refl = np.stack([base.copy() for _ in range(T)])
    for t in range(T):
        refl[t] += rng.normal(0, 15, refl[t].shape)                     # sensor noise
        refl[t, 4, 5:20, 5:20] *= 1 + 0.06 * t                          # creep: SWIR up ~5%/yr -> NDBI +0.03/yr
        if t >= 3:
            refl[t, 4, 30:45, 5:20] *= 1.6                              # sudden: one big jump
        f = t / (T - 1)                                                  # track: 3 px strip cleared to bare soil
        refl[t, 0, 50:53, 5:55] = 800 + 400 * f                         # red up, NIR down -> NDVI -0.33
        refl[t, 3, 50:53, 5:55] = 3000 - 1000 * f
        refl[t, 4, 50:53, 5:55] = 1800 - 467 * f                        # NDBI only +0.05: not built-up
    valid = np.ones((T, H, W), bool)
    valid[2, 30:35, 40:45] = False                                      # cloud in one year
    out = detect(refl, valid)
    assert out["creep"][7:18, 7:18].mean() > 0.9, out["creep"][7:18, 7:18].mean()      # creep found
    assert not out["creep"][30:45, 5:20].any()                                           # sudden jump is not creep
    assert out["creep"][25:, 25:].mean() < 0.01                                          # noise is not creep
    assert out["track"][50:53, 10:50].mean() > 0.9, out["track"][50:53, 10:50].mean()  # thin strip -> track
    assert out["unobservable"][30:35, 40:45].all() and not out["creep"][30:35, 40:45].any()
    prot = np.zeros((H, W), bool)
    prot[5:20, 25:40] = True
    refl2 = refl.copy()
    for t in range(T):
        refl2[t, 4, 5:20, 25:40] *= 1 + 0.03 * t                        # half-speed creep
    assert not detect(refl2, valid)["creep"][7:18, 27:38].any()
    assert detect(refl2, valid, prot)["creep"][7:18, 27:38].mean() > 0.9                 # only recall-first catches it
    print("creep self-check ok")
