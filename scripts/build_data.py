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
    
    print("\n--- 1. Processing OSCD Mumbai (Sentinel-2 Multispectral) ---")
    try:
        mumbai_meta = builder.prepare_oscd_city("mumbai")
    except Exception as e:
        print(f"Error processing Mumbai: {e}")

    print("\n--- 2. Processing LEVIR-CD Benchmark Samples (0.5m High-Res) ---")
    samples = [
        "test_2_0000_0000.png",
        "test_2_0000_0512.png",
        "test_77_0512_0256.png"
    ]
    for s in samples:
        try:
            builder.prepare_levir_sample(s)
        except Exception as e:
            print(f"Error processing LEVIR sample {s}: {e}")

    print("\nAll initial GeoTIFF datasets generated successfully in data/geotiff/!")


if __name__ == "__main__":
    main()
