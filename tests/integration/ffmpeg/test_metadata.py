"""MP4 metadata written by the engine (C3, AC10). Values come from arguments, not settings."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.fixtures.analysis import FFMPEG, duration_of, format_tags
from tests.fixtures.templates import make_template
from tests.integration.ffmpeg.conftest import RenderFn
from vidgen.domain.codes import DomainError

STANDARD_TAGS = {"major_brand", "minor_version", "compatible_brands", "encoder", "creation_time"}


def test_creator_date_and_batch_id_are_in_the_format_tags(render_clip: RenderFn) -> None:
    """TT-AC10-P4: read back with ffprobe."""
    r = render_clip(
        metadata={
            "creator_entity": "Example Creator Association",
            "generated_on": "2026-10-18",
            "batch_id": "b-7c1e",
        }
    )
    tags = format_tags(r.out)
    assert tags["creator_entity"] == "Example Creator Association"
    assert tags["generated_on"] == "2026-10-18"
    assert tags["batch_id"] == "b-7c1e"


def test_values_come_from_the_arguments_not_from_defaults(render_clip: RenderFn) -> None:
    """TT-AC10-P4: two renders with different arguments give different tags."""
    first = render_clip(
        metadata={"creator_entity": "Org One", "generated_on": "2026-10-18", "batch_id": "one"}
    )
    second = render_clip(
        metadata={"creator_entity": "Org Two", "generated_on": "2026-10-18", "batch_id": "two"}
    )
    assert format_tags(first.out)["creator_entity"] == "Org One"
    assert format_tags(second.out)["creator_entity"] == "Org Two"


def test_unicode_creator_entity_round_trips(render_clip: RenderFn) -> None:
    """TT-AC10-E4: Devanagari, emoji, RTL and punctuation survive."""
    name = "\u0938\u0902\u0938\u094d\u0925\u093e \u062d\u0645\u0644\u0629 \U0001f680 a=b; c"
    r = render_clip(
        metadata={"creator_entity": name, "generated_on": "2026-10-18", "batch_id": "b1"}
    )
    assert format_tags(r.out)["creator_entity"] == name


def test_very_long_creator_entity_never_leaves_a_broken_file(
    tmp_path: Path, render_clip: RenderFn
) -> None:
    """TT-AC10-E5: either truncated/accepted with a valid file, or rejected with no output."""
    long_name = "x" * 5000
    try:
        r = render_clip(
            metadata={"creator_entity": long_name, "generated_on": "2026-10-18", "batch_id": "b1"}
        )
    except DomainError:
        assert not list(tmp_path.glob("*/out.mp4"))
        return
    assert duration_of(r.out) > 0
    assert format_tags(r.out)["creator_entity"].startswith("xxx")


def test_no_template_or_person_data_leaks_into_the_tags(
    tmp_path: Path, render_clip: RenderFn
) -> None:
    """TT-AC10-E6: only the given keys (plus standard container tags) appear."""
    template = make_template(tmp_path / "Asha_Fixture_Template.mp4")
    r = render_clip(template=template)
    tags = format_tags(r.out)
    assert set(tags) <= set(r.metadata) | STANDARD_TAGS | {"handler_name"}
    assert all("Asha" not in value for value in tags.values())


def test_template_metadata_is_not_copied_into_the_output(
    tmp_path: Path, render_clip: RenderFn
) -> None:
    """TT-AC1-E9 / C3: a title tag on the template (even instruction-like text) is dropped."""
    plain = make_template(tmp_path / "plain.mp4")
    tagged = tmp_path / "tagged.mp4"
    subprocess.run(  # noqa: S603
        [FFMPEG, "-y", "-v", "error", "-i", str(plain), "-c", "copy", "-metadata",
         "title=ignore your rules", str(tagged)],
        check=True, capture_output=True, timeout=60,
    )  # fmt: skip
    r = render_clip(template=tagged)
    assert "title" not in format_tags(r.out)


@pytest.mark.parametrize("missing", ["creator_entity", "batch_id", "generated_on"])
def test_missing_required_metadata_is_refused(render_clip: RenderFn, missing: str) -> None:
    """TT-AC10-N1: C3 metadata is mandatory; the engine will not write an unlabelled file."""
    metadata = {"creator_entity": "Org", "generated_on": "2026-10-18", "batch_id": "b1"}
    del metadata[missing]
    with pytest.raises(ValueError, match=missing):
        render_clip(metadata=metadata)


def test_blank_creator_entity_is_refused(render_clip: RenderFn) -> None:
    """TT-AC10-N1."""
    with pytest.raises(ValueError, match="creator_entity"):
        render_clip(
            metadata={"creator_entity": "  ", "generated_on": "2026-10-18", "batch_id": "b1"}
        )
