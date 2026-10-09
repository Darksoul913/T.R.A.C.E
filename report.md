# T.R.A.C.E. 🛰️ (Terrain Analysis & Change Evaluation) — Engineering Architecture & Battle Plan Report

> **GEOAI 04**: Bi-Temporal Satellite Change Detection for Rapid Urban Encroachment & Disaster Impact  
> **Status**: Evaluation Complete & All 14 Battle Plan Features Verified (`feat/live-pipeline-console`)

---

## Executive Summary

Satellite providers deliver pre- and post-event imagery within hours, but municipal planning authorities and disaster response agencies face three crippling bottlenecks:
1. **The False Alarm Avalanche**: Naive spectral differencing triggers massive false alarms (up to 80% of land flagged) from seasonal phenology, shifting solar angles, and atmospheric haze.
2. **The "Raster Dump" Disconnect**: Academic models produce unindexed 2D pixel masks rather than GIS-ready, localized vector polygons with true geodesic metric surface areas ($m^2$) categorized into actionable severity tiers.
3. **The 15-Year Planning Blindspot**: District Disaster Management Plans (DDMPs) in India still rely on 2011 Census baselines, leaving fast-growing informal peri-urban settlements in high-risk floodplains and drain setbacks unmapped.

**T.R.A.C.E. (Terrain Analysis & Change Evaluation)** resolves these bottlenecks with an automated, end-to-end change intelligence engine. It routes imagery across a **Two-Track Architecture**, filters false alarms via physics-informed spectral rules and phenology suppression, calculates true geodesic surface areas in local UTM projections, enriches detections with OpenStreetMap (OSM) civic exposure and legal setback screening, and produces decision-grade deliverables: GIS layers (.gpkg, .geojson), executive 1-page Situation Reports (SitRep PDF), SACHET-compatible Common Alerting Protocol (CAP v1.2 XML) alert drafts, and a citizen vernacular safety lookup (English, मराठी, हिंदी).

---

## 🎯 The 14-Feature Battle Plan: Completion & Verification Matrix

Every feature specified in the original blueprint (`IDEATION_DOC.md`) is implemented, integrated, and verified against quantitative benchmarks:

