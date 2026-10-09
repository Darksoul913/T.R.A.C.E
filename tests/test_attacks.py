"""
test_attacks.py - Skeptical Attack Suite probing edge cases, unprojected inputs,
grayscale rasters, zero change scenes, and full REST workflow.
"""

import os
import sys
import tempfile
import pathlib
import numpy as np
from PIL import Image
import rasterio
from rasterio.transform import from_origin
from fastapi.testclient import TestClient

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.pipeline.change_engine import (
    RasterInspector,
    ChangeEngine,
    PixelIntelligenceInspector,
    PolygonIntelligenceInspector,
    get_active_session
)
from src.exporters.comprehensive_report import ComprehensiveReportGenerator
from src.server.app import app

client = TestClient(app)

def test_attack_png_unprojected():
    """Attack 1: Standard non-georeferenced PNG images."""
    print("Testing Attack 1: Non-georeferenced PNG images...")
    with tempfile.TemporaryDirectory() as tmpdir:
        p1 = os.path.join(tmpdir, "img1.png")
        p2 = os.path.join(tmpdir, "img2.png")
        
        # Create 128x128 RGB images with a square change
        arr1 = np.full((128, 128, 3), 100, dtype=np.uint8)
        arr2 = np.full((128, 128, 3), 100, dtype=np.uint8)
        arr2[40:80, 40:80, :] = 240  # Significant change
        
        Image.fromarray(arr1).save(p1)
        Image.fromarray(arr2).save(p2)
        
        # 1. RasterInspector
        m1 = RasterInspector.inspect_file(p1)
        m2 = RasterInspector.inspect_file(p2)
        assert m1["is_georeferenced"] is False
        assert "Pixel Space" in m1["crs"]
        assert m1["reliable_metric_area"] is False
        
        # 2. ChangeEngine Pipeline
        res = ChangeEngine.execute_pipeline(
            t1_path=p1,
            t2_path=p2,
            prob_threshold=0.30,
            min_area_px=4,
            model_choice="naive_diff",
            mode="encroachment"
        )
        anl_id = res["analysis_id"]
        session = get_active_session(anl_id)
        assert session is not None
        assert res["kpis"]["total_polygons"] > 0
        
        # 3. Pixel Inspector on unprojected image
        pix = PixelIntelligenceInspector.inspect_pixel(session, 50, 50)
        assert pix["lat"] is None
        assert pix["lon"] is None
        assert "Image Space" in pix["coordinates"]
        assert "raw_vs_normalized" in pix
        assert "matched_polygon_id" in pix
        
        # 4. Polygon Inspector on unprojected image
        poly_id = session["_gdf"].iloc[0]["feature_id"]
        poly_info = PolygonIntelligenceInspector.inspect_polygon(session, poly_id)
        assert poly_info["centroid"]["lat"] is None
        assert poly_info["centroid"]["lon"] is None
        assert len(poly_info["twelve_questions"]) == 12
        assert len(poly_info["evidence_table"]) >= 4
        
        # 5. Full Scene PDF Generation on unprojected image
        pdf_full = os.path.join(tmpdir, "full_unprojected.pdf")
        ComprehensiveReportGenerator.generate_full_scene_report(session, pdf_full)
        assert os.path.exists(pdf_full)
        assert os.path.getsize(pdf_full) > 20000
        
        # 6. Single Polygon PDF Generation on unprojected image
        pdf_single = os.path.join(tmpdir, "single_unprojected.pdf")
        ComprehensiveReportGenerator.generate_single_polygon_report(session, poly_id, pdf_single)
        assert os.path.exists(pdf_single)
        assert os.path.getsize(pdf_single) > 20000
        
        # 7. GeoJSON & GPKG exports for unprojected image
        assert os.path.exists(session["export_paths"]["geojson"])
        assert os.path.exists(session["export_paths"]["geopackage"])
        print("PASS: Attack 1 - Non-georeferenced PNG images")


def test_attack_1band_grayscale():
    """Attack 2: 1-Band grayscale rasters."""
    print("Testing Attack 2: 1-Band grayscale GeoTIFFs...")
    with tempfile.TemporaryDirectory() as tmpdir:
        t1 = os.path.join(tmpdir, "gray_t1.tif")
        t2 = os.path.join(tmpdir, "gray_t2.tif")
        
        transform = from_origin(500000, 3000000, 1.0, 1.0)
        profile = {
            "driver": "GTiff", "height": 64, "width": 64, "count": 1,
            "dtype": "uint8", "crs": "EPSG:32643", "transform": transform
        }
        
        d1 = np.full((1, 64, 64), 50, dtype=np.uint8)
        d2 = np.full((1, 64, 64), 50, dtype=np.uint8)
        d2[0, 20:40, 20:40] = 220
        
        with rasterio.open(t1, "w", **profile) as dst:
            dst.write(d1)
        with rasterio.open(t2, "w", **profile) as dst:
            dst.write(d2)
            
        m1 = RasterInspector.inspect_file(t1)
        assert m1["bands"] == 1
        
        res = ChangeEngine.execute_pipeline(
            t1_path=t1,
            t2_path=t2,
            prob_threshold=0.30,
            min_area_px=4,
            model_choice="naive"
        )
        assert res["kpis"]["total_polygons"] > 0
        print("PASS: Attack 2 - 1-Band grayscale GeoTIFFs")


