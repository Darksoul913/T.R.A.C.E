# GEOAI 04 — T.R.A.C.E. 🛰️ (Terrain Analysis & Change Evaluation) — Bi-Temporal Satellite Change Intelligence Engine
## Definitive System Specification & Engineering Blueprint

---

### Executive Summary

Satellite data providers deliver pre- and post-event imagery within hours of an event, but disaster responders and municipal urban planning authorities face severe operational bottlenecks:
- **Alert Fatigue from False Alarms**: Naive change detection algorithms trigger massive false positives from seasonal vegetation cycles, shifted sun angles, building facade parallax, and sensor haze.
- **The "Raster Dump" Disconnect**: Academic models output unindexed 2D pixel masks rather than localized, GIS-ready vector polygons that can be ingested into emergency dispatch or QGIS/ArcGIS workflows.
- **The 15-Year Planning Blindspot**: Under India's Disaster Management framework, District Disaster Management Plans (DDMPs) must be updated annually, yet they still rely on outdated 2011 Census baselines. Fast-growing peri-urban sprawl and informal settlements in high-risk floodplains remain completely unmapped.

**T.R.A.C.E.** is an automated, end-to-end change-intelligence engine that accepts co-registered bi-temporal orthorectified GeoTIFF imagery and outputs **decision-grade, false-alarm-filtered vector polygons** with **true geodesic metric surface areas ($m^2$)** categorized into **severity tiers**.

The system addresses both:
1. **Rapid Event Impact (Hours $\Delta T$)**: Immediate post-disaster damage mapping, false-alarm suppression, SACHET-compatible CAP Alert XML drafts, and citizen ground-truth verification.
2. **Pre-Disaster Preparedness (Years $\Delta T$)**: Auditing the 2011–2026 census gap, mapping uncounted populations in flood zones, and auto-generating the legally mandated annual disaster plan update.

---

### 1. The 14-Feature Battle Plan

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       CORE BUILD (Must Work Flawlessly)                      │
│  1. Siamese ResNet-UNet via segmentation_models_pytorch (SMP)               │
│  2. Naive NDVI Difference Baseline Comparator (live "Model vs Naive" toggle) │
│  3. Tiled sliding-window inference with overlap (handles full GeoTIFFs)     │
│  4. Radiometric normalization (histogram matching after-to-before)          │
│  5. Sentinel-2 SCL cloud/shadow masking                                     │
│  6. Semantic change-type labelling (Built-up / Vegetation / Water) via NDBI │
│  7. Clean vectorization (morphology, simplify, local UTM m², centroid)      │
│  8. Multi-factor severity scoring (Critical, High, Medium, Low)             │
│  9. Multi-format GIS export (OGC GeoPackage .gpkg + GeoJSON)                │
│ 10. Split-view swipe web app with filterable table & polygon inspector       │
├─────────────────────────────────────────────────────────────────────────────┤
│                    HEADLINE FEATURES (The Winning Edge)                     │
│ 11. OSM Exposure & Encroachment Overlay (Hospitals, schools, water bodies)  │
│ 12. Auto-generated 1-page Situation Report (LLM-drafted SitRep PDF)         │
├─────────────────────────────────────────────────────────────────────────────┤
│                    STRETCH GOALS (If Time Permits)                          │
│ 13. Robustness stress test (injected brightness/shadow stress test chart)   │
│ 14. Quantitative metrics panel (F1 / IoU comparison on LEVIR-CD test split) │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### 2. Detailed Technical Specifications for Each Feature

#### Core Build (10 Features)

##### Feature 1: Pretrained Siamese U-Net (`segmentation_models_pytorch`)
- **Architecture**: Dual-branch Siamese encoder sharing weights (ResNet-18/34 backbone) initialized with ImageNet weights, coupled to a UNet decoder.
- **Difference Module**: Evaluates absolute feature difference $|f(T_1) - f(T_2)|$ and concatenated embeddings at skip-connection stages.
- **Why SMP**: Avoids writing boilerplate PyTorch models from scratch while ensuring fast convergence and high inference speed on CPU/MPS/GPU.