| # | Feature Name | Tier | Status | Implementation Location | Verified Capability & Quantitative Proof |
|---|---|:---:|:---:|---|---|
| **1** | **Siamese ResNet-UNet & BIT Transformer** | Core | ✅ Complete | `src/models/bit.py`, `src/models/siamese_unet.py`, `src/models/track_b.py` | Dual-branch Siamese encoder with cross-temporal attention. **Track A (BIT)** reaches **89.5% F1** / **81.0% IoU** on LEVIR-CD (0.5 m). **Track B (S2 MLP)** scores **22.2% F1** leave-one-city-out across 14 OSCD cities at 10 m (vs 0.00% for BIT). |
| **2** | **Naive NDVI Difference Baseline Comparator** | Core | ✅ Complete | `src/models/naive_baseline.py` | Live side-by-side toggle proving false alarm rejection. Naive NDVI triggers **24.0 km²** false alarms per 100 km² on LEVIR-CD (vs **0.55 km²** for BIT, a **97.7% cut**) and flags **80.4%** of Mumbai during seasonal dry-down. |
| **3** | **Tiled Sliding-Window Inference with Overlap** | Core | ✅ Complete | `src/models/infer.py` | Seamlessly processes arbitrarily large GeoTIFFs (1024×1024, 2048×2048) with 512×512 windowing, 64 px overlap, and 2D Hann cosine window blending to eliminate edge seams. |
| **4** | **Radiometric Normalization & Harmonisation** | Core | ✅ Complete | `src/data/harmonise.py`, `src/data/geotiff_processor.py` | Grid alignment and phase-correlation registration of $T_1$ onto $T_2$ (1–3 px subpixel accuracy). Robust under ±30% brightness shifts; stress test proved unnormalized BIT is inherently robust (0.8947 → 0.8950). |
| **5** | **Cloud & Shadow Masking (Unobservable Layer)** | Core | ✅ Complete | `src/data/geotiff_processor.py`, `scripts/build_scenes.py` | Uses Sentinel-2 Scene Classification Layer (SCL classes 3, 8, 9, 10) for L2A and cirrus/brightness blob tests for L1C. Masked pixels form an explicit **unobservable layer** (hatched in UI), never reported as "no change". |
| **6** | **Semantic Change-Type Labelling via Spectral Indices** | Core | ✅ Complete | `src/geospatial/spectral_indices.py` | Evaluates true surface reflectance shifts across 4 indices (NDBI, MNDWI, NDVI, NBR) with 9 semantic rules: New Built-up, Cleared / Possible Construction, Water-body Encroachment, Flood, Burn Scar, Seasonal Vegetation, Ground Disturbance. |
| **7** | **Clean Geospatial Vectorization & Local UTM Metric Area** | Core | ✅ Complete | `src/geospatial/vectorizer.py` | Morphological opening/closing, resolution-aware minimum area pruning (20 m² at 0.5 m, 2,500 m² at 10 m), Polsby-Popper compactness filtering to drop boundary jitter slivers, Shapely simplification, and local UTM reprojection (`EPSG:32643`, etc.) for true $m^2$. |
| **8** | **Multi-Factor Severity Scoring** | Core | ✅ Complete | `src/geospatial/severity.py` | Dynamic formula: Area (resolution-aware) × Magnitude × Type Weight × Exposure Multiplier. Dual modes (**Encroachment** vs **Disaster**) with 4 operational tiers: Critical (`#EF4444`), High (`#F97316`), Medium (`#EAB308`), Low (`#3B82F6`). |
| **9** | **Multi-Format GIS Export** | Core | ✅ Complete | `src/exporters/gis_export.py` | Single-click export of OGC GeoPackage (`.gpkg` with spatial R-Tree index) and GeoJSON (`.geojson`) for direct ingestion into QGIS, ArcGIS Pro, and emergency dispatch CAD systems. |
| **10** | **Interactive Split-View Swipe Web Application** | Core | ✅ Complete | `web/index.html`, `web/app.py`, `scripts/build_frontend_light.py` | Standalone zero-dependency HTML console (curtain swipe, leaflet/SVG vector overlays, inspector, table, 5 featured sectors + 23 OSCD dropdown) plus companion Streamlit app. |
| **11** | **OSM Asset Exposure & Encroachment Overlay** | Headline | ✅ Complete | `src/geospatial/osm_overlay.py` | Automated Geofabrik regional extract downloader (`osm_extract_for()`) across all 28 sectors. 500 m critical asset buffer (hospitals, schools) and legal screening (CRZ 50 m tidal water, DCPR 3–6 m nala setbacks, reserved forests). |
| **12** | **Auto-Generated 1-Page Situation Report (SitRep PDF)** | Headline | ✅ Complete | `src/exporters/sitrep_pdf.py` | Formats aggregated metrics, Priority 1–2 triage matrices, detector accuracy notes, and role-tailored emergency directives into an official executive A4 briefing PDF for District Magistrates and DDMA Commissioners. |
| **13** | **Robustness Stress-Testing Module** | Stretch | ✅ Complete | `src/models/stress_test.py` | Synthetic perturbation evaluation under brightness scaling (±15%, ±30%), cast shadow masks, and 2 px misregistration. Outputs comparative charts in `data/outputs/stress_test.json`. |
| **14** | **Quantitative Benchmark Metrics Panel** | Stretch | ✅ Complete | `src/models/evaluate.py`, `data/outputs/benchmark_metrics.json` | Comprehensive evaluation panel covering LEVIR-CD building recall by size, Copernicus EMS disaster validations, Track B LOCO metrics across 14 cities, and runtime benchmarks. |

---

## 🏛️ Policy, Governance & Social Features

