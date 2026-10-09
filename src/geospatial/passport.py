"""
passport.py - Scene Passport & Comparability Score (Ideation #18).

A context record for an image pair: identity (sensor, resolution, scene ids, processing level, source,
licence, checksums), conditions (sun angles, unobservable share, measured misregistration) and season
(IMD season and crop-calendar stage in India, meteorological season elsewhere), plus a 0-100
Comparability Score: how far a before/after difference can be trusted to be real change rather than
season, illumination, cloud, misregistration or a sensor mismatch.

A low score warns the analyst and tightens the detection threshold (tightened_threshold).

Sun angles come from the STAC item when the scene was fetched from Earth Search; otherwise (OSCD tiles
carry dates only) they are computed for the Sentinel-2 mean overpass, 10:30 local mean solar time.
"""

import hashlib
import math
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional

S2_LOCAL_OVERPASS_H = 10.5     # Sentinel-2 descending node: 10:30 local mean solar time
LOW, FAIR = 60, 80             # score bands: < 60 low, 60-79 fair, >= 80 good
MAX_TIGHTEN = 0.25             # a score of 0 raises the threshold by at most 25 %

# weights of the six comparability factors (sum 100)
WEIGHTS = {"season": 30, "sun": 20, "cloud": 15, "registration": 15, "sensor": 10, "gap": 10}


def sun_position(when: datetime, lat: float, lon: float):
    """(elevation, azimuth) in degrees, NOAA solar position equations (no refraction). when is UTC."""
    rad, deg = math.radians, math.degrees
    jd = when.timestamp() / 86400 + 2440587.5
    t = (jd - 2451545) / 36525
    l0 = (280.46646 + t * (36000.76983 + t * 0.0003032)) % 360
    m = 357.52911 + t * (35999.05029 - 0.0001537 * t)
    ecc = 0.016708634 - t * (0.000042037 + 0.0000001267 * t)
    c = (math.sin(rad(m)) * (1.914602 - t * (0.004817 + 0.000014 * t)) + math.sin(rad(2 * m)) * (0.019993 - 0.000101 * t)
         + math.sin(rad(3 * m)) * 0.000289)
    app = l0 + c - 0.00569 - 0.00478 * math.sin(rad(125.04 - 1934.136 * t))
    obl = 23 + (26 + (21.448 - t * (46.815 + t * (0.00059 - t * 0.001813))) / 60) / 60 + 0.00256 * math.cos(rad(125.04 - 1934.136 * t))
    decl = math.asin(math.sin(rad(obl)) * math.sin(rad(app)))
    y = math.tan(rad(obl / 2)) ** 2
    eqt = 4 * deg(y * math.sin(2 * rad(l0)) - 2 * ecc * math.sin(rad(m)) + 4 * ecc * y * math.sin(rad(m)) * math.cos(2 * rad(l0))
                  - 0.5 * y * y * math.sin(4 * rad(l0)) - 1.25 * ecc * ecc * math.sin(2 * rad(m)))
    tst = (when.hour * 60 + when.minute + when.second / 60 + eqt + 4 * lon) % 1440
    ha = rad(tst / 4 - 180)
    la = rad(lat)
    cz = max(-1.0, min(1.0, math.sin(la) * math.sin(decl) + math.cos(la) * math.cos(decl) * math.cos(ha)))
    zen = math.acos(cz)
    ca = (math.sin(la) * cz - math.sin(decl)) / max(math.cos(la) * math.sin(zen), 1e-9)
    a = deg(math.acos(max(-1.0, min(1.0, ca))))
    az = (a + 180) % 360 if ha > 0 else (540 - a) % 360
    return 90 - deg(zen), az


def s2_overpass(d: date, lon: float) -> datetime:
    """UTC time of the Sentinel-2 mean overpass (10:30 local mean solar time) on day d."""
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc) + timedelta(hours=S2_LOCAL_OVERPASS_H - lon / 15)


def in_india(lat: float, lon: float) -> bool:
    return 6 <= lat <= 37.5 and 68 <= lon <= 97.5