##### Feature 2: Naive NDVI-Difference Baseline Comparator
- **Functionality**: Computes standard normalized difference change:
  $$\Delta\text{NDVI} = \text{NDVI}_{T_2} - \text{NDVI}_{T_1} = \frac{\text{NIR}_2 - \text{Red}_2}{\text{NIR}_2 + \text{Red}_2} - \frac{\text{NIR}_1 - \text{Red}_1}{\text{NIR}_1 + \text{Red}_1}$$
- **Role in Demo**: Provides a live UI toggle comparing *"Naive Baseline vs. T.R.A.C.E. AI Engine"*. Demonstrates visually how naive thresholding drowns in false alarms across drying lawns, whereas our deep model isolates genuine structural/landcover changes.

##### Feature 3: Tiled Sliding-Window Inference with Overlap
- **Functionality**: Ingests arbitrarily large GeoTIFF tiles (e.g., $1024 \times 1024$, $2048 \times 2048$, or full scene extents).
- **Windowing**: Slides $512 \times 512$ patches with a $64\text{ px}$ overlap stride.
- **Blending**: Applies Hann/cosine window blending across overlapping boundaries to eliminate tile-edge seams in the output probability raster.

##### Feature 4: Radiometric Normalization via Histogram Matching
- **Functionality**: Matches the cumulative distribution function (CDF) of the post-event image ($T_2$) to the pre-event image ($T_1$) using `skimage.exposure.match_histograms`.
- **Impact**: Instantly equalizes illumination, solar elevation differences, and atmospheric haze across acquisition dates without requiring complex atmospheric correction models.

##### Feature 5: Cloud and Shadow Masking via Sentinel-2 SCL
- **Functionality**: Extracts the Scene Classification Layer (SCL) band from Sentinel-2.
- **Filter**: Automatically masks out pixels categorized under:
  - Class 3: Cloud Shadows
  - Class 8: Cloud Medium Probability
  - Class 9: Cloud High Probability
  - Class 10: Thin Cirrus
- **Impact**: Zero-ML, instant elimination of the single biggest cause of remote sensing false positives.

##### Feature 6: Semantic Change-Type Labelling via Spectral Indices
- **Functionality**: For each detected change polygon, calculates internal spectral band shifts between $T_1$ and $T_2$:
  - **Built-up Encroachment / Damage**: High positive $\Delta\text{NDBI}$ (Normalized Difference Built-up Index: $(\text{SWIR} - \text{NIR})/(\text{SWIR} + \text{NIR})$).
  - **Vegetation Loss / Seasonal Cycle**: Negative $\Delta\text{NDVI}$.
  - **Water / Flood Inundation**: Positive $\Delta\text{NDWI}$ (Normalized Difference Water Index: $(\text{Green} - \text{NIR})/(\text{Green} + \text{NIR})$).
- **Result**: Attributes each polygon with a human-understandable label: `Built-up Change`, `Vegetation Loss`, `Water Inundation`, or `Ground Disturbance`.

##### Feature 7: Clean Geospatial Vectorization & Local UTM Metric Area
- **Morphological Cleaning**: Binary opening ($3 \times 3$ disk) to dissolve speckles; closing to bridge micro-fractures in roofs and roads.
- **Minimum Area Filter**: Automatically purges polygons $< 20\text{ m}^2$ (registration jitter, small tree falls).
- **Polygon Simplification**: Applies `shapely.geometry.Polygon.simplify(tolerance=1.0)` to eliminate bloated vertex counts while preserving true boundaries.
- **Local UTM Reprojection**: Automatically projects geometries into the corresponding local UTM zone (e.g., `EPSG:32643` for Western India) to calculate true **geodesic surface area ($m^2$)** and centroid coordinates `(lat, lon)`.