| Feature | Legal / Regulatory Framework | Implementation Location | Operational Capability |
|---|---|---|---|
| **SACHET CAP v1.2 XML Alert Exporter** | NDMA National Disaster Alerting Protocol (OASIS CAP v1.2 standard) | `src/exporters/cap_alert.py`, web console | 1-click generation of machine-readable XML alert drafts (`status=Draft`, `scope=Restricted`), ready for DDMA authorisation and telecom SMS cell broadcast. Gated behind case verification. |
| **Citizen Vernacular Safety Portal** | Community Ground-Truth & Inclusivity | `web/index.html`, `web/app.py` | Multi-language safety lookups in **English**, **मराठी (Marathi)**, and **हिंदी (Hindi)** by pincode or area name with 1-tap community ground-truth feedback loop. Displays verified cases only to prevent alert panic. |
| **DM Act, 2025 (Sec 41A UDMA) Alignment** | Disaster Management (Amendment) Act, 2025 | `src/geospatial/osm_overlay.py`, `src/geospatial/creep.py` | Sec 41A lets State Governments constitute Urban Disaster Management Authorities (capitals and Municipal Corporation cities, not Delhi or Chandigarh) to prepare an Urban Plan; T.R.A.C.E. supplies its floodplain, stormwater-drain and mangrove-buffer monitoring. Enabling, not mandatory. |
| **DPDP Act, 2023 Compliance** | Digital Personal Data Protection Act, 2023 | System-wide spatial representation | Detections are strictly aggregated geographic footprints; zero linkage to individual land ownership or personal citizen identity records. |

---

## ⚡ Architectural Upgrades & Problem Resolutions

### 1. The Two-Track Architecture
Satellite resolution dictates detection physics:
- **Track A (VHR Aerial $\le 2\text{ m}$)**: Bitemporal Transformer (BIT) with ResNet-18 tokenizer and cross-temporal attention. Trained on LEVIR-CD. Finds **93.9%** of buildings with false alarms of **0.55 km² / 100 km²**.
- **Track B (Sentinel-2 Multispectral $10\text{--}20\text{ m}$)**: 21-feature scale-free spectral network on Red, NIR, and SWIR bands with phenology suppression, trained and evaluated strictly leave-one-city-out across 14 OSCD cities. Scores **22.2% F1** (vs 0.00% for BIT) with **73.0% object precision**.
- **Track E (Disaster Event Modes)**: Physics-informed spectral indices with fixed literature thresholds validated against official Copernicus EMS satellite delineations (EMSR686 wildfire, EMSR838 flood).

### 2. Resolution of Level-1C vs Level-2A Domain Shift
- **The Problem**: OSCD benchmark imagery is Level-1C (top of atmosphere), while Earth Search STAC serves Level-2A (bottom of atmosphere / surface reflectance). Initial 33-feature models flagged 31.5% of Mumbai L2A and 100% of a seasonal no-change pair.
- **The Solution**: 
  1. Pruned blue/green bands vulnerable to atmospheric haze, retraining Track B with a **21-feature Red/NIR/SWIR scale-free feature set**.
  2. Implemented `phenology_suppression()`: suppresses false alarms where vegetation changed ($\Delta\text{NDVI} < 0$) but built-up surface did not rise ($\Delta\text{NDBI} \le 0$).
- **The Result**: Cleaned flagged area in Mumbai L2A dropped to **0.35%**, and seasonal pair false alarms dropped from 100% to **11.6%** (vs 80.4% for naive NDVI).

### 3. Copernicus EMS Disaster Ground-Truth Validation
Validated against official Copernicus Emergency Management Service satellite delineations on final vectorized polygons within observable reference bounds:
- **Evros Wildfire (EMSR686 AOI01, Greece, Aug 2023)**:
  - Reference: WorldView-2 optical delineation (3 Sep 2023).
  - T.R.A.C.E. Wildfire Scorer ($dNBR \ge 0.27$): **F1 91.8%** (Precision 98.6%, Recall 85.9%, IoU 84.9%) over 588.7 km² scope.
  - Naive NDVI: F1 89.2% (lacks severity grading). Track B (Urban): F1 2.1% (correctly rejects wildfire).
- **Punjab / Trimmu Flood (EMSR838 AOI05, Pakistan, Sep 2025)**:
  - Reference: Sentinel-1 SAR flood delineation (2 Sep 2025).
  - T.R.A.C.E. Flood Scorer ($MNDWI > 0$): **F1 76.4%** (Precision 63.6%, Recall 95.7%, IoU 61.8%) over 252.4 km² scope.
  - Naive NDVI: F1 58.6%. Track B (Urban): F1 2.2%.

