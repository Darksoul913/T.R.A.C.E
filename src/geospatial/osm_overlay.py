"""
osm_overlay.py - OpenStreetMap (OSM) Asset Exposure & Encroachment Overlay (Feature #11).

Intersects change polygons with:
1. Critical civic infrastructure (hospitals, clinics, schools, colleges, nursing homes).
2. Water, by the rule that governs it:
   - tidal water, mangroves, salt marsh, coastline -> CRZ 2019: 50 m no-development zone
   - nalas / drains / streams / rivers -> DCPR 2034: 6 m setback, reducible to 3 m for nallahs
   - other wetlands / lakes / ponds -> Wetlands Rules 2017: zone of influence is set per notification
   - parks, forests, woods, protected areas -> new construction inside one is a possible encroachment
Encroachment is a screening flag ("possible", verify against DP / CRZ maps), never a legal finding.
Buffers per Down To Earth's DCPR 2034 vs CRZ 2019 analysis; confirm against the official texts.

OSM source, in order:
1. A snapshot in data/osm/*.geojson whose bbox covers the scene (works offline).
   Build one from a Geofabrik .osm.pbf with OSMExposureOverlay.build_snapshot().
2. The live Overpass API.
3. Otherwise every polygon is marked "Not assessed" - nothing is invented.
"""

import glob
import json
import os
from typing import Any, Dict, List, Optional

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
from shapely.geometry import Point, box

from src.geospatial.severity import SeverityScorer

AMENITY_RE = "hospital|clinic|school|college|nursing_home"
WATERWAY_RE = "river|stream|drain|canal|ditch"
WATER_NATURAL_RE = "water|wetland|bay"
TIDAL_WETLAND_RE = "mangrove|tidalflat|saltmarsh"
EXPOSURE_RADIUS_M = 500.0   # Ideation Baseline #11: critical assets within 500 m raise priority
CRZ_BUFFER_M = 50.0        # CRZ 2019 no-development zone along tidal water bodies
NALA_SETBACK_M = 6.0       # DCPR 2034 development-free strip (3 m for nallahs)
NEAR_WATER_REPORT_M = 50.0 # report proximity to other water / wetlands within this distance
BUILT_TYPES = ("New Built-up Surface", "New Building / Structure", "Vegetation Cleared / Possible Construction",
               "Water-body Encroachment")
SNAPSHOT_DIR = os.path.join(os.path.dirname(__file__), "../../data/osm")


