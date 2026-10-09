"""
severity.py - Multi-Factor Severity Scoring & Triage Tiering (Feature #8).

Combines:
1. Metric Footprint Area (m²)
2. Change Magnitude / Model Confidence
3. Semantic Change Type (e.g. Structural Encroachment vs Vegetation)
4. Critical Asset Proximity Multiplier (Exposure)
"""

from typing import Dict, Any


class SeverityScorer:
    """Calculates operational severity tiers for disaster & urban management."""

    # Tiers and styling tokens
    TIER_COLORS = {
        "Critical": "#EF4444",  # Red
        "High": "#F97316",      # Orange
        "Moderate": "#EAB308",  # Yellow
        "Minor": "#3B82F6",     # Blue
        "Filtered": "#9CA3AF"   # Gray
    }

    @classmethod
    def compute_severity(
        cls,
        area_sqm: float,
        magnitude: float,
        change_type: str,
        near_critical_asset: bool = False
    ) -> Dict[str, Any]:
        """
        Calculates severity tier and composite hazard score.

        Args:
            area_sqm: Geodesic metric area in square meters
            magnitude: Mean change confidence in [0.0, 1.0]
            change_type: Semantic classification label
            near_critical_asset: True if near hospital, school, nala, or dense slum

        Returns:
            dict containing tier, color, composite_score, action_priority
        """
        # Exposure multiplier
        exposure_mult = 1.35 if near_critical_asset else 1.0

        # Base composite score in [0.0, 100.0]
        area_factor = min(area_sqm / 1000.0, 1.0) * 50.0  # Up to 50 pts
        mag_factor = magnitude * 50.0                     # Up to 50 pts
        raw_score = (area_factor + mag_factor) * exposure_mult
        composite_score = round(min(raw_score, 100.0), 1)

        # Tier classification logic
        if (area_sqm >= 400.0 and magnitude >= 0.75) or (near_critical_asset and area_sqm >= 250.0 and magnitude >= 0.70):
            tier = "Critical"
            priority = "Priority 1 - Immediate Field Triage / Official Alert"
        elif (area_sqm >= 150.0 and magnitude >= 0.65) or (near_critical_asset and area_sqm >= 100.0):
            tier = "High"
            priority = "Priority 2 - Inspection Within 24 Hours"
        elif area_sqm >= 50.0 and magnitude >= 0.55:
            tier = "Moderate"
            priority = "Priority 3 - Scheduled Municipal / Survey Review"
        else:
            tier = "Minor"
            priority = "Priority 4 - Low Impact / Routine Audit"

        return {
            "severity_tier": tier,
            "color_hex": cls.TIER_COLORS[tier],
            "composite_score": composite_score,
            "action_priority": priority
        }
