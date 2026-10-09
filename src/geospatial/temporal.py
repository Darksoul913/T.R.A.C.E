"""
temporal.py - Temporal Context Engine (Ideation #19) on a stack of dated Sentinel-2 frames.

Per polygon, from its mean spectral index in every frame:

- change dating  : the first frame where the index had moved past the change rule's threshold from the
                   earliest frame (evidence for notices and courts: "first visible between A and B")
- pre-existing   : already visible at or before the pair's "before" image (wrong-baseline check)
- persistence    : did it hold in every later frame, or revert (transient)
- seasonal check : is the pair's change larger than this spot's own seasonal swing (post-monsoon vs dry
                   season pair) and its year-to-year noise? If not, it is downgraded as seasonal
- recovery       : disaster mode, after the event: flood water still present, burnt area regaining NBR

Frames with less than MIN_OBSERVED of the polygon observable (SCL cloud / shadow / no data) count as
missing, never as "no change".
"""

import math
from typing import Dict, List, Optional, Sequence

import numpy as np

MIN_OBSERVED = 0.5
# index and the direction a change type moves it; thresholds are the change-type rules
# (spectral_indices.py: NDBI +0.10, NDVI -0.15 / +0.20, MNDWI +0.20, NBR -0.25)
INDEX_FOR = {
    "New Built-up Surface": ("ndbi", 1), "Vegetation Cleared / Possible Construction": ("ndbi", 1),
    "Water-body Encroachment": ("ndbi", 1), "Slow Built-up Creep": ("ndbi", 1), "New Building / Structure": ("ndbi", 1),
    "Structural Change": ("ndbi", 1), "Precursor: Cleared Plot": ("ndvi", -1), "Precursor: New Track": ("ndvi", -1),
    "Seasonal Vegetation Change": ("ndvi", -1), "Vegetation Loss / Clearing": ("ndvi", -1),
    "Vegetation Regrowth": ("ndvi", 1), "Water / Flood Inundation": ("mndwi", 1), "Burn Scar": ("nbr", -1),
}
RULE_DELTA = {"ndbi": 0.10, "ndvi": 0.15, "mndwi": 0.20, "nbr": 0.25}
MIN_DELTA = 0.03
NAMES = {"ndbi": "NDBI", "ndvi": "NDVI", "mndwi": "MNDWI", "nbr": "NBR"}


def nd(a, b):
    a, b = a.astype(np.float32), b.astype(np.float32)
    return (a - b) / np.maximum(a + b, 1e-6)


def indices(refl: np.ndarray) -> Dict[str, np.ndarray]:
    """Reflectance (B04 B03 B02 B08 B11 B12) -> NDBI, NDVI, MNDWI, NBR."""
    return {"ndbi": nd(refl[4], refl[3]), "ndvi": nd(refl[3], refl[0]), "mndwi": nd(refl[1], refl[4]),
            "nbr": nd(refl[3], refl[5])}


def polygon_means(labels: np.ndarray, n: int, arr: np.ndarray, valid: np.ndarray):
    """Mean of arr over each label 1..n using only valid pixels, and the observed share of each label."""
    lab = labels.ravel()
    v = valid.ravel()
    total = np.bincount(lab, minlength=n + 1)[1:]
    seen = np.bincount(lab, weights=v, minlength=n + 1)[1:]
    s = np.bincount(lab, weights=np.where(v, arr.ravel(), 0), minlength=n + 1)[1:]
    obs = np.where(total > 0, seen / np.maximum(total, 1), 0)
    return np.where(seen > 0, s / np.maximum(seen, 1), np.nan), obs


def index_for(change_type: str, deltas: Optional[Dict[str, float]] = None):
    """(index, direction) for a change type; for types without one (ground disturbance), the index that
    moved most between the pair."""
    if change_type in INDEX_FOR:
        return INDEX_FOR[change_type]
    deltas = {k: v for k, v in (deltas or {}).items() if v is not None and v == v}   # drop None / NaN
    if not deltas:
        return "ndbi", 1
    k = max(deltas, key=lambda x: abs(deltas[x]))
    return k, 1 if deltas[k] >= 0 else -1


