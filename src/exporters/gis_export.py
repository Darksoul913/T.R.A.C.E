"""
gis_export.py - Multi-Format GIS Export Engine (Feature #9).
Exports GeoDataFrame to OGC-standard GeoPackage (.gpkg) and GeoJSON (.geojson).
"""

import os
from typing import Dict, Any
import geopandas as gpd
from rasterio.crs import CRS


class GISExporter:
    """Exports attributed vector change footprints to standard GIS formats."""

    @staticmethod
    def export_geojson(gdf: gpd.GeoDataFrame, output_path: str) -> str:
        """
        Exports GeoDataFrame to GeoJSON in WGS84 (EPSG:4326).
        Standard format for web mapping.
        """
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        # Ensure CRS is WGS84 for web consumption
        if gdf.crs is not None and not gdf.crs.is_geographic:
            web_gdf = gdf.to_crs(epsg=4326)
        else:
            web_gdf = gdf

        web_gdf.to_file(output_path, driver="GeoJSON")
        return output_path

    @staticmethod
    def export_geopackage(
        gdf: gpd.GeoDataFrame,
        output_path: str,
        layer_name: str = "change_intelligence"
    ) -> str:
        """
        Exports GeoDataFrame to OGC GeoPackage (.gpkg).
        Standard open format for QGIS, ArcGIS Pro, and emergency control rooms.
        """
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        gdf.to_file(output_path, layer=layer_name, driver="GPKG")
        return output_path

    @classmethod
    def export_all(
        cls,
        gdf: gpd.GeoDataFrame,
        base_name: str,
        output_dir: str = "data/outputs"
    ) -> Dict[str, str]:
        """Exports both GeoJSON and GeoPackage with a single call."""
        geojson_path = os.path.join(output_dir, f"{base_name}.geojson")
        gpkg_path = os.path.join(output_dir, f"{base_name}.gpkg")

        cls.export_geojson(gdf, geojson_path)
        cls.export_geopackage(gdf, gpkg_path)

        return {
            "geojson": geojson_path,
            "geopackage": gpkg_path
        }
