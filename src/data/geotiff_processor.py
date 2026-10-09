"""
geotiff_processor.py - Core GeoTIFF I/O, Radiometric Normalization & Preprocessing.

Handles:
1. Raster reading/writing via Rasterio with Affine transforms & CRS.
2. Radiometric normalization (Histogram matching of T2 -> T1) for sun-angle/haze invariance.
3. Percentile-based contrast normalization for multi-spectral / 16-bit sensors.
"""

from typing import Tuple, Optional, Dict, Any
import numpy as np
import rasterio
from rasterio.transform import Affine, from_bounds
from rasterio.crs import CRS
from skimage.exposure import match_histograms


class GeoTIFFProcessor:
    """Utilities for reading, normalizing, and writing geospatial raster tiles."""

    @staticmethod
    def read_geotiff(
        path: str,
        bands: Optional[list] = None
    ) -> Tuple[np.ndarray, Dict[str, Any]]:
        """
        Reads a GeoTIFF file.
        Returns:
            data: np.ndarray of shape (C, H, W)
            meta: dictionary containing crs, transform, bounds, shape, dtype
        """
        with rasterio.open(path) as src:
            if bands is not None:
                data = src.read(bands)
            else:
                data = src.read()
            
            meta = {
                "driver": "GTiff",
                "dtype": data.dtype,
                "count": data.shape[0],
                "height": src.height,
                "width": src.width,
                "crs": src.crs,
                "transform": src.transform,
                "bounds": src.bounds,
                "nodata": src.nodata
            }
        return data, meta

    @staticmethod
    def write_geotiff(
        path: str,
        data: np.ndarray,
        transform: Affine,
        crs: Any,
        nodata: Optional[float] = None
    ) -> str:
        """
        Writes a numpy array (C, H, W) or (H, W) to an orthorectified GeoTIFF.
        """
        if data.ndim == 2:
            data = data[np.newaxis, ...]
        
        c, h, w = data.shape
        dtype = data.dtype

        # Ensure CRS is rasterio-compatible
        if isinstance(crs, str):
            crs = CRS.from_string(crs)
        elif isinstance(crs, int):
            crs = CRS.from_epsg(crs)

        profile = {
            "driver": "GTiff",
            "height": h,
            "width": w,
            "count": c,
            "dtype": dtype,
            "crs": crs,
            "transform": transform,
            "nodata": nodata,
            "compress": "lzw"
        }

        with rasterio.open(path, "w", **profile) as dst:
            dst.write(data)

        return path

    @staticmethod
    def match_radiometry(
        img_source: np.ndarray,
        img_reference: np.ndarray
    ) -> np.ndarray:
        """
        Feature #4: Radiometric Normalization via Histogram Matching.
        Matches the histogram of img_source (T2) to img_reference (T1) channel-wise.
        Eliminates illumination, sun elevation, and atmospheric haze discrepancy.

        Args:
            img_source: (C, H, W) array representing T2 (After)
            img_reference: (C, H, W) array representing T1 (Before)
        Returns:
            normalized: (C, H, W) array matched to reference radiometry
        """
        matched = np.zeros_like(img_source)
        for i in range(img_source.shape[0]):
            matched[i] = match_histograms(
                img_source[i],
                img_reference[i]
            )
        return matched

    @staticmethod
    def percentile_stretch(
        data: np.ndarray,
        p_low: float = 2.0,
        p_high: float = 98.0
    ) -> np.ndarray:
        """
        Robust percentile-based stretching to scale [0, 1] float32.
        Crucial for 12/16-bit Sentinel-2 reflectance data.
        """
        out = np.zeros_like(data, dtype=np.float32)
        for i in range(data.shape[0]):
            band = data[i].astype(np.float32)
            v_min = np.percentile(band, p_low)
            v_max = np.percentile(band, p_high)
            if v_max > v_min:
                stretched = np.clip((band - v_min) / (v_max - v_min), 0.0, 1.0)
            else:
                stretched = np.zeros_like(band)
            out[i] = stretched
        return out

    @staticmethod
    def to_uint8_rgb(img_01: np.ndarray) -> np.ndarray:
        """Converts (3, H, W) float [0, 1] to (H, W, 3) uint8 [0, 255]."""
        scaled = np.clip(img_01 * 255.0, 0, 255).astype(np.uint8)
        return np.transpose(scaled[:3], (1, 2, 0))
