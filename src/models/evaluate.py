"""
evaluate.py - Quantitative Evaluation & Benchmark Metrics Panel (Stretch Feature #14).

Computes IoU, Precision, Recall, F1-Score, and False Alarm Rate (FAR) across
the LEVIR-CD test split, comparing the ChangeIntel AI Engine vs Naive Baseline.
"""

import os
import sys
import json
import glob
from typing import Dict, Any, List

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import numpy as np
import rasterio
import torch

from src.models.infer import TiledInferenceEngine
from src.models.naive_baseline import NaiveBaselineComparator


def compute_metrics(pred_bin: np.ndarray, gt_bin: np.ndarray) -> Dict[str, float]:
    """Computes standard computer vision and change detection metrics."""
    tp = np.logical_and(pred_bin == 1, gt_bin == 1).sum()
    fp = np.logical_and(pred_bin == 1, gt_bin == 0).sum()
    fn = np.logical_and(pred_bin == 0, gt_bin == 1).sum()
    tn = np.logical_and(pred_bin == 0, gt_bin == 0).sum()

    precision = float(tp / (tp + fp)) if (tp + fp) > 0 else 0.0
    recall = float(tp / (tp + fn)) if (tp + fn) > 0 else 0.0
    f1 = float((2 * precision * recall) / (precision + recall)) if (precision + recall) > 0 else 0.0
    iou = float(tp / (tp + fp + fn)) if (tp + fp + fn) > 0 else 0.0
    far = float(fp / (fp + tn)) if (fp + tn) > 0 else 0.0  # False Alarm Rate

    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1_score": round(f1, 4),
        "iou": round(iou, 4),
        "false_alarm_rate": round(far, 4)
    }


def run_benchmark_evaluation(data_dir: str = "data/geotiff", output_path: str = "data/outputs/benchmark_metrics.json") -> Dict[str, Any]:
    """Runs comparative evaluation across all prepared LEVIR GeoTIFF test pairs."""
    t1_files = sorted(glob.glob(os.path.join(data_dir, "levir_*_t1_pre.tif")))
    
    if not t1_files:
        print("[Evaluate] No LEVIR GeoTIFF files found in data/geotiff/")
        return {}

    engine = TiledInferenceEngine()

    ai_metrics_list = []
    naive_metrics_list = []

    for t1_path in t1_files:
        base = t1_path.replace("_t1_pre.tif", "")
        t2_path = f"{base}_t2_post.tif"
        gt_path = f"{base}_ground_truth.tif"

        if not os.path.exists(t2_path) or not os.path.exists(gt_path):
            continue

        with rasterio.open(t1_path) as s1, rasterio.open(t2_path) as s2, rasterio.open(gt_path) as sg:
            t1 = s1.read()
            t2 = s2.read()
            gt = (sg.read(1) > 0).astype(np.uint8)

        # 1. AI Engine Prediction
        prob_ai = engine.run_inference(t1, t2, normalize_radiometry=True)
        pred_ai = (prob_ai > 0.5).astype(np.uint8)
        m_ai = compute_metrics(pred_ai, gt)
        ai_metrics_list.append(m_ai)

        # 2. Naive Baseline Prediction
        diff_naive, pred_naive = NaiveBaselineComparator.compute_naive_change(t1, t2, threshold=0.18)
        m_naive = compute_metrics(pred_naive, gt)
        naive_metrics_list.append(m_naive)

    # Average metrics
    def average_metrics(m_list: List[Dict[str, float]]) -> Dict[str, float]:
        if not m_list:
            return {}
        keys = m_list[0].keys()
        return {k: round(float(np.mean([m[k] for m in m_list])), 4) for k in keys}

    avg_ai = average_metrics(ai_metrics_list)
    avg_naive = average_metrics(naive_metrics_list)

    summary = {
        "evaluation_samples_count": len(ai_metrics_list),
        "changeintel_ai_engine": avg_ai,
        "naive_spectral_baseline": avg_naive,
        "false_alarm_reduction_percentage": round(
            max(0.0, (avg_naive.get("false_alarm_rate", 0) - avg_ai.get("false_alarm_rate", 0)) / (avg_naive.get("false_alarm_rate", 0.0001) + 1e-6) * 100.0), 1
        ),
        "f1_improvement_percentage": round(
            max(0.0, (avg_ai.get("f1_score", 0) - avg_naive.get("f1_score", 0)) / (avg_naive.get("f1_score", 0.0001) + 1e-6) * 100.0), 1
        )
    }

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(summary, f, indent=2)

    print("=" * 60)
    print("BENCHMARK EVALUATION RESULTS (LEVIR-CD TEST SPLIT):")
    print(f"  ChangeIntel AI -> F1: {avg_ai.get('f1_score')}, IoU: {avg_ai.get('iou')}, FAR: {avg_ai.get('false_alarm_rate')}")
    print(f"  Naive Baseline -> F1: {avg_naive.get('f1_score')}, IoU: {avg_naive.get('iou')}, FAR: {avg_naive.get('false_alarm_rate')}")
    print(f"  False Alarm Reduction: -{summary['false_alarm_reduction_percentage']}%")
    print(f"  F1-Score Gain: +{summary['f1_improvement_percentage']}%")
    print("=" * 60)

    return summary


if __name__ == "__main__":
    run_benchmark_evaluation()
