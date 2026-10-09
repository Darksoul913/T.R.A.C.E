"""
spectral_indices.py - Spectral Index Computations & Semantic Change Labelling (Feature #5 & #6).

Computes:
1. NDVI (Normalized Difference Vegetation Index)
2. NDBI (Normalized Difference Built-up Index)
3. NDWI (Normalized Difference Water Index)
4. Semantic change-type classification (Built-up, Vegetation Loss, Flood/Water, Disturbance).
"""

from typing import Tuple, Dict, Any
import numpy as np

NDBI_RISE = 0.10   # minimum ΔNDBI to call a change built-up


class SpectralClassifier:
    """Computes remote sensing spectral indices and classifies polygon change semantics."""

    @staticmethod
    def calc_ndvi(red: np.ndarray, nir: np.ndarray) -> np.ndarray:
        """NDVI = (NIR - Red) / (NIR + Red)"""
        red = red.astype(np.float32)
        nir = nir.astype(np.float32)
        denom = nir + red
        denom[denom == 0] = 1e-6
        return np.clip((nir - red) / denom, -1.0, 1.0)

    @staticmethod
    def calc_ndwi(green: np.ndarray, nir: np.ndarray) -> np.ndarray:
        """NDWI (McFeeters) = (Green - NIR) / (Green + NIR)"""
        green = green.astype(np.float32)
        nir = nir.astype(np.float32)
        denom = green + nir
        denom[denom == 0] = 1e-6
        return np.clip((green - nir) / denom, -1.0, 1.0)

    @staticmethod
    def calc_ndbi(swir: np.ndarray, nir: np.ndarray) -> np.ndarray:
        """NDBI = (SWIR - NIR) / (SWIR + NIR)"""
        swir = swir.astype(np.float32)
        nir = nir.astype(np.float32)
        denom = swir + nir
        denom[denom == 0] = 1e-6
        return np.clip((swir - nir) / denom, -1.0, 1.0)

    @classmethod
    def classify_polygon_change(
        cls,
        t1_bands: np.ndarray,
        t2_bands: np.ndarray,
        mask: np.ndarray
    ) -> Dict[str, Any]:
        """
        Calculates internal spectral shifts inside a polygon mask and labels the change type.

        Args:
            t1_bands: (C, H, W) array for T1 (e.g. B04 Red, B03 Green, B02 Blue, B08 NIR)
            t2_bands: (C, H, W) array for T2
            mask: (H, W) boolean mask for the polygon

        Returns:
            dict containing change_type, d_ndvi, d_ndwi, d_ndbi (None without SWIR), and explanation
        """
        if not np.any(mask):
            return {
                "change_type": "Unknown",
                "d_ndvi": 0.0,
                "d_ndwi": 0.0,
                "summary": "Empty mask"
            }

        # Cast before any arithmetic: uint8 band sums overflow (e.g. NIR + Red > 255 wraps)
        t1_bands = t1_bands.astype(np.float32)
        t2_bands = t2_bands.astype(np.float32)
        c = t1_bands.shape[0]

        d_ndbi = d_nbr = None
        # Case 1: Multispectral (reflectance; see GeoTIFFProcessor.load_reflectance).
        # Band order: Red=0, Green=1, Blue=2, NIR=3, optional SWIR16 (B11)=4, SWIR22 (B12)=5.
        if c >= 4:
            band = lambda t, i: t[i][mask]
            nd = lambda a, b: float(np.mean((a - b) / (a + b + 1e-6)))
            idx = lambda t, i, j: nd(band(t, i), band(t, j))
            d_ndvi = idx(t2_bands, 3, 0) - idx(t1_bands, 3, 0)
            # water: MNDWI (green vs SWIR) when SWIR exists, McFeeters NDWI (green vs NIR) otherwise
            wi_b = 4 if c >= 5 else 3
            wi1, wi2 = idx(t1_bands, 1, wi_b), idx(t2_bands, 1, wi_b)
            d_ndwi = wi2 - wi1
            wi_name = "MNDWI" if c >= 5 else "NDWI"
            if c >= 5:
                d_ndbi = idx(t2_bands, 4, 3) - idx(t1_bands, 4, 3)
            if c >= 6:
                d_nbr = idx(t2_bands, 3, 5) - idx(t1_bands, 3, 5)
            vis = lambda t: float(np.mean([band(t, i).mean() for i in range(3)]))
            built_up = d_ndbi is not None and d_ndbi > NDBI_RISE

            # Rule table, Ideation Baseline §5.2. NDBI alone confuses built-up with bare soil, and dry-season
            # browning lowers NDVI / raises NDBI like construction on green land, so the labels say what the
            # evidence supports. ponytail: fixed thresholds; calibrate against labelled change per region.
            if d_ndwi > 0.20 and wi2 > 0.0:       # the water index also rises when vegetation becomes concrete,
                change_type = "Water / Flood Inundation"   # so it must actually be water at T2
                summary = f"Surface water appeared ({wi_name}: {wi1:+.2f} → {wi2:+.2f})."
            elif wi1 > 0.0 and d_ndwi < -0.20 and built_up:
                change_type = "Water-body Encroachment"
                summary = f"Water at T1 replaced by built-up surface (Δ{wi_name} = {d_ndwi:+.2f}, ΔNDBI = {d_ndbi:+.2f})."
            elif d_nbr is not None and d_nbr < -0.25 and vis(t2_bands) <= vis(t1_bands):
                change_type = "Burn Scar"           # burnt ground darkens; clearing / construction brightens
                summary = f"Burn ratio dropped and the surface darkened (ΔNBR = {d_nbr:+.2f})."
            elif built_up and abs(d_ndvi) <= 0.15:
                change_type = "New Built-up Surface"
                summary = f"Built-up index rose with little vegetation change (ΔNDBI = {d_ndbi:+.2f}, ΔNDVI = {d_ndvi:+.2f})."
            elif built_up and d_ndvi < -0.15:
                change_type = "Vegetation Cleared / Possible Construction"
                summary = (f"Vegetation lost and built-up index rose (ΔNDVI = {d_ndvi:+.2f}, ΔNDBI = {d_ndbi:+.2f}): "
                           "new construction or bare / dried ground. Verify on site.")
            elif d_ndvi < -0.15 and d_ndbi is not None:
                change_type = "Seasonal Vegetation Change"   # phenology rule: NDVI-only change, no built-up signal
                summary = f"Vegetation dropped with no built-up signal, likely seasonal (ΔNDVI = {d_ndvi:+.2f}, ΔNDBI = {d_ndbi:+.2f})."
            elif d_ndvi < -0.15:
                change_type = "Vegetation Loss / Clearing"   # no SWIR: cannot tell seasonal from clearing
                summary = f"Vegetation canopy removal or loss detected (ΔNDVI = {d_ndvi:+.2f}; no SWIR band to rule out construction)."
            elif d_ndvi > 0.20:
                change_type = "Vegetation Regrowth"
                summary = f"Vegetation greening (ΔNDVI = {d_ndvi:+.2f})."
            else:
                change_type = "Ground Disturbance"
                summary = (f"Change with no dominant index (ΔNDVI = {d_ndvi:+.2f}, Δ{wi_name} = {d_ndwi:+.2f}"
                           + (f", ΔNDBI = {d_ndbi:+.2f})." if d_ndbi is not None else "; no SWIR band for NDBI)."))

        # Case 2: RGB Only (e.g. LEVIR-CD high-res)
        else:
            r1, g1, b1 = t1_bands[0][mask], t1_bands[1][mask], t1_bands[2][mask]
            r2, g2, b2 = t2_bands[0][mask], t2_bands[1][mask], t2_bands[2][mask]

            brightness1 = np.mean(0.299 * r1 + 0.587 * g1 + 0.114 * b1)
            brightness2 = np.mean(0.299 * r2 + 0.587 * g2 + 0.114 * b2)
            d_bright = float(brightness2 - brightness1)

            d_ndvi = 0.0
            d_ndwi = 0.0

            if abs(d_bright) > 20:
                change_type = "New Building / Structure"
                summary = f"High-contrast physical building modification (Brightness drift = {d_bright:+.1f})."
            else:
                change_type = "Ground Disturbance"
                summary = f"Textural ground surface disturbance (Brightness drift = {d_bright:+.1f})."

        return {
            "change_type": change_type,
            "d_ndvi": round(d_ndvi, 3),
            "d_ndwi": round(d_ndwi, 3),
            "d_ndbi": round(d_ndbi, 3) if d_ndbi is not None else None,
            "d_nbr": round(d_nbr, 3) if d_nbr is not None else None,
            "summary": summary
        }


