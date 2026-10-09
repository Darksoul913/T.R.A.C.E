"""
app.py - FastAPI Application Server for T.R.A.C.E. (Terrain Analysis & Change Evaluation).

Provides RESTful API endpoints for:
- Uploading & validating satellite image pairs (T1, T2)
- Selecting bundled multi-sensor satellite scenes
- Initiating background change detection with live progress tracking
- Serving raster visualization layers (T1, T2, probability heatmap, binary & cleaned masks)
- Deep pixel-level inspection (Level 1-5 reasoning, spectral indices, 11x11 neighborhood context)
- Clickable polygon investigation (visual crops, 12-question auditable reasoning, evidence tables)
- Whole-scene dashboard KPIs and distributions
- Comprehensive PDF report generation (Full Scene & Single Polygon dossiers)
- Multi-format GIS exports (GeoJSON, GeoPackage, CAP XML)
"""

import os
import sys
import shutil
import uuid
import json
import threading
from typing import Dict, Any, Optional, List

from fastapi import FastAPI, UploadFile, File, Form, Query, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Add project root to sys.path
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.pipeline.change_engine import (
    RasterInspector,
    ChangeEngine,
    PixelIntelligenceInspector,
    PolygonIntelligenceInspector,
    get_active_session,
    _ACTIVE_SESSIONS
)
from src.exporters.comprehensive_report import ComprehensiveReportGenerator
from src.exporters.cap_alert import CAPAlertExporter

app = FastAPI(
    title="T.R.A.C.E. (Terrain Analysis & Change Evaluation) — Bi-Temporal Satellite Change Intelligence Engine",
    version="2.0.0",
    description="Advanced Pixel-Level Change Detection, Explainable GeoIntelligence & Comprehensive Reporting"
)

# Enable CORS for flexible development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Session and Progress tracking state
SESSIONS_DIR = os.path.join(ROOT_DIR, "data", "sessions")
os.makedirs(SESSIONS_DIR, exist_ok=True)

_JOB_STATUS: Dict[str, Dict[str, Any]] = {}


# Pre-configured sample scenes bundled with the system
BUNDLED_SCENES = {
    "mumbai_urban": {
        "id": "mumbai_urban",
        "name": "Mumbai Eastern Urban Corridor (Chembur - Ghatkopar)",
        "sensor": "Sentinel-2 MSI (10m Resolution, 4-Band RGB+NIR)",
        "dates": "30 Nov 2015 -> 19 Mar 2018",
        "t1_path": "data/geotiff/mumbai_t1_pre.tif",
        "t2_path": "data/geotiff/mumbai_t2_post.tif",
        "default_mode": "encroachment",
        "description": "Peri-urban development and land conversion along eastern Mumbai transport corridor."
    },
    "mumbai_s2_growth": {
        "id": "mumbai_s2_growth",
        "name": "Mumbai Suburban Growth (2019 -> 2025 Series)",
        "sensor": "Sentinel-2 L2A (10m Resolution, SCL Cloud Masked)",
        "dates": "2019 -> 2025 Multi-Year",
        "t1_path": "data/geotiff/mumbai_s2_t1_pre.tif",
        "t2_path": "data/geotiff/mumbai_s2_t2_post.tif",
        "default_mode": "encroachment",
        "description": "Multi-year coastal and suburban infrastructure expansion with cloud masking."
    },
    "evros_wildfire": {
        "id": "evros_wildfire",
        "name": "Evros Wildfire (EMSR686 Copernicus EMS, Greece)",
        "sensor": "Sentinel-2 MSI (10m Resolution, L2A True Reflectance)",
        "dates": "18 Aug 2023 -> 28 Aug 2023",
        "t1_path": "data/geotiff/evros_fire_t1_pre.tif",
        "t2_path": "data/geotiff/evros_fire_t2_post.tif",
        "default_mode": "disaster",
        "description": "Major European wildfire burn scar validated against Copernicus EMS delineations (F1 91.8%)."
    },
    "trimmu_flood": {
        "id": "trimmu_flood",
        "name": "Trimmu Flood AOI05 (EMSR838 Copernicus EMS, Pakistan)",
        "sensor": "Sentinel-2 MSI (10m Resolution, Water Index MNDWI)",
        "dates": "Aug 2025 -> Sep 2025",
        "t1_path": "data/geotiff/trimmu_flood_t1_pre.tif",
        "t2_path": "data/geotiff/trimmu_flood_t2_post.tif",
        "default_mode": "disaster",
        "description": "Monsoon river inundation validated against official Sentinel-1 SAR reference."
    },
    "levir_sector1": {
        "id": "levir_sector1",
        "name": "LEVIR-CD High-Resolution Sector 1 (Texas Urban)",
        "sensor": "Aerial Orthophoto (0.5m GSD, Sub-meter Optical RGB)",
        "dates": "T1 Pre-Build -> T2 Post-Build",
        "t1_path": "data/geotiff/levir_test_2_0000_0000_t1_pre.tif",
        "t2_path": "data/geotiff/levir_test_2_0000_0000_t2_post.tif",
        "default_mode": "encroachment",
        "description": "Sub-meter building construction benchmark (Siamese ResNet-18 BIT Model F1 89.5%)."
    },
    "levir_sector2": {
        "id": "levir_sector2",
        "name": "LEVIR-CD High-Resolution Sector 2 (Demolition & Rebuild)",
        "sensor": "Aerial Orthophoto (0.5m GSD, Optical RGB)",
        "dates": "T1 Baseline -> T2 Post-Demolition",
        "t1_path": "data/geotiff/levir_test_2_0000_0512_t1_pre.tif",
        "t2_path": "data/geotiff/levir_test_2_0000_0512_t2_post.tif",
        "default_mode": "encroachment",
        "description": "High-contrast building demolition and structural footprint change."
    }
}


