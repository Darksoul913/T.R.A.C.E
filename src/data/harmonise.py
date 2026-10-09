"""
harmonise.py - Input harmonisation before change detection (Ideation Baseline #1).

1. align()                  : put T2 on T1's grid when CRS / transform / shape differ.
2. correct_shift()          : estimate and undo a small (1-3 px) misregistration of one image against another.
                              Pipelines register T1 onto T2: outputs stay in the post-event frame (where new
                              structures are, and where LEVIR-CD's labels are drawn).
3. stable_pixel_normalise() : per-band linear gain/offset T2 -> T1 fitted only on low-change
                              ("stable") pixels, so large real change (a flood, a new estate)
                              doesn't get normalised away the way global histogram matching does.
"""

from typing import Any, Dict, Tuple

import numpy as np
from rasterio.warp import Resampling, reproject
from scipy.ndimage import shift as nd_shift
from skimage.registration import phase_cross_correlation

MAX_SHIFT_PX = 3.0
MIN_SHIFT_PX = 1.0


def align(t1: np.ndarray, t2: np.ndarray, meta1: Dict[str, Any], meta2: Dict[str, Any]) -> Tuple[np.ndarray, bool]:
    """Returns T2 resampled onto T1's grid (meta = {'transform', 'crs'}), and whether it had to be."""
    same = (meta1["crs"] == meta2["crs"] and meta1["transform"] == meta2["transform"] and t1.shape[1:] == t2.shape[1:])
    if same:
        return t2, False
    out = np.zeros((t2.shape[0],) + t1.shape[1:], dtype=t2.dtype)
    for b in range(t2.shape[0]):
        reproject(t2[b], out[b], src_transform=meta2["transform"], src_crs=meta2["crs"],
                  dst_transform=meta1["transform"], dst_crs=meta1["crs"], resampling=Resampling.bilinear)
    return out, True


def _gray(img: np.ndarray) -> np.ndarray:
    return img[:3].astype(np.float32).mean(axis=0)


def correct_shift(t1: np.ndarray, t2: np.ndarray, max_shift_px: float = MAX_SHIFT_PX,
                  min_shift_px: float = MIN_SHIFT_PX) -> Tuple[np.ndarray, Tuple[float, float]]:
    """Sub-pixel phase correlation on grayscale. Shifts T2 only when the offset is between min_shift_px and
    max_shift_px; a larger estimate is more likely real change than misregistration, so it is ignored."""
    (dy, dx), _, _ = phase_cross_correlation(_gray(t1), _gray(t2), upsample_factor=10)
    if max(abs(dy), abs(dx)) > max_shift_px or max(abs(dy), abs(dx)) < min_shift_px:
        return t2, (0.0, 0.0)
    return apply_shift(t2, (dy, dx)), (float(dy), float(dx))


def apply_shift(img: np.ndarray, shift: Tuple[float, float]) -> np.ndarray:
    """Applies a (dy, dx) shift from correct_shift() to another stack on the same grid (e.g. reflectance bands)."""
    if shift == (0.0, 0.0):
        return img
    return np.stack([nd_shift(img[b].astype(np.float32), shift, order=1, mode="nearest") for b in range(img.shape[0])]).astype(img.dtype)


def stable_pixel_normalise(t1: np.ndarray, t2: np.ndarray, stable_frac: float = 0.6) -> np.ndarray:
    """Per band, fits T1 ≈ gain·T2 + offset on the stable_frac least-changed pixels and applies it to T2.
    ponytail: one global linear fit per band (relative radiometric normalisation); IR-MAD would pick
    stable pixels more robustly if this proves too crude."""
    a, b = t1.astype(np.float32), t2.astype(np.float32)
    scale = np.maximum(a.reshape(a.shape[0], -1).std(axis=1), 1e-6)[:, None, None]
    score = (np.abs(a - b) / scale).mean(axis=0)
    stable = score <= np.quantile(score, stable_frac)
    out = np.empty_like(b)
    for i in range(b.shape[0]):
        x, y = b[i][stable], a[i][stable]
        var = x.var()
        # least-squares gain/offset; a near-constant band (var ~ 0) or wild fit falls back towards gain 1
        gain = float(np.clip(((x - x.mean()) * (y - y.mean())).mean() / var, 0.5, 2.0)) if var > 1e-8 else 1.0
        out[i] = gain * b[i] + (y.mean() - gain * x.mean())
    lo, hi = (0.0, 1.0) if t2.dtype.kind == "f" and t2.max() <= 1.0 else (0.0, float(np.iinfo(t2.dtype).max) if t2.dtype.kind in "ui" else np.inf)
    return np.clip(out, lo, hi).astype(t2.dtype)


if __name__ == "__main__":
    rng = np.random.default_rng(0)
    t1 = rng.uniform(0.1, 0.6, (3, 128, 128)).astype(np.float32)
    t1 = np.stack([np.clip(t1[b] + np.sin(np.arange(128) / 6.0)[None, :] * 0.2, 0, 1) for b in range(3)])

    # 1. a 2-px shift is found and undone
    t2 = np.roll(t1, (2, -1), axis=(1, 2))
    fixed, (dy, dx) = correct_shift(t1, t2)
    assert abs(dy + 2) < 0.2 and abs(dx - 1) < 0.2, (dy, dx)
    assert np.abs(fixed[:, 10:-10, 10:-10] - t1[:, 10:-10, 10:-10]).mean() < 0.02

    # 2. darkened T2 with a big bright "flood" patch: stable-pixel fit restores the background
    #    without erasing the patch, which global histogram matching would partly do
    t2 = t1 * 0.7
    t2[:, :50, :50] = 0.95
    norm = stable_pixel_normalise(t1, t2)
    assert np.abs(norm[:, 70:, 70:] - t1[:, 70:, 70:]).mean() < 0.01
    assert (norm[:, :50, :50] - t1[:, :50, :50]).mean() > 0.3

    # 3. align is a no-op on identical grids
    from rasterio.transform import from_origin
    m = {"transform": from_origin(0, 0, 10, 10), "crs": "EPSG:32643"}
    assert align(t1, t2, m, m)[1] is False
    print("harmonise self-check ok")
