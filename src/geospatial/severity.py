"""
severity.py - Multi-Factor Severity Scoring & Triage Tiering (Feature #8, Ideation Baseline §5.3).

    score = norm_area × magnitude × type_weight[mode][change_type] × exposure_multiplier

- norm_area is resolution-aware: area is counted in pixels, so the same thresholds behave sensibly at
  0.5 m and 10 m (a 300 m² roof at 0.5 m is 1,200 px; a 12 ha patch at 10 m is 1,200 px).
- Two modes weight change types differently: "encroachment" (years ΔT, planning) and "disaster"
  (hours ΔT, response). Every polygon is scored in both; the console switches between them.
- Fixed score bands map to Critical / High / Medium / Low.
"""

from typing import Any, Dict

import numpy as np

MODES = ("encroachment", "disaster")
REF_PX = 20000            # area (in pixels) that counts as "full size": norm_area = 1
EXPOSURE_MULT = 1.35      # near a hospital / school, or a possible encroachment
TIER_BANDS = (("Critical", 0.60), ("High", 0.35), ("Medium", 0.15), ("Low", 0.0))
DEFAULT_WEIGHT = 0.5

# How much each change type matters per mode. ponytail: hand-set, shown in the console so the score is
# explainable; revisit with officer verdicts once the workflow has collected some.
TYPE_WEIGHTS = {
    "encroachment": {
        "Water-body Encroachment": 1.0, "Slow Built-up Creep": 0.9, "New Built-up Surface": 0.9,
        "New Building / Structure": 0.9, "Structural Change": 0.8,
        "Vegetation Cleared / Possible Construction": 0.7, "Precursor: Cleared Plot": 0.6, "Precursor: New Track": 0.6,
        "Ground Disturbance": 0.5, "Vegetation Loss / Clearing": 0.5, "Water / Flood Inundation": 0.4,
        "Burn Scar": 0.4, "Vegetation Regrowth": 0.2, "Seasonal Vegetation Change": 0.15,
    },
    "disaster": {
        "Water / Flood Inundation": 1.0, "Burn Scar": 0.9, "Structural Change": 0.9,
        "New Building / Structure": 0.8, "Ground Disturbance": 0.7, "Vegetation Loss / Clearing": 0.5,
        "Vegetation Cleared / Possible Construction": 0.5, "New Built-up Surface": 0.4, "Water-body Encroachment": 0.4,
        "Slow Built-up Creep": 0.3, "Precursor: Cleared Plot": 0.2, "Precursor: New Track": 0.2,
        "Seasonal Vegetation Change": 0.15, "Vegetation Regrowth": 0.1,
    },
}
PRIORITY = {
    "Critical": "Priority 1 - Immediate Field Triage / Official Alert",
    "High": "Priority 2 - Inspection Within 24 Hours",
    "Medium": "Priority 3 - Scheduled Municipal / Survey Review",
    "Low": "Priority 4 - Low Impact / Routine Audit",
}


class SeverityScorer:
    """Calculates operational severity tiers for disaster & urban management."""

    TIER_COLORS = {"Critical": "#EF4444", "High": "#F97316", "Medium": "#EAB308", "Low": "#3B82F6"}

    @staticmethod
    def norm_area(area_sqm: float, pixel_area_sqm: float) -> float:
        px = max(area_sqm, 0.0) / max(pixel_area_sqm, 1e-9)
        return float(min(1.0, np.log1p(px) / np.log1p(REF_PX)))

    @classmethod
    def compute_severity(
        cls,
        area_sqm: float,
        magnitude: float,
        change_type: str,
        near_critical_asset: bool = False,
        pixel_area_sqm: float = 100.0,
        mode: str = "encroachment",
    ) -> Dict[str, Any]:
        """Tier, score (0-1), composite_score (0-100, kept for exports) and action priority for one mode."""
        weight = TYPE_WEIGHTS[mode].get(change_type, DEFAULT_WEIGHT)
        score = cls.norm_area(area_sqm, pixel_area_sqm) * float(magnitude) * weight * (EXPOSURE_MULT if near_critical_asset else 1.0)
        score = min(score, 1.0)
        tier = next(t for t, lo in TIER_BANDS if score >= lo)
        return {
            "severity_tier": tier,
            "color_hex": cls.TIER_COLORS[tier],
            "composite_score": round(score * 100, 1),
            "action_priority": PRIORITY[tier],
        }

    @classmethod
    def compute_all_modes(cls, area_sqm, magnitude, change_type, near_critical_asset=False,
                          pixel_area_sqm=100.0, primary_mode="encroachment") -> Dict[str, Any]:
        """Primary-mode columns (severity_tier, composite_score, ...) plus tier_<mode> / score_<mode> for every mode."""
        out = {}
        for m in MODES:
            s = cls.compute_severity(area_sqm, magnitude, change_type, near_critical_asset, pixel_area_sqm, m)
            out[f"tier_{m}"], out[f"score_{m}"] = s["severity_tier"], s["composite_score"]
            if m == primary_mode:
                out.update(s)
        out["exposure_mult"] = EXPOSURE_MULT if near_critical_asset else 1.0
        out["norm_area"] = round(cls.norm_area(area_sqm, pixel_area_sqm), 3)
        return out


if __name__ == "__main__":
    S = SeverityScorer.compute_severity
    # resolution-aware: the same pixel count scores the same at 0.5 m and 10 m
    assert S(300, 0.9, "New Built-up Surface", pixel_area_sqm=0.25) == S(120000, 0.9, "New Built-up Surface", pixel_area_sqm=100)
    # mode changes the ranking: a flood outranks new construction in disaster mode, and vice versa
    flood = lambda m: S(50000, 0.9, "Water / Flood Inundation", mode=m)["composite_score"]
    built = lambda m: S(50000, 0.9, "New Built-up Surface", mode=m)["composite_score"]
    assert flood("disaster") > built("disaster") and built("encroachment") > flood("encroachment")
    # phenology: seasonal change stays Low unless huge and exposed
    assert S(500000, 0.9, "Seasonal Vegetation Change")["severity_tier"] == "Low"
    # exposure multiplier raises the score
    assert S(5000, 0.8, "New Built-up Surface", near_critical_asset=True)["composite_score"] > S(5000, 0.8, "New Built-up Surface")["composite_score"]
    # bands are monotone and cover every score
    tiers = [S(a, 0.95, "Water-body Encroachment")["severity_tier"] for a in (100, 2000, 30000, 2e6)]
    assert tiers == sorted(tiers, key=["Low", "Medium", "High", "Critical"].index), tiers
    both = SeverityScorer.compute_all_modes(30000, 0.8, "Burn Scar", primary_mode="disaster")
    assert both["severity_tier"] == both["tier_disaster"] and "tier_encroachment" in both
    print("severity self-check ok", tiers)