def date_change(values: Sequence[Optional[float]], t1_i: int, t2_i: int, index: str, direction: int,
                swing: Optional[float] = None) -> Dict:
    """Change dating, persistence and seasonal check for one polygon's index series (None = not observed)."""
    obs = [i for i, v in enumerate(values) if v is not None]
    if len(obs) < 3:
        return {"assessed": False, "reason": "fewer than 3 observable frames"}
    pre = [values[i] for i in obs if i <= t1_i] or [values[obs[0]]]
    early = [values[i] for i in obs if i < t1_i]
    # pre-existing: the change was already well under way at the before-image compared with earlier years
    # (the wrong-baseline problem); then it is dated against those earlier years
    rise = direction * (values[t1_i] - float(np.median(early))) if early and values[t1_i] is not None else 0.0
    pre_existing = rise >= max(MIN_DELTA, 0.5 * RULE_DELTA[index])
    base = float(np.median(early)) if pre_existing else float(np.median(pre))
    rel = {i: direction * (values[i] - base) for i in obs}
    end = t2_i if values[t2_i] is not None else obs[-1]
    delta = max(MIN_DELTA, min(RULE_DELTA[index], 0.6 * abs(rel[end])))
    start = obs[0] if pre_existing else t1_i
    first = next((i for i in obs if i > start and rel[i] >= delta), None)
    out = {"assessed": True, "delta": round(delta, 3), "first_seen": first, "pre_existing": bool(pre_existing),
           "last_clear": max((i for i in obs if i < first), default=None) if first is not None else None}
    if first is None:
        out.update(persistent=None, persist=[0, 0])
    else:
        # persistent: still there in the latest image and in at least 3 of every 4 later images (one noisy or
        # odd-month frame is not a reversal); reverted: the frame from which it never came back
        later = [i for i in obs if i > first]
        hold = [i for i in later if rel[i] >= 0.5 * delta]
        last_ok = not later or rel[later[-1]] >= 0.5 * delta
        gone = None if last_ok else next(i for i in later if all(rel[j] < 0.5 * delta for j in later if j >= i))
        out.update(persist=[len(hold), len(later)], persistent=last_ok and len(hold) >= math.ceil(0.75 * len(later)),
                   reverted=gone)
    # seasonal check: the pair's own change vs this spot's seasonal swing and same-season year-to-year noise.
    # The yearly frames share one season window, so a change that holds in two or more later frames is not a
    # seasonal swing, however large this spot's monsoon-to-dry-season swing is (tidal marsh, paddy).
    if values[t1_i] is not None and values[t2_i] is not None:
        change = direction * (values[t2_i] - values[t1_i])
        steps = np.abs(np.diff([values[i] for i in obs]))
        noise = float(np.median(np.sort(steps)[:-1])) if len(steps) > 1 else 0.0   # drop the largest step: the change itself
        bar = max(swing or 0.0, 2 * noise)
        held = bool(out.get("persistent")) and out["persist"][1] >= 2
        verdict = "not confirmed" if change <= MIN_DELTA else "real" if change > bar or held else "seasonal"
        out["seasonal"] = {"verdict": verdict, "change": round(change, 3), "swing": None if swing is None else round(swing, 3),
                           "noise": round(noise, 3), "held": held}
    return out


def recovery(event: str, values: Sequence[Optional[float]], shares: Sequence[Optional[float]]) -> Dict:
    """Disaster frames [pre, post, revisit...]. Flood: share of the polygon still water in each revisit.
    Wildfire: share of the NBR lost in the fire that has come back (0 = still burnt, 1 = pre-fire level)."""
    pre, post = values[0], values[1]
    rec = []
    for v, s in zip(values[2:], shares[2:]):
        if v is None:
            rec.append(None)
        elif event == "flood":
            rec.append(round(float(s), 3))
        else:
            lost = (pre - post) if pre is not None and post is not None else None
            rec.append(round(float(np.clip((v - post) / lost, -0.5, 1.5)), 3) if lost and lost > 0 else None)
    if event == "flood":
        gone = next((i for i, r in enumerate(rec) if r is not None and r < 0.1), None)
        status = "still flooded" if gone is None and any(r is not None for r in rec) else "receded"
        return {"metric": "share still water", "per_revisit": rec, "receded_at": None if gone is None else gone + 2, "status": status}
    done = next((i for i, r in enumerate(rec) if r is not None and r >= 0.8), None)
    return {"metric": "share of lost NBR regained", "per_revisit": rec, "recovered_at": None if done is None else done + 2,
            "status": "recovered" if done is not None else "recovering" if any(r and r > 0.2 for r in rec) else "still burnt"}