if __name__ == "__main__":
    m = np.ones((4, 4), bool)
    # reflectance x10000: Red, Green, Blue, NIR, SWIR16, SWIR22
    t = lambda *v: np.stack([np.full((4, 4), x, np.float32) for x in v])
    veg = t(500, 700, 400, 3500, 1800, 900)
    built = t(1600, 1500, 1400, 2000, 2600, 2300)
    bare = t(1800, 1500, 1200, 2600, 2400, 2200)
    dry = t(800, 850, 550, 2700, 1400, 700)         # leaf senescence: NDVI down, NDBI flat. (Browning that also
                                                    # raises NDBI lands in "Cleared / Possible Construction".)
    water = t(300, 600, 500, 250, 100, 60)
    burnt = t(400, 380, 300, 900, 1600, 1500)       # dark, NIR collapsed, SWIR22 up
    cls = lambda a, b: SpectralClassifier.classify_polygon_change(a, b, m)["change_type"]
    cases = [
        (bare, built, "New Built-up Surface"),
        (veg, built, "Vegetation Cleared / Possible Construction"),
        (veg, dry, "Seasonal Vegetation Change"),
        (veg, water, "Water / Flood Inundation"),
        (water, built, "Water-body Encroachment"),
        (veg, burnt, "Burn Scar"),
        (built, veg, "Vegetation Regrowth"),
        (veg, veg * 1.01, "Ground Disturbance"),
        (veg[:4], built[:4], "Vegetation Loss / Clearing"),       # no SWIR: no built-up / seasonal claim
    ]
    for a, b, want in cases:
        assert cls(a, b) == want, (want, cls(a, b), SpectralClassifier.classify_polygon_change(a, b, m))
    print(f"spectral self-check ok ({len(cases)} rules)")