class OSMExposureOverlay:
    """Queries and intersects OpenStreetMap features to establish civic vulnerability & violations."""

    OVERPASS_URL = "https://overpass-api.de/api/interpreter"

    @staticmethod
    def build_snapshot(pbf_path: str, bbox: List[float], out_path: str) -> gpd.GeoDataFrame:
        """Extracts amenities and water features inside bbox [min_lon, min_lat, max_lon, max_lat]
        from an OSM .pbf extract (e.g. Geofabrik) into a small GeoJSON snapshot."""
        import pyogrio

        bb = tuple(bbox)
        pts = pyogrio.read_dataframe(pbf_path, layer="points", bbox=bb)
        lines = pyogrio.read_dataframe(pbf_path, layer="lines", bbox=bb)
        polys = pyogrio.read_dataframe(pbf_path, layer="multipolygons", bbox=bb)

        pt_amenity = pts.other_tags.fillna("").str.extract(f'"amenity"=>"({AMENITY_RE})"')[0]
        pts = pts.assign(type=pt_amenity).dropna(subset=["type"])
        poly_am = polys[polys.amenity.fillna("").str.fullmatch(AMENITY_RE)]
        amenities = pd.concat([
            pts[["name", "type", "geometry"]],
            gpd.GeoDataFrame({"name": poly_am.name, "type": poly_am.amenity,
                              "geometry": poly_am.geometry.representative_point()}, crs=polys.crs),
        ]).assign(kind="amenity")

        tag = lambda df, k: df.other_tags.fillna("").str.extract(f'"{k}"=>"([^"]+)"')[0].fillna("")
        ww = lines[lines.waterway.fillna("").str.fullmatch(WATERWAY_RE)]
        coast = lines[tag(lines, "natural") == "coastline"]
        wp = polys[polys.natural.fillna("").str.fullmatch(WATER_NATURAL_RE)]
        wl, wt, tidal = tag(wp, "wetland"), tag(wp, "water"), tag(wp, "tidal") == "yes"
        wp_cls = np.select(
            [tidal | wl.str.fullmatch(TIDAL_WETLAND_RE) | (wp.natural == "bay") | wt.isin(["lagoon", "bay"]),
             wt.isin(["drain", "canal", "river", "stream"]), wp.natural == "wetland"],
            ["tidal", "nala", "wetland"], "waterbody")
        water = pd.concat([
            gpd.GeoDataFrame({"name": ww.name, "type": ww.waterway, "cls": np.where(ww.waterway == "river", "river", "nala"),
                              "geometry": ww.geometry}, crs=lines.crs),
            gpd.GeoDataFrame({"name": coast.name, "type": "coastline", "cls": "tidal", "geometry": coast.geometry}, crs=lines.crs),
            gpd.GeoDataFrame({"name": wp.name, "type": np.where(wl != "", wl, np.where(wt != "", wt, wp.natural)), "cls": wp_cls,
                              "geometry": wp.geometry}, crs=polys.crs),
        ]).assign(kind="water")

        # protected open land; note polys["boundary"], not polys.boundary (the geometric boundary)
        prot_type = np.select(
            [polys.leisure.fillna("").isin(["park", "nature_reserve"]), polys.landuse.fillna("") == "forest",
             polys.natural.fillna("") == "wood", polys["boundary"].fillna("").isin(["protected_area", "national_park"])],
            [polys.leisure.fillna(""), "forest", "wood", "protected area"], "")
        pr = polys[prot_type != ""]
        protected = gpd.GeoDataFrame({"name": pr.name, "type": prot_type[prot_type != ""], "cls": None,
                                      "geometry": pr.geometry}, crs=polys.crs).assign(kind="protected")

        snap = gpd.GeoDataFrame(pd.concat([amenities, water, protected], ignore_index=True), crs="EPSG:4326")
        snap["geometry"] = snap.geometry.simplify(1e-5)
        snap["name"] = snap["name"].where(snap["name"].notna(), None)
        fc = json.loads(snap.to_json(drop_id=True))
        fc["bbox"] = list(bbox)
        fc["source"] = os.path.basename(pbf_path)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(fc, f)
        return snap

    @staticmethod
    def build_gazetteer(pbf_path: str, bbox: List[float], out_path: str, min_postcode_hits: int = 3) -> List[Dict[str, Any]]:
        """Offline place / pincode lookup table for the citizen portal: named suburbs, neighbourhoods
        and localities (with Marathi / Hindi names when tagged), plus each 6-digit addr:postcode located
        at the median of the features carrying it.
        ponytail: OSM has no Indian postal boundaries, so a pincode is a point, not an area."""
        import pyogrio

        bb = tuple(bbox)
        pts = pyogrio.read_dataframe(pbf_path, layer="points", bbox=bb)
        polys = pyogrio.read_dataframe(pbf_path, layer="multipolygons", bbox=bb)
        tag = lambda s, k: s.fillna("").str.extract(f'"{k}"=>"([^"]+)"')[0]

        places = pts[pts.place.isin(["suburb", "neighbourhood", "locality", "quarter"]) & pts.name.notna()]
        out = [{"name": r.name, "name_mr": mr if isinstance(mr, str) else None, "name_hi": hi if isinstance(hi, str) else None,
                "kind": r.place, "lat": round(r.geometry.y, 6), "lon": round(r.geometry.x, 6)}
               for r, mr, hi in zip(places.itertuples(), tag(places.other_tags, "name:mr"), tag(places.other_tags, "name:hi"))]

        coded = pd.concat([
            pd.DataFrame({"pin": tag(pts.other_tags, "addr:postcode"), "x": pts.geometry.x, "y": pts.geometry.y}),
            pd.DataFrame({"pin": tag(polys.other_tags, "addr:postcode"),
                          "x": polys.geometry.representative_point().x, "y": polys.geometry.representative_point().y}),
        ])
        coded = coded[coded.pin.fillna("").str.fullmatch(r"\d{6}")]
        for pin, g in coded.groupby("pin"):
            if len(g) >= min_postcode_hits:
                out.append({"name": pin, "kind": "pincode", "lat": round(float(g.y.median()), 6),
                            "lon": round(float(g.x.median()), 6), "hits": int(len(g))})

        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(out, f, ensure_ascii=False)
        return out

    @staticmethod
    def _snapshot_for(bbox: List[float]) -> Optional[gpd.GeoDataFrame]:
        for path in sorted(glob.glob(os.path.join(SNAPSHOT_DIR, "*.geojson"))):
            with open(path) as f:
                fc = json.load(f)
            b = fc.get("bbox")
            if b and b[0] <= bbox[0] and b[1] <= bbox[1] and b[2] >= bbox[2] and b[3] >= bbox[3]:
                return gpd.GeoDataFrame.from_features(fc["features"], crs="EPSG:4326")
        return None

    @classmethod
    def _overpass(cls, bbox: List[float], timeout_sec: int) -> Optional[gpd.GeoDataFrame]:
        """Live Overpass query; returns point features (way centres), or None when unreachable."""
        min_lon, min_lat, max_lon, max_lat = bbox
        q = f"""
        [out:json][timeout:{timeout_sec}];
        (
          nwr["amenity"~"^({AMENITY_RE})$"]({min_lat},{min_lon},{max_lat},{max_lon});
          way["waterway"~"^({WATERWAY_RE})$"]({min_lat},{min_lon},{max_lat},{max_lon});
          nwr["natural"~"^({WATER_NATURAL_RE})$"]({min_lat},{min_lon},{max_lat},{max_lon});
          way["natural"="coastline"]({min_lat},{min_lon},{max_lat},{max_lon});
        );
        out center;
        """
        try:
            resp = requests.post(cls.OVERPASS_URL, data={"data": q}, timeout=timeout_sec)
            resp.raise_for_status()
            rows = []
            for el in resp.json().get("elements", []):
                lat = el.get("lat") or el.get("center", {}).get("lat")
                lon = el.get("lon") or el.get("center", {}).get("lon")
                tags = el.get("tags", {})
                if lat is None or lon is None:
                    continue
                kind = "amenity" if "amenity" in tags else "water"
                wtype = tags.get("waterway") or tags.get("wetland") or tags.get("water") or tags.get("natural")
                cls_ = ("tidal" if tags.get("tidal") == "yes" or tags.get("wetland") in TIDAL_WETLAND_RE.split("|") or tags.get("natural") in ("bay", "coastline")
                        else "nala" if tags.get("waterway") or tags.get("water") in ("drain", "canal", "river", "stream")
                        else "wetland" if tags.get("natural") == "wetland" else "waterbody")
                rows.append({"kind": kind, "name": tags.get("name"), "type": tags.get("amenity") or wtype,
                             "cls": None if kind == "amenity" else cls_, "geometry": Point(lon, lat)})
            return gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326") if rows else \
                gpd.GeoDataFrame(columns=["kind", "name", "type", "geometry"], geometry="geometry", crs="EPSG:4326")
        except Exception:
            return None

    @classmethod
    def fetch_osm_features(cls, bbox: List[float], timeout_sec: int = 5) -> Optional[gpd.GeoDataFrame]:
        """OSM features (kind, name, type, geometry in EPSG:4326) for bbox, or None if unavailable."""
        snap = cls._snapshot_for(bbox)
        if snap is not None:
            return snap.clip(box(*bbox))
        return cls._overpass(bbox, timeout_sec)

    @classmethod
    def enrich_with_exposure(cls, gdf: gpd.GeoDataFrame, bbox: Optional[List[float]] = None,
                             georeferenced: bool = True, gsd_m: float = 10.0) -> gpd.GeoDataFrame:
        """Adds civic_exposure and encroachment_violation (screening notes), and re-scores severity for
        polygons near a hospital/school or flagged as possible encroachment. gsd_m is the pixel size:
        the DCPR nala setback is only assessed when the imagery can resolve it."""
        if gdf.empty:
            return gdf
        enriched = gdf.copy()
        if not georeferenced:
            enriched["encroachment_violation"] = enriched["civic_exposure"] = "Not assessed (tile not georeferenced)"
            return enriched

        utm = enriched.estimate_utm_crs()
        if bbox is None:
            # search beyond the detections themselves, or nearby assets just outside them are missed
            pad = gpd.GeoSeries([box(*enriched.to_crs(utm).total_bounds).buffer(EXPOSURE_RADIUS_M + 50)], crs=utm)
            bbox = [float(v) for v in pad.to_crs(4326).total_bounds]

        osm = cls.fetch_osm_features(bbox)
        if osm is None:
            enriched["encroachment_violation"] = enriched["civic_exposure"] = "Not assessed (OSM unavailable)"
            return enriched

        osm = osm.to_crs(utm)
        if "cls" not in osm.columns:
            osm["cls"] = None
        amen, protected = osm[osm.kind == "amenity"], osm[osm.kind == "protected"]
        water = {c: osm[(osm.kind == "water") & (osm.cls == c)] for c in ("tidal", "nala", "river", "wetland", "waterbody")}
        label = lambda r: r["name"] if isinstance(r["name"], str) and r["name"] else f"unnamed {str(r['type']).replace('_', ' ')}"

        def nearest(layer, geom):
            if not len(layer):
                return None, None
            d = layer.distance(geom)
            return float(d.min()), layer.loc[d.idxmin()]

        exposure, violation, flag = [], [], []
        for geom, ctype in zip(enriched.to_crs(utm).geometry, enriched["change_type"].astype(str)):
            d, a = nearest(amen, geom)
            exposure.append(f"High Exposure: {d:.0f} m from {label(a)} ({a['type'].replace('_', ' ')})"
                            if d is not None and d <= EXPOSURE_RADIUS_M else f"No hospital or school within {EXPOSURE_RADIUS_M:.0f} m")

            built = ctype in BUILT_TYPES
            dt, t = nearest(water["tidal"], geom)
            dn, n = nearest(pd.concat([water["nala"], water["river"]]), geom)
            dw, w = nearest(pd.concat([water["wetland"], water["waterbody"]]), geom)
            dp, pz = nearest(protected, geom)
            possible = False
            if dt is not None and dt <= CRZ_BUFFER_M:
                where = f"{dt:.0f} m from {label(t)} ({t['type']}), inside the CRZ {CRZ_BUFFER_M:.0f} m no-development zone"
                possible = built
                note = (f"Possible encroachment: new construction {where}. Verify against CRZ map" if built
                        else f"Within CRZ buffer: {where}")
            elif built and dp is not None and dp == 0:
                possible = True
                note = (f"Possible encroachment: new construction inside {label(pz)} ({pz['type']}). "
                        f"Verify against Development Plan")
            elif dn is not None and gsd_m <= NALA_SETBACK_M / 2 and dn <= NALA_SETBACK_M:
                where = f"{dn:.0f} m from {label(n)} ({n['type']}), inside the DCPR {NALA_SETBACK_M:.0f} m setback"
                possible = built
                note = (f"Possible encroachment: new construction {where}. Verify against Development Plan" if built
                        else f"Within nala setback: {where}")
            elif dn is not None and dn <= NEAR_WATER_REPORT_M:
                note = (f"Near nala: {dn:.0f} m from {label(n)} ({n['type']}), outside the DCPR {NALA_SETBACK_M:.0f} m setback"
                        if gsd_m <= NALA_SETBACK_M / 2 else
                        f"Near nala: {dn:.0f} m from {label(n)} ({n['type']}). The DCPR 3-6 m setback is below "
                        f"{gsd_m:.0f} m sensor precision; field check")
            elif dw is not None and dw <= NEAR_WATER_REPORT_M:
                note = (f"Near {w['type']}: {dw:.0f} m from {label(w)}. Wetland zone of influence is set per "
                        f"notification; not assessed")
            else:
                note = f"No tidal water, nala or wetland within {NEAR_WATER_REPORT_M:.0f} m"
            violation.append(note)
            flag.append(exposure[-1].startswith("High") or possible)

        enriched["civic_exposure"] = exposure
        enriched["encroachment_violation"] = violation
        for i in [i for i, f in zip(enriched.index, flag) if f]:
            r = enriched.loc[i]
            sev = SeverityScorer.compute_all_modes(r["area_sqm"], r["magnitude"], r["change_type"], near_critical_asset=True,
                                                   pixel_area_sqm=r.get("pixel_area_sqm", 100.0),
                                                   primary_mode=r.get("severity_mode", "encroachment"))
            for k, v in sev.items():
                if k in enriched.columns:
                    enriched.at[i, k] = v
        return enriched