def label_values(stack: List[Dict[str, np.ndarray]], valid: List[np.ndarray], labels: np.ndarray, n: int,
                 index: str, threshold: Optional[float] = None):
    """Per-frame (means, observed share) and, with threshold, the share of each polygon above it."""
    means, obs, above = [], [], []
    for frame, ok in zip(stack, valid):
        m, o = polygon_means(labels, n, frame[index], ok)
        means.append(m)
        obs.append(o)
        if threshold is not None:
            a, _ = polygon_means(labels, n, (frame[index] > threshold).astype(np.float32), ok)
            above.append(a)
    to_list = lambda arrs, j: [None if (o[j] < MIN_OBSERVED or np.isnan(a[j])) else round(float(a[j]), 3) for a, o in zip(arrs, obs)]
    return [(to_list(means, j), to_list(above, j) if above else None) for j in range(n)]


if __name__ == "__main__":
    # creep that starts in frame 3 and stays; the pair is frames 2 -> 8
    v = [0.10, 0.11, 0.10, 0.17, 0.22, 0.24, 0.25, None, 0.26, 0.27]
    r = date_change(v, 2, 8, "ndbi", 1, swing=0.02)
    assert r["first_seen"] == 4 and r["last_clear"] == 3 and r["persistent"] and not r["pre_existing"], r
    assert r["seasonal"]["verdict"] == "real", r
    # change already there before the pair's before-image: wrong baseline
    r = date_change([0.10, 0.25, 0.26, 0.26, 0.27], 2, 4, "ndbi", 1)
    assert r["pre_existing"] and r["first_seen"] == 1, r
    # transient: rises then falls back for good
    r = date_change([0.10, 0.10, 0.30, 0.31, 0.11, 0.10], 1, 3, "ndbi", 1)
    assert not r["persistent"] and r["reverted"] == 4, r
    # one odd frame among later ones is not a reversal
    r = date_change([0.10, 0.10, 0.30, 0.31, 0.12, 0.30, 0.31, 0.32], 1, 3, "ndbi", 1)
    assert r["persistent"] and r["reverted"] is None and r["persist"] == [4, 5], r
    # an NDVI drop no bigger than the spot's normal post-monsoon -> dry-season swing is seasonal
    r = date_change([0.62, 0.60, 0.63, 0.45, 0.61, 0.60], 2, 3, "ndvi", -1, swing=0.25)
    assert r["seasonal"]["verdict"] == "seasonal", r
    # a big jump at a spot with a bigger monsoon swing still counts as real once it holds year after year
    r = date_change([0.0, 0.02, 0.01, 0.38, 0.37, 0.40, 0.39], 2, 4, "ndbi", 1, swing=0.5)
    assert r["seasonal"]["verdict"] == "real" and r["seasonal"]["held"], r
    assert not date_change([0.1, None, None, 0.2], 0, 3, "ndbi", 1)["assessed"]
    # flood: 60 % then 5 % still water -> receded at the second revisit (frame index 3)
    fr = recovery("flood", [-0.3, 0.4, 0.1, -0.2], [0.0, 1.0, 0.6, 0.05])
    assert fr["status"] == "receded" and fr["receded_at"] == 3, fr
    # fire: NBR 0.6 -> -0.2, back to 0.0 then 0.5 -> 25 % then 87.5 % regained
    ff = recovery("wildfire", [0.6, -0.2, 0.0, 0.5], [None] * 4)
    assert ff["per_revisit"] == [0.25, 0.875] and ff["recovered_at"] == 3, ff
    # polygon means honour the valid mask
    lab = np.array([[1, 1], [2, 0]])
    m, o = polygon_means(lab, 2, np.array([[1.0, 3.0], [5.0, 9.0]]), np.array([[True, False], [True, True]]))
    assert m.tolist() == [1.0, 5.0] and o.tolist() == [0.5, 1.0]
    print("temporal self-check ok")