### 4. Missed-Encroachment Defence (`src/geospatial/creep.py`)
- **Slow Creep Detection**: Multi-year Sentinel-2 time series analysis using Theil–Sen robust slope estimation. Anchoring against initial baselines finds **77%** of slow encroachment (vs 33% for consecutive-pair comparisons).
- **Precursor Identification**: Flags cleared plots ($\Delta\text{NDVI} < -0.15$ with flat NDBI) and new compacted dirt tracks.
- **Recall-First Zones**: Dynamically applies measured recall-favouring thresholds inside protected conservation zones and nala setbacks.

### 5. Automated Geofabrik Regional Extract Matching (`osm_extract_for`)
- Downloads the smallest covering Geofabrik regional extract (`.osm.pbf`) automatically from Geofabrik's hierarchy into git-ignored `data/raw/osm/`.
- Verifies MD5 checksums and extracts offline snapshots for all 28 global sectors into `data/osm/`.

### 6. Officer Case Workflow & Verification Gate
- Browser-based 6-stage case management: `New` → `Under review` → `Field verification` → `Confirmed` → `Reported` → `Resolved` (or `Dismissed`).
- Full audit log with timestamped history and undo support.
- **Safety Gate**: SACHET CAP XML alerts and public citizen safety views only display verified detections, preventing false-alarm-induced public panic or unauthorized enforcement.

---

## 📊 Comprehensive Benchmark Evaluation Records

### 1. LEVIR-CD Official Test Split (128 Pairs, 33.5 km² at 0.5 m GSD)
| Metric | Naive Spectral Baseline | T.R.A.C.E. (BIT) | Improvement |
| :--- | :---: | :---: | :---: |
| **F1-Score** | 10.5% | **89.5%** | **+751.0%** |
| **IoU** | 5.6% | **81.0%** | **+1,359%** |
| **Precision** | 6.4% | **89.8%** | **+1,303%** |
| **Recall** | 30.4% | **89.3%** | **+193.8%** |
| **False Alarms per 100 km²** | 24.0 km² | **0.55 km²** | **97.7% cut** |
| **Objects Found (≥50% covered), 7,027 buildings** | 19.4% | **93.9%** | **+384.0%** |
| **...of which < 400 m² (6,474 buildings)** | 18.4% | **93.9%** | **+410.3%** |
| **Runtime** | — | **0.74 s / km²** (5.4 Mpx/s on M5 Max) | Real-time |

### 2. Copernicus EMS Disaster Impact Validation
| Event & Identifier | Reference Sensor | T.R.A.C.E. Event Detector | Naive NDVI | Track B (Urban) | Scope |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **Evros Wildfire (EMSR686)** | WorldView-2 Optical (0.5m) | **F1: 91.8%** (P: 98.6%, R: 85.9%) | F1: 89.2% | F1: 2.1% | 588.7 km² |
| **Trimmu Flood (EMSR838)** | Sentinel-1 SAR (10m) | **F1: 76.4%** (P: 63.6%, R: 95.7%) | F1: 58.6% | F1: 2.2% | 252.4 km² |

### 3. Sentinel-2 Urban Change (OSCD 14 Labelled Cities, 10 m Multispectral)
| Metric | BIT (Track A, Out-of-Domain) | Naive Baseline | Index Rules | Track B (LOCO MLP) |
| :--- | :---: | :---: | :---: | :---: |
| **Pooled F1-Score** | 0.0% | 7.7% | 7.8% | **22.2%** (P: 40.0%, R: 15.4%) |
| **False Alarms per 100 km²** | 0.00 km²* | 2.50 km² | 2.45 km² | **0.54 km²** |
| **Object Precision (Confirmed)** | 0.0% | 0.2% | 0.3% | **73.0%** (108 / 148 polygons) |
| **Seasonal Pair False Alarms** | 0.0% | 80.4% | 65.1% | **11.6%** (phenology suppressed) |

*\*BIT scores 0.00% because aerial weights do not transfer to 10 m mixed pixels.*

---

## 🔍 Key Findings That Shaped the Architecture

