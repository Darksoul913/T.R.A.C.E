# T.R.A.C.E. 🛰️ (Terrain Analysis & Change Evaluation) — Bi-Temporal Satellite Change Intelligence Engine
> **GEOAI 04**: Bi-Temporal Satellite Change Detection for Rapid Urban Encroachment & Disaster Impact

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![PyTorch MPS](https://img.shields.io/badge/PyTorch-MPS%20Accelerated-orange.svg)](https://pytorch.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## 📌 Executive Summary

Satellite providers routinely deliver pre- and post-event imagery within hours of an event, but emergency agencies (FEMA, UN-SPIDER, NDRF, SDMA/DDMAs) and urban planning authorities face severe operational bottlenecks:
1. **The "False Alarm Avalanche"**: Traditional difference models trigger massive false alarms from seasonal vegetation cycles, sun angle variations, building facade parallax, and sensor haze.
2. **The "Raster Dump Dilemma"**: Academic models output raw, unindexed 2D pixel masks rather than localized, GIS-ready vector polygons loadable into emergency dispatch or QGIS/ArcGIS workflows.
3. **The 15-Year Planning Blindspot**: Under India's Disaster Management framework, District Disaster Management Plans (DDMPs) must be updated annually, yet they still rely on 2011 Census baselines. Fast-growing peri-urban sprawl in floodplains remains completely unmapped.

**T.R.A.C.E.** is an automated, end-to-end change-intelligence engine that accepts co-registered bi-temporal orthorectified GeoTIFF imagery and extracts **actionable, false-alarm-filtered vector polygons** with **true geodesic metric surface areas ($m^2$)** categorized into **severity tiers**.

---

## ⚡ Two-Track Architecture & The 14-Feature Battle Plan

T.R.A.C.E. routes imagery through specialized detection engines depending on sensor resolution and operational context:
- **Track A (VHR Aerial $\le 2\text{ m}$)**: Bitemporal Transformer (BIT) with ResNet-18 tokenizer and cross-temporal attention.
- **Track B (Sentinel-2 Multispectral $10\text{--}20\text{ m}$)**: 21-feature spectral network on Red, NIR, and SWIR bands with phenology suppression, trained and evaluated strictly leave-one-city-out across 14 OSCD cities.
- **Track E (Disaster Event Modes)**: Physics-informed spectral indices with fixed literature thresholds validated against official Copernicus EMS satellite delineations (EMSR686 wildfire, EMSR838 flood).

### The 14-Feature Battle Plan (IDEATION_DOC.md Mapping)

#### Core Build (Must Work Flawlessly)
1. **Pretrained Siamese Architecture & Two-Track Router**: Bitemporal Transformer (BIT) for $\le 2\text{ m}$ aerial imagery (F1 **$89.5\%$** on LEVIR-CD); Track B MLP for $10\text{ m}$ Sentinel-2 with phenology suppression (F1 **$22.2\%$** LOCO vs $0.00\%$ for BIT).
2. **Naive NDVI Difference Baseline Comparator**: Live side-by-side toggle proving false alarm rejection over naive thresholding.
3. **Tiled Sliding-Window Inference with Overlap**: Slices arbitrarily large GeoTIFFs ($1024 \times 1024$, $2048 \times 2048$) with 2D Hann window blending to eliminate edge seams.
4. **Radiometric Normalization & Harmonisation**: Grid alignment, phase-correlation registration of $T_1$ onto $T_2$ (1–3 px), and radiometric assessment.
5. **Sentinel-2 SCL Cloud & Shadow Masking**: SCL classes (L2A) or spectral cirrus/brightness tests (L1C); masked pixels form an explicit **unobservable** layer, never reported as "no change".
6. **Semantic Change-Type Labelling**: 9-rule decision table on true surface reflectance ($\Delta$NDBI, $\Delta$MNDWI, $\Delta$NDVI, $\Delta$NBR): new built-up, cleared / possible construction, water-body encroachment, flood, burn scar, seasonal vegetation, ground disturbance.
7. **Clean Geospatial Vectorization**: Morphological opening/closing, Polsby-Popper compactness filtering (removes boundary slivers), Shapely simplification, and local UTM reprojection for true geodesic metric area ($m^2$).
8. **Multi-Factor Severity Scoring**: Dynamic formula: Area (resolution-aware) × Magnitude × Type Weight × Exposure, in Encroachment and Disaster modes, banded Critical / High / Medium / Low.
9. **Multi-Format GIS Export**: Direct download of OGC GeoPackage (`.gpkg` with spatial index) and GeoJSON (`.geojson`).
10. **Interactive Split-View Swipe Web Application**: Standalone light console (`web/index.html`) with curtain swipe, detector badges, EMS reference outlines, filterable attribute table, and click-to-zoom inspector, plus Streamlit console (`web/app.py`).

#### Headline Features (The Winning Edge)
11. **OSM Asset Exposure & Encroachment Overlay**: Automated Geofabrik extract matching (`osm_extract_for()`) across all 28 global sectors. 500 m critical asset buffer (hospitals, schools) and conservation screening (CRZ 50 m tidal water, DCPR nalas, reserved forests).
12. **Auto-Generated 1-Page Situation Report (SitRep PDF)**: Executive briefing PDF with sector-tailored emergency directives and detector accuracy notes ready for DDMA / District Magistrates.

#### Stretch Goals (Validated in Evaluation)
13. **Robustness Stress-Testing Module**: Perturbation analysis under brightness ($\pm 15/30\%$), cast shadows, and misregistration (`src/models/stress_test.py`).
14. **Quantitative Benchmark Metrics Panel**: Multi-modal metrics card showing LEVIR-CD building recall by size, Copernicus EMS event validation, Track B LOCO evaluation, and false alarms per 100 km².

#### Extended Platform Capabilities
- **Copernicus EMS Disaster Impact Validation**: Dedicated disaster detectors for wildfire burn severity ($dNBR \ge 0.27$, Evros EMSR686, F1 **$91.8\%$**) and flood inundation ($MNDWI > 0$, Trimmu EMSR838, F1 **$76.4\%$**) validated against official EMS delineations.
- **Missed-Encroachment Defence**: Multi-year Sentinel-2 trend analysis (Theil–Sen slope), precursor detection (cleared plots, new tracks), and recall-first thresholds inside protected zones.
- **Officer Case Workflow**: Browser-based audit trail: New → Under review → Field verification → Confirmed → Reported → Resolved (or Dismissed), CAP alerts gated on verification, and citizen lookup showing verified cases only.

---

## 📊 Benchmark Evaluation Results

### 1. High-Resolution Aerial Benchmark (LEVIR-CD Official Test Split, 128 Pairs, 33.5 km² at 0.5 m)
| Metric | Naive Spectral Baseline | T.R.A.C.E. (BIT) |
| :--- | :---: | :---: |
| **F1-Score** | 10.5% | **89.5%** |
| **IoU** | 5.6% | **81.0%** |
| **False alarms per 100 km² of unchanged land** | 24.0 km² | **0.55 km²** |
| **Objects found (≥ 50% covered), 7,027 buildings** | 19.4% | **93.9%** |
| **…of which < 400 m²** | 18.4% | **93.9%** |

- **Slow change (synthetic 4-step sequences)**: Comparing only consecutive images finds 33% of objects; anchoring to the initial baseline finds 77%.
- **Runtime**: 0.74 s per km² at 0.5 m (5.4 Mpx/s) on Apple Silicon GPU/MPS.

### 2. Disaster Event Validation vs. Copernicus EMS Delineations
Evaluated on final vectorized polygons within official EMS reference AOIs:

| Event & Sensor | Copernicus Reference | T.R.A.C.E. Event Detector | Naive NDVI Baseline | Track B (Urban S2) |
| :--- | :--- | :---: | :---: | :---: |
| **Evros Wildfire (EMSR686)**<br>Sentinel-2 (10 m), Aug 2023 | WorldView-2 Post-fire Optical Delineation | **F1: 91.8%**<br>(P: 98.6%, R: 85.9%) | F1: 89.2%<br>(P: 95.4%, R: 83.8%) | F1: 2.1%<br>(P: 90.4%, R: 1.1%) |
| **Trimmu Flood (EMSR838 AOI05)**<br>Sentinel-2 (10 m), Sep 2025 | Sentinel-1 SAR Flood Inundation Delineation | **F1: 76.4%**<br>(P: 63.6%, R: 95.7%) | F1: 58.6%<br>(P: 44.0%, R: 88.0%) | F1: 2.2%<br>(P: 36.8%, R: 1.1%) |

*Note: Event detectors use fixed literature thresholds ($dNBR \ge 0.27$ for wildfire, $MNDWI > 0$ for flood) without event tuning. Naive NDVI detects wildfire well but lacks severity banding; Track B is trained on urban change and correctly rejects disaster signals.*

### 3. Sentinel-2 Urban Change Benchmark (OSCD 14 Labelled Cities, 10 m Multispectral)
| Metric | BIT (Track A, Out-of-Domain) | Naive NDVI Baseline | Index Rules Baseline | Track B (Spectral Network, LOCO) |
| :--- | :---: | :---: | :---: | :---: |
| **Pooled F1-Score** | 0.0% | 7.7% | 7.8% | **22.2%** (Precision: 40.0%, Recall: 15.4%) |
| **False alarms per 100 km²** | 0.00 km²* | 2.50 km² | 2.45 km² | **0.54 km²** |
| **Object Precision (real polygons)** | 0.0% | 0.2% | 0.3% | **73.0%** (108 of 148 polygons confirmed) |
| **Seasonal Pair False Alarms (Mumbai)** | 0.0% | 80.4% | 65.1% | **11.6%** (filtered by phenology suppression) |

*\*BIT scores 0.00% because aerial weights do not transfer to 10 m mixed pixels.*

---

## 🏛️ Policy & Standards Alignment
- **SACHET / NDMA**: 1-click generation of OASIS CAP v1.2 XML alert drafts (`Draft - Awaiting DDMA Approval`).
- **Disaster Management (Amendment) Act, 2025**: Continuous floodplain and drain monitoring for newly formed **Urban Disaster Management Authorities (UDMAs - Sec 41A)**.
- **DPDP Act, 2023**: Aggregated spatial footprints; zero individual property or personal citizen identification.
- **Citizen Vernacular Safety Portal**: Plain-language safety lookups in **English**, **मराठी (Marathi)**, and **हिंदी (Hindi)** with a 1-tap community ground-truth confirmation loop.

---

## 🚀 Quick Start Guide

### 1. Prerequisites
- Python 3.12
- macOS (Apple Silicon MPS GPU accelerated) or Linux/Windows with PyTorch

### 2. Setup Virtual Environment
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Generate Standardized GeoTIFF Test Pairs & Train Track B
```bash
python scripts/build_data.py        # OSCD Mumbai & local LEVIR sample tiles
python scripts/fetch_s2.py          # Earth Search Sentinel-2 L2A + Copernicus EMS event sectors (Evros wildfire, Trimmu flood)
python -m src.models.track_b        # Trains Track B 14-fold LOCO models + full network -> checkpoints/s2_track_b.pt (~24s)
```
`fetch_s2.py` writes the `mumbai_s2` change pair (2019 → 2025, SCL cloud mask), Copernicus EMS disaster event pairs (`evros_fire`, `trimmu_flood` with official EMS ground-truth rasters), and multi-year series for slow-creep analysis.

Self-checks (plain asserts):
```bash
python tests/test_synthetic.py                 # Vectorizer, UTM projection, morphology, sliver rejection
python -m src.geospatial.events                # Copernicus EMS event scorers (wildfire dNBR, flood MNDWI)
python -m src.geospatial.creep                 # Theil-Sen slow creep, precursor plots/tracks, recall-first zones
python -m src.data.harmonise                   # Phase-correlation registration, shift correction
python src/geospatial/spectral_indices.py      # 9-rule semantic change-type classification
python -m src.geospatial.severity              # Multi-factor severity scoring (Encroachment & Disaster modes)
python -m src.geospatial.osm_overlay           # CRZ tidal water, DCPR nalas, and protected zone screening
```

### 4. Run Quantitative Benchmark Evaluation & Stress Test
```bash
python src/models/evaluate.py      # ~10 min -> LEVIR-CD, OSCD LOCO, Copernicus EMS event validation, seasonal pair
python src/models/stress_test.py   # ~35 min -> Illumination & cast shadow robustness analysis
```
`evaluate.py` benchmarks:
1. High-resolution aerial performance on 128 LEVIR-CD test pairs (F1 89.5%, object recall 93.9%).
2. Disaster impact validation against official Copernicus EMS satellite delineations (Evros wildfire F1 91.8%, Trimmu flood F1 76.4%).
3. Track B urban change detector evaluated leave-one-city-out across 14 labelled OSCD cities (F1 22.2%, object precision 73.0%).
4. False alarm rejection across a monsoon-to-dry-season seasonal pair (phenology suppression).

### 5. Build Standalone Static Console (`web/index.html`)
```bash
.venv/bin/python scripts/build_scenes.py         # Runs Track A / Track B / Event detectors across all 28 sectors
python scripts/build_frontend_light.py            # Bundles all sectors, images, and benchmarks into web/index.html
```

#### Automated OSM Extract Matching (`osm_extract_for`)
OSM asset exposure (hospitals, schools, protected zones) uses offline committed snapshots in `data/osm/`. When generating a new sector, `osm_extract_for()` automatically queries Geofabrik's hierarchy to download the smallest regional extract covering the bounding box into `data/raw/osm/`, checksum-verifying the file before extracting vector features.

### 6. Launch Console
Open `web/index.html` directly in any web browser, or serve it locally:
```bash
python -m http.server 8000 --directory web
```
Open `http://localhost:8000`.

Alternatively, launch the interactive Streamlit GIS console:
```bash
streamlit run web/app.py
```
Open `http://localhost:8501`.

---

## 📁 Repository Structure
```
HFD/
├── IDEATION_DOC.md           # Definitive system specification & ideation blueprint
├── report.md                 # Detailed evaluation audit, battle plan status & benchmark metrics
├── requirements.txt          # Python dependencies
├── checkpoints/              # Model weights: BIT_LEVIR_best.pt (Track A) & s2_track_b.pt (Track B)
├── data/
│   ├── raw/                  # Downloaded raw rasters & Geofabrik OSM extracts (git-ignored)
│   ├── osm/                  # Offline OSM exposure snapshots & gazetteers for all 28 sectors
│   ├── watch_areas.json      # Sentinel-2 coordinates, acquisition dates, and event AOIs
│   ├── geotiff/              # Standardized orthorectified GeoTIFF pairs + EMS ground truth
│   └── outputs/              # Exported GeoPackage, GeoJSON, CAP XML, SitRep PDFs, and benchmark JSONs
├── src/
│   ├── data/                 # GeoTIFF I/O, phase correlation harmonisation, and dataset loaders
│   ├── models/               # BIT Transformer (Track A), Track B S2 MLP, Naive baseline, and Tiled inference
│   ├── geospatial/           # Vectorization, UTM projection, spectral indices, events, creep, and OSM overlay
│   └── exporters/            # GeoPackage, GeoJSON, SACHET CAP XML, and SitRep PDF generators
├── web/
│   ├── index.html            # Standalone single-page mission control console (zero external assets)
│   └── scenes.json           # Serialized feature vectors, metadata, and benchmarks across 28 sectors
└── scripts/
    ├── build_scenes.py       # Full pipeline runner across all 28 sectors (Track A, Track B, Event engines)
    ├── build_frontend_light.py # Single-file inlining generator for web/index.html
    └── fetch_s2.py           # Earth Search STAC Sentinel-2 L2A & Copernicus EMS harvester
```
