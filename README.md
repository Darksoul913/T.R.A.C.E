# T.R.A.C.E. 🛰️ — Bi-Temporal Satellite Change Intelligence Engine
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

## ⚡ The 14-Feature Battle Plan

### Core Build (Must Work Flawlessly)
1. **Bitemporal Transformer (BIT)**: ResNet-18 tokenizer + Cross-temporal Transformer attention (verified **$94.7\%$ validation accuracy** on LEVIR-CD).
2. **Naive NDVI Difference Baseline Comparator**: Live side-by-side toggle proving our false alarm rejection over naive thresholding.
3. **Tiled Sliding-Window Inference with Overlap**: Slices arbitrarily large GeoTIFFs ($1024 \times 1024$, $2048 \times 2048$) with 2D Hann window blending to eliminate edge seams.
4. **Input Harmonisation**: grid alignment, phase-correlation registration of $T_1$ onto $T_2$ (1–3 px), and optional radiometric normalisation (global histogram or stable-pixel). The stress test showed both normalisations lower F1 on LEVIR-CD, so the default is none.
5. **Cloud & Shadow Masking**: Sentinel-2 SCL classes (L2A) or spectral tests (L1C); masked pixels form an explicit **unobservable** layer, never "no change".
6. **Semantic Change-Type Labelling**: rule table on reflectance ($\Delta$NDBI, $\Delta$MNDWI, $\Delta$NDVI, $\Delta$NBR): new built-up, cleared / possible construction, water-body encroachment, flood, burn scar, seasonal vegetation (phenology rule), ground disturbance.
7. **Clean Geospatial Vectorization**: Morphological opening/closing, Polsby-Popper compactness filtering (removes boundary slithers), Shapely simplification, and local UTM reprojection for true metric area ($m^2$).
8. **Multi-Factor Severity Scoring**: score = resolution-aware area × magnitude × type weight × exposure, in Encroachment and Disaster modes, banded Critical / High / Medium / Low.
9. **Multi-Format GIS Export**: Direct download of OGC GeoPackage (`.gpkg`) and GeoJSON (`.geojson`).
10. **Interactive Web Console**: Split-screen curtain swipe map (Folium / Leaflet) with filterable attribute table and click-to-zoom inspector.

### Headline Features (The Winning Edge)
11. **OSM Asset Exposure & Encroachment Overlay**: hospitals / schools within 500 m raise priority; new construction near tidal water (CRZ 50 m), nalas (DCPR 3–6 m, when resolvable) or inside parks / forests is flagged as a *possible* encroachment to verify, never as a legal finding.
12. **Missed-Encroachment Defence**: slow built-up creep over a yearly Sentinel-2 series, precursor flags (cleared plots, new tracks) and recall-first thresholds inside protected zones.
13. **Officer Case Workflow**: New → Under review → Field verification → Confirmed → Reported → Resolved (or Dismissed), audit log, verdict export; CAP alerts gated on verification; the citizen lookup shows verified cases only.
14. **Auto-Generated 1-Page Situation Report (SitRep PDF)**: Generates an executive emergency brief ready for the District Magistrate / DDMA Commissioner.

### Stretch Goals
15. **Robustness Stress-Testing Module**: brightness ±15/30%, cast shadows and misregistration; normalisation options compared.
16. **Quantitative Benchmark Metrics Panel**: pixel and object metrics, misses by object size, false alarms per 100 km², creep-vs-sudden, OSCD, runtime.

---

## 📊 Benchmark Evaluation Results

LEVIR-CD official test split: 128 pairs, 33.5 km² at 0.5 m, pixel counts pooled (`src/models/evaluate.py`).

| Metric | Naive Spectral Baseline | ChangeIntel (BIT) |
| :--- | :---: | :---: |
| **F1-Score** | 10.5% | **89.5%** |
| **IoU** | 5.6% | **81.0%** |
| **False alarms per 100 km² of unchanged land** | 24.0 km² | **0.55 km²** |
| **Objects found (≥ 50% covered), 7,027 buildings** | 19.4% | **93.9%** |
| **…of which < 400 m²** | 18.4% | **93.9%** |

- Slow change (synthetic 4-step sequences): comparing only consecutive images finds 33% of objects, anchoring to the first image 77%.
- Runtime: 0.74 s per km² at 0.5 m (5.4 Mpx/s) on Apple M5 Max.
- Out of domain: on 14 labelled OSCD Sentinel-2 cities the model scores F1 ≈ 0 (trained on 0.5 m aerial imagery); naive NDVI 7.7%, index rules 7.8%. A Mumbai post-monsoon vs dry-season pair shows naive NDVI flagging 80% of the land.
- Stress test (`src/models/stress_test.py`): neither global histogram matching nor stable-pixel normalisation helps under ±30% brightness or cast shadows, so the pipeline uses none.

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

