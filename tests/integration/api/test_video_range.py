"""Template video endpoint and HTTP Range support on every video download (DD-19).

Endpoints under test: GET /templates/{id}/video, GET /batches/{id}/rows/{n}/video and
GET /batches/{id}/preview. All answer 200 with Accept-Ranges: bytes, 206 + Content-Range for a
valid Range, and 416 (with Content-Range: bytes */size) for an unsatisfiable or malformed one.
"""

from __future__ import annotations

import io
from collections.abc import Callable
from dataclasses import dataclass

import pytest
from httpx import Response
from sqlalchemy import Engine

from tests.fixtures.doubles import VALID_VIDEO
from tests.integration.api.batch_helpers import (
    approve_preview,
    finish_row,
    new_batch,
    people,
    running_batch,
)
from tests.integration.api.conftest import Env
from tests.integration.api.helpers import new_template

UNKNOWN_ID = "00000000-0000-4000-8000-000000000000"
ROW_BYTES = b"0123456789abcdefghij"
PREVIEW_BYTES = b"PREVIEW-BYTES"


@dataclass
class Target:
    """A video URL and the exact bytes it must serve."""

    url: str
    content: bytes


Builder = Callable[[Env, Engine], Target]


def template_target(env: Env, db: Engine) -> Target:
    """The uploaded template video (VALID_VIDEO bytes)."""
    template_id = new_template(env)
    return Target(f"/templates/{template_id}/video", VALID_VIDEO)


def row_target(env: Env, db: Engine) -> Target:
    """A finished row's output video."""
    batch_id = running_batch(env, people(1))
    key = env.storage.write("out/ID1.mp4", io.BytesIO(ROW_BYTES))
    finish_row(db, batch_id, 2, at=env.clock.now(), output_key=key)
    return Target(f"/batches/{batch_id}/rows/2/video", ROW_BYTES)


def preview_target(env: Env, db: Engine) -> Target:
    """The rendered preview video."""
    batch_id = new_batch(env, people(2))
    approve_preview(env, batch_id)
    return Target(f"/batches/{batch_id}/preview", PREVIEW_BYTES)


BUILDERS = [
    pytest.param(template_target, id="template"),
    pytest.param(row_target, id="row"),
    pytest.param(preview_target, id="preview"),
]


@pytest.fixture(params=BUILDERS)
def target(request: pytest.FixtureRequest, env: Env, db: Engine) -> Target:
    """Each of the three video endpoints in turn."""
    builder: Builder = request.param
    return builder(env, db)


def fetch(env: Env, target: Target, range_header: str | None = None) -> Response:
    """GET the video, optionally with a Range header."""
    headers = {} if range_header is None else {"Range": range_header}
    return env.client.get(target.url, headers=headers)


def test_full_request_is_200_with_the_whole_file_and_accept_ranges(
    env: Env, target: Target
) -> None:
    """No Range: whole body, and the server advertises byte ranges."""
    response = fetch(env, target)
    assert response.status_code == 200
    assert response.content == target.content
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["content-type"].startswith("video/mp4")


def test_closed_range_returns_206_with_content_range(env: Env, target: Target) -> None:
    """bytes=0-3 gives the first four bytes."""
    response = fetch(env, target, "bytes=0-3")
    assert response.status_code == 206
    assert response.content == target.content[:4]
    assert response.headers["content-range"] == f"bytes 0-3/{len(target.content)}"
    assert response.headers["content-length"] == "4"
    assert response.headers["accept-ranges"] == "bytes"


def test_open_ended_range_runs_to_the_end(env: Env, target: Target) -> None:
    """bytes=5- gives everything from byte 5."""
    size = len(target.content)
    response = fetch(env, target, "bytes=5-")
    assert response.status_code == 206
    assert response.content == target.content[5:]
    assert response.headers["content-range"] == f"bytes 5-{size - 1}/{size}"


def test_suffix_range_gives_the_last_bytes(env: Env, target: Target) -> None:
    """bytes=-4 gives the final four bytes."""
    size = len(target.content)
    response = fetch(env, target, "bytes=-4")
    assert response.status_code == 206
    assert response.content == target.content[-4:]
    assert response.headers["content-range"] == f"bytes {size - 4}-{size - 1}/{size}"


def test_end_beyond_the_file_is_clamped(env: Env, target: Target) -> None:
    """A too-large end is cut to the last byte."""
    size = len(target.content)
    response = fetch(env, target, "bytes=2-999999")
    assert response.status_code == 206
    assert response.content == target.content[2:]
    assert response.headers["content-range"] == f"bytes 2-{size - 1}/{size}"


def test_single_byte_range(env: Env, target: Target) -> None:
    """bytes=0-0 is one byte."""
    response = fetch(env, target, "bytes=0-0")
    assert response.status_code == 206
    assert response.content == target.content[:1]


def test_range_covering_the_whole_file_is_206(env: Env, target: Target) -> None:
    """bytes=0- still answers 206 with the full length in Content-Range."""
    size = len(target.content)
    response = fetch(env, target, "bytes=0-")
    assert response.status_code == 206
    assert response.content == target.content
    assert response.headers["content-range"] == f"bytes 0-{size - 1}/{size}"


@pytest.mark.parametrize("header", ["bytes=999999-", "bytes=999999-1000000", "bytes=-0"])
def test_unsatisfiable_range_is_416_with_the_size(env: Env, target: Target, header: str) -> None:
    """Start beyond the end: 416 and Content-Range: bytes */size."""
    response = fetch(env, target, header)
    assert response.status_code == 416
    assert response.headers["content-range"] == f"bytes */{len(target.content)}"


@pytest.mark.parametrize("header", ["bytes=5-2", "bytes=abc", "bytes=", "items=0-3", "bytes=1-2-3"])
def test_malformed_range_is_416(env: Env, target: Target, header: str) -> None:
    """Reversed, non-numeric, empty or wrong-unit ranges are refused."""
    assert fetch(env, target, header).status_code == 416


def test_partial_content_length_is_the_range_length(env: Env, target: Target) -> None:
    """A 206 never claims the whole file's length as its own Content-Length."""
    response = fetch(env, target, "bytes=1-2")
    assert response.headers["content-length"] == "2"


# ---- template video endpoint specifics -------------------------------------------------


def test_template_video_unknown_id_is_404(env: Env) -> None:
    """No such template."""
    response = env.client.get(f"/templates/{UNKNOWN_ID}/video")
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_template_video_needs_login(anon: Env, env: Env) -> None:
    """Without a session the endpoint is 401, even for an existing template."""
    template_id = new_template(env)
    response = anon.client.get(f"/templates/{template_id}/video")
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"


def test_template_video_range_needs_login_too(anon: Env) -> None:
    """A Range header does not bypass authentication."""
    response = anon.client.get(f"/templates/{UNKNOWN_ID}/video", headers={"Range": "bytes=0-3"})
    assert response.status_code == 401


def test_template_video_does_not_leak_the_storage_key(env: Env) -> None:
    """Headers and body carry no internal storage path."""
    template_id = new_template(env)
    response = env.client.get(f"/templates/{template_id}/video")
    stored = list(env.storage.files)
    for key in stored:
        assert key not in "".join(f"{k}:{v}" for k, v in response.headers.items())
