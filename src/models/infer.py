"""
infer.py - Tiled Sliding-Window Inference Engine with Overlap & Hann Blending (Feature #3).
Allows processing arbitrarily large GeoTIFF scenes without edge seam artifacts.
"""

from typing import Optional, Tuple
import numpy as np
import torch
from scipy.signal.windows import hann

from src.data.geotiff_processor import GeoTIFFProcessor
from src.models.bit_model import load_bit_model, BitemporalTransformer


class TiledInferenceEngine:
    """
    Runs sliding-window inference on large GeoTIFF pairs with:
    1. Radiometric histogram matching (T2 -> T1).
    2. Overlapping patch sliding (e.g. 256x256 window with 64px overlap).
    3. 2D Hann window blending to eliminate boundary seam artifacts.
    """

    def __init__(
        self,
        model: Optional[torch.nn.Module] = None,
        patch_size: int = 256,
        stride: int = 192,
        device: Optional[str] = None
    ):
        if device is None:
            self.device = "mps" if torch.backends.mps.is_available() else "cpu"
        else:
            self.device = device

        if model is None:
            self.model = load_bit_model(device=self.device)
        else:
            self.model = model.to(self.device)
            self.model.eval()

        self.patch_size = patch_size
        self.stride = stride

        # Create 2D Hann blending window
        h1d = hann(patch_size, sym=True)
        self.window_2d = np.outer(h1d, h1d).astype(np.float32)
        # Avoid zero division at extreme edges
        self.window_2d = np.clip(self.window_2d, 1e-4, 1.0)

    def run_inference(
        self,
        img_t1: np.ndarray,
        img_t2: np.ndarray,
        normalize_radiometry: bool = True
    ) -> np.ndarray:
        """
        Runs tiled inference on a pair of (C, H, W) images.

        Args:
            img_t1: (C, H, W) numpy array [0, 255] or [0, 1] for T1
            img_t2: (C, H, W) numpy array [0, 255] or [0, 1] for T2
            normalize_radiometry: If True, matches histogram of T2 to T1

        Returns:
            prob_map: (H, W) float32 array in [0.0, 1.0] representing change probability
        """
        # Ensure 3-channel RGB for BIT model
        c, h, w = img_t1.shape
        t1_rgb = img_t1[:3].copy()
        t2_rgb = img_t2[:3].copy()

        # Scale to [0, 1] float
        if t1_rgb.max() > 1.0:
            t1_rgb = t1_rgb.astype(np.float32) / 255.0
        if t2_rgb.max() > 1.0:
            t2_rgb = t2_rgb.astype(np.float32) / 255.0

        # Feature #4: Radiometric Normalization
        if normalize_radiometry:
            t2_rgb = GeoTIFFProcessor.match_radiometry(t2_rgb, t1_rgb)

        # Pad image so it divides cleanly by patch_size if needed
        pad_h = (self.patch_size - (h % self.patch_size)) % self.patch_size
        pad_w = (self.patch_size - (w % self.patch_size)) % self.patch_size
        
        # Ensure minimum size of at least patch_size
        if h < self.patch_size:
            pad_h = self.patch_size - h
        if w < self.patch_size:
            pad_w = self.patch_size - w

        t1_padded = np.pad(t1_rgb, ((0, 0), (0, pad_h), (0, pad_w)), mode="reflect")
        t2_padded = np.pad(t2_rgb, ((0, 0), (0, pad_h), (0, pad_w)), mode="reflect")

        _, ph, pw = t1_padded.shape

        prob_accum = np.zeros((ph, pw), dtype=np.float32)
        weight_accum = np.zeros((ph, pw), dtype=np.float32)

        # Slide across rows and columns
        y_steps = list(range(0, ph - self.patch_size + 1, self.stride))
        if y_steps[-1] != ph - self.patch_size:
            y_steps.append(ph - self.patch_size)

        x_steps = list(range(0, pw - self.patch_size + 1, self.stride))
        if x_steps[-1] != pw - self.patch_size:
            x_steps.append(pw - self.patch_size)

        with torch.no_grad():
            for y in y_steps:
                for x in x_steps:
                    p1 = t1_padded[:, y:y+self.patch_size, x:x+self.patch_size]
                    p2 = t2_padded[:, y:y+self.patch_size, x:x+self.patch_size]

                    # Scale to [-1, 1] for BIT architecture
                    t_x1 = torch.tensor((p1 - 0.5) / 0.5, dtype=torch.float32).unsqueeze(0).to(self.device)
                    t_x2 = torch.tensor((p2 - 0.5) / 0.5, dtype=torch.float32).unsqueeze(0).to(self.device)

                    logits = self.model(t_x1, t_x2)
                    patch_prob = torch.softmax(logits, dim=1)[0, 1].cpu().numpy()

                    # Accumulate weighted by 2D Hann window
                    prob_accum[y:y+self.patch_size, x:x+self.patch_size] += patch_prob * self.window_2d
                    weight_accum[y:y+self.patch_size, x:x+self.patch_size] += self.window_2d

        # Normalize by accumulated weights
        weight_accum[weight_accum == 0] = 1.0
        full_prob = prob_accum / weight_accum

        # Unpad to original shape (H, W)
        final_prob = full_prob[:h, :w]
        return np.clip(final_prob, 0.0, 1.0)
