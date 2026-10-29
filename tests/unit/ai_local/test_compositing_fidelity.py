"""Mouth-only compositing and the fidelity measure (L8). Needs numpy and cv2 (the local-ai extra).

Skipped when those are not installed, so the base install and CI stay green.
"""

from __future__ import annotations

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("cv2")

from vidgen.infrastructure.local_ai.compositing import (  # noqa: E402
    composite_mouth,
    mouth_masks,
)
from vidgen.infrastructure.local_ai.fidelity import (  # noqa: E402
    Fidelity,
    frame_fidelity,
    lower_face_mask,
    mean_fidelity,
)

BOX = (40, 30, 168, 190)  # 128 x 160 face box inside a 240 x 200 frame


def textured_frame(seed: int = 1, shape: tuple[int, int] = (200, 240)) -> np.ndarray:
    """A reproducible noisy BGR frame (noise stands in for beard texture)."""
    rng = np.random.default_rng(seed)
    return rng.integers(60, 200, size=(*shape, 3), dtype=np.uint8)


def face_crop(frame: np.ndarray, box: tuple[int, int, int, int] = BOX) -> np.ndarray:
    """The generated face: here the box content itself."""
    x1, y1, x2, y2 = box
    return frame[y1:y2, x1:x2].copy()


# ---- mouth_masks ------------------------------------------------------------------------


@pytest.mark.parametrize("size", [(128, 160), (64, 64), (301, 97), (10, 10), (3, 5)])
def test_masks_have_the_box_shape_and_stay_between_zero_and_one(size: tuple[int, int]) -> None:
    width, height = size
    outer, core = mouth_masks(width, height)
    for mask in (outer, core):
        assert mask.shape == (height, width)
        assert float(mask.min()) >= 0.0
        assert float(mask.max()) <= 1.0 + 1e-6


@pytest.mark.parametrize("size", [(128, 160), (64, 64), (301, 97)])
def test_core_lies_inside_the_outer_mask(size: tuple[int, int]) -> None:
    outer, core = mouth_masks(*size)
    assert float(core.sum()) < float(outer.sum())
    # Feathering differs per mask, so compare the solid parts: where core is solid, outer is too.
    assert bool((outer[core > 0.5] > 0.5).all())


def test_outer_mask_is_centred_on_the_mouth_and_empty_at_the_top() -> None:
    outer, _ = mouth_masks(128, 160)
    assert outer[round(160 * 0.72), 64] > 0.5
    assert float(outer[:10].max()) < 1e-3


# ---- composite_mouth --------------------------------------------------------------------


def test_identical_face_gives_an_identical_frame() -> None:
    frame = textured_frame()
    result = composite_mouth(frame, face_crop(frame), BOX)
    assert int(np.abs(result.astype(int) - frame.astype(int)).max()) <= 1


def test_pixels_outside_the_box_are_unchanged() -> None:
    frame = textured_frame()
    result = composite_mouth(frame, np.full((160, 128, 3), 250, np.uint8), BOX)
    x1, y1, x2, y2 = BOX
    keep = np.ones(frame.shape[:2], bool)
    keep[y1:y2, x1:x2] = False
    assert np.array_equal(result[keep], frame[keep])


def test_the_original_frame_object_is_not_modified() -> None:
    frame = textured_frame()
    before = frame.copy()
    composite_mouth(frame, np.full((160, 128, 3), 250, np.uint8), BOX)
    assert np.array_equal(frame, before)


def test_pixels_far_from_the_mouth_ellipse_are_unchanged() -> None:
    frame = textured_frame()
    result = composite_mouth(frame, np.full((160, 128, 3), 255, np.uint8), BOX)
    x1, y1, x2, _y2 = BOX
    top = (slice(y1, y1 + 40), slice(x1, x2))  # forehead area, far above the mouth
    assert np.array_equal(result[top], frame[top])


def test_a_different_generated_mouth_changes_pixels_inside_the_ellipse() -> None:
    frame = textured_frame()
    face = np.full((160, 128, 3), 255, np.uint8)
    result = composite_mouth(frame, face, BOX)
    x1, y1, _, _ = BOX
    cy, cx = y1 + round(160 * 0.72), x1 + 64
    assert not np.array_equal(
        result[cy - 3 : cy + 3, cx - 3 : cx + 3], frame[cy - 3 : cy + 3, cx - 3 : cx + 3]
    )


