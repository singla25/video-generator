"""Header normalisation and column mapping (AC2 pure part). Cases TT-AC2-P3, N5, N6, E8."""

from __future__ import annotations

import pytest

from vidgen.domain.headers import (
    AmbiguousHeaderError,
    ColumnMapping,
    ColumnNotFoundError,
    DuplicateMappingError,
    normalize_header,
    resolve_mapping,
)


@pytest.mark.parametrize("raw", [" VID ", "vid", "Vid", "\tVID\n", "VID"])
def test_normalize_header_ignores_case_and_surrounding_whitespace(raw: str) -> None:
    """TT-AC2-P3."""
    assert normalize_header(raw) == "vid"


def test_normalize_header_keeps_devanagari_text() -> None:
    """TT-AC2-E8."""
    assert normalize_header("  \u0928\u093e\u092e ") == "\u0928\u093e\u092e"


def test_resolve_mapping_returns_column_indexes_for_name_id_and_spoken() -> None:
    """TT-AC2-P4."""
    mapping = resolve_mapping(
        ["Extra", " NAME ", "vid", "Spoken Name"],
        name="name",
        id_="VID ",
        spoken_name="spoken name",
    )
    assert mapping == ColumnMapping(name_index=1, id_index=2, spoken_name_index=3)


def test_resolve_mapping_without_spoken_name_gives_none() -> None:
    """TT-AC2-P5."""
    mapping = resolve_mapping(["Name", "ID"], name="Name", id_="ID")
    assert mapping.spoken_name_index is None


def test_resolve_mapping_missing_name_column_raises_column_not_found() -> None:
    """TT-AC2-N1."""
    with pytest.raises(ColumnNotFoundError) as info:
        resolve_mapping(["A", "ID"], name="Name", id_="ID")
    assert info.value.code == "COLUMN_NOT_FOUND"


def test_resolve_mapping_missing_id_column_raises_column_not_found() -> None:
    """TT-AC2-N2."""
    with pytest.raises(ColumnNotFoundError):
        resolve_mapping(["Name", "A"], name="Name", id_="ID")


def test_resolve_mapping_missing_spoken_column_raises_column_not_found() -> None:
    """TT-AC2-N1 (optional column that is mapped but absent)."""
    with pytest.raises(ColumnNotFoundError):
        resolve_mapping(["Name", "ID"], name="Name", id_="ID", spoken_name="Spoken")


def test_resolve_mapping_rejects_headers_equal_after_normalisation() -> None:
    """TT-AC2-N5: `ID` and `id ` are ambiguous."""
    with pytest.raises(AmbiguousHeaderError):
        resolve_mapping(["Name", "ID", "id "], name="Name", id_="ID")


def test_resolve_mapping_rejects_same_column_for_name_and_id() -> None:
    """TT-AC2-N6."""
    with pytest.raises(DuplicateMappingError):
        resolve_mapping(["Name", "ID"], name="Name", id_=" name")


def test_resolve_mapping_works_with_devanagari_headers() -> None:
    """TT-AC2-E8."""
    mapping = resolve_mapping(["\u0928\u093e\u092e", "ID"], name="\u0928\u093e\u092e", id_="id")
    assert mapping.name_index == 0