class ProcessRequest(BaseModel):
    session_id: str
    prob_threshold: float = 0.50
    min_area_px: int = 4
    morphology_radius: int = 1
    model_choice: str = "auto"
    normalize_radiometry: str = "stable"
    mode: str = "encroachment"


class ReportRequest(BaseModel):
    polygon_id: Optional[str] = None


@app.get("/api/health")
def health_check():
    return {"status": "healthy", "service": "T.R.A.C.E. AI Engine", "version": "2.0.0"}


@app.get("/api/sample-scenes")
def list_sample_scenes():
    """Returns bundled multi-sensor satellite scenes."""
    return list(BUNDLED_SCENES.values())


@app.post("/api/load-sample")
def load_sample_scene(scene_id: str = Form(...)):
    """Initializes a session from a bundled test scene."""
    if scene_id not in BUNDLED_SCENES:
        raise HTTPException(status_code=404, detail=f"Scene '{scene_id}' not found.")

    sc = BUNDLED_SCENES[scene_id]
    t1_full = os.path.join(ROOT_DIR, sc["t1_path"])
    t2_full = os.path.join(ROOT_DIR, sc["t2_path"])

    if not os.path.exists(t1_full) or not os.path.exists(t2_full):
        raise HTTPException(status_code=404, detail="Underlying raster files for this scene are missing on disk.")

    session_id = f"SES_{scene_id}_{uuid.uuid4().hex[:6]}"
    sess_dir = os.path.join(SESSIONS_DIR, session_id)
    os.makedirs(sess_dir, exist_ok=True)

    # Copy files to session dir
    sess_t1 = os.path.join(sess_dir, "t1_pre.tif")
    sess_t2 = os.path.join(sess_dir, "t2_post.tif")
    shutil.copyfile(t1_full, sess_t1)
    shutil.copyfile(t2_full, sess_t2)

    # Inspect
    meta1 = RasterInspector.inspect_file(sess_t1)
    meta2 = RasterInspector.inspect_file(sess_t2)
    val = RasterInspector.validate_pair(meta1, meta2)

    _JOB_STATUS[session_id] = {
        "status": "ready",
        "progress": 0,
        "stage": "Ready",
        "message": f"Loaded bundled scene '{sc['name']}' successfully.",
        "t1_path": sess_t1,
        "t2_path": sess_t2,
        "meta_t1": meta1,
        "meta_t2": meta2,
        "validation": val,
        "default_mode": sc["default_mode"]
    }

    return {
        "session_id": session_id,
        "scene_name": sc["name"],
        "default_mode": sc["default_mode"],
        "meta_t1": meta1,
        "meta_t2": meta2,
        "validation": val
    }