def test_attack_zero_change():
    """Attack 3: Zero change pair (T1 == T2)."""
    print("Testing Attack 3: Zero change pair (T1 == T2)...")
    t1_path = str(ROOT / "data/geotiff/levir_test_2_0000_0000_t1_pre.tif")
    
    # Process identical images
    res = ChangeEngine.execute_pipeline(
        t1_path=t1_path,
        t2_path=t1_path,
        prob_threshold=0.50,
        min_area_px=4,
        model_choice="bit_resnet18"
    )
    session = get_active_session(res["analysis_id"])
    assert res["kpis"]["total_polygons"] == 0
    assert res["kpis"]["total_area_sqm"] == 0
    
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_full = os.path.join(tmpdir, "zero_change.pdf")
        ComprehensiveReportGenerator.generate_full_scene_report(session, pdf_full)
        assert os.path.exists(pdf_full)
        assert os.path.getsize(pdf_full) > 10000
    print("PASS: Attack 3 - Zero change pair")


def test_attack_rest_live_workflow():
    """Attack 4: Complete FastAPI REST workflow including downloads."""
    print("Testing Attack 4: Complete REST workflow...")
    # Load sample
    r = client.post("/api/load-sample", data={"scene_id": "levir_sector2"})
    assert r.status_code == 200
    sess_id = r.json()["session_id"]
    
    # Process
    r = client.post("/api/process", json={
        "session_id": sess_id,
        "prob_threshold": 0.50,
        "min_area_px": 4,
        "morphology_radius": 1,
        "model_choice": "bit_resnet18",
        "normalize_radiometry": "stable",
        "mode": "encroachment"
    })
    assert r.status_code == 200
    assert r.json()["status"] == "started"

    # Poll status
    import time
    max_wait = 60
    start = time.time()
    anl_id = None
    while time.time() - start < max_wait:
        r = client.get(f"/api/analysis/{sess_id}/status")
        assert r.status_code == 200
        st = r.json()
        if st["status"] == "completed":
            anl_id = st["analysis_id"]
            break
        elif st["status"] == "failed":
            raise AssertionError(f"Processing failed: {st['message']}")
        time.sleep(0.5)
    assert anl_id is not None, "Pipeline timed out"
    
    # Summary
    r = client.get(f"/api/analysis/{anl_id}/summary")
    assert r.status_code == 200
    sum_data = r.json()
    assert "console_features" in sum_data
    assert len(sum_data["console_features"]) > 0
    assert "wgs84_bounds" in sum_data
    
    # Check console_features format (0..100 coords)
    f0 = sum_data["console_features"][0]
    assert "pts" in f0
    assert len(f0["pts"]) >= 3
    for pt in f0["pts"]:
        assert 0.0 <= pt[0] <= 100.0
        assert 0.0 <= pt[1] <= 100.0
        
    # Downloads
    r_gj = client.get(f"/api/analysis/{anl_id}/export/geojson")
    assert r_gj.status_code == 200
    assert "FeatureCollection" in r_gj.text
    
    r_gpkg = client.get(f"/api/analysis/{anl_id}/export/gpkg")
    assert r_gpkg.status_code == 200
    assert len(r_gpkg.content) > 1000
    
    poly_id = f0["id"]
    r_cap = client.get(f"/api/analysis/{anl_id}/export/cap/{poly_id}")
    assert r_cap.status_code == 200
    assert "<alert" in r_cap.text
    
    # PDF reports
    r_rep_full = client.post(f"/api/analysis/{anl_id}/report", json={})
    assert r_rep_full.status_code == 200
    assert "download_url" in r_rep_full.json()
    
    r_rep_poly = client.post(f"/api/analysis/{anl_id}/report", json={"polygon_id": poly_id})
    assert r_rep_poly.status_code == 200
    assert "download_url" in r_rep_poly.json()
    
    print("PASS: Attack 4 - Complete REST workflow")


if __name__ == "__main__":
    test_attack_png_unprojected()
    test_attack_1band_grayscale()
    test_attack_zero_change()
    test_attack_rest_live_workflow()
    print("\nALL ATTACK TESTS PASSED SKEPTICALLY AND DECISIVELY!")
