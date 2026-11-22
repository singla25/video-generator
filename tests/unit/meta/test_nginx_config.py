"""Static checks of the dashboard web server config (no nginx or Docker needed)."""

from __future__ import annotations

import re

import pytest

from tests.unit.meta.conftest import ROOT
from vidgen.settings import Settings

NGINX_CONF = ROOT / "frontend" / "docker" / "nginx.conf"
MEGABYTE = 1024 * 1024
REQUIRED_HEADERS = (
    "Content-Security-Policy",
    "X-Frame-Options",
    "X-Content-Type-Options",
    "Referrer-Policy",
)


def _text() -> str:
    return NGINX_CONF.read_text(encoding="utf-8")


def _body_limit_bytes() -> int:
    """The ``client_max_body_size`` of the API location, in bytes."""
    match = re.search(r"client_max_body_size\s+(\d+)([kmg]?)\s*;", _text(), re.IGNORECASE)
    assert match, "client_max_body_size is missing"
    factor = {"": 1, "k": 1024, "m": MEGABYTE, "g": 1024 * MEGABYTE}[match.group(2).lower()]
    return int(match.group(1)) * factor


def test_upload_limit_covers_the_largest_allowed_video() -> None:
    """A video the API accepts must also pass the dashboard proxy (413 otherwise)."""
    max_video = Settings.model_fields["max_video_bytes"].default
    assert _body_limit_bytes() >= max_video + 20 * MEGABYTE  # room for multipart overhead


def test_upload_limit_is_not_unbounded() -> None:
    """Zero means no limit in nginx; keep a finite cap."""
    assert 0 < _body_limit_bytes() <= 1024 * MEGABYTE


@pytest.mark.parametrize("header", REQUIRED_HEADERS)
def test_security_header_is_sent_on_every_response(header: str) -> None:
    """Each header is added with ``always`` so error pages carry it too."""
    assert re.search(rf"add_header\s+{header}\s+\"[^\"]+\"\s+always\s*;", _text()), header


def test_csp_forbids_framing_and_foreign_scripts() -> None:
    """The policy only allows own-origin scripts and refuses to be framed."""
    csp = re.search(r"add_header\s+Content-Security-Policy\s+\"([^\"]+)\"", _text())
    assert csp, "Content-Security-Policy value must be a quoted string"
    policy = csp.group(1)
    assert "frame-ancestors 'none'" in policy
    assert re.search(r"script-src 'self'(?!\s*'unsafe)", policy)
    assert "'unsafe-eval'" not in policy


def test_headers_are_not_overridden_in_a_location() -> None:
    """Keep add_header at server level: a location with its own add_header drops inherited ones."""
    text = _text()
    first_location = re.search(r"^\s*location\s", text, re.MULTILINE)
    assert first_location, "no location block found"
    assert "add_header" in text[: first_location.start()]
    assert "add_header" not in text[first_location.start() :]