if __name__ == "__main__":
    from shapely.geometry import LineString
    # synthetic scene in UTM 43N (Mumbai): mangrove edge at x=0, nala along y=1000, school at (2000, 0)
    utm = "EPSG:32643"
    o = (300000, 2110000)
    at = lambda x, y, r=5: Point(o[0] + x, o[1] + y).buffer(r)
    osm = gpd.GeoDataFrame({
        "kind": ["water", "water", "amenity", "protected"], "cls": ["tidal", "nala", None, None],
        "name": ["Test Creek", "Test Nala", "Test School", "Test Park"], "type": ["mangrove", "drain", "school", "park"],
        "geometry": [box(o[0] - 500, o[1] - 500, o[0], o[1] + 500), LineString([(o[0] + 900, o[1] + 1000), (o[0] + 1300, o[1] + 1000)]),
                     Point(o[0] + 2000, o[1]), box(o[0] + 4000, o[1], o[0] + 4400, o[1] + 400)]}, crs=utm).to_crs(4326)
    OSMExposureOverlay.fetch_osm_features = classmethod(lambda c, bbox, timeout_sec=5: osm)
    dets = gpd.GeoDataFrame({
        "change_type": ["New Built-up Surface", "Vegetation Loss / Clearing", "New Built-up Surface", "New Built-up Surface",
                        "New Built-up Surface"],
        "area_sqm": [3000.0] * 5, "magnitude": [0.6] * 5, "severity_tier": ["Medium"] * 5, "composite_score": [0.0] * 5,
        "geometry": [at(30, 0), at(30, 100), at(1100, 1020), at(1900, 0), at(4200, 200)]}, crs=utm).to_crs(4326)
    out = OSMExposureOverlay.enrich_with_exposure(dets)
    v, e = out.encroachment_violation.tolist(), out.civic_exposure.tolist()
    assert v[0].startswith("Possible encroachment") and "CRZ" in v[0], v[0]          # built, 25 m from mangrove
    assert v[1].startswith("Within CRZ buffer"), v[1]                                 # same place, not construction
    assert v[2].startswith("Near nala") and "sensor precision" in v[2], v[2]          # 15 m from nala at 10 m GSD
    assert "outside the DCPR" in OSMExposureOverlay.enrich_with_exposure(dets, gsd_m=0.5).encroachment_violation[2]  # 0.5 m GSD resolves it
    assert e[3].startswith("High Exposure") and out.composite_score[3] > 0, (e[3], out.composite_score[3])
    assert out.composite_score[0] > 0 and out.composite_score[1] == 0     # only flagged ones re-scored
    assert v[4].startswith("Possible encroachment") and "Test Park" in v[4], v[4]   # built inside a park
    assert e[2] == "No hospital or school within 500 m", e[2]                          # school ~1.4 km away
    print("osm overlay self-check ok")
