"""
stress_test.py - Robustness Stress Test (Stretch Feature #13).

Perturbs only T2 (global brightness shifts, synthetic cast shadows) on the LEVIR-CD test
split and measures pooled F1 / false alarm rate for T.R.A.C.E. with and without
histogram matching, and for the naive baseline. Ground truth is unchanged, so any
new detections under a perturbation are pure false alarms.

    .venv/bin/python src/models/stress_test.py
"""

import os
import sys
import json
import zlib

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import numpy as np
from scipy.ndimage import gaussian_filter, shift as nd_shift

from src.data.harmonise import correct_shift
from src.models.evaluate import confusion, metrics_from, levir_png_samples, geotiff_samples
from src.models.infer import TiledInferenceEngine
from src.models.naive_baseline import NaiveBaselineComparator


def brightness(factor):
    return lambda img, rng: np.clip(img.astype(np.float32) * factor, 0, 255).astype(np.uint8)


def shadows(img, rng, count=6, darken=0.45):
    """Soft elliptical shadows covering roughly 15-20% of the tile."""
    _, h, w = img.shape
    yy, xx = np.mgrid[:h, :w]
    mask = np.zeros((h, w), np.float32)
    for _ in range(count):
        cy, cx = rng.uniform(0, h), rng.uniform(0, w)
        ry, rx = rng.uniform(0.06, 0.16) * h, rng.uniform(0.06, 0.16) * w
        mask[((yy - cy) / ry) ** 2 + ((xx - cx) / rx) ** 2 <= 1] = 1
    mask = gaussian_filter(mask, sigma=max(h, w) / 200)
    return np.clip(img.astype(np.float32) * (1 - (1 - darken) * mask), 0, 255).astype(np.uint8)


CONDITIONS = {
    "Clean": lambda img, rng: img,
    "Brightness -30%": brightness(0.70),
    "Brightness -15%": brightness(0.85),
    "Brightness +15%": brightness(1.15),
    "Brightness +30%": brightness(1.30),
    "Cast shadows": shadows,
}
# AI variants: radiometric normalisation none / global histogram / stable-pixel
METHODS = ("ai_raw", "ai_hist_matched", "ai_stable", "naive")
LABELS = {"ai_raw": "AI raw", "ai_hist_matched": "AI + hist match", "ai_stable": "AI + stable norm", "naive": "Naive"}
MISREG = (2, 1)   # px; applied to T1 because LEVIR-CD labels are drawn on T2


def run_stress_test(levir_root="data/raw/levir_cd_test", data_dir="data/geotiff",
                    output_path="data/outputs/stress_test.json"):
    if os.path.isdir(os.path.join(levir_root, "label")):
        samples, dataset = levir_png_samples, "LEVIR-CD official test split"
        src = levir_root
    else:
        samples, dataset = lambda d: geotiff_samples(d, "levir_*_t1_pre.tif"), "LEVIR-CD test tiles (local subset)"
        src = data_dir

    engine = TiledInferenceEngine()
    totals = {c: {m: np.zeros(4, np.int64) for m in METHODS} for c in CONDITIONS}
    n = 0
    for name, t1, t2, gt, _ in samples(src):
        n += 1
        for cond, perturb in CONDITIONS.items():
            t2p = perturb(t2, np.random.default_rng(zlib.crc32(name.encode())))
            for m, norm in (("ai_raw", "none"), ("ai_hist_matched", "global"), ("ai_stable", "stable")):
                totals[cond][m] += confusion(engine.run_inference(t1, t2p, normalize_radiometry=norm) > 0.5, gt)
            totals[cond]["naive"] += confusion(NaiveBaselineComparator.compute_naive_change(t1, t2p, threshold=0.18)[1], gt)
        if n % 16 == 0:
            print(f"  {n} pairs done")

    misreg = misregistration_check(engine, samples, src)
    result = {
        "dataset": dataset,
        "misregistration": misreg,
        "samples": n,
        "perturbation": "applied to T2 only; ground truth unchanged",
        "conditions": [{"name": c, **{m: metrics_from(totals[c][m]) for m in METHODS}} for c in CONDITIONS],
    }
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(result, f, indent=2)

    print("=" * 118)
    print(f"Stress test · {dataset} · {n} pairs   (F1 / false alarm rate)")
    print(f"  {'Condition':<20}" + "".join(f"{LABELS[m]:>20}" for m in METHODS))
    for c in result["conditions"]:
        print(f"  {c['name']:<20}" + "".join(f"{c[m]['f1_score']:>11.3f} / {c[m]['false_alarm_rate']:<6.3f}" for m in METHODS))
    print(f"  T1 misregistered {MISREG} px: AI raw F1 {misreg['ai_raw']['f1_score']:.3f} -> registered "
          f"{misreg['ai_registered']['f1_score']:.3f} ({misreg['corrected_pairs']} pairs corrected)")
    print("=" * 118)
    return result


def misregistration_check(engine, samples, src):
    """T1 shifted by MISREG px: AI as-is vs after registering T1 onto T2 (harmonise.correct_shift)."""
    raw, reg, applied = np.zeros(4, np.int64), np.zeros(4, np.int64), 0
    for _, t1, t2, gt, _ in samples(src):
        t1p = np.stack([nd_shift(b, MISREG, order=0, mode="nearest") for b in t1])
        fixed, sh = correct_shift(t2, t1p)
        applied += sh != (0.0, 0.0)
        raw += confusion(engine.run_inference(t1p, t2) > 0.5, gt)
        reg += confusion(engine.run_inference(fixed, t2) > 0.5, gt)
    return {"shift_px": list(MISREG), "ai_raw": metrics_from(raw), "ai_registered": metrics_from(reg), "corrected_pairs": applied}


def _self_check():
    img = np.full((3, 64, 64), 200, np.uint8)
    assert brightness(1.3)(img, None).max() == 255 and brightness(0.5)(img, None).max() == 100
    s = shadows(img, np.random.default_rng(0))
    assert s.shape == img.shape and s.min() < 120 and s.max() == 200


if __name__ == "__main__":
    _self_check()
    run_stress_test()