def season(d: date, lat: float, lon: float) -> Dict[str, Optional[str]]:
    """IMD season + crop-calendar stage in India; meteorological season (by hemisphere) elsewhere."""
    mo = d.month
    if in_india(lat, lon):
        name = ("Winter" if mo in (1, 2) else "Pre-monsoon" if mo in (3, 4, 5)
                else "Southwest monsoon" if mo in (6, 7, 8, 9) else "Post-monsoon")
        crop = ("Kharif growing" if mo in (6, 7, 8, 9) else "Kharif harvest" if mo == 10
                else "Rabi growing" if mo in (11, 12, 1, 2) else "Rabi harvest" if mo in (3, 4) else "Zaid / fallow")
        return {"season": name, "crop_stage": crop, "scheme": "IMD"}
    north = ["Winter", "Winter", "Spring", "Spring", "Spring", "Summer", "Summer", "Summer", "Autumn", "Autumn", "Autumn", "Winter"]
    flip = {"Winter": "Summer", "Summer": "Winter", "Spring": "Autumn", "Autumn": "Spring"}
    name = north[mo - 1] if lat >= 0 else flip[north[mo - 1]]
    return {"season": name, "crop_stage": None, "scheme": "meteorological"}


def _clip(v: float) -> float:
    return max(0.0, min(1.0, v))


def comparability(d1: date, d2: date, sun1: float, sun2: float, unobservable_pct: float, shift_px: float,
                  same_sensor: bool = True, same_level: bool = True, mode: str = "encroachment") -> Dict:
    """0-100 score from six factors, each a 0-1 quality, plus the factors ranked by how much they cost."""
    doy = abs(d2.timetuple().tm_yday - d1.timetuple().tm_yday)
    days = abs((d2 - d1).days)
    q = {
        # 0 days apart in the year = 1, six months apart (opposite season) = 0
        "season": 0.5 * (1 + math.cos(2 * math.pi * min(doy, 365 - doy) / 365.25)),
        # 30 deg of sun elevation difference changes shadow length enough to read as change
        "sun": _clip(1 - abs(sun1 - sun2) / 30),
        "cloud": _clip(1 - unobservable_pct / 30),
        "registration": _clip(1 - shift_px / 3),
        "sensor": 1.0 if same_sensor and same_level else 0.7 if same_sensor else 0.4,
        # disaster pairs should bracket the event closely; planning pairs span years by design
        "gap": _clip(1 - max(0, days - 30) / 335) if mode == "disaster" else _clip(1 - days / 365.25 / 20),
    }
    score = round(sum(WEIGHTS[k] * q[k] for k in WEIGHTS))
    why = {
        "season": f"{min(doy, 365 - doy)} days apart in the seasonal cycle",
        "sun": f"sun elevation {sun1:.0f}° vs {sun2:.0f}°",
        "cloud": f"{unobservable_pct:.1f}% of the tile unobservable",
        "registration": f"{shift_px:.1f} px misregistration measured",
        "sensor": "same sensor and processing level" if q["sensor"] == 1 else "different processing level" if same_sensor else "different sensors",
        "gap": f"{days} days between images",
    }
    factors = sorted(({"factor": k, "quality": round(q[k], 2), "cost": round(WEIGHTS[k] * (1 - q[k]), 1), "detail": why[k]}
                      for k in WEIGHTS), key=lambda f: -f["cost"])
    band = "Good" if score >= FAIR else "Fair" if score >= LOW else "Low"
    return {"score": score, "band": band, "factors": factors}


