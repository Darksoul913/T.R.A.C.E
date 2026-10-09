"""
vectorizer.py - Clean Raster-to-Polygon Vectorization & Geodesic Attribution (Feature #7).

Performs:
1. Morphological opening & closing for noise suppression.
2. Rasterio contour-to-polygon shape extraction.
3. Slither & registration noise pruning via Polsby-Popper compactness.
4. Automatic local UTM reprojection for true metric surface area (m²).
5. Polygon simplification via Shapely.
6. Attribution with centroid, change type, magnitude, and severity tier.
"""

from typing import Optional, List, Dict, Any, Tuple
import numpy as np
import rasterio
from rasterio.features import shapes, geometry_mask
from rasterio.transform import Affine
from rasterio.crs import CRS
from shapely.geometry import shape, Polygon, MultiPolygon
from shapely.ops import transform as shapely_transform
import pyproj
import geopandas as gpd
from skimage.morphology import disk, opening, closing

from src.geospatial.spectral_indices import SpectralClassifier
from src.geospatial.severity import SeverityScorer


class GeospatialVectorizer:
    """Extracts clean, attributed, GIS-ready vector polygons from raster heatmaps."""

    def __init__(
        self,
        min_area_sqm: Optional[float] = None,
        prob_threshold: float = 0.50,
        morphology_radius: int = 1,
        min_compactness: float = 0.05,
        simplify_tolerance: float = 0.00002,
        min_area_px: int = 4,
        min_width_px: float = 1.5
    ):
        # Minimum area is resolution-aware: min_area_px pixels (4 px = 1 m² at 0.5 m, 400 m² at 10 m).
        # min_area_sqm, if given, overrides it.
        self.min_area_sqm = min_area_sqm
        self.min_area_px = min_area_px
        self.min_width_px = min_width_px
        self.prob_threshold = prob_threshold
        self.morphology_radius = morphology_radius
        self.min_compactness = min_compactness
        self.simplify_tolerance = simplify_tolerance

    @classmethod
    def pixel_area_sqm(cls, transform: Affine, crs: Any, shape_hw: Tuple[int, int]) -> float:
        """Ground area of one pixel at the raster centre, in m² (geographic CRSs via local UTM)."""
        crs = CRS.from_user_input(crs) if isinstance(crs, (str, int)) else crs
        if crs is None or not crs.is_geographic:
            return abs(transform.a * transform.e - transform.b * transform.d)
        r, c = shape_hw[0] // 2, shape_hw[1] // 2
        x0, y0 = transform * (c, r)
        x1, y1 = transform * (c + 1, r + 1)
        project = pyproj.Transformer.from_crs(crs, CRS.from_epsg(cls.get_utm_epsg(x0, y0)), always_xy=True).transform
        return float(shapely_transform(project, Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])).area)

    @staticmethod
    def get_utm_epsg(lon: float, lat: float) -> int:
        """Determines the appropriate WGS84 UTM EPSG code for a given Lat/Lon."""
        zone = int((lon + 180.0) / 6.0) + 1
        if lat >= 0:
            return 32600 + zone
        else:
            return 32700 + zone

    def vectorize(
        self,
        prob_map: np.ndarray,
        transform: Affine,
        crs: Any,
        t1_bands: Optional[np.ndarray] = None,
        t2_bands: Optional[np.ndarray] = None,
        mode: str = "encroachment",
        threshold_map: Optional[np.ndarray] = None
    ) -> gpd.GeoDataFrame:
        """
        Converts a continuous change probability heatmap into an attributed GeoDataFrame.

        Args:
            prob_map: (H, W) float array in [0.0, 1.0]
            transform: Affine transform from GeoTIFF metadata
            crs: CRS of the input raster
            t1_bands: Optional (C, H, W) bands for spectral analysis
            t2_bands: Optional (C, H, W) bands for spectral analysis
            mode: severity mode for the primary tier columns ("encroachment" | "disaster");
                  tier_<mode> / score_<mode> are filled for both
            threshold_map: optional (H, W) per-pixel probability threshold, e.g. lower inside protected
                  zones (recall-first); defaults to prob_threshold everywhere

        Returns:
            GeoDataFrame containing clean, attributed vector polygons.
        """
        h, w = prob_map.shape
        thr = self.prob_threshold if threshold_map is None else threshold_map
        raw_binary = (prob_map >= thr).astype(np.uint8)

        # 1. Morphological Cleaning
        selem = disk(self.morphology_radius)
        opened = opening(raw_binary, selem)
        clean_binary = closing(opened, selem).astype(np.uint8)

        # 2. Extract Shapes via Rasterio
        # Mask out 0s (background) so we only extract positive changes
        shape_generator = shapes(
            clean_binary,
            mask=(clean_binary == 1),
            transform=transform
        )

        # Standardize CRS object
        if isinstance(crs, (str, int)):
            raster_crs = CRS.from_user_input(crs)
        else:
            raster_crs = crs

        is_georef = (raster_crs is not None)
        is_geographic = bool(raster_crs.is_geographic) if is_georef else False
        pixel_area = self.pixel_area_sqm(transform, raster_crs, (h, w)) if is_georef else 1.0
        gsd = float(np.sqrt(pixel_area))
        min_area = self.min_area_sqm if self.min_area_sqm is not None else self.min_area_px * pixel_area
        # centroid_lon/lat are WGS84 when georeferenced, or pixel coordinates when ungeoreferenced
        to_wgs84 = (pyproj.Transformer.from_crs(raster_crs, CRS.from_epsg(4326), always_xy=True).transform
                    if (is_georef and not is_geographic) else None)

        features_data = []

        feat_counter = 1
        for geom_dict, val in shape_generator:
            if val != 1:
                continue

            geom = shape(geom_dict)
            if not geom.is_valid:
                geom = geom.buffer(0)
            if geom.is_empty:
                continue

            # Convert to Polygon if MultiPolygon with 1 element
            if isinstance(geom, MultiPolygon) and len(geom.geoms) == 1:
                geom = geom.geoms[0]

            # 3. Simplify geometry
            if is_geographic:
                geom_simplified = geom.simplify(self.simplify_tolerance, preserve_topology=True)
            else:
                geom_simplified = geom.simplify(1.0, preserve_topology=True)

            centroid = geom_simplified.centroid
            if is_georef:
                lon, lat = centroid.x, centroid.y
                if to_wgs84:
                    lon, lat = to_wgs84(lon, lat)
                lon, lat = round(lon, 6), round(lat, 6)
            else:
                lon, lat = None, None

            # 4. Calculate True Geodesic Area in m² via Local UTM (or px² if ungeoreferenced)
            if is_geographic and is_georef:
                utm_epsg = self.get_utm_epsg(lon, lat)
                project = pyproj.Transformer.from_crs(
                    raster_crs, CRS.from_epsg(utm_epsg), always_xy=True
                ).transform
                projected_geom = shapely_transform(project, geom_simplified)
                area_sqm = float(projected_geom.area)
                perimeter_m = float(projected_geom.length)
            else:
                area_sqm = float(geom_simplified.area)
                perimeter_m = float(geom_simplified.length)

            # Minimum Area Pruning
            if area_sqm < min_area:
                continue

            # 5. Polsby-Popper Compactness Score: 4 * pi * Area / Perimeter^2
            if perimeter_m > 0:
                compactness = (4.0 * np.pi * area_sqm) / (perimeter_m ** 2)
            else:
                compactness = 0.0

            # Discard registration-jitter slivers: thin edge artefacts along roads / roofs
            # (mean width = 2·area/perimeter, compared in pixels so it behaves the same at any resolution)
            if perimeter_m > 0 and 2.0 * area_sqm / perimeter_m < self.min_width_px * gsd:
                continue
            if compactness < self.min_compactness and area_sqm < 8 * pixel_area:
                continue

            # 6. Mean Change Probability Magnitude inside Polygon
            # Create a localized pixel mask to evaluate mean probability
            minx, miny, maxx, maxy = geom.bounds
            # Approximate bounding box pixel window
            col_min, row_max = ~transform * (minx, miny)
            col_max, row_min = ~transform * (maxx, maxy)

            c_min = max(0, int(np.floor(col_min)))
            c_max = min(w, int(np.ceil(col_max)))
            r_min = max(0, int(np.floor(row_min)))
            r_max = min(h, int(np.ceil(row_max)))

            sub_prob = prob_map[r_min:r_max, c_min:c_max]
            # this polygon's own pixels: its bbox window can contain neighbouring polygons
            own = geometry_mask([geom], out_shape=(r_max - r_min, c_max - c_min),
                                transform=transform * Affine.translation(c_min, r_min), invert=True)
            sub_bin = (clean_binary[r_min:r_max, c_min:c_max] == 1) & own
            if np.any(sub_bin == 1):
                magnitude = float(np.mean(sub_prob[sub_bin == 1]))
            else:
                magnitude = float(self.prob_threshold)

            # 7. Semantic Change Labelling
            if t1_bands is not None and t2_bands is not None:
                sub_t1 = t1_bands[:, r_min:r_max, c_min:c_max]
                sub_t2 = t2_bands[:, r_min:r_max, c_min:c_max]
                sem = SpectralClassifier.classify_polygon_change(sub_t1, sub_t2, (sub_bin == 1))
                change_type = sem["change_type"]
                sem_summary = sem["summary"]
            else:
                sem = {}
                change_type = "Structural Change"
                sem_summary = "High-confidence structural change detected."

            # 8. Multi-Factor Severity Scoring
            sev = SeverityScorer.compute_all_modes(area_sqm, magnitude, change_type,
                                                   pixel_area_sqm=pixel_area, primary_mode=mode)

            feature_id = f"CHG_{feat_counter:04d}"
            feat_counter += 1

            record = {
                "feature_id": feature_id,
                "area_sqm": round(area_sqm, 1),
                "magnitude": round(magnitude, 3),
                "severity_tier": sev["severity_tier"],
                "color_hex": sev["color_hex"],
                "composite_score": sev["composite_score"],
                "action_priority": sev["action_priority"],
                **{k: sev[k] for k in sev if k.startswith(("tier_", "score_"))},
                "norm_area": sev["norm_area"],
                "exposure_mult": sev["exposure_mult"],
                "pixel_area_sqm": round(pixel_area, 4),
                "severity_mode": mode,
                "change_type": change_type,
                "summary": sem_summary,
                # index shifts behind the label (None without the bands), for the case card and copilot facts
                "d_ndvi": sem.get("d_ndvi"), "d_mndwi": sem.get("d_ndwi"), "d_ndbi": sem.get("d_ndbi"), "d_nbr": sem.get("d_nbr"),
                "compactness": round(compactness, 3),
                "centroid_lon": lon,
                "centroid_lat": lat,
                "verification_status": "AI Detected",
                "verification_count": 0,
                "geometry": geom_simplified
            }
            features_data.append(record)

        if not features_data:
            # Return empty GeoDataFrame with correct schema
            return gpd.GeoDataFrame(
                columns=[
                    "feature_id", "area_sqm", "magnitude", "severity_tier",
                    "color_hex", "composite_score", "action_priority",
                    "change_type", "summary", "compactness",
                    "centroid_lon", "centroid_lat", "verification_status",
                    "verification_count", "geometry"
                ],
                crs=raster_crs
            )

        gdf = gpd.GeoDataFrame(features_data, crs=raster_crs)
        return gdf
