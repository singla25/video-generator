"""Paste only the generated mouth back into a frame; keep every other pixel of the original.

MuseTalk generates the whole lower face (cheeks, jaw, beard) at 256 px, which comes out smooth
and slightly lighter than the real face. This module keeps the generated pixels only inside a
mouth ellipse, feathers its edge, restores the original's fine texture (beard) around the lips and
matches the generated colours to the original. Pure numpy/cv2; the model code decides when to call.
"""

from __future__ import annotations

from typing import Any

Box = tuple[int, int, int, int]

# Mouth ellipse as fractions of the face box (x1, y1, x2, y2 plus the model's bottom margin).
MOUTH_CENTER_X = 0.50
MOUTH_CENTER_Y = 0.72
MOUTH_RADIUS_X = 0.30  # half width: lips plus the corners when the mouth opens wide
MOUTH_RADIUS_Y = 0.15
CORE_SHRINK = 0.60  # the inner ellipse (lips and teeth) keeps the generated texture entirely
FEATHER_FRACTION = 0.10  # Gaussian sigma of the mask edge, as a share of the box width
DETAIL_SIGMA_FRACTION = 0.015  # low-pass sigma for the texture split, share of the box width
MIN_SIGMA = 1.0
MAX_COLOR_SHIFT = 40.0  # never shift colours by more than this per channel (guards bad frames)


def mouth_masks(width: int, height: int) -> tuple[Any, Any]:
    """Return ``(outer, core)`` float masks in 0..1 for a face box of ``width`` x ``height``."""
    import cv2  # type: ignore[import-not-found,unused-ignore]
    import numpy as np  # type: ignore[import-not-found,unused-ignore]

    centre = (round(width * MOUTH_CENTER_X), round(height * MOUTH_CENTER_Y))
    axes = (round(width * MOUTH_RADIUS_X), round(height * MOUTH_RADIUS_Y))
    sigma = max(MIN_SIGMA, width * FEATHER_FRACTION)
    masks = []
    for scale in (1.0, CORE_SHRINK):
        mask = np.zeros((height, width), dtype=np.float32)
        scaled = (max(1, round(axes[0] * scale)), max(1, round(axes[1] * scale)))
        cv2.ellipse(mask, centre, scaled, 0, 0, 360, 1.0, -1)
        masks.append(cv2.GaussianBlur(mask, (0, 0), sigma * scale))
    return masks[0], masks[1]


def _low_pass(image: Any, sigma: float) -> Any:
    import cv2  # type: ignore[import-not-found,unused-ignore]

    return cv2.GaussianBlur(image, (0, 0), sigma)


def _color_shift(original: Any, generated: Any, ring: Any) -> Any:
    """Per-channel mean offset original - generated, measured on the ring around the mouth."""
    import numpy as np  # type: ignore[import-not-found,unused-ignore]

    weights = ring[..., None]
    total = max(float(weights.sum()), 1e-6)
    shift = ((original - generated) * weights).sum(axis=(0, 1)) / total
    return np.clip(shift, -MAX_COLOR_SHIFT, MAX_COLOR_SHIFT)


def composite_mouth(original: Any, face: Any, box: Box) -> Any:
    """Return ``original`` with the generated ``face`` blended in around the mouth only.

    ``face`` has the size of ``box`` (the crop MuseTalk generated). Outside the outer mouth
    ellipse the result equals ``original`` exactly. Inside it, the low frequencies come from the
    colour-matched generated face and the high frequencies (beard texture) from the original,
    except in the core where the generated lips and teeth are kept as they are.
    """
    import numpy as np  # type: ignore[import-not-found,unused-ignore]

    x1, y1, x2, y2 = box
    height, width = y2 - y1, x2 - x1
    base = original[y1:y2, x1:x2].astype(np.float32)
    generated = face.astype(np.float32)
    outer, core = mouth_masks(width, height)
    sigma = max(MIN_SIGMA, width * DETAIL_SIGMA_FRACTION)
    ring = np.clip(outer - core, 0.0, 1.0)
    generated = generated + _color_shift(base, generated, ring)
    core3, outer3 = core[..., None], outer[..., None]
    detail = base - _low_pass(base, sigma)
    synthetic = (generated - _low_pass(generated, sigma)) * core3
    patch = _low_pass(generated, sigma) + detail * (1.0 - core3) + synthetic
    blended = base * (1.0 - outer3) + patch * outer3
    result = original.copy()
    result[y1:y2, x1:x2] = np.clip(blended, 0, 255).astype(np.uint8)
    return result
