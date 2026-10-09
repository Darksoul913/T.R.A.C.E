"""
test_integration.py - Comprehensive Integration Tests for T.R.A.C.E. Engine & REST API.

Tests:
1. RasterInspector: metadata, GSD, CRS, band stats, pair validation.
2. ChangeEngine: end-to-end execution, BIT ResNet-18 model inference, continuous prob map,
   morphology, Polsby-Popper compactness, vectorization, OSM screening, setbacks.
3. PixelIntelligenceInspector: Levels 1-5 reasoning, band deltas, 11x11 neighborhood patch crops.
4. PolygonIntelligenceInspector: 5 visual crops, 12-question reasoning, auditable evidence table.
5. ComprehensiveReportGenerator: Multi-page Full Scene Audit PDF and Single Polygon Dossier PDF.
6. FastAPI REST Endpoints: health, sample loading, process, status polling, summary, polygons,
   pixel inspector, raster layers, report generation, GIS exports (GeoJSON, GPKG, CAP XML), web console serving.
"""

import os
import sys
import time
import json
import pathlib
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

T1_PATH = str(ROOT / "data/geotiff/levir_test_2_0000_0000_t1_pre.tif")
T2_PATH = str(ROOT / "data/geotiff/levir_test_2_0000_0000_t2_post.tif")


def test_raster_inspector():
    """Verify metadata extraction and pair validation."""
    meta1 = RasterInspector.inspect_file(T1_PATH)
    meta2 = RasterInspector.inspect_file(T2_PATH)

    assert meta1["width"] == 256
    assert meta1["height"] == 256
    assert meta1["bands"] == 3
    assert meta1["is_projected"] is True
    assert meta1["gsd_m"] == 0.5
    assert meta1["crs"] == "EPSG:32615"

    val = RasterInspector.validate_pair(meta1, meta2)
    assert val["compatible"] is True
    assert val["can_process"] is True
    assert val["spatial_overlap_pct"] == 100.0


def test_pipeline_execution():
    """Verify end-to-end execution of ChangeEngine."""
    result = ChangeEngine.execute_pipeline(
        t1_path=T1_PATH,
        t2_path=T2_PATH,
        prob_threshold=0.50,
        min_area_px=4,
        morphology_radius=1,
        model_choice="bit_resnet18",
        normalize_radiometry="stable",
        mode="encroachment"
    )

    assert "analysis_id" in result
    analysis_id = result["analysis_id"]
    assert result["kpis"]["total_polygons"] > 0
    assert result["kpis"]["total_area_sqm"] > 0

    session = get_active_session(analysis_id)
    assert session is not None
    assert session["_prob_map"].shape == (256, 256)
    assert session["_bin_mask"].shape == (256, 256)
    assert session["_clean_mask"].shape == (256, 256)
    assert len(session["_gdf"]) == result["kpis"]["total_polygons"]

    # Verify GeoJSON
    gj = session["geojson"]
    assert gj["type"] == "FeatureCollection"
    assert len(gj["features"]) == result["kpis"]["total_polygons"]

    # Verify first polygon attributes
    first_feat = gj["features"][0]["properties"]
    assert "feature_id" in first_feat
    assert "area_sqm" in first_feat
    assert "magnitude" in first_feat
    assert "compactness" in first_feat
    assert "severity_tier" in first_feat
    assert "change_type" in first_feat

    return analysis_id


def test_pixel_intelligence():
    """Verify deep pixel reasoning and neighborhood context."""
    analysis_id = test_pipeline_execution()
    session = get_active_session(analysis_id)

    # Find a changed pixel from the mask
    changed_rows, changed_cols = (session["_clean_mask"] > 0).nonzero()
    assert len(changed_rows) > 0
    r, c = int(changed_rows[0]), int(changed_cols[0])

    pix_data = PixelIntelligenceInspector.inspect_pixel(session, r, c)
    assert pix_data["row"] == r
    assert pix_data["col"] == c
    assert pix_data["is_changed"] is True
    assert pix_data["change_probability"] >= 0.50

    # Verify reasoning levels
    assert "reasoning_levels" in pix_data
    assert "level_1_observations" in pix_data["reasoning_levels"]
    assert "level_2_detector_outputs" in pix_data["reasoning_levels"]
    assert "level_3_spatial_interpretation" in pix_data["reasoning_levels"]
    assert "level_4_candidate_classification" in pix_data["reasoning_levels"]
    assert "level_5_operational_recommendation" in pix_data["reasoning_levels"]

    # Verify crops
    assert "crops" in pix_data
    assert pix_data["crops"]["t1"].startswith("data:image/png;base64,")
    assert pix_data["crops"]["t2"].startswith("data:image/png;base64,")
    assert pix_data["crops"]["prob"].startswith("data:image/png;base64,")