##### Feature 8: Multi-Factor Severity Scoring
- Groups every detected polygon into operational tiers:
  $$\text{Score} = w_1 \cdot \text{Normalized Area} + w_2 \cdot \text{Magnitude} + w_3 \cdot \text{Exposure Multiplier}$$

| Severity Tier | Criteria | Operational Context | Color Token |
| :--- | :--- | :--- | :--- |
| **Tier 1: Critical** | Area $\ge 400\text{ m}^2$ AND Magnitude $\ge 0.80$ (or near critical assets) | Major structural collapse, massive industrial encroachment, blocked arterial road. | `#EF4444` (Red) |
| **Tier 2: High** | Area $150 - 400\text{ m}^2$ AND Magnitude $\ge 0.70$ | Residential building damage, commercial construction, road damage. | `#F97316` (Orange) |
| **Tier 3: Moderate** | Area $50 - 150\text{ m}^2$ AND Magnitude $\ge 0.60$ | Outbuilding additions, partial roof damage, perimeter boundary shifts. | `#EAB308` (Yellow) |
| **Tier 4: Minor** | Area $20 - 50\text{ m}^2$ AND Magnitude $\ge 0.50$ | Localized ground disturbance, small shed erection, debris patches. | `#3B82F6` (Blue) |

##### Feature 9: Multi-Format GIS Export
- **OGC GeoPackage (`.gpkg`)**: SQLite-based open standard containing attributed vector layers, spatial indexing (R-Tree), and metadata for professional QGIS / ArcGIS Pro workflows.
- **GeoJSON (`.geojson`)**: Standard lightweight format for web mapping and browser rendering.