@app.post("/api/upload")
async def upload_image_pair(
    file_t1: UploadFile = File(...),
    file_t2: UploadFile = File(...)
):
    """Handles multipart upload of T1 and T2 images and inspects their metadata."""
    session_id = f"SES_UPL_{uuid.uuid4().hex[:8]}"
    sess_dir = os.path.join(SESSIONS_DIR, session_id)
    os.makedirs(sess_dir, exist_ok=True)

    ext1 = os.path.splitext(file_t1.filename)[1] or ".tif"
    ext2 = os.path.splitext(file_t2.filename)[1] or ".tif"
    sess_t1 = os.path.join(sess_dir, f"t1{ext1}")
    sess_t2 = os.path.join(sess_dir, f"t2{ext2}")

    with open(sess_t1, "wb") as f1:
        f1.write(await file_t1.read())
    with open(sess_t2, "wb") as f2:
        f2.write(await file_t2.read())

    meta1 = RasterInspector.inspect_file(sess_t1)
    meta2 = RasterInspector.inspect_file(sess_t2)
    val = RasterInspector.validate_pair(meta1, meta2)

    _JOB_STATUS[session_id] = {
        "status": "ready",
        "progress": 0,
        "stage": "Ready",
        "message": "Images uploaded and validated.",
        "t1_path": sess_t1,
        "t2_path": sess_t2,
        "meta_t1": meta1,
        "meta_t2": meta2,
        "validation": val,
        "default_mode": "encroachment"
    }

    return {
        "session_id": session_id,
        "meta_t1": meta1,
        "meta_t2": meta2,
        "validation": val
    }


@app.post("/api/process")
def process_analysis(req: ProcessRequest, background_tasks: BackgroundTasks):
    """Initiates change detection processing for a session."""
    session_id = req.session_id
    if session_id not in _JOB_STATUS:
        raise HTTPException(status_code=404, detail="Session not found. Please upload or load images first.")

    sess_info = _JOB_STATUS[session_id]
    if sess_info.get("status") == "running":
        return {"status": "running", "message": "Analysis is already executing."}

    def run_worker():
        _JOB_STATUS[session_id]["status"] = "running"
        _JOB_STATUS[session_id]["progress"] = 5
        _JOB_STATUS[session_id]["stage"] = "Starting"
        _JOB_STATUS[session_id]["message"] = "Initializing change detection pipeline..."

        def cb(pct, stage, msg):
            _JOB_STATUS[session_id]["progress"] = pct
            _JOB_STATUS[session_id]["stage"] = stage
            _JOB_STATUS[session_id]["message"] = msg

        try:
            result = ChangeEngine.execute_pipeline(
                t1_path=sess_info["t1_path"],
                t2_path=sess_info["t2_path"],
                prob_threshold=req.prob_threshold,
                min_area_px=req.min_area_px,
                morphology_radius=req.morphology_radius,
                model_choice=req.model_choice,
                normalize_radiometry=req.normalize_radiometry,
                mode=req.mode,
                progress_cb=cb
            )
            _JOB_STATUS[session_id]["status"] = "completed"
            _JOB_STATUS[session_id]["progress"] = 100
            _JOB_STATUS[session_id]["stage"] = "Finished"
            _JOB_STATUS[session_id]["message"] = "Processing completed successfully!"
            _JOB_STATUS[session_id]["analysis_id"] = result["analysis_id"]
        except Exception as e:
            _JOB_STATUS[session_id]["status"] = "failed"
            _JOB_STATUS[session_id]["stage"] = "Error"
            _JOB_STATUS[session_id]["message"] = str(e)

    # Launch background thread for smooth async updates
    thread = threading.Thread(target=run_worker)
    thread.daemon = True
    thread.start()

    return {"status": "started", "session_id": session_id}


@app.get("/api/analysis/{session_id}/status")
def get_analysis_status(session_id: str):
    """Polls processing progress."""
    if session_id not in _JOB_STATUS:
        raise HTTPException(status_code=404, detail="Session not found.")
    info = _JOB_STATUS[session_id]
    return {
        "status": info.get("status", "unknown"),
        "progress": info.get("progress", 0),
        "stage": info.get("stage", ""),
        "message": info.get("message", ""),
        "analysis_id": info.get("analysis_id", "")
    }


