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
from rasterio.features import shapes
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
        min_area_sqm: float = 25.0,
        prob_threshold: float = 0.50,
        morphology_radius: int = 1,
        min_compactness: float = 0.05,
        simplify_tolerance: float = 0.00002
    ):
        self.min_area_sqm = min_area_sqm
        self.prob_threshold = prob_threshold
        self.morphology_radius = morphology_radius
        self.min_compactness = min_compactness
        self.simplify_tolerance = simplify_tolerance

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
        t2_bands: Optional[np.ndarray] = None
    ) -> gpd.GeoDataFrame:
        """
        Converts a continuous change probability heatmap into an attributed GeoDataFrame.

        Args:
            prob_map: (H, W) float array in [0.0, 1.0]
            transform: Affine transform from GeoTIFF metadata
            crs: CRS of the input raster
            t1_bands: Optional (C, H, W) bands for spectral analysis
            t2_bands: Optional (C, H, W) bands for spectral analysis

        Returns:
            GeoDataFrame containing clean, attributed vector polygons.
        """
        h, w = prob_map.shape
        raw_binary = (prob_map >= self.prob_threshold).astype(np.uint8)

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

        is_geographic = raster_crs.is_geographic if raster_crs else True
        # centroid_lon/lat are always WGS84, even when the raster is projected (e.g. UTM)
        to_wgs84 = None if is_geographic else pyproj.Transformer.from_crs(raster_crs, CRS.from_epsg(4326), always_xy=True).transform

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
            lon, lat = centroid.x, centroid.y
            if to_wgs84:
                lon, lat = to_wgs84(lon, lat)

            # 4. Calculate True Geodesic Area in m² via Local UTM
            if is_geographic:
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
            if area_sqm < self.min_area_sqm:
                continue

            # 5. Polsby-Popper Compactness Score: 4 * pi * Area / Perimeter^2
            if perimeter_m > 0:
                compactness = (4.0 * np.pi * area_sqm) / (perimeter_m ** 2)
            else:
                compactness = 0.0

            # Discard boundary registration slithers
            if compactness < self.min_compactness and area_sqm < 80.0:
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
            sub_bin = clean_binary[r_min:r_max, c_min:c_max]
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
                change_type = "Structural Change"
                sem_summary = "High-confidence structural change detected."

            # 8. Multi-Factor Severity Scoring
            sev = SeverityScorer.compute_severity(
                area_sqm=area_sqm,
                magnitude=magnitude,
                change_type=change_type
            )

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
                "change_type": change_type,
                "summary": sem_summary,
                "compactness": round(compactness, 3),
                "centroid_lon": round(lon, 6),
                "centroid_lat": round(lat, 6),
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
