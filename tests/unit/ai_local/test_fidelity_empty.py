"""mean_fidelity over no frames returns a documented neutral result (no numpy needed)."""

from __future__ import annotations

from vidgen.infrastructure.local_ai.fidelity import Fidelity, mean_fidelity


def test_mean_of_no_frames_is_the_neutral_result_not_a_crash() -> None:
    assert mean_fidelity([]) == Fidelity(ssim=1.0, mean_abs_diff=0.0, texture_ratio=1.0)


def test_mean_of_one_frame_is_that_frame() -> None:
    one = Fidelity(0.9, 3.0, 0.8)
    assert mean_fidelity([one]) == one