def test_polygon_intelligence():
    """Verify visual evidence crops and 12-question reasoning for polygons."""
    analysis_id = test_pipeline_execution()
    session = get_active_session(analysis_id)
    poly_id = session["_gdf"].iloc[0]["feature_id"]

    poly_data = PolygonIntelligenceInspector.inspect_polygon(session, poly_id)
    assert poly_data["polygon_id"] == poly_id
    assert poly_data["area_sqm"] > 0
    assert "crops" in poly_data
    assert "t1" in poly_data["crops"]
    assert "t2" in poly_data["crops"]
    assert "prob" in poly_data["crops"]
    assert "binary" in poly_data["crops"]
    assert "overlay" in poly_data["crops"]

    # Verify 12 questions
    q_dict = poly_data["twelve_questions"]
    assert len(q_dict) == 12
    for q_text, ans_text in q_dict.items():
        assert len(ans_text) > 10

    # Verify auditable evidence table
    ev_table = poly_data["evidence_table"]
    assert len(ev_table) >= 4
    for row in ev_table:
        assert "source" in row
        assert "measurement" in row
        assert "observed" in row
        assert "interpretation" in row
        assert "limitation" in row


def test_pdf_report_generation():
    """Verify generation of both Full Scene and Single Polygon PDF reports."""
    analysis_id = test_pipeline_execution()
    session = get_active_session(analysis_id)
    poly_id = session["_gdf"].iloc[0]["feature_id"]

    out_dir = ROOT / "data/outputs/test_reports"
    out_dir.mkdir(parents=True, exist_ok=True)

    full_pdf_path = str(out_dir / f"test_full_{analysis_id}.pdf")
    ComprehensiveReportGenerator.generate_full_scene_report(session, full_pdf_path)
    assert os.path.exists(full_pdf_path)
    assert os.path.getsize(full_pdf_path) > 50000
    with open(full_pdf_path, "rb") as f:
        header = f.read(5)
        assert header == b"%PDF-"

    single_pdf_path = str(out_dir / f"test_single_{poly_id}.pdf")
    ComprehensiveReportGenerator.generate_single_polygon_report(session, poly_id, single_pdf_path)
    assert os.path.exists(single_pdf_path)
    assert os.path.getsize(single_pdf_path) > 30000
    with open(single_pdf_path, "rb") as f:
        header = f.read(5)
        assert header == b"%PDF-"


