"""
build_data.py - Generates standardized GeoTIFF test pairs for both OSCD Mumbai
and LEVIR-CD building change samples.
"""

import sys
import os

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.data.dataset_builder import DatasetBuilder


def main():
    builder = DatasetBuilder(base_dir=".")
    
    print("\n--- 1. Processing OSCD cities (Sentinel-2 Multispectral) ---")
    oscd = "Onera Satellite Change Detection/images/Onera Satellite Change Detection dataset - Images"
    for city in sorted(c for c in os.listdir(oscd) if os.path.isdir(os.path.join(oscd, c))):
        try:
            builder.prepare_oscd_city(city)
        except Exception as e:
            print(f"Error processing {city}: {e}")

    print("\n--- 2. Processing LEVIR-CD Benchmark Samples (0.5m High-Res) ---")
    samples = sorted(f for f in os.listdir("data/raw/levir/label") if f.startswith("test_"))
    for s in samples:
        try:
            builder.prepare_levir_sample(s)
        except Exception as e:
            print(f"Error processing LEVIR sample {s}: {e}")

    print("\nAll initial GeoTIFF datasets generated successfully in data/geotiff/!")


if __name__ == "__main__":
    main()