@app.get("/api/analysis/{analysis_id}/summary")
def get_analysis_summary(analysis_id: str):
    """Retrieves scene-level intelligence summary and KPIs."""
    session = get_active_session(analysis_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Analysis '{analysis_id}' not found.")

    return {
        "analysis_id": session["analysis_id"],
        "timestamp": session["timestamp"],
        "detector_name": session["detector_name"],
        "mode": session["mode"],
        "config": session["config"],
        "dimensions": session["dimensions"],
        "kpis": session["kpis"],
        "category_counts": session["category_counts"],
        "category_areas": session["category_areas"],
        "exposed_assets": session["exposed_assets"],
        "meta_t1": session["meta_t1"],
        "meta_t2": session["meta_t2"],
        "validation": session["validation"],
        "console_features": session.get("console_features", []),
        "wgs84_bounds": session.get("meta_t1", {}).get("wgs84_bounds"),
        "export_paths": session.get("export_paths", {})
    }


@app.get("/api/analysis/{analysis_id}/polygons")
def get_analysis_polygons(analysis_id: str):
    """Returns detected vector polygons as GeoJSON."""
    session = get_active_session(analysis_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Analysis '{analysis_id}' not found.")
    return session["geojson"] or {"type": "FeatureCollection", "features": []}


@app.get("/api/analysis/{analysis_id}/polygon/{poly_id}")
def get_polygon_details(analysis_id: str, poly_id: str):
    """Returns deep auditable intelligence for a specific polygon."""
    session = get_active_session(analysis_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Analysis '{analysis_id}' not found.")
    try:
        data = PolygonIntelligenceInspector.inspect_polygon(session, poly_id)
        return data
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/analysis/{analysis_id}/pixel")
def get_pixel_details(analysis_id: str, row: int = Query(...), col: int = Query(...)):
    """Returns pixel-level reasoning and 11x11 neighborhood context."""
    session = get_active_session(analysis_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Analysis '{analysis_id}' not found.")
    try:
        data = PixelIntelligenceInspector.inspect_pixel(session, row, col)
        return data
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/analysis/{analysis_id}/layers/{layer_name}")
def get_raster_layer(analysis_id: str, layer_name: str):
    """Serves high-resolution PNG visualization layers for web mapping."""
    session = get_active_session(analysis_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Analysis '{analysis_id}' not found.")

    p_dict = session.get("raster_paths", {})
    aliases = {"bin": "binary", "clean": "cleaned"}
    resolved_name = aliases.get(layer_name, layer_name)
    if resolved_name not in p_dict or not os.path.exists(p_dict[resolved_name]):
        raise HTTPException(status_code=404, detail=f"Layer '{layer_name}' not available.")

    return FileResponse(p_dict[resolved_name], media_type="image/png")


@app.post("/api/analysis/{analysis_id}/report")
def generate_pdf_report(analysis_id: str, req: ReportRequest):
    """Generates either a Full Scene PDF Audit or a Single-Polygon Investigation Dossier."""
    session = get_active_session(analysis_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Analysis '{analysis_id}' not found.")

    out_dir = os.path.join(ROOT_DIR, "data", "outputs", analysis_id)
    os.makedirs(out_dir, exist_ok=True)

    if req.polygon_id:
        filename = f"TRACE_Dossier_{req.polygon_id}.pdf"
        out_path = os.path.join(out_dir, filename)
        ComprehensiveReportGenerator.generate_single_polygon_report(session, req.polygon_id, out_path)
    else:
        filename = f"TRACE_Full_Audit_{analysis_id}.pdf"
        out_path = os.path.join(out_dir, filename)
        ComprehensiveReportGenerator.generate_full_scene_report(session, out_path)

    return {
        "status": "ready",
        "filename": filename,
        "download_url": f"/api/analysis/{analysis_id}/report/{filename}"
    }


@app.get("/api/analysis/{analysis_id}/report/{filename}")
def download_pdf_report(analysis_id: str, filename: str):
    """Serves generated PDF reports."""
    pdf_path = os.path.join(ROOT_DIR, "data", "outputs", analysis_id, filename)
    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="Report file not found.")
    return FileResponse(pdf_path, media_type="application/pdf", filename=filename)


@app.get("/api/analysis/{analysis_id}/export/{fmt}")
def export_gis_data(analysis_id: str, fmt: str):
    """Downloads GeoJSON or GeoPackage exports."""
    session = get_active_session(analysis_id)
    if not session:
        raise HTTPException(status_code=404, detail="Analysis not found.")

    paths = session.get("export_paths", {})
    if fmt == "geojson" and "geojson" in paths and os.path.exists(paths["geojson"]):
        return FileResponse(paths["geojson"], media_type="application/geo+json", filename=f"{analysis_id}_changes.geojson")
    elif fmt == "gpkg" and "geopackage" in paths and os.path.exists(paths["geopackage"]):
        return FileResponse(paths["geopackage"], media_type="application/octet-stream", filename=f"{analysis_id}_changes.gpkg")
    else:
        raise HTTPException(status_code=404, detail=f"Format '{fmt}' not available for download.")


@app.get("/api/analysis/{analysis_id}/export/cap/{poly_id}")
def export_cap_xml(analysis_id: str, poly_id: str):
    """Downloads SACHET OASIS CAP v1.2 XML alert draft."""
    session = get_active_session(analysis_id)
    if not session:
        raise HTTPException(status_code=404, detail="Analysis not found.")
    gdf = session["_gdf"]
    matches = gdf[gdf["feature_id"] == poly_id]
    if matches.empty:
        raise HTTPException(status_code=404, detail="Polygon not found.")

    row = matches.iloc[0].to_dict()
    xml_str = CAPAlertExporter.generate_cap_xml(row, event=session["mode"])
    return Response(content=xml_str, media_type="application/xml", headers={
        "Content-Disposition": f"attachment; filename=SACHET_CAP_{poly_id}.xml"
    })


# ---------------------------------------------------------------------------------------------
# "Explain this change" copilot (#45): answers from one case's facts bundle only. The console sends
# the bundle it shows on the Change-to-Action Card; every number in the reply is checked against it
# (src/exporters/grounding.py) and sentences that fail are dropped. Offline, the console answers the
# suggested questions itself from the same facts (web/copilot.js).
# ---------------------------------------------------------------------------------------------
COPILOT_MODEL = os.environ.get("TRACE_COPILOT_MODEL", "claude-opus-5-5")
COPILOT_SYSTEM = (
    "You explain one satellite change-detection case to a government officer who is not a remote-sensing "
    "specialist. Use only the facts in the JSON bundle you are given.\n"
    "- observed_facts: short sentences stating facts from the bundle that answer the question. Copy numbers "
    "exactly as the bundle writes them, with their units.\n"
    "- possible_explanations: short hypotheses that could explain what was observed, phrased as possibilities "
    "the officer should check on the ground, never as conclusions.\n"
    "Never introduce a number, date, place, asset, law or person that is not in the bundle. If the bundle "
    "cannot answer the question, say so as the only observed fact. Plain words; gloss any index name once "
    "(for example 'NDBI, a built-up index'). At most four items per list."
)
COPILOT_SCHEMA = {
    "type": "object",
    "properties": {"observed_facts": {"type": "array", "items": {"type": "string"}},
                   "possible_explanations": {"type": "array", "items": {"type": "string"}}},
    "required": ["observed_facts", "possible_explanations"],
    "additionalProperties": False,
}


class ExplainRequest(BaseModel):
    question: str
    facts: Dict[str, Any]


@app.post("/api/explain")
def explain_change(req: ExplainRequest):
    from src.exporters.grounding import keep_grounded
    question = req.question.strip()[:500]
    if not question:
        raise HTTPException(status_code=400, detail="Ask a question about the selected case.")
    try:
        import anthropic
    except ImportError:
        raise HTTPException(status_code=503, detail="Copilot model unavailable: the anthropic package is not installed.")
    try:
        client = anthropic.Anthropic()
        # fallbacks="default": if a safety classifier declines, the API re-runs the request on its
        # recommended fallback model instead of returning the refusal
        resp = client.beta.messages.create(
            model=COPILOT_MODEL,
            max_tokens=4000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=COPILOT_SYSTEM,
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": COPILOT_SCHEMA}},
            messages=[{"role": "user", "content": "Case facts (JSON):\n"
                       + json.dumps(req.facts, ensure_ascii=False, sort_keys=True) + f"\n\nQuestion: {question}"}],
        )
    except anthropic.AuthenticationError:
        raise HTTPException(status_code=503, detail="Copilot model unavailable: no Anthropic credentials on the server.")
    except anthropic.RateLimitError:
        raise HTTPException(status_code=429, detail="Copilot is busy; try again in a minute.")
    except anthropic.APIStatusError as e:
        raise HTTPException(status_code=502, detail=f"Copilot model error ({e.status_code}).")
    except anthropic.APIConnectionError:
        raise HTTPException(status_code=503, detail="Copilot model unreachable from the server.")
    except anthropic.AnthropicError as e:
        raise HTTPException(status_code=503, detail=f"Copilot model unavailable: {e}")
    except TypeError as e:                  # the SDK raises this when no credential source is configured at all
        if "authentication" not in str(e):
            raise
        raise HTTPException(status_code=503, detail="Copilot model unavailable: no Anthropic credentials on the server.")
    if resp.stop_reason == "refusal":
        return {"observed_facts": [], "possible_explanations": [], "removed": 0, "refused": True, "model": resp.model}
    text = next((b.text for b in resp.content if b.type == "text"), "{}")
    data = json.loads(text)
    facts = keep_grounded(data.get("observed_facts", []), req.facts)
    hyps = keep_grounded(data.get("possible_explanations", []), req.facts)
    return {"observed_facts": facts["kept"], "possible_explanations": hyps["kept"],
            "removed": len(facts["dropped"]) + len(hyps["dropped"]), "model": resp.model}


# ---------------------------------------------------------------------------------------------
# Field verification sync (#31). The console keeps an offline outbox of case actions and site photos;
# when it is served by this app and online it pushes the outbox here and pulls everyone else's entries.
# ponytail: one JSON file + a process lock; move to the Supabase workflow (#13) for multi-site use.
# ---------------------------------------------------------------------------------------------
FIELD_SYNC = os.path.join(SESSIONS_DIR, "field_sync.json")
_SYNC_LOCK = threading.Lock()
MAX_PHOTO_CHARS = 4_000_000          # ~3 MB image as a data URI; the console downsizes photos before queueing
ENTRY_KEYS = {"uid", "ts", "sector", "case", "from", "to", "role", "actor", "note", "action", "assignee", "photos", "method"}


class FieldSync(BaseModel):
    entries: List[Dict[str, Any]] = []
    photos: List[Dict[str, Any]] = []


def _load_sync() -> Dict[str, list]:
    if os.path.exists(FIELD_SYNC):
        with open(FIELD_SYNC, encoding="utf-8") as f:
            return json.load(f)
    return {"entries": [], "photos": []}


@app.post("/api/field/sync")
def field_sync(req: FieldSync):
    entries = [{k: v for k, v in e.items() if k in ENTRY_KEYS} for e in req.entries
               if isinstance(e.get("uid"), str) and isinstance(e.get("case"), str) and isinstance(e.get("to"), str)]
    photos = [p for p in req.photos if isinstance(p.get("id"), str) and isinstance(p.get("data"), str)
              and p["data"].startswith("data:image/") and len(p["data"]) <= MAX_PHOTO_CHARS]
    with _SYNC_LOCK:
        store = _load_sync()
        seen = {e["uid"] for e in store["entries"]}
        new = [e for e in entries if e["uid"] not in seen]
        store["entries"].extend(new)
        have = {p["id"] for p in store["photos"]}
        store["photos"].extend(p for p in photos if p["id"] not in have)
        with open(FIELD_SYNC, "w", encoding="utf-8") as f:
            json.dump(store, f, ensure_ascii=False)
    return {"accepted": len(new), "entries": store["entries"], "photo_ids": [p["id"] for p in store["photos"]]}


@app.get("/api/field/photo/{photo_id}")
def field_photo(photo_id: str):
    match = next((p for p in _load_sync()["photos"] if p["id"] == photo_id), None)
    if match is None:
        raise HTTPException(status_code=404, detail="Photo not synced yet.")
    return match


# Mount frontend static directory
web_dir = os.path.join(ROOT_DIR, "web")
if os.path.exists(web_dir):
    app.mount("/static", StaticFiles(directory=web_dir), name="static")

    @app.get("/")
    def serve_frontend():
        return FileResponse(os.path.join(web_dir, "index.html"))
