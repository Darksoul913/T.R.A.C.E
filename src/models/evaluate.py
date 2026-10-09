"""
evaluate.py - Quantitative Evaluation & Benchmark Metrics Panel (Stretch Feature #14).

Computes IoU, Precision, Recall, F1-Score, and False Alarm Rate (FAR) across
the LEVIR-CD test split, comparing the T.R.A.C.E. AI Engine vs Naive Baseline.
"""

import os
import sys
import json
import glob
import time
from typing import Any, Dict, Iterator, List, Optional, Tuple

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import numpy as np
import rasterio
import torch
from PIL import Image

from src.data.geotiff_processor import GeoTIFFProcessor
from src.models.infer import TiledInferenceEngine
from src.models.naive_baseline import NaiveBaselineComparator


def confusion(pred_bin: np.ndarray, gt_bin: np.ndarray) -> np.ndarray:
    """[tp, fp, fn, tn] pixel counts."""
    p, g = pred_bin.astype(bool), gt_bin.astype(bool)
    return np.array([(p & g).sum(), (p & ~g).sum(), (~p & g).sum(), (~p & ~g).sum()], dtype=np.int64)


def metrics_from(cm: np.ndarray) -> Dict[str, float]:
    """Precision, recall, F1, IoU and false alarm rate (FP / all no-change pixels)."""
    tp, fp, fn, tn = (int(x) for x in cm)
    div = lambda a, b: a / b if b else 0.0
    precision, recall = div(tp, tp + fp), div(tp, tp + fn)
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1_score": round(div(2 * precision * recall, precision + recall), 4),
        "iou": round(div(tp, tp + fp + fn), 4),
        "false_alarm_rate": round(div(fp, fp + tn), 4),
    }


def compute_metrics(pred_bin: np.ndarray, gt_bin: np.ndarray) -> Dict[str, float]:
    return metrics_from(confusion(pred_bin, gt_bin))


def geotiff_samples(data_dir: str, pattern: str) -> Iterator[Tuple[str, np.ndarray, np.ndarray, np.ndarray]]:
    for p in sorted(glob.glob(os.path.join(data_dir, pattern))):
        base = p[:-len("_t1_pre.tif")]
        if not os.path.exists(f"{base}_ground_truth.tif"):
            continue
        with rasterio.open(p) as s1, rasterio.open(f"{base}_t2_post.tif") as s2, rasterio.open(f"{base}_ground_truth.tif") as sg:
            refl = GeoTIFFProcessor.load_reflectance(base)
            yield os.path.basename(base), s1.read(), s2.read(), sg.read(1) > 0, refl


def levir_png_samples(root: str) -> Iterator[Tuple[str, np.ndarray, np.ndarray, np.ndarray]]:
    """Official LEVIR-CD layout: A/, B/, label/ with matching PNG names."""
    rgb = lambda f: np.asarray(Image.open(f).convert("RGB")).transpose(2, 0, 1)
    for f in sorted(os.listdir(os.path.join(root, "label"))):
        yield (os.path.splitext(f)[0], rgb(os.path.join(root, "A", f)), rgb(os.path.join(root, "B", f)),
               np.asarray(Image.open(os.path.join(root, "label", f)).convert("L")) > 127, None)


SIZE_BINS = ((0, 400, "< 400 m²"), (400, 2500, "400–2,500 m²"), (2500, float("inf"), "> 2,500 m²"))


def spectral_rule_change(refl1: np.ndarray, refl2: np.ndarray) -> np.ndarray:
    """Training-free Sentinel-2 detector built from the same indices as the change-type rules:
    |ΔNDBI| + |ΔMNDWI| + |ΔNDVI| per pixel, thresholded with Otsu."""
    from skimage.filters import threshold_otsu
    nd = lambda a, b: (a - b) / np.maximum(a + b, 1e-6)
    f1, f2 = refl1.astype(np.float32), refl2.astype(np.float32)
    score = sum(np.abs(nd(f2[i], f2[j]) - nd(f1[i], f1[j])) for i, j in ((4, 3), (1, 4), (3, 0)))
    return score > threshold_otsu(score)