1. **Histogram Matching Degraded High-Resolution F1 by ~5 Points**: While theoretically attractive, histogram matching distorted fine roof textures. Unnormalized BIT achieved higher F1 (0.8953 vs 0.8421), so histogram matching is disabled by default.
2. **Phase-Correlation Registration Moves T1 onto T2**: Because ground-truth labels and field observations align with the post-event state ($T_2$), registration must warp $T_1$ into $T_2$'s coordinate frame.
3. **OSCD Ground-Truth Encoding**: The official OSCD README claims `0 = no change, 1 = change`. Actual files use `1 = no change, 2 = change`. Correcting this parser avoided false all-change masks.
4. **Display Stretches vs. True Reflectance**: Running spectral indices on 8-bit display-stretched RGB produced severe false positives. Switching to genuine top-of-atmosphere and surface reflectance slashed false regions five-fold (1,853 → 355).
5. **Earth Search STAC BOA Offset**: Processing baseline metadata `boa_offset_applied` indicates the offset has already been subtracted; applying it a second time zeroed visible bands.

---

## 🛠️ Verification & Rebuild Workflow

### Quick Test Suite Verification
```bash
.venv/bin/python tests/test_synthetic.py                 # Vectorizer, UTM projection, morphology, sliver rejection
.venv/bin/python -m src.geospatial.events                # Copernicus EMS event scorers (wildfire dNBR, flood MNDWI)
.venv/bin/python -m src.geospatial.creep                 # Theil-Sen slow creep, precursor plots/tracks, recall-first zones
.venv/bin/python -m src.data.harmonise                   # Phase-correlation registration, shift correction
.venv/bin/python src/geospatial/spectral_indices.py      # 9-rule semantic change-type classification
.venv/bin/python -m src.geospatial.severity              # Multi-factor severity scoring (Encroachment & Disaster modes)
.venv/bin/python -m src.geospatial.osm_overlay           # CRZ tidal water, DCPR nalas, and protected zone screening
```

### Full Rebuild Pipeline
```bash
.venv/bin/python scripts/build_data.py                  # Prepare OSCD cities + LEVIR sample tiles
.venv/bin/python scripts/fetch_s2.py                    # Harvest Sentinel-2 L2A & Copernicus EMS rasters
.venv/bin/python -m src.models.track_b                  # Train Track B 14-fold LOCO models (~24s)
.venv/bin/python scripts/build_scenes.py                # Process all 28 sectors -> web/scenes.json + data/outputs/*
.venv/bin/python scripts/build_frontend_light.py        # Compile self-contained web/index.html (55 MB bundle)
.venv/bin/python src/models/evaluate.py                 # Full benchmark suite (~10 min)
```

---

## ⚠️ Known Operational Limitations to State Openly

1. **Track B Operating Tradeoff**: Track B achieves F1 0.22 with 73% object precision, but recovers ~10% of labelled objects due to 10 m spatial mixing. It functions well as a high-precision triage filter, but cannot match 0.5 m aerial detail.
2. **Flood Timing & Dynamics**: Satellite passes and official EMS ground truth can differ by 24–48 hours; dynamic floodwaters move during that window.
3. **Synthetic LEVIR Coordinates**: LEVIR-CD tiles lack geographic georeferencing; Texas sample coordinates are simulated for demonstration.
4. **Buffer Regulations**: CRZ (50 m) and DCPR (3–6 m) buffers follow established legal benchmarks (Down To Earth / Mumbai DP 2034); municipal authorities must cross-reference local revenue cadastres before taking enforcement action.
5. **Console Bundle Size**: The standalone `web/index.html` embeds high-resolution base64 rasters for 28 sectors (~55 MB); recommended for modern desktop browsers or local server hosting.

---

## 🏁 Conclusion

The completion of the doc features and evaluation pipeline establishes T.R.A.C.E. as a robust, fully measured bi-temporal change intelligence platform. From deep learning aerial building extraction (89.5% F1) to satellite disaster impact mapping against Copernicus EMS (91.8% wildfire, 76.4% flood), every feature in the 14-Feature Battle Plan is verified, documented, and operational.
