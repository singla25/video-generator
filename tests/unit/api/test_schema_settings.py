"""BL-8 SS-ST*: the schema_check_ttl_seconds setting (default 5, range 1-300)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from tests.integration.api.conftest import make_settings

URL = "postgresql+psycopg://vidgen:devpassword@127.0.0.1:5432/vidgen_unit_nodb_test"


def test_default_is_five_seconds(tmp_path: Path) -> None:
    """SS-ST-P1."""
    assert make_settings(URL, tmp_path).schema_check_ttl_seconds == 5


@pytest.mark.parametrize("ttl", [1, 5, 300])
def test_accepts_values_in_range(tmp_path: Path, ttl: int) -> None:
    """SS-ST-P2: both bounds are valid."""
    assert (
        make_settings(URL, tmp_path, schema_check_ttl_seconds=ttl).schema_check_ttl_seconds == ttl
    )


@pytest.mark.parametrize("ttl", [0, -1, 301, 10_000])
def test_rejects_values_out_of_range(tmp_path: Path, ttl: int) -> None:
    """SS-ST-N1."""
    with pytest.raises(ValidationError):
        make_settings(URL, tmp_path, schema_check_ttl_seconds=ttl)
