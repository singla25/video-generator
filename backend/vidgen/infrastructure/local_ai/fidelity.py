"""How much a lip-synced frame still looks like the original, outside the mouth (L8 measure).

Region: the lower half of the face box (cheeks, jaw, beard) minus the mouth box. Numbers: SSIM,
mean absolute pixel difference, and texture retention (Laplacian variance, result / original;
target >= 0.85, so a smoothed beard shows up as a low value). Pure numpy/cv2, no extra packages.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from vidgen.infrastructure.local_ai.compositing import (
    MOUTH_CENTER_X,
    MOUTH_CENTER_Y,
    MOUTH_RADIUS_X,
    MOUTH_RADIUS_Y,
    Box,
)

LOWER_FACE_START = 0.5  # the region starts at this fraction of the box height
SSIM_SIGMA = 1.5
SSIM_C1 = (0.01 * 255) ** 2
SSIM_C2 = (0.03 * 255) ** 2
TEXTURE_TARGET = 0.85


@dataclass(frozen=True)
class Fidelity:
    """Metrics for one frame, or the mean over several."""

    ssim: float
    mean_abs_diff: float
    texture_ratio: float


def lower_face_mask(shape: tuple[int, int], box: Box) -> Any:
    """Boolean ``shape`` (h, w) mask: lower half of ``box`` without the mouth rectangle."""
    import numpy as np  # type: ignore[import-not-found,unused-ignore]

    x1, y1, x2, y2 = box
    width, height = x2 - x1, y2 - y1
    mask = np.zeros(shape, dtype=bool)
    mask[y1 + round(height * LOWER_FACE_START) : y2, x1:x2] = True
    cx, cy = x1 + width * MOUTH_CENTER_X, y1 + height * MOUTH_CENTER_Y
    rx, ry = width * MOUTH_RADIUS_X, height * MOUTH_RADIUS_Y
    mask[round(cy - ry) : round(cy + ry) + 1, round(cx - rx) : round(cx + rx) + 1] = False
    return mask


def _gray(image: Any) -> Any:
    import cv2  # type: ignore[import-not-found,unused-ignore]
    import numpy as np  # type: ignore[import-not-found,unused-ignore]

    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float64)


def _ssim_map(a: Any, b: Any) -> Any:
    """Gaussian-window SSIM per pixel (grayscale float arrays)."""
    import cv2  # type: ignore[import-not-found,unused-ignore]

    def blur(x: Any) -> Any:
        return cv2.GaussianBlur(x, (0, 0), SSIM_SIGMA)

    mu_a, mu_b = blur(a), blur(b)
    var_a, var_b = blur(a * a) - mu_a**2, blur(b * b) - mu_b**2
    cov = blur(a * b) - mu_a * mu_b
    numerator = (2 * mu_a * mu_b + SSIM_C1) * (2 * cov + SSIM_C2)
    return numerator / ((mu_a**2 + mu_b**2 + SSIM_C1) * (var_a + var_b + SSIM_C2))


def _laplacian_variance(gray: Any, mask: Any) -> float:
    import cv2  # type: ignore[import-not-found,unused-ignore]

    return float(cv2.Laplacian(gray, cv2.CV_64F)[mask].var())


def frame_fidelity(original: Any, result: Any, box: Box) -> Fidelity:
    """Metrics of ``result`` against ``original`` (BGR uint8 arrays) in the lower-face region."""
    import numpy as np  # type: ignore[import-not-found,unused-ignore]

    mask = lower_face_mask(original.shape[:2], box)
    gray_o, gray_r = _gray(original), _gray(result)
    ssim = float(_ssim_map(gray_o, gray_r)[mask].mean())
    diff = float(np.abs(original.astype(np.float64) - result.astype(np.float64))[mask].mean())
    base = _laplacian_variance(gray_o, mask)
    return Fidelity(ssim, diff, _laplacian_variance(gray_r, mask) / base if base else 1.0)


def mean_fidelity(items: list[Fidelity]) -> Fidelity:
    """Average of per-frame metrics; no frames gives the neutral result (identical, no change)."""
    count = len(items)
    if count == 0:
        return Fidelity(ssim=1.0, mean_abs_diff=0.0, texture_ratio=1.0)
    return Fidelity(
        sum(i.ssim for i in items) / count,
        sum(i.mean_abs_diff for i in items) / count,
        sum(i.texture_ratio for i in items) / count,
    )
