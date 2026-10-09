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

    @staticmethod
    def load_oscd_city(city: str, base_dir: str = ".", oscd_root: str = "Onera Satellite Change Detection") -> Dict[str, Any]:
        """One OSCD city as arrays on its 10 m grid (imgs_*_rect):
        disp1/disp2 : uint8 B04 B03 B02 B08, percentile-stretched per date (model input / display)
        refl1/refl2 : uint16 reflectance x10000, B04 B03 B02 B08 B11 B12 (spectral indices)
        gt          : uint8 change mask, or None for cities without released labels
        cloud       : bool cloud / cirrus / shadow mask from either date
        """
        img_dir = os.path.join(base_dir, oscd_root, "images", "Onera Satellite Change Detection dataset - Images", city)
        label_dir = os.path.join(base_dir, oscd_root, "train_labels",
                                 "Onera Satellite Change Detection dataset - Train Labels", city, "cm")

        with open(os.path.join(img_dir, f"{city}.geojson"), "r") as f:
            coords = json.load(f)["features"][0]["geometry"]["coordinates"][0]
        lons, lats = [c[0] for c in coords], [c[1] for c in coords]

        def read(sub_dir: str, bands) -> np.ndarray:
            out = []
            for b in bands:
                with rasterio.open(os.path.join(img_dir, sub_dir, f"{b}.tif")) as src:
                    out.append(src.read(1))
            return np.stack(out, axis=0)

        band_names = ["B04", "B03", "B02", "B08"]
        refl1 = read("imgs_1_rect", band_names + ["B11", "B12"]).astype(np.uint16)
        refl2 = read("imgs_2_rect", band_names + ["B11", "B12"]).astype(np.uint16)
        _, h, w = refl1.shape
        transform = from_bounds(min(lons), min(lats), max(lons), max(lats), w, h)

        # Ground truth: OSCD's README says the .tif is 0/1, but the shipped files are 1 = no change,
        # 2 = change. The .png is 0/255 (possibly RGBA). Either way, change is the top value.
        gt = None
        cm_path = os.path.join(label_dir, f"{city}-cm.tif")
        if os.path.exists(cm_path):
            with rasterio.open(cm_path) as s:
                gt_arr = s.read(1)
        elif os.path.exists(os.path.join(label_dir, "cm.png")):
            gt_arr = np.array(Image.open(os.path.join(label_dir, "cm.png")))
        else:
            gt_arr = None
        if gt_arr is not None:
            gt_arr = gt_arr[..., 0] if gt_arr.ndim == 3 else gt_arr
            gt = (gt_arr == gt_arr.max()).astype(np.uint8) if gt_arr.min() < gt_arr.max() else np.zeros_like(gt_arr, np.uint8)

        # Feature #5: cloud / shadow mask from either date (L1C has no SCL, so spectral tests)
        cloud = np.zeros((h, w), bool)
        for sub in ("imgs_1_rect", "imgs_2_rect"):
            cloud |= GeoTIFFProcessor.cloud_mask(*(read(sub, [b])[0].astype(np.float32) / 10000.0
                                                   for b in ("B02", "B03", "B04", "B08", "B11", "B10")))
        stretch = lambda r: (GeoTIFFProcessor.percentile_stretch(r[:4]) * 255).astype(np.uint8)
        return {"disp1": stretch(refl1), "disp2": stretch(refl2), "refl1": refl1, "refl2": refl2, "gt": gt,
                "cloud": cloud, "transform": transform, "crs": CRS.from_epsg(4326),
                "bounds": [min(lons), min(lats), max(lons), max(lats)]}

    def prepare_oscd_city(
        self,
        city: str = "mumbai",
        oscd_root: str = "Onera Satellite Change Detection"
    ) -> Dict[str, str]:
        """Writes an OSCD city (default: Mumbai) as standardized GeoTIFFs: display pair (B04 B03 B02 B08),
        reflectance pair (+ B11 B12), ground truth and cloud mask, georeferenced from the city geojson."""
        d = self.load_oscd_city(city, self.base_dir, oscd_root)
        transform, crs, cloud = d["transform"], d["crs"], d["cloud"]
        _, h, w = d["refl1"].shape
        t1_out = os.path.join(self.output_dir, f"{city}_t1_pre.tif")
        t2_out = os.path.join(self.output_dir, f"{city}_t2_post.tif")
        gt_out = os.path.join(self.output_dir, f"{city}_ground_truth.tif")
        cloud_out = os.path.join(self.output_dir, f"{city}_cloud_mask.tif")
        GeoTIFFProcessor.write_geotiff(t1_out, d["disp1"], transform, crs)
        GeoTIFFProcessor.write_geotiff(t2_out, d["disp2"], transform, crs)
        if d["gt"] is not None:
            GeoTIFFProcessor.write_geotiff(gt_out, d["gt"], transform, crs)
        for tag in ("1", "2"):
            GeoTIFFProcessor.write_geotiff(os.path.join(self.output_dir, f"{city}_t{tag}_reflectance.tif"), d[f"refl{tag}"], transform, crs)
        GeoTIFFProcessor.write_geotiff(cloud_out, cloud.astype(np.uint8), transform, crs)
        min_lon, min_lat, max_lon, max_lat = d["bounds"]

        print(f"[DatasetBuilder] Successfully generated GeoTIFF pair for OSCD {city.upper()}:")
        print(f"  T1 (Pre): {t1_out} ({w}x{h}, 4 bands: RGB+NIR)")
        print(f"  T2 (Post): {t2_out} ({w}x{h}, 4 bands: RGB+NIR)")
        print(f"  GT Mask: {gt_out}")
        print(f"  Cloud/shadow mask: {cloud_out} ({cloud.mean():.2%} masked)")

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