def test_colour_shift_is_clamped() -> None:
    frame = np.full((200, 240, 3), 100, np.uint8)
    face = np.full((160, 128, 3), 250, np.uint8)  # 150 brighter than the original
    result = composite_mouth(frame, face, BOX)
    x1, y1, _, _ = BOX
    cy, cx = y1 + round(160 * 0.72), x1 + 64
    centre = int(result[cy, cx, 0])
    # Unclamped, the shift would pull the centre down to about 100; the cap keeps it far above.
    assert 150 < centre < 250


def test_colour_is_matched_when_the_difference_is_small() -> None:
    frame = np.full((200, 240, 3), 100, np.uint8)
    face = np.full((160, 128, 3), 120, np.uint8)
    result = composite_mouth(frame, face, BOX)
    x1, y1, _, _ = BOX
    cy, cx = y1 + round(160 * 0.72), x1 + 64
    assert abs(int(result[cy, cx, 0]) - 100) <= 3  # the 20-level offset is removed


@pytest.mark.parametrize("box", [(5, 5, 9, 9), (0, 0, 7, 11), (10, 10, 11, 11), (20, 20, 53, 77)])
def test_tiny_and_odd_sized_boxes_do_not_crash(box: tuple[int, int, int, int]) -> None:
    frame = textured_frame()
    x1, y1, x2, y2 = box
    result = composite_mouth(frame, np.full((y2 - y1, x2 - x1, 3), 200, np.uint8), box)
    assert result.shape == frame.shape
    assert result.dtype == np.uint8


def test_box_at_the_frame_edge_is_handled() -> None:
    frame = textured_frame()
    box = (112, 40, 240, 200)
    result = composite_mouth(frame, face_crop(frame, box), box)
    assert result.shape == frame.shape


# ---- fidelity ---------------------------------------------------------------------------


def test_lower_face_mask_excludes_the_mouth_rectangle_and_the_upper_half() -> None:
    mask = lower_face_mask((200, 240), BOX)
    x1, y1, _x2, y2 = BOX
    cy, cx = y1 + round(160 * 0.72), x1 + 64
    assert not mask[cy, cx]
    assert not mask[y1 + 10, cx]  # upper half
    assert not mask[y1 + 100, x1 - 5]  # outside the box
    assert mask[y2 - 2, x1 + 3]  # chin corner counts
    assert mask.dtype == bool


def test_lower_face_mask_is_not_empty() -> None:
    assert int(lower_face_mask((200, 240), BOX).sum()) > 0


def test_identical_frames_have_ssim_one_and_texture_ratio_one() -> None:
    frame = textured_frame()
    fid = frame_fidelity(frame, frame.copy(), BOX)
    assert fid.ssim == pytest.approx(1.0, abs=1e-6)
    assert fid.texture_ratio == pytest.approx(1.0)
    assert fid.mean_abs_diff == pytest.approx(0.0)


def test_a_blurred_lower_face_loses_texture_and_ssim() -> None:
    import cv2

    frame = textured_frame()
    blurred = cv2.GaussianBlur(frame, (0, 0), 3)
    fid = frame_fidelity(frame, blurred, BOX)
    assert fid.texture_ratio < 1.0
    assert fid.texture_ratio < 0.85  # the target the measure is built to catch
    assert fid.ssim < 1.0
    assert fid.mean_abs_diff > 0


def test_a_flat_original_does_not_divide_by_zero() -> None:
    flat = np.full((200, 240, 3), 90, np.uint8)
    fid = frame_fidelity(flat, flat.copy(), BOX)
    assert fid.texture_ratio == 1.0


def test_mouth_only_compositing_keeps_more_texture_than_a_full_face_paste() -> None:
    import cv2

    frame = textured_frame()
    smooth = cv2.GaussianBlur(face_crop(frame), (0, 0), 3)
    x1, y1, x2, y2 = BOX
    pasted = frame.copy()
    pasted[y1:y2, x1:x2] = smooth
    mouth_only = composite_mouth(frame, smooth, BOX)
    assert (
        frame_fidelity(frame, mouth_only, BOX).texture_ratio
        > frame_fidelity(frame, pasted, BOX).texture_ratio
    )


def test_mean_fidelity_averages_each_metric() -> None:
    mean = mean_fidelity([Fidelity(1.0, 0.0, 1.0), Fidelity(0.5, 4.0, 0.5)])
    assert mean == Fidelity(0.75, 2.0, 0.75)
