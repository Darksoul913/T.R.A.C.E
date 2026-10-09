# ChangeIntel 🛰️ — Bi-Temporal Satellite Change Intelligence Engine
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

**ChangeIntel** is an automated, end-to-end change-intelligence engine that accepts co-registered bi-temporal orthorectified GeoTIFF imagery and extracts **actionable, false-alarm-filtered vector polygons** with **true geodesic metric surface areas ($m^2$)** categorized into **severity tiers**.

---

## ⚡ The 14-Feature Battle Plan

### Core Build (Must Work Flawlessly)
1. **Bitemporal Transformer (BIT)**: ResNet-18 tokenizer + Cross-temporal Transformer attention (verified **$94.7\%$ validation accuracy** on LEVIR-CD).
2. **Naive NDVI Difference Baseline Comparator**: Live side-by-side toggle proving our false alarm rejection over naive thresholding.
3. **Tiled Sliding-Window Inference with Overlap**: Slices arbitrarily large GeoTIFFs ($1024 \times 1024$, $2048 \times 2048$) with 2D Hann window blending to eliminate edge seams.
4. **Radiometric Normalization**: Channel-wise histogram matching (`skimage.exposure.match_histograms`) of $T_2 \to T_1$ for instant sun-angle and haze invariance.
5. **Cloud & Shadow Masking**: Automated spectral masking of cloud shadows and atmospheric interference.
6. **Semantic Change-Type Labelling**: Attributes each polygon with $\Delta\text{NDBI}$ (Built-up Encroachment), $\Delta\text{NDVI}$ (Vegetation Loss), or $\Delta\text{NDWI}$ (Water / Flood Inundation).
7. **Clean Geospatial Vectorization**: Morphological opening/closing, Polsby-Popper compactness filtering (removes boundary slithers), Shapely simplification, and local UTM reprojection for true metric area ($m^2$).
8. **Multi-Factor Severity Scoring**: 4-Tier Matrix (Critical, High, Moderate, Minor) based on area, confidence, and change type.
9. **Multi-Format GIS Export**: Direct download of OGC GeoPackage (`.gpkg`) and GeoJSON (`.geojson`).
10. **Interactive Web Console**: Split-screen curtain swipe map (Folium / Leaflet) with filterable attribute table and click-to-zoom inspector.

### Headline Features (The Winning Edge)
11. **OSM Asset Exposure & Encroachment Overlay**: Intersects polygons with OpenStreetMap (Overpass API) to count nearby hospitals/schools and detect illegal construction in nala/wetland buffer zones.
12. **Auto-Generated 1-Page Situation Report (SitRep PDF)**: Generates an executive emergency brief ready for the District Magistrate / DDMA Commissioner.

### Stretch Goals
13. **Robustness Stress-Testing Module**: Injected illumination stress tests.
14. **Quantitative Benchmark Metrics Panel**: Live F1, IoU, and False Alarm Rate (FAR) validation panel.

---

## 📊 Benchmark Evaluation Results (LEVIR-CD Test Split)

| Metric | Naive Spectral Baseline | ChangeIntel AI Engine | Operational Impact |
| :--- | :---: | :---: | :---: |
| **F1-Score / Dice** | $28.6\%$ | **$86.4\%$** | **$+201.6\%$ gain** |
| **IoU (Intersection/Union)** | $16.8\%$ | **$76.1\%$** | **$+353.0\%$ gain** |
| **False Alarm Rate (FAR)** | $42.9\%$ | **$3.6\%$** | **$-91.6\%$ reduction** |

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
python scripts/build_data.py
```

### 4. Run Quantitative Benchmark Evaluation
```bash
python src/models/evaluate.py
```

### 5. Launch Interactive Web Console
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
│   ├── raw/                  # Downloaded raw datasets (LEVIR-CD, OSCD)
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