### 3. Generate Standardized GeoTIFF Test Pairs
```bash
python scripts/build_data.py     # OSCD Mumbai (display + reflectance + labels + cloud mask) and local LEVIR tiles
python scripts/fetch_s2.py       # ~8 min: Sentinel-2 L2A from Earth Search (public STAC) for data/watch_areas.json
```
`fetch_s2.py` writes the `mumbai_s2` change pair (2019 → 2025, real SCL cloud mask) to `data/geotiff/`, and a
2017–2025 dry-season series plus a seasonal no-change pair to `data/raw/s2/` (git-ignored) for creep detection
and the seasonal false-alarm benchmark.

Self-checks (plain asserts):
```bash
python tests/test_synthetic.py                 # 100x100 px change -> one polygon, area ±1%, right centroid
python -m src.data.harmonise                   # shift correction, stable-pixel normalisation
python src/geospatial/spectral_indices.py      # change-type rule table
python -m src.geospatial.severity              # severity formula and modes
python -m src.geospatial.osm_overlay           # CRZ / nala / protected-zone screening
python -m src.geospatial.creep                 # slow creep, precursors, recall-first zones
```

### 4. Run Quantitative Benchmark Evaluation & Stress Test
Uses the official LEVIR-CD test split (128 pairs) if it is in `data/raw/levir_cd_test/` (`A/`, `B/`, `label/`), otherwise the local GeoTIFF tiles:
```bash
mkdir -p data/raw/levir_cd_test && curl -L -o data/raw/levir_cd_test/test.zip \
  https://huggingface.co/datasets/satellite-image-deep-learning/LEVIR-CD/resolve/6a6bb0a5b389403d81c05e33bf08bc0b9e5f13a6/test.zip
(cd data/raw/levir_cd_test && unzip -q test.zip && rm test.zip)   # 496 MB, md5 07d5dd89e46f5c1359e2eca746989ed9

python src/models/evaluate.py      # ~10 min -> data/outputs/benchmark_metrics.json
python src/models/stress_test.py   # ~35 min -> data/outputs/stress_test.json
```
`evaluate.py` reports pixel metrics, object recall by size (missed changes), false alarms per 100 km², a
creep-vs-sudden miss test, runtime, the 14 labelled OSCD cities (with a training-free index-rule detector) and the
seasonal no-change pair. `stress_test.py` compares radiometric normalisation options under brightness / shadow
perturbations and checks misregistration.

### 5. Build the Static Console (`web/index.html`)
```bash
.venv/bin/python scripts/build_scenes.py         # runs BIT + naive baseline per sector -> web/scenes.json + data/outputs/*
python scripts/build_frontend_light.py            # inlines scenes into a self-contained web/index.html
```
Sectors are configured in `SECTORS` at the top of `scripts/build_scenes.py`.

OSM exposure and the citizen pincode / area lookup read committed snapshots in `data/osm/`, so the build works offline.
To regenerate them (e.g. for a new sector), delete the sector's files in `data/osm/` and provide the Geofabrik extract:
```bash
mkdir -p data/raw/osm && curl -L -o data/raw/osm/western-zone-latest.osm.pbf \
  https://download.geofabrik.de/asia/india/western-zone-latest.osm.pbf   # ~220 MB
```
Without a snapshot, the overlay falls back to the live Overpass API, then to "Not assessed".

### 6. Launch Interactive Web Console (Streamlit)
```bash
streamlit run web/app.py
```
Open your browser at `http://localhost:8501`.

---

## 📁 Repository Structure
```
HFD/
├── IDEATION_DOC.md           # Definitive system specification & ideation blueprint
├── requirements.txt          # Python dependencies
├── checkpoints/              # Pretrained model weights (BIT_LEVIR_best.pt - 94.7% acc)
├── data/
│   ├── raw/                  # Downloaded raw data (LEVIR-CD test, OSM extract, Sentinel-2 series), git-ignored
│   ├── osm/                  # OSM exposure snapshots + place / pincode gazetteers (offline)
│   ├── watch_areas.json      # Sentinel-2 areas, change pair, yearly series windows
│   ├── geotiff/              # Standardized orthorectified GeoTIFF test pairs
│   └── outputs/              # Exported GeoPackage, GeoJSON, CAP XML, and SitRep PDFs
├── src/
│   ├── data/                 # GeoTIFF I/O, histogram matching, and dataset builder
│   ├── models/               # BIT Transformer, Siamese UNet, Naive Baseline, and Tiled Inference
│   ├── geospatial/           # Vectorization, UTM projection, spectral indices, and OSM overlay
│   └── exporters/            # GeoPackage, GeoJSON, SACHET CAP XML, and SitRep PDF generators
├── web/
│   └── app.py                # Streamlit split-view interactive dashboard
└── scripts/
    └── build_data.py         # Data preparation and GeoTIFF conversion script
```
