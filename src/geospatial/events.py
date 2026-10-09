"""
events.py - Event-impact detectors for Disaster mode (Ideation Baseline: Event Impact, hours-days ΔT).

The urban-change models (BIT, Track B) learned new buildings, not water or fire, so disaster sectors use
physically based per-pixel detectors on Sentinel-2 reflectance (B04 B03 B02 B08 B11 B12, x10000) with
fixed literature thresholds, validated against Copernicus EMS delineations (scripts/build_scenes.py):

- flood    : new water. MNDWI (green vs SWIR16) > 0 after the event where it was not water before.
- wildfire : burn severity dNBR = NBR_pre - NBR_post (NBR = NIR vs SWIR22). >= 0.27 is the USGS
             "moderate-low" break (Key & Benson 2006); classes up to "high" >= 0.66.

Each detector returns a probability-like score where 0.5 sits exactly on the rule's threshold, so the
standard vectorizer (prob_threshold 0.5) applies it and polygon magnitude reflects severity.
"""

from typing import Dict

import numpy as np

DNBR_CLASSES = ((0.66, "high severity"), (0.44, "moderate-high severity"), (0.27, "moderate-low severity"),
                (0.10, "low severity"))
DNBR_MIN = 0.27
EVENT_TYPES = {"flood": "Water / Flood Inundation", "wildfire": "Burn Scar"}


def nd(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    a, b = a.astype(np.float32), b.astype(np.float32)
    return (a - b) / np.maximum(a + b, 1e-6)


def flood_score(refl1: np.ndarray, refl2: np.ndarray) -> np.ndarray:
    """0.5 + MNDWI_post on pixels that were not water before (MNDWI_pre <= 0), else 0."""
    w1, w2 = nd(refl1[1], refl1[4]), nd(refl2[1], refl2[4])
    return np.where(w1 <= 0, np.clip(0.5 + w2, 0, 1), 0).astype(np.float32)


def dnbr(refl1: np.ndarray, refl2: np.ndarray) -> np.ndarray:
    return nd(refl1[3], refl1[5]) - nd(refl2[3], refl2[5])


def burn_score(refl1: np.ndarray, refl2: np.ndarray) -> np.ndarray:
    """dNBR scaled so DNBR_MIN maps to 0.5 and twice that (high severity) to 1."""
    return np.clip(dnbr(refl1, refl2) / (2 * DNBR_MIN), 0, 1).astype(np.float32)


SCORERS = {"flood": flood_score, "wildfire": burn_score}


def severity_class(d: float) -> str:
    return next((name for lo, name in DNBR_CLASSES if d >= lo), "unburnt / regrowth")


def describe(event: str, refl1: np.ndarray, refl2: np.ndarray, mask: np.ndarray) -> str:
    """Polygon summary from the same indices the detector used."""
    if event == "wildfire":
        d = float(dnbr(refl1, refl2)[mask].mean())
        return f"Burnt area, mean dNBR {d:.2f} ({severity_class(d)}, USGS classes)."
    w2 = float(nd(refl2[1], refl2[4])[mask].mean())
    return f"Newly flooded land: water index (MNDWI) {w2:+.2f} after the event, not water before."


def validate(pred: np.ndarray, ref: np.ndarray, scope: np.ndarray) -> Dict[str, float]:
    """Pixel agreement with a reference delineation, counted only where the reference mapped (scope)."""
    p, r = pred[scope], ref[scope]
    tp, fp, fn = int((p & r).sum()), int((p & ~r).sum()), int((~p & r).sum())
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    return {"precision": round(prec, 4), "recall": round(rec, 4),
            "f1_score": round(2 * prec * rec / (prec + rec), 4) if prec + rec else 0.0,
            "iou": round(tp / (tp + fp + fn), 4) if tp + fp + fn else 0.0,
            "detected_km2": round((tp + fp) * 100 / 1e6, 2), "reference_km2": round((tp + fn) * 100 / 1e6, 2)}


if __name__ == "__main__":
    t = lambda *v: np.stack([np.full((4, 4), x, np.float32) for x in v])
    field, water = t(900, 1100, 800, 3000, 2400, 1500), t(300, 700, 600, 300, 150, 80)
    forest, burnt = t(300, 500, 300, 3200, 1500, 700), t(600, 550, 450, 1200, 2000, 2200)
    assert (flood_score(field, water) > 0.5).all() and (flood_score(water, water) == 0).all()   # old water != flood
    assert (flood_score(field, field) < 0.5).all()
    assert (burn_score(forest, burnt) > 0.5).all() and (burn_score(forest, forest) < 0.5).all()
    assert severity_class(float(dnbr(forest, burnt).mean())) == "high severity"
    v = validate(np.array([1, 1, 0, 0], bool), np.array([1, 0, 1, 0], bool), np.ones(4, bool))
    assert v["precision"] == 0.5 and v["recall"] == 0.5
    print("events self-check ok")