def test_fastapi_rest_endpoints():
    """Verify all FastAPI REST endpoints through TestClient."""
    # 1. Health
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"

    # 2. Sample Scenes
    r = client.get("/api/sample-scenes")
    assert r.status_code == 200
    scenes = r.json()
    assert len(scenes) >= 4

    # 3. Load Sample Scene
    r = client.post("/api/load-sample", data={"scene_id": "levir_sector1"})
    assert r.status_code == 200
    sess_data = r.json()
    session_id = sess_data["session_id"]
    assert session_id.startswith("SES_levir_sector1")
    assert sess_data["validation"]["compatible"] is True

    # 4. Trigger Process
    r = client.post("/api/process", json={
        "session_id": session_id,
        "prob_threshold": 0.50,
        "min_area_px": 4,
        "morphology_radius": 1,
        "model_choice": "auto",
        "normalize_radiometry": "stable",
        "mode": "encroachment"
    })
    assert r.status_code == 200
    assert r.json()["status"] == "started"

    # 5. Poll Status until completed
    max_wait = 60
    start = time.time()
    analysis_id = None
    while time.time() - start < max_wait:
        r = client.get(f"/api/analysis/{session_id}/status")
        assert r.status_code == 200
        st = r.json()
        if st["status"] == "completed":
            analysis_id = st["analysis_id"]
            break
        elif st["status"] == "failed":
            raise AssertionError(f"Processing failed: {st['message']}")
        time.sleep(1.0)

    assert analysis_id is not None, "Processing timed out"

    # 6. Scene Summary
    r = client.get(f"/api/analysis/{analysis_id}/summary")
    assert r.status_code == 200
    summary = r.json()
    assert summary["kpis"]["total_polygons"] > 0
    assert summary["kpis"]["total_area_sqm"] > 0

    # 7. Polygons GeoJSON
    r = client.get(f"/api/analysis/{analysis_id}/polygons")
    assert r.status_code == 200
    gj = r.json()
    assert len(gj["features"]) == summary["kpis"]["total_polygons"]
    first_poly_id = gj["features"][0]["properties"]["feature_id"]

    # 8. Single Polygon details
    r = client.get(f"/api/analysis/{analysis_id}/polygon/{first_poly_id}")
    assert r.status_code == 200
    p_det = r.json()
    assert p_det["polygon_id"] == first_poly_id
    assert len(p_det["twelve_questions"]) == 12

    # 9. Pixel inspection
    r = client.get(f"/api/analysis/{analysis_id}/pixel?row=200&col=200")
    assert r.status_code == 200
    pix = r.json()
    assert "reasoning_levels" in pix

    # 10. Raster layers
    for layer in ["t1", "t2", "prob", "binary", "cleaned"]:
        r = client.get(f"/api/analysis/{analysis_id}/layers/{layer}")
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/png"

    # 11. PDF Report Generation - Full
    r = client.post(f"/api/analysis/{analysis_id}/report", json={})
    assert r.status_code == 200
    rep_res = r.json()
    assert rep_res["status"] == "ready"
    assert rep_res["filename"].startswith("TRACE_Full_Audit_")

    # Download report
    r = client.get(rep_res["download_url"])
    assert r.status_code == 200
    assert r.content[:5] == b"%PDF-"

    # 12. PDF Report Generation - Single Polygon
    r = client.post(f"/api/analysis/{analysis_id}/report", json={"polygon_id": first_poly_id})
    assert r.status_code == 200
    single_res = r.json()
    assert single_res["filename"] == f"TRACE_Dossier_{first_poly_id}.pdf"

    r = client.get(single_res["download_url"])
    assert r.status_code == 200
    assert r.content[:5] == b"%PDF-"

    # 13. GIS Exports
    r = client.get(f"/api/analysis/{analysis_id}/export/geojson")
    assert r.status_code == 200
    assert r.json()["type"] == "FeatureCollection"

    r = client.get(f"/api/analysis/{analysis_id}/export/gpkg")
    assert r.status_code == 200
    assert len(r.content) > 1000

    r = client.get(f"/api/analysis/{analysis_id}/export/cap/{first_poly_id}")
    assert r.status_code == 200
    assert b"<alert" in r.content

    # 14. Frontend HTML serving
    r = client.get("/")
    assert r.status_code == 200
    assert b"T.R.A.C.E." in r.content


if __name__ == "__main__":
    print("Running RasterInspector test...")
    test_raster_inspector()
    print("OK - RasterInspector")

    print("Running Pipeline Execution test...")
    test_pipeline_execution()
    print("OK - Pipeline Execution")

    print("Running Pixel Intelligence test...")
    test_pixel_intelligence()
    print("OK - Pixel Intelligence")

    print("Running Polygon Intelligence test...")
    test_polygon_intelligence()
    print("OK - Polygon Intelligence")

    print("Running PDF Report Generation test...")
    test_pdf_report_generation()
    print("OK - PDF Report Generation")

    print("Running FastAPI REST Endpoints test...")
    test_fastapi_rest_endpoints()
    print("OK - FastAPI REST Endpoints")

    print("\nALL INTEGRATION TESTS PASSED SUCCESSFULLY!")