def object_matches(pred: np.ndarray, gt: np.ndarray, pixel_area: float) -> Dict[str, Any]:
    """Object-level matching on 8-connected components. A ground-truth object is 'hit' when predictions
    cover >= 50% of it and 'matched' when IoU (against all overlapping predictions) > 0.5; a predicted object
    is a true positive when its IoU against overlapping ground truth is > 0.5."""
    from scipy.ndimage import label
    eight = np.ones((3, 3), int)
    lg, ng = label(gt, eight)
    lp, npred = label(pred, eight)
    inter = np.bincount((lg * (npred + 1) + lp).ravel(), minlength=(ng + 1) * (npred + 1)).reshape(ng + 1, npred + 1)
    ag, ap = inter.sum(axis=1), inter.sum(axis=0)
    gt_objs = []
    for g in range(1, ng + 1):
        ov = inter[g, 1:]
        union = ag[g] + ap[1:][ov > 0].sum() - ov.sum()
        gt_objs.append((ag[g] * pixel_area, ov.sum() / union, ov.sum() / ag[g]))
    pred_tp = 0
    for q in range(1, npred + 1):
        ov = inter[1:, q]
        union = ap[q] + ag[1:][ov > 0].sum() - ov.sum()
        pred_tp += ov.sum() / union > 0.5
    return {"gt": gt_objs, "pred_n": int(npred), "pred_tp": int(pred_tp)}


def summarise_objects(matches: List[Dict[str, Any]]) -> Dict[str, Any]:
    gts = [o for m in matches for o in m["gt"]]
    pn, tp = sum(m["pred_n"] for m in matches), sum(m["pred_tp"] for m in matches)
    rate = lambda xs, cond: round(sum(cond(x) for x in xs) / len(xs), 4) if xs else None
    return {
        "gt_objects": len(gts),
        "recall_iou50": rate(gts, lambda o: o[1] > 0.5),
        "recall_hit50": rate(gts, lambda o: o[2] >= 0.5),
        "precision_iou50": round(tp / pn, 4) if pn else None,
        "recall_by_size": [{"bin": name, "objects": len(b := [o for o in gts if lo <= o[0] < hi]),
                            "recall_hit50": rate(b, lambda o: o[2] >= 0.5), "recall_iou50": rate(b, lambda o: o[1] > 0.5)}
                           for lo, hi, name in SIZE_BINS],
    }


def _evaluate(samples, engine: TiledInferenceEngine, normalize=None, pixel_area: float = 0.25,
              spectral: bool = False) -> Dict[str, Any]:
    """Pools pixel counts over all samples (micro-average), so small or empty tiles can't skew the score.
    Also collects object-level matches, BIT inference time, and (spectral=True) the training-free index rules."""
    total = {k: np.zeros(4, np.int64) for k in ("ai", "naive", "spectral")}
    objs = {k: [] for k in total}
    per_sample, infer_s, pixels = [], 0.0, 0
    for name, t1, t2, gt, refl in samples:
        gt = gt.astype(bool)
        t0 = time.perf_counter()
        pred = {"ai": engine.run_inference(t1, t2, normalize_radiometry=normalize) > 0.5}
        infer_s += time.perf_counter() - t0
        pixels += gt.size
        pred["naive"] = NaiveBaselineComparator.compute_naive_change(*(refl or (t1, t2)), threshold=0.18)[1].astype(bool)
        if spectral and refl is not None:
            pred["spectral"] = spectral_rule_change(*refl)
        cms = {}
        for k, p in pred.items():
            cms[k] = confusion(p, gt)
            total[k] += cms[k]
            objs[k].append(object_matches(p, gt, pixel_area))
        per_sample.append({"sample": name, "pixels": int(gt.size), "ai": metrics_from(cms["ai"]), "naive": metrics_from(cms["naive"])})
    ai, nv = metrics_from(total["ai"]), metrics_from(total["naive"])
    pct_change = lambda old, new: round((new - old) / old * 100.0, 1) if old else 0.0
    km2 = pixels * pixel_area / 1e6
    out = {
        "evaluation_samples_count": len(per_sample),
        "evaluated_pixels": int(total["ai"].sum()),
        "area_km2": round(km2, 2),
        "changeintel_ai_engine": ai,
        "naive_spectral_baseline": nv,
        "false_alarm_reduction_percentage": -pct_change(nv["false_alarm_rate"], ai["false_alarm_rate"]),
        "f1_improvement_percentage": pct_change(nv["f1_score"], ai["f1_score"]),
        # FAR is a fraction of no-change ground; x100 = km² falsely flagged per 100 km² of unchanged land
        "false_alarm_km2_per_100km2": {k: round(metrics_from(total[k])["false_alarm_rate"] * 100, 2)
                                       for k in total if objs[k]},
        "objects": {k: summarise_objects(objs[k]) for k in total if objs[k]},
        "runtime": {"bit_inference_s": round(infer_s, 1), "s_per_km2": round(infer_s / km2, 3) if km2 else None,
                    "megapixels_per_s": round(pixels / 1e6 / infer_s, 2) if infer_s else None},
        "per_sample": per_sample,
    }
    if objs["spectral"]:
        out["spectral_index_rules"] = metrics_from(total["spectral"])
    return out


