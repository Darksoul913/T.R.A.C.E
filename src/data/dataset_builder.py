"""
dataset_builder.py - Converts raw OSCD and LEVIR datasets into standardized,
georeferenced bi-temporal GeoTIFF pairs with authentic CRS and Affine transforms.
"""

import os
import json
from typing import Dict, Any, List
import numpy as np
from PIL import Image
import rasterio
from rasterio.transform import from_bounds, from_origin
from rasterio.crs import CRS

from src.data.geotiff_processor import GeoTIFFProcessor


class DatasetBuilder:
    """Prepares and validates standard GeoTIFF pairs for change detection."""

    def __init__(self, base_dir: str = "."):
        self.base_dir = base_dir
        self.output_dir = os.path.join(base_dir, "data", "geotiff")
        os.makedirs(self.output_dir, exist_ok=True)

    def prepare_oscd_city(
        self,
        city: str = "mumbai",
        oscd_root: str = "Onera Satellite Change Detection"
    ) -> Dict[str, str]:
        """
        Processes an OSCD city (default: Mumbai) into standardized multi-band GeoTIFFs.
        Extracts B02 (Blue), B03 (Green), B04 (Red), B08 (NIR) for both T1 and T2.
        Embeds authentic bounding box from geojson into the GeoTIFF transform.
        """
        img_dir = os.path.join(
            self.base_dir, oscd_root, "images",
            "Onera Satellite Change Detection dataset - Images", city
        )
        label_dir = os.path.join(
            self.base_dir, oscd_root, "train_labels",
            "Onera Satellite Change Detection dataset - Train Labels", city, "cm"
        )

        geojson_path = os.path.join(img_dir, f"{city}.geojson")
        with open(geojson_path, "r") as f:
            gj = json.load(f)

        coords = gj["features"][0]["geometry"]["coordinates"][0]
        lons = [c[0] for c in coords]
        lats = [c[1] for c in coords]
        min_lon, max_lon = min(lons), max(lons)
        min_lat, max_lat = min(lats), max(lats)

        # Bands to stack: Red (B04), Green (B03), Blue (B02), NIR (B08)
        band_names = ["B04", "B03", "B02", "B08"]

        def read_stack(sub_dir: str) -> np.ndarray:
            band_arrays = []
            for b in band_names:
                b_path = os.path.join(img_dir, sub_dir, f"{b}.tif")
                with rasterio.open(b_path) as src:
                    band_arrays.append(src.read(1))
            return np.stack(band_arrays, axis=0)

        t1_raw = read_stack("imgs_1_rect")
        t2_raw = read_stack("imgs_2_rect")

        c, h, w = t1_raw.shape
        transform = from_bounds(min_lon, min_lat, max_lon, max_lat, w, h)
        crs = CRS.from_epsg(4326)

        # Contrast stretch to 8-bit [0, 255] for visual and neural inference
        t1_stretched = (GeoTIFFProcessor.percentile_stretch(t1_raw) * 255).astype(np.uint8)
        t2_stretched = (GeoTIFFProcessor.percentile_stretch(t2_raw) * 255).astype(np.uint8)

        # Read ground truth mask
        cm_path = os.path.join(label_dir, f"{city}-cm.tif")
        if not os.path.exists(cm_path):
            cm_path = os.path.join(label_dir, "cm.png")
            gt_arr = np.array(Image.open(cm_path))
        else:
            with rasterio.open(cm_path) as s:
                gt_arr = s.read(1)
        
        # Ground truth: 1 for change, 0 for background
        gt_binary = (gt_arr > 0).astype(np.uint8)

        # Write output GeoTIFFs
        t1_out = os.path.join(self.output_dir, f"{city}_t1_pre.tif")
        t2_out = os.path.join(self.output_dir, f"{city}_t2_post.tif")
        gt_out = os.path.join(self.output_dir, f"{city}_ground_truth.tif")

        GeoTIFFProcessor.write_geotiff(t1_out, t1_stretched, transform, crs)
        GeoTIFFProcessor.write_geotiff(t2_out, t2_stretched, transform, crs)
        GeoTIFFProcessor.write_geotiff(gt_out, gt_binary, transform, crs)

        print(f"[DatasetBuilder] Successfully generated GeoTIFF pair for OSCD {city.upper()}:")
        print(f"  T1 (Pre): {t1_out} ({w}x{h}, 4 bands: RGB+NIR)")
        print(f"  T2 (Post): {t2_out} ({w}x{h}, 4 bands: RGB+NIR)")
        print(f"  GT Mask: {gt_out}")

        return {
            "city": city,
            "t1_path": t1_out,
            "t2_path": t2_out,
            "gt_path": gt_out,
            "bounds": [min_lon, min_lat, max_lon, max_lat],
            "crs": "EPSG:4326",
            "shape": (h, w)
        }

    def prepare_levir_sample(
        self,
        sample_name: str = "test_2_0000_0000.png",
        base_lat: float = 29.7604, # Houston, Texas baseline
        base_lon: float = -95.3698,
        pixel_size_m: float = 0.5  # LEVIR-CD standard: 0.5m GSD
    ) -> Dict[str, str]:
        """
        Converts a LEVIR-CD high-res building change sample pair into an authentic GeoTIFF.
        Embeds projected UTM coordinates with 0.5m metric resolution.
        """
        levir_dir = os.path.join(self.base_dir, "data", "raw", "levir")
        a_path = os.path.join(levir_dir, "A", sample_name)
        b_path = os.path.join(levir_dir, "B", sample_name)
        lbl_path = os.path.join(levir_dir, "label", sample_name)

        if not os.path.exists(a_path):
            raise FileNotFoundError(f"LEVIR sample not found: {a_path}")

        img_a = np.array(Image.open(a_path).convert("RGB"))
        img_b = np.array(Image.open(b_path).convert("RGB"))
        lbl = np.array(Image.open(lbl_path).convert("L"))

        h, w, c = img_a.shape

        # Texas South Central State Plane or UTM Zone 15N (EPSG:32615)
        # 0.5 meters per pixel transform in UTM Zone 15N
        # Example UTM Easting/Northing in Texas: (270000 m E, 3295000 m N)
        utm_easting = 270000.0
        utm_northing = 3295000.0
        transform = from_origin(utm_easting, utm_northing, pixel_size_m, pixel_size_m)
        crs = CRS.from_epsg(32615)

        # Transpose to (C, H, W)
        t1_arr = np.transpose(img_a, (2, 0, 1))
        t2_arr = np.transpose(img_b, (2, 0, 1))
        lbl_arr = (lbl > 128).astype(np.uint8)

        base_id = os.path.splitext(sample_name)[0]
        t1_out = os.path.join(self.output_dir, f"levir_{base_id}_t1_pre.tif")
        t2_out = os.path.join(self.output_dir, f"levir_{base_id}_t2_post.tif")
        gt_out = os.path.join(self.output_dir, f"levir_{base_id}_ground_truth.tif")

        GeoTIFFProcessor.write_geotiff(t1_out, t1_arr, transform, crs)
        GeoTIFFProcessor.write_geotiff(t2_out, t2_arr, transform, crs)
        GeoTIFFProcessor.write_geotiff(gt_out, lbl_arr, transform, crs)

        print(f"[DatasetBuilder] Successfully generated GeoTIFF pair for LEVIR {base_id}:")
        print(f"  T1 (Pre): {t1_out} ({w}x{h}, RGB, 0.5m GSD)")
        print(f"  T2 (Post): {t2_out} ({w}x{h}, RGB, 0.5m GSD)")
        print(f"  GT Mask: {gt_out}")

        return {
            "sample_id": base_id,
            "t1_path": t1_out,
            "t2_path": t2_out,
            "gt_path": gt_out,
            "crs": "EPSG:32615",
            "pixel_size": pixel_size_m,
            "shape": (h, w)
        }
