"""
spectral_indices.py - Spectral Index Computations & Semantic Change Labelling (Feature #5 & #6).

Computes:
1. NDVI (Normalized Difference Vegetation Index)
2. NDBI (Normalized Difference Built-up Index)
3. NDWI (Normalized Difference Water Index)
4. Semantic change-type classification (Built-up, Vegetation Loss, Flood/Water, Disturbance).
"""

from typing import Tuple, Dict, Any
import numpy as np


class SpectralClassifier:
    """Computes remote sensing spectral indices and classifies polygon change semantics."""

    @staticmethod
    def calc_ndvi(red: np.ndarray, nir: np.ndarray) -> np.ndarray:
        """NDVI = (NIR - Red) / (NIR + Red)"""
        red = red.astype(np.float32)
        nir = nir.astype(np.float32)
        denom = nir + red
        denom[denom == 0] = 1e-6
        return np.clip((nir - red) / denom, -1.0, 1.0)

    @staticmethod
    def calc_ndwi(green: np.ndarray, nir: np.ndarray) -> np.ndarray:
        """NDWI (McFeeters) = (Green - NIR) / (Green + NIR)"""
        green = green.astype(np.float32)
        nir = nir.astype(np.float32)
        denom = green + nir
        denom[denom == 0] = 1e-6
        return np.clip((green - nir) / denom, -1.0, 1.0)

    @staticmethod
    def calc_ndbi(swir: np.ndarray, nir: np.ndarray) -> np.ndarray:
        """NDBI = (SWIR - NIR) / (SWIR + NIR)"""
        swir = swir.astype(np.float32)
        nir = nir.astype(np.float32)
        denom = swir + nir
        denom[denom == 0] = 1e-6
        return np.clip((swir - nir) / denom, -1.0, 1.0)

    @classmethod
    def classify_polygon_change(
        cls,
        t1_bands: np.ndarray,
        t2_bands: np.ndarray,
        mask: np.ndarray
    ) -> Dict[str, Any]:
        """
        Calculates internal spectral shifts inside a polygon mask and labels the change type.

        Args:
            t1_bands: (C, H, W) array for T1 (e.g. B04 Red, B03 Green, B02 Blue, B08 NIR)
            t2_bands: (C, H, W) array for T2
            mask: (H, W) boolean mask for the polygon

        Returns:
            dict containing change_type, d_ndvi, d_ndwi, and explanation
        """
        if not np.any(mask):
            return {
                "change_type": "Unknown",
                "d_ndvi": 0.0,
                "d_ndwi": 0.0,
                "summary": "Empty mask"
            }

        # Cast before any arithmetic: uint8 band sums overflow (e.g. NIR + Red > 255 wraps)
        t1_bands = t1_bands.astype(np.float32)
        t2_bands = t2_bands.astype(np.float32)
        c = t1_bands.shape[0]

        # Case 1: Multispectral with NIR (e.g. Sentinel-2 OSCD: Red=0, Green=1, Blue=2, NIR=3)
        if c >= 4:
            r1, g1, b1, nir1 = t1_bands[0][mask], t1_bands[1][mask], t1_bands[2][mask], t1_bands[3][mask]
            r2, g2, b2, nir2 = t2_bands[0][mask], t2_bands[1][mask], t2_bands[2][mask], t2_bands[3][mask]

            ndvi1 = np.mean((nir1.astype(np.float32) - r1.astype(np.float32)) / (nir1 + r1 + 1e-6))
            ndvi2 = np.mean((nir2.astype(np.float32) - r2.astype(np.float32)) / (nir2 + r2 + 1e-6))
            d_ndvi = float(ndvi2 - ndvi1)

            ndwi1 = np.mean((g1.astype(np.float32) - nir1.astype(np.float32)) / (g1 + nir1 + 1e-6))
            ndwi2 = np.mean((g2.astype(np.float32) - nir2.astype(np.float32)) / (g2 + nir2 + 1e-6))
            d_ndwi = float(ndwi2 - ndwi1)

            # Heuristic decision tree for semantic labeling
            if d_ndwi > 0.20:
                change_type = "Water / Flood Inundation"
                summary = f"Significant increase in surface water moisture (ΔNDWI = {d_ndwi:+.2f})."
            elif d_ndvi < -0.15:
                change_type = "Vegetation Loss / Clearing"
                summary = f"Vegetation canopy removal or loss detected (ΔNDVI = {d_ndvi:+.2f})."
            elif d_ndvi > 0.20:
                change_type = "Vegetation Regrowth"
                summary = f"Seasonal vegetation greening (ΔNDVI = {d_ndvi:+.2f})."
            else:
                change_type = "Built-up Structural Encroachment"
                summary = f"Impervious structural surface change (Stable vegetation index: ΔNDVI = {d_ndvi:+.2f})."

        # Case 2: RGB Only (e.g. LEVIR-CD high-res)
        else:
            r1, g1, b1 = t1_bands[0][mask], t1_bands[1][mask], t1_bands[2][mask]
            r2, g2, b2 = t2_bands[0][mask], t2_bands[1][mask], t2_bands[2][mask]

            brightness1 = np.mean(0.299 * r1 + 0.587 * g1 + 0.114 * b1)
            brightness2 = np.mean(0.299 * r2 + 0.587 * g2 + 0.114 * b2)
            d_bright = float(brightness2 - brightness1)

            d_ndvi = 0.0
            d_ndwi = 0.0

            if abs(d_bright) > 20:
                change_type = "New Building / Structural Encroachment"
                summary = f"High-contrast physical building modification (Brightness drift = {d_bright:+.1f})."
            else:
                change_type = "Landcover Disturbance"
                summary = f"Textural ground surface disturbance (Brightness drift = {d_bright:+.1f})."

        return {
            "change_type": change_type,
            "d_ndvi": round(d_ndvi, 3),
            "d_ndwi": round(d_ndwi, 3),
            "summary": summary
        }