def tightened_threshold(thr: float, score: Optional[int]) -> float:
    """Raises a probability threshold for low-comparability pairs: unchanged at >= LOW, +MAX_TIGHTEN at 0."""
    if score is None or score >= LOW:
        return thr
    return round(min(0.95, thr * (1 + MAX_TIGHTEN * (LOW - score) / LOW)), 4)


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build(dates: List[date], lat: float, lon: float, sensor: str, level: str, gsd_m: float,
          unobservable_pct: float, shift_px: List[float], mode: str, scenes: Optional[List[Dict]] = None,
          source: str = "", licence: str = "", checksums: Optional[Dict[str, str]] = None) -> Dict:
    """Scene Passport for one pair. scenes: STAC metadata per date (id, datetime, sun angles) when known."""
    scenes = scenes or [{}, {}]
    images = []
    for d, sc in zip(dates, scenes):
        if sc.get("sun_elevation") is not None:
            elev, az, how = sc["sun_elevation"], sc["sun_azimuth"], "STAC item"
        else:
            elev, az = sun_position(s2_overpass(d, lon), lat, lon)
            how = "computed for the 10:30 local solar time overpass"
        images.append({"date": d.isoformat(), "scene_id": sc.get("id"), "acquired": sc.get("datetime"),
                       "sun_elevation": round(elev, 1), "sun_azimuth": round(az, 1), "sun_source": how,
                       "scene_cloud_pct": sc.get("cloud"), "processing_baseline": sc.get("processing_baseline"),
                       **season(d, lat, lon)})
    shift = math.hypot(*shift_px)
    # Sentinel-2 processing baseline 04.00 (Jan 2022) changed the L2A radiometry (a +1000 DN offset):
    # a pair straddling it is the same sensor at a different processing level
    pb = [sc.get("processing_baseline") for sc in scenes]
    same_level = not all(pb) or (float(pb[0]) >= 4) == (float(pb[1]) >= 4)
    comp = comparability(dates[0], dates[1], images[0]["sun_elevation"], images[1]["sun_elevation"],
                         unobservable_pct, shift, same_level=same_level, mode=mode)
    if not same_level:
        next(f for f in comp["factors"] if f["factor"] == "sensor")["detail"] = f"processing baselines {pb[0]} vs {pb[1]}"
    return {"sensor": sensor, "processing_level": level, "resolution_m": round(gsd_m, 2), "source": source,
            "licence": licence, "images": images, "unobservable_pct": unobservable_pct,
            "misregistration_px": round(shift, 2), "gap_days": abs((dates[1] - dates[0]).days),
            "same_season": images[0]["season"] == images[1]["season"], "comparability": comp,
            "checksums": checksums or {}}


if __name__ == "__main__":
    # NOAA equations vs the sun angles Earth Search publishes for S2B_43QBB_20260322_0_L2A
    # (acquired 2026-03-22T05:53:37Z; 62.42 deg elevation, 130.38 deg azimuth at the scene centre)
    e, a = sun_position(datetime(2026, 3, 22, 5, 53, 37, tzinfo=timezone.utc), 19.5, 72.5)
    assert abs(e - 62.42) < 1.5 and abs(a - 130.38) < 2.5, (e, a)
    # the 10:30 local-time estimate lands within a few degrees of the real overpass on the same day
    e2, _ = sun_position(s2_overpass(date(2026, 3, 22), 72.5), 19.5, 72.5)
    assert abs(e2 - 62.42) < 4, e2
    assert season(date(2025, 7, 1), 19.1, 72.9)["season"] == "Southwest monsoon"
    assert season(date(2025, 7, 1), -15.8, -47.9)["season"] == "Winter"          # Brasilia, southern hemisphere
    good = comparability(date(2019, 3, 29), date(2025, 3, 20), 62, 63, 0.0, 0.0)
    bad = comparability(date(2015, 7, 4), date(2018, 2, 11), 68, 33, 12.0, 2.0)  # opposite season, low winter sun
    assert good["score"] >= FAIR and bad["score"] < LOW, (good["score"], bad["score"])
    assert bad["factors"][0]["factor"] in ("season", "sun")
    assert tightened_threshold(0.5, 90) == 0.5 and 0.5 < tightened_threshold(0.5, 30) <= 0.5 * (1 + MAX_TIGHTEN)
    # disaster pairs: a two-month gap costs more than in planning mode
    assert comparability(date(2023, 7, 29), date(2023, 9, 30), 60, 50, 0, 0, mode="disaster")["score"] < \
        comparability(date(2023, 7, 29), date(2023, 9, 30), 60, 50, 0, 0)["score"]
    print("passport self-check ok", good["score"], bad["score"], f"sun {e:.2f}/{a:.2f}")