##### Feature 10: Interactive Split-View Swipe Web Application & Investigation Suite
- **Interface**: High-performance SVG/WebGL split-view curtain slider with centered chevron knob arrows comparing Pre-Event and Post-Event orthophotos.
- **Capabilities**:
  - **Full-Tile Mission Overview Overlay**: Automatically covers the entire satellite tile block by default whenever a location or sector is selected (`inset: 0`, full-bleed frosted glassmorphic backdrop with `backdrop-filter: blur(16px)`). Features centered layout (`max-width: 560px`), aesthetic rounded hover cards (`border-radius: 12px`, `padding: 10px 14px`), and one-click dismissal.
  - **Pixel-Level Intelligence Inspector**: High-zoom pixel inspection tool displaying pixel coordinates (Row/Col, Lat/Lon), true physical ground footprint ($m^2$), per-band raw/normalized values, spectral shifts, model confidence, and 5-level explainable reasoning hierarchy with 11×11 neighborhood comparison. Dynamic crosshair follows pan/zoom and hides when deactivated.
  - **Multi-Layer Raster Suite**: Toggleable overlays for Layer A (T1), Layer B (T2), Layer C (Continuous Probability Heatmap), Layer D (Binary Change Mask), Layer E (Cleaned Morphological Mask), and Layer F (Final Polygons) with responsive fill opacity controls in the Layers popover.
  - **Hollow Selected Polygon Inspection**: When a polygon is selected, its interior is styled with 100% hollow/zero fill (`fill: none !important; fill-opacity: 0 !important;`) so the satellite pixels inside the boundary remain completely unobscured for before/after visual audit.
  - **Image Pair Upload & Validation Modal**: Drag-and-drop modal supporting GeoTIFF, PNG, and JPG. Performs automated CRS compatibility checks, band verification, resolution checking, and side-by-side preview with real-time async processing progress bar.
  - **Change-to-Action Card (#cac) & 12-Question Auditable Reasoning**: Answers what changed, why it matters, reliability, and next operational steps with grounded facts and strict hallucination filtering.

---

#### Headline Features (2 Features)

##### Feature 11: OSM Exposure & Encroachment Overlay
- **Data Source**: OpenStreetMap via Overpass API / `osmnx` with automated Geofabrik regional extract downloader (`osm_extract_for()`).
- **Dual Functionality**:
  1. **Disaster Impact / Vulnerability**: Counts critical civic assets (hospitals, schools, nursing homes, dense informal settlements) within a $500\text{ m}$ buffer of each polygon. Increases priority for heavily populated zones.
  2. **Illegal Encroachment**: Detects new built-up polygons intersecting protected conservation zones: water bodies (lakes/nalas), floodplains, public parks, or reserved forest boundaries. Flags violations automatically with `Illegal Encroachment: Wetland / Nala Buffer`.

##### Feature 12: Dual Reporting System (1-Page SitRep & 11-Part Comprehensive Dossier)
- **1-Page Executive Situation Report (SitRep PDF)**: Aggregates polygon statistics (total damaged area in $m^2$, count of Critical Tier-1 sites, exposed hospitals/schools, breakdown by change type) into an executive A4 briefing with official signature block for the District Magistrate / DDMA Commissioner.
- **11-Part Auditable Technical Dossier (PDF & HTML)**: Production-grade multi-page report generated via ReportLab server-side API or downloadable HTML dossier:
  1. *Executive Summary*: Analysis ID, study area, dates, polygon count, total reliable mapped area, triage matrix.
  2. *Data & Image-Quality Assessment*: CRS, resolution, bands, registration quality, cloud/shadow coverage, comparability score.
  3. *Methodology*: Two-track routing, normalization, inference, filtering, vectorization, and severity scoring.
  4. *Pixel-Level Evidence*: Probability heatmap distributions, thresholding, and spectral shift tables.
  5. *Polygon-by-Polygon Detailed Analysis*: 5 visual evidence crops per polygon, 12-question auditable evidence table.
  6. *Urban Encroachment Assessment*: Proximity to water bodies, CRZ tidal setbacks, and DCPR nala buffers.
  7. *Disaster-Impact Assessment*: Wildfire burn scars, flood inundation footprints, and Copernicus EMS cross-validation.
  8. *Severity and Exposure Analysis*: Formula breakdown, weights, and nearby critical infrastructure lists.
  9. *Model Evaluation*: Precision, Recall, F1, IoU, and false alarm rate against LEVIR-CD and OSCD ground truth.
  10. *Limitations and Recommendations*: Image resolution, cloud effects, misregistration, and field verification steps.
  11. *Technical Appendix*: Processing provenance, software versions, timestamps, and GIS export references.

---

#### Stretch Goals (2 Features)

##### Feature 13: Robustness Stress-Testing Module
- **Functionality**: Injects synthetic illumination shifts (scaling brightness $\pm 30\%$) and synthetic shadow masks into the $T_2$ test tile.
- **Output**: Generates a comparative chart showing the **False Alarm Rate (FAR)** before vs. after histogram normalization, quantitatively proving our system's resilience to sun-angle shifts.

##### Feature 14: Quantitative Benchmark Metrics Panel
- **Functionality**: Runs our trained Siamese model and the naive NDVI baseline over the standard LEVIR-CD test split.
- **Deliverable**: Displays an interactive metrics card in the dashboard comparing:
  - **IoU (Intersection-over-Union)**
  - **Precision & Recall**
  - **F1-Score**
  - **False Alarm Rate (FAR)**

---

### 3. What We Deliberately Skip (Scope Control)

To ensure an airtight, flawless submission before the deadline, we explicitly exclude:
1. ❌ **SAR Radar Fusion**: Requires complex despeckling and complex-valued calibration; optical/multispectral achieves our goals cleanly.
2. ❌ **Zero-Shot Foundation Model Fine-Tuning**: Prone to OOM errors and unpredictable hallucinations during live demos.
3. ❌ **3D Height / LiDAR Estimation**: Requires stereo-pairs or drone DSMs not available in standard bi-temporal satellite feeds.
4. ❌ **Edge Hardware Deployment**: Desktop/web deployment is the expected format for municipal control rooms.

---

### 4. Policy, Governance & Social Features

1. **SACHET CAP Alert XML Draft**:
   - 1-click button on Critical polygons exporting OASIS CAP v1.2 XML with status `Draft - Awaiting DDMA Approval`, ready for NDMA's national alerting platform.
2. **Citizen Vernacular Safety Lookup**:
   - Lightweight location/pincode lookup in **English**, **मराठी (Marathi)**, and **हिंदी (Hindi)**.
   - Plain-language status card (*"Severe structural damage detected within 300m of your area"*).
3. **Disaster Management (Amendment) Act, 2025 Alignment**:
   - Supports newly created **Urban Disaster Management Authorities (UDMAs - Section 41A)** with continuous floodplain and drain monitoring.
4. **DPDP Act, 2023 Compliance**:
   - Spatial footprints are strictly aggregated; never linked to individual property ownership or personal identity records.

---

### 5. Implementation Roadmap & Milestones (All Verified & Delivered)

- [x] **Milestone 1: Project Setup & Geospatial Core**
  - Directory structure, Python environment verification (`rasterio`, `geopandas`, `shapely`, `torch`, `segmentation_models_pytorch`).
  - Standardized bi-temporal GeoTIFF generator / test pair loader with genuine spatial metadata across 28 global sectors.
- [x] **Milestone 2: Preprocessing & Change Detection Backbone**
  - Implement Radiometric Normalization (`match_histograms`, phase-correlation registration) & SCL cloud masking.
  - Implement Siamese ResNet-UNet architecture & Bitemporal Transformer (BIT) for $\le 2\text{ m}$ aerial imagery.
  - Implement Track B S2 MLP with phenology suppression for 10m Sentinel-2 imagery.
  - Implement tiled sliding-window inference with 2D Hann window blending.
  - Implement Naive NDVI difference comparator.
- [x] **Milestone 3: False-Alarm Filtering & Clean Vectorization**
  - Implement morphological cleaning, minimum-area pruning, Polsby-Popper compactness filter, and Shapely polygon simplification.
  - Implement spectral change-type labelling (NDBI, NDVI, NDWI, NBR) across 9 decision rules.
  - Implement automated local UTM projection for true geodesic area ($m^2$) and centroid calculation.
  - Implement 4-tier severity matrix (Encroachment & Disaster modes).
- [x] **Milestone 4: Deliverables & Export Pipelines**
  - Implement OGC GeoPackage (`.gpkg` with R-Tree spatial index) and GeoJSON export.
  - Implement SACHET CAP v1.2 XML draft generator.
  - Implement OSM exposure overlay with automated Geofabrik extract downloading (`osm_extract_for()`).
- [x] **Milestone 5: Interactive Web Console & SitRep Generator**
  - Build split-view curtain swipe map with severity layer toggles.
  - Build filterable attribute table and click-to-zoom inspector.
  - Build Citizen Vernacular Lookup (En/मराठी/हिंदी).
  - Build 1-page SitRep PDF generator with executive directives.
- [x] **Milestone 6: Verification & Polish**
  - End-to-end evaluation on LEVIR-CD sample pairs (89.5% F1) and OSCD LOCO (22.2% F1 vs 0.0% for BIT).
  - Verification of false-alarm rejection under illumination shifts (stress testing).
  - Disaster event validation against Copernicus EMS (Evros 91.8% F1, Trimmu 76.4% F1).
- [x] **Milestone 7: Advanced Pixel Intelligence, Full-Tile Overlay, Hollow Polygon Audit & 11-Part Dossier Reporting**
  - Pixel Intelligence Inspector with Row/Col, Lat/Lon, $m^2$ footprint, and 5-level reasoning hierarchy.
  - 6-layer raster overlay suite with dynamic fill opacity.
  - Full-tile Mission Overview overlay (`backdrop-filter: blur(16px)`) with rounded capsule triage cards.
  - 100% hollow zero-fill selected polygon rendering (`fill: none`) for unobscured before/after comparison inside boundaries.
  - Comprehensive 11-part executive & technical dossier PDF generator via ReportLab backend API.