def oscd_samples(cities, base_dir="."):
    """Labelled OSCD cities as (name, display t1, display t2, gt, (refl1, refl2))."""
    from src.data.dataset_builder import DatasetBuilder
    for city in cities:
        d = DatasetBuilder.load_oscd_city(city, base_dir)
        if d["gt"] is not None and d["gt"].any():
            yield city, d["disp1"], d["disp2"], d["gt"], (d["refl1"], d["refl2"])


def oscd_labelled_cities(root="Onera Satellite Change Detection"):
    lab = os.path.join(root, "train_labels", "Onera Satellite Change Detection dataset - Train Labels")
    return sorted(c for c in os.listdir(lab) if os.path.isdir(os.path.join(lab, c))) if os.path.isdir(lab) else []


def creep_vs_sudden(engine: TiledInferenceEngine, samples, steps: int = 4) -> Dict[str, Any]:
    """Miss benchmark for slow change (#16). Each LEVIR test pair becomes a synthetic sequence: the background
    stays T1 while every ground-truth object fades from its T1 to its T2 appearance in `steps` equal steps.
    Compares a pairwise system that only compares consecutive images (each step shows 1/steps of the change)
    with one anchored to the first image. ponytail: linear blending is a stand-in for real staged construction."""
    consec, anchored, per_step = [], [], {"consecutive": [[] for _ in range(steps)], "anchored": [[] for _ in range(steps)]}
    for _, t1, t2, gt, _ in samples:
        gt = gt.astype(bool)
        if not gt.any():
            continue
        a, b = t1.astype(np.float32), t2.astype(np.float32)
        frames = [np.where(gt, a + (b - a) * k / steps, a).astype(np.uint8) for k in range(steps + 1)]
        union = np.zeros_like(gt)
        for k in range(1, steps + 1):
            c = engine.run_inference(frames[k - 1], frames[k]) > 0.5
            union |= c
            per_step["consecutive"][k - 1].append(object_matches(c, gt, 0.25))
            per_step["anchored"][k - 1].append(object_matches(engine.run_inference(frames[0], frames[k]) > 0.5, gt, 0.25))
        consec.append(object_matches(union, gt, 0.25))
    hit = lambda ms: summarise_objects(ms)["recall_hit50"]
    return {
        "steps": steps,
        "pairs": len(consec),
        "consecutive_any_step_recall_hit50": hit(consec),
        "anchored_final_recall_hit50": hit(per_step["anchored"][-1]),
        "per_step": [{"step": k + 1, "change_shown": f"{(k + 1) * 100 // steps}% (anchored) vs {100 // steps}% (consecutive)",
                      "consecutive_recall_hit50": hit(per_step["consecutive"][k]),
                      "anchored_recall_hit50": hit(per_step["anchored"][k])} for k in range(steps)],
    }


def seasonal_no_change(engine: TiledInferenceEngine, prefix: str = "data/raw/s2/mumbai_s2_seasonal",
                       meta_path: str = "data/geotiff/mumbai_s2_meta.json") -> Optional[Dict[str, Any]]:
    """Area flagged on a post-monsoon vs dry-season pair of the same place a few months apart (scripts/fetch_s2.py).
    Little real change happens in that window, so flagged area is an upper bound on seasonal false alarms."""
    if not os.path.exists(f"{prefix}_t1_pre.tif"):
        return None
    with rasterio.open(f"{prefix}_t1_pre.tif") as s1, rasterio.open(f"{prefix}_t2_post.tif") as s2:
        t1, t2, px = s1.read(), s2.read(), abs(s1.transform.a * s1.transform.e)
    refl = GeoTIFFProcessor.load_reflectance(prefix)
    dates = None
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            dates = [m["date"] for m in json.load(f).get("seasonal_pair", [])]
    flagged = {"ai": engine.run_inference(t1, t2) > 0.5,
               "naive": NaiveBaselineComparator.compute_naive_change(*refl, threshold=0.18)[1].astype(bool),
               "spectral": spectral_rule_change(*refl)}
    from src.models import track_b
    tb = track_b.change_probability(*refl)
    if tb is not None:
        flagged["track_b"] = track_b.cleaned(tb[0] >= tb[1])
    area_km2 = t1.shape[1] * t1.shape[2] * px / 1e6
    return {"dates": dates, "area_km2": round(area_km2, 1),
            "flagged_km2_per_100km2": {k: round(v.sum() * px / 1e6 / area_km2 * 100, 2) for k, v in flagged.items()}}


