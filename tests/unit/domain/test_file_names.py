"""ID to file name (R6.3). Cases TT-AC11-P4, P5, N5, E2, E4, E5."""

from __future__ import annotations

import pytest

from tests.fixtures import names as n
from vidgen.domain.naming import id_key, output_file_name


def test_plain_id_becomes_id_dot_mp4() -> None:
    """TT-AC11-P4."""
    assert output_file_name("183866") == "183866.mp4"


def test_slashes_become_underscores() -> None:
    """TT-AC11-P5."""
    assert output_file_name(n.SLASHED_ID) == "RJ_12_097_183866.mp4"


@pytest.mark.parametrize("bad", ["a<b", "a>b", "a:b", 'a"b', "a|b", "a?b", "a*b", "a\\b", "a b"])
def test_unsafe_characters_are_replaced_with_underscore(bad: str) -> None:
    """TT-AC11-P5: unsafe characters become `_`."""
    assert output_file_name(bad) == "a_b.mp4"


def test_id_made_only_of_unsafe_characters_keeps_length() -> None:
    """TT-AC11-E4."""
    assert output_file_name("///") == "___.mp4"


def test_leading_dot_does_not_create_a_hidden_file() -> None:
    """TT-AC11-E4."""
    assert not output_file_name(".hidden").startswith(".")


def test_devanagari_id_is_kept() -> None:
    """TT-AC11-E2."""
    assert output_file_name("\u0906\u0930-12") == "\u0906\u0930-12.mp4"


def test_file_name_never_exceeds_255_bytes_and_keeps_extension() -> None:
    """TT-AC11-E2: truncation is deterministic and never splits a character."""
    name = output_file_name("\u0906" * 300)
    assert len(name.encode("utf-8")) <= 255
    assert name.endswith(".mp4")
    name.encode("utf-8").decode("utf-8")  # still valid UTF-8
    assert output_file_name("\u0906" * 300) == name


def test_id_key_trims_casefolds_and_sanitises() -> None:
    """A2: the comparison key for duplicates."""
    assert id_key(" RJ/12/097 ") == id_key("rj_12_097")
    assert id_key("RJ12") != id_key("RJ012")


def test_id_key_is_case_insensitive_for_file_system_collisions() -> None:
    """TT-AC11-E5."""
    assert id_key("abc") == id_key("ABC")


def test_ids_that_collide_after_sanitising_share_a_key() -> None:
    """TT-AC11-N5: `A/1` and `A_1` would write the same file."""
    assert id_key("A/1") == id_key("A_1")
    assert output_file_name("A/1") == output_file_name("A_1")
