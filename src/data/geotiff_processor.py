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
        """Converts (C, H, W) or (H, W) float [0, 1] to (H, W, 3) uint8 [0, 255]."""
        arr = img_01.copy()
        if arr.ndim == 2:
            arr = np.stack([arr] * 3, axis=0)
        elif arr.shape[0] == 1:
            arr = np.repeat(arr[:1], 3, axis=0)
        elif arr.shape[0] == 2:
            arr = np.concatenate([arr[:2], arr[:1]], axis=0)
        scaled = np.clip(arr * 255.0, 0, 255).astype(np.uint8)
        return np.transpose(scaled[:3], (1, 2, 0))

    @staticmethod
    def cloud_mask(blue, green, red, nir, swir1, cirrus, min_cloud_px: int = 500) -> np.ndarray:
        """Cloud / cirrus / cloud-shadow mask from Sentinel-2 L1C TOA reflectance (0-1) bands
        B02, B03, B04, B08, B11, B10 (Feature #5). Used because OSCD ships L1C, which has no SCL layer.
        ponytail: fixed-threshold heuristic; bright roofs can trip the opaque-cloud test and shadows are
        found by darkness near clouds, not sun geometry; min_cloud_px (500 px = 5 ha at 10 m) keeps
        large bright roofs out. Swap in s2cloudless or L2A SCL if available."""
        from scipy.ndimage import binary_dilation, label
        vis = (blue + green + red) / 3.0
        cirrus_px = cirrus > 0.012
        opaque = (vis > 0.30) & (swir1 > 0.25) & (blue >= red * 0.9)    # bright, white, bright in SWIR
        # bright roofs pass both tests too (B10 is 60 m, so they leak into it); clouds are far bigger
        lab, _ = label(cirrus_px | opaque)
        cloud = (np.bincount(lab.ravel()) >= min_cloud_px)[lab] & (lab > 0)
        if not cloud.any():
            return cloud
        near = binary_dilation(cloud, iterations=50)                  # shadows fall within ~500 m at 10 m GSD
        ndwi = (green - nir) / np.maximum(green + nir, 1e-6)
        shadow = near & ~cloud & (nir < 0.08) & (swir1 < 0.08) & (ndwi < 0)   # dark land, not water
        return cloud | shadow

    # Sentinel-2 L2A Scene Classification classes that make a pixel unobservable:
    # no data, saturated / defective, cloud shadow, cloud medium / high probability, thin cirrus
    SCL_UNOBSERVABLE = (0, 1, 3, 8, 9, 10)

    @staticmethod
    def load_reflectance(tile_prefix: str):
        """(t1, t2) reflectance x10000 (B04, B03, B02, B08, B11, B12) from
        <tile_prefix>_t{1,2}_reflectance.tif, or None. Spectral indices and the naive NDVI baseline need
        these: the _pre/_post GeoTIFFs are per-band, per-date stretched to 0-255 for the model and display,
        which distorts every band ratio."""
        import os
        paths = [f"{tile_prefix}_t1_reflectance.tif", f"{tile_prefix}_t2_reflectance.tif"]
        if not all(os.path.exists(p) for p in paths):
            return None
        out = []
        for p in paths:
            with rasterio.open(p) as s:
                out.append(s.read())
        return tuple(out)

    @staticmethod
    def load_cloud_mask(tile_prefix: str) -> Optional[np.ndarray]:
        """Boolean mask from <tile_prefix>_cloud_mask.tif, or None when the tile has none."""
        import os
        path = f"{tile_prefix}_cloud_mask.tif"
        if not os.path.exists(path):
            return None
        with rasterio.open(path) as s:
            return s.read(1) > 0


if __name__ == "__main__":
    z = np.zeros((4, 4), np.float32)
    clear = GeoTIFFProcessor.cloud_mask(z + 0.08, z + 0.07, z + 0.06, z + 0.25, z + 0.2, z + 0.001)
    assert not clear.any()
    b = z + 0.08
    b[0, 0] = 0.5
    cir = z + 0.001
    cir[3, 3] = 0.03
    sw = z + 0.2
    sw[0, 0] = 0.4
    m = GeoTIFFProcessor.cloud_mask(b, b, np.where(b > 0.4, 0.45, 0.06), z + 0.25, sw, cir)
    assert not m.any(), m                                         # 1-px bright roof / cirrus speck ignored
    m = GeoTIFFProcessor.cloud_mask(b, b, np.where(b > 0.4, 0.45, 0.06), z + 0.25, sw, cir, min_cloud_px=1)
    assert m[0, 0] and m[3, 3] and m.sum() == 2, m                # both count once big enough
    print("cloud_mask self-check ok")
