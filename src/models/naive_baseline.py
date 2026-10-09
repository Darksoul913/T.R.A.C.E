"""
naive_baseline.py - Naive Spectral Change Baseline Comparator (Feature #2).
Computes pixel-wise NDVI / spectral difference thresholding to serve as a live
benchmark showing why deep learning + false-alarm filtering is required.
"""

from typing import Tuple
import numpy as np


class NaiveBaselineComparator:
    """
    Computes naive NDVI/spectral difference.
    Demonstrates the 'False Alarm Avalanche' in traditional thresholding.
    """

    @staticmethod
    def compute_ndvi(red_band: np.ndarray, nir_band: np.ndarray) -> np.ndarray:
        """Computes Normalized Difference Vegetation Index (NDVI)."""
        red = red_band.astype(np.float32)
        nir = nir_band.astype(np.float32)
        denom = nir + red
        denom[denom == 0] = 1e-6
        ndvi = (nir - red) / denom
        return np.clip(ndvi, -1.0, 1.0)

    @staticmethod
    def compute_pseudo_ndvi_rgb(rgb_img: np.ndarray) -> np.ndarray:
        """
        Computes visible Green-Red difference index for RGB imagery without NIR:
        (Green - Red) / (Green + Red)
        """
        r = rgb_img[0].astype(np.float32)
        g = rgb_img[1].astype(np.float32)
        denom = g + r
        denom[denom == 0] = 1e-6
        vndvi = (g - r) / denom
        return np.clip(vndvi, -1.0, 1.0)

    @classmethod
    def compute_naive_change(
        cls,
        img_t1: np.ndarray,
        img_t2: np.ndarray,
        threshold: float = 0.20
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Computes naive difference heatmap and binary change mask.

        Args:
            img_t1: (C, H, W) array for T1
            img_t2: (C, H, W) array for T2
            threshold: cutoff for naive binary classification

        Returns:
            diff_map: Continuous difference map [0.0, 1.0]
            binary_mask: Binary mask where difference > threshold (uint8 0 or 1)
        """
        # If 4 bands (RGB + NIR) available (e.g. Sentinel-2 OSCD)
        if img_t1.shape[0] >= 4 and img_t2.shape[0] >= 4:
            # Band 0: Red, Band 3: NIR
            ndvi1 = cls.compute_ndvi(img_t1[0], img_t1[3])
            ndvi2 = cls.compute_ndvi(img_t2[0], img_t2[3])
            diff_map = np.abs(ndvi2 - ndvi1)
        else:
            # Fall back to RGB pseudo-NDVI or euclidean color distance
            p_ndvi1 = cls.compute_pseudo_ndvi_rgb(img_t1)
            p_ndvi2 = cls.compute_pseudo_ndvi_rgb(img_t2)
            # Combine spectral index drift with intensity drift
            spec_diff = np.abs(p_ndvi2 - p_ndvi1)
            intensity_diff = np.mean(
                np.abs(img_t2.astype(np.float32) - img_t1.astype(np.float32)) / 255.0,
                axis=0
            )
            diff_map = (spec_diff + intensity_diff) / 2.0

        # Normalize difference to [0, 1]
        diff_norm = np.clip(diff_map / (diff_map.max() + 1e-6), 0.0, 1.0)
        binary_mask = (diff_map > threshold).astype(np.uint8)

        return diff_norm, binary_mask