def run_benchmark_evaluation(data_dir: str = "data/geotiff", output_path: str = "data/outputs/benchmark_metrics.json",
                             levir_root: str = "data/raw/levir_cd_test") -> Dict[str, Any]:
    """Headline: the full official LEVIR-CD test split when downloaded, else the local LEVIR GeoTIFF tiles.
    OSCD (14 labelled Sentinel-2 cities, incl. Mumbai) is reported separately: out of domain for BIT
    (10 m multispectral vs 0.5 m aerial training data)."""
    if os.path.isdir(os.path.join(levir_root, "label")):
        levir, dataset = lambda: levir_png_samples(levir_root), "LEVIR-CD official test split"
    elif glob.glob(os.path.join(data_dir, "levir_*_t1_pre.tif")):
        levir, dataset = lambda: geotiff_samples(data_dir, "levir_*_t1_pre.tif"), "LEVIR-CD test tiles (local subset)"
    else:
        print("[Evaluate] No LEVIR test data found")
        return {}

    engine = TiledInferenceEngine()
    summary = {"dataset": dataset, **_evaluate(levir(), engine)}
    # Ablation: same model with histogram matching (T2 -> T1), which the pipeline leaves off
    summary["with_histogram_matching"] = _evaluate(levir(), engine, normalize="global")["changeintel_ai_engine"]
    summary["creep_vs_sudden"] = creep_vs_sudden(engine, levir())
    cities = oscd_labelled_cities()
    if cities:
        o = _evaluate(oscd_samples(cities), engine, pixel_area=100.0, spectral=True)
        summary["oscd"] = {"cities": [s["sample"] for s in o["per_sample"]], **{k: v for k, v in o.items() if k != "per_sample"}}
        if os.path.exists("data/outputs/track_b_metrics.json"):
            with open("data/outputs/track_b_metrics.json") as f:
                tb_met = json.load(f)
            summary["track_b_loco"] = tb_met
            summary["oscd"]["track_b"] = tb_met.get("pooled")
            if "false_alarm_km2_per_100km2" in summary["oscd"]:
                summary["oscd"]["false_alarm_km2_per_100km2"]["track_b"] = tb_met.get("false_alarm_km2_per_100km2")
    oscd = list(geotiff_samples(data_dir, "mumbai_t1_pre.tif"))
    if oscd:
        summary["oscd_mumbai"] = {k: v for k, v in _evaluate(oscd, engine, pixel_area=100.0).items() if k != "per_sample"}
    summary["seasonal_no_change"] = seasonal_no_change(engine)

    # Event validation against Copernicus EMS (Evros wildfire & Trimmu flood)
    from src.geospatial import events
    from src.models import track_b
    event_val = {}
    for area, ref_info in [
        ("evros_fire", {"event": "Evros wildfire (EMSR686)", "src": "data/geotiff/evros_fire"}),
        ("trimmu_flood", {"event": "Trimmu flood AOI05 (EMSR838)", "src": "data/geotiff/trimmu_flood"}),
    ]:
        prefix = ref_info["src"]
        if os.path.exists(f"{prefix}_ground_truth.tif") and os.path.exists(f"{prefix}_reference_aoi.tif"):
            refl = GeoTIFFProcessor.load_reflectance(prefix)
            if refl:
                r1, r2 = refl
                with rasterio.open(f"{prefix}_ground_truth.tif") as sg, rasterio.open(f"{prefix}_reference_aoi.tif") as sa:
                    gt = sg.read(1) > 0
                    scope = sa.read(1) > 0
                cloud = GeoTIFFProcessor.load_cloud_mask(prefix)
                unobs = (r1 == 0).all(axis=0) | (r2 == 0).all(axis=0)
                if cloud is not None:
                    unobs |= cloud
                scope_obs = scope & ~unobs
                ev_type = "wildfire" if "fire" in area else "flood"
                pred_ev = (events.SCORERS[ev_type](r1, r2) >= 0.5) & ~unobs
                _, naive_mask = NaiveBaselineComparator.compute_naive_change(*refl, threshold=0.18)
                tbp = track_b.change_probability(r1, r2)
                event_val[area] = {
                    "event": ref_info["event"],
                    "scope_km2": round(float(scope_obs.sum()) * 100.0 / 1e6, 1),
                    "changeintel": events.validate(pred_ev, gt, scope_obs),
                    "naive_ndvi": events.validate(naive_mask.astype(bool), gt, scope_obs),
                    "track_b_urban": events.validate(track_b.cleaned(tbp[0] >= tbp[1]), gt, scope_obs) if tbp else None
                }
    if event_val:
        summary["event_validation"] = event_val

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(summary, f, indent=2, default=float)

    ai, nv, raw = summary["changeintel_ai_engine"], summary["naive_spectral_baseline"], summary["with_histogram_matching"]
    ob, rt, cs = summary["objects"]["ai"], summary["runtime"], summary["creep_vs_sudden"]
    print("=" * 72)
    print(f"{dataset}: {summary['evaluation_samples_count']} pairs, {summary['area_km2']} km² (pooled)")
    print(f"  T.R.A.C.E. AI       -> F1 {ai['f1_score']}, IoU {ai['iou']}, FAR {ai['false_alarm_rate']}")
    print(f"  ...+ hist matching  -> F1 {raw['f1_score']}, IoU {raw['iou']}, FAR {raw['false_alarm_rate']}")
    print(f"  Naive Baseline      -> F1 {nv['f1_score']}, IoU {nv['iou']}, FAR {nv['false_alarm_rate']}")
    print(f"  Objects: {ob['gt_objects']} | recall@IoU.5 {ob['recall_iou50']} | hit {ob['recall_hit50']} | precision {ob['precision_iou50']}")
    print("    by size: " + ", ".join(f"{b['bin']} {b['recall_hit50']} (n={b['objects']})" for b in ob["recall_by_size"]))
    print(f"  Runtime: {rt['s_per_km2']} s/km² at 0.5 m, {rt['megapixels_per_s']} Mpx/s")
    print(f"  Creep ({cs['steps']} steps): consecutive-pair recall {cs['consecutive_any_step_recall_hit50']} vs anchored {cs['anchored_final_recall_hit50']}")
    if "oscd" in summary:
        o = summary["oscd"]
        tb_f1 = summary.get("track_b_loco", {}).get("pooled", {}).get("f1_score", "N/A")
        print(f"OSCD {len(o['cities'])} cities: Track B LOCO F1 {tb_f1} | BIT (out of domain) F1 {o['changeintel_ai_engine']['f1_score']} | "
              f"naive F1 {o['naive_spectral_baseline']['f1_score']} | spectral rules F1 {o['spectral_index_rules']['f1_score']}")
        print(f"  false alarms km²/100km²: {o['false_alarm_km2_per_100km2']}")
    if "event_validation" in summary:
        print("Copernicus EMS Event Validation:")
        for ev_k, ev_v in summary["event_validation"].items():
            print(f"  {ev_v['event']}: T.R.A.C.E. F1 {ev_v['changeintel']['f1_score']} ")
                  f"(P {ev_v['changeintel']['precision']}, R {ev_v['changeintel']['recall']}) | "
                  f"Naive NDVI F1 {ev_v['naive_ndvi']['f1_score']} | "
                  f"Track B F1 {ev_v['track_b_urban']['f1_score'] if ev_v['track_b_urban'] else 'N/A'}")
    if summary["seasonal_no_change"]:
        print(f"Seasonal no-change pair, flagged km²/100km²: {summary['seasonal_no_change']['flagged_km2_per_100km2']}")
    print("=" * 72)
    return summary


if __name__ == "__main__":
    # object matching self-check: one 10x10 object hit by an 8x10 prediction, one missed, one false object
    g = np.zeros((40, 40), bool); g[2:12, 2:12] = True; g[20:24, 20:24] = True
    p = np.zeros_like(g); p[2:10, 2:12] = True; p[30:35, 30:35] = True
    m = summarise_objects([object_matches(p, g, 1.0)])
    assert m["gt_objects"] == 2 and m["recall_hit50"] == 0.5 and m["recall_iou50"] == 0.5 and m["precision_iou50"] == 0.5, m
    run_benchmark_evaluation()
