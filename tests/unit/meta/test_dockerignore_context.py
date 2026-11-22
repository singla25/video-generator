"""Static checks that the Docker build context stays small and complete (no Docker needed)."""

from __future__ import annotations

import os
import re
import subprocess
from functools import lru_cache

import pytest

from tests.unit.meta.conftest import DOTENV_NAME, ROOT

MAX_CONTEXT_BYTES = 20 * 1024 * 1024
MAX_FILE_BYTES = 5 * 1024 * 1024

Rules = list[tuple[bool, re.Pattern[str]]]


# --- helper: apply .dockerignore the way Docker does -------------------------------------------


def _to_regex(pattern: str) -> re.Pattern[str]:
    """Translate one dockerignore pattern to a regex matched against a whole relative path.

    `**/` matches zero or more directories, `**` anything, `*` within one segment, `?` one
    non-slash character. Patterns are anchored at the context root.
    """
    out: list[str] = []
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(out))


def parse_rules(text: str) -> Rules:
    """Return (negated, regex) per effective line; comments and blanks are dropped."""
    rules: Rules = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        negated = line.startswith("!")
        if negated:
            line = line[1:].strip()
        line = line.lstrip("/").rstrip("/")
        rules.append((negated, _to_regex(line)))
    return rules


def is_ignored(path: str, rules: Rules) -> bool:
    """True if the path, or any parent directory of it, is excluded (last match wins)."""
    parts = path.split("/")
    for n in range(1, len(parts) + 1):
        prefix = "/".join(parts[:n])
        state = False
        for negated, rx in rules:
            if rx.fullmatch(prefix):
                state = not negated
        if state:
            return True
    return False


@lru_cache(maxsize=1)
def _rules() -> Rules:
    return parse_rules((ROOT / ".dockerignore").read_text())


def ignored(path: str) -> bool:
    """Whether the repo's real .dockerignore excludes `path`."""
    return is_ignored(path, _rules())


# --- helper self-tests -------------------------------------------------------------------------

_ENV_RULES = f"{DOTENV_NAME}\n{DOTENV_NAME}.*\n!{DOTENV_NAME}.example"


@pytest.mark.parametrize(
    ("rules", "path", "expected"),
    [
        ("node_modules", "node_modules/a.js", True),
        ("node_modules", "frontend/node_modules/a.js", False),  # root-relative only
        ("**/node_modules", "node_modules/a.js", True),
        ("**/node_modules", "a/b/node_modules/x.js", True),
        ("*.mp4", "clip.mp4", True),
        ("*.mp4", "a/clip.mp4", False),  # `*` never crosses a slash
        ("**/*.mp4", "a/b/clip.mp4", True),
        ("a?c", "abc", True),
        ("a?c", "a/c", False),
        ("backend/spikes", "backend/spikes/x/y.py", True),  # directory excludes its children
        (_ENV_RULES, f"{DOTENV_NAME}.example", False),
        (_ENV_RULES, f"{DOTENV_NAME}.local", True),
        ("# comment\n\nfoo", "foo", True),
        ("# foo", "# foo", False),
        ("foo\n!foo\nfoo", "foo", True),  # last match wins
        ("foo\n!foo", "foo", False),
    ],
)
def test_helper_applies_dockerignore_semantics(rules: str, path: str, expected: bool) -> None:
    assert is_ignored(path, parse_rules(rules)) is expected


# --- the real .dockerignore --------------------------------------------------------------------

MUST_BE_IGNORED = [
    "backend/spikes/m2_mac/work/hf/hub/models--x/blobs/abc",
    "backend/spikes/m2_mac/work/musetalk/models/unet.pth",
    "backend/spikes/m2_mac/work/whisper_sizes/medium/model.bin",
    "backend/spikes/m2_mac/work/real/chk.wav",
    "backend/spikes/m2_mac/work/real/check_frame.jpg",
    "backend/spikes/m2_mac/s6_real.py",
    "frontend/node_modules/react/index.js",
    "backend/vidgen/__pycache__/app.cpython-311.pyc",
    "backend/migrations/__pycache__/x.pyc",
    "backend/vidgen/x/.DS_Store",
    ".DS_Store",
    DOTENV_NAME,
    f"{DOTENV_NAME}.local",
]
MODEL_EXTENSIONS = [
    "safetensors", "pt", "pth", "ckpt", "onnx", "bin", "wav", "mp3", "mp4", "mov",
]  # fmt: skip
MEDIA_PATHS = [
    f"{base}/{name}.{ext}"
    for ext in MODEL_EXTENSIONS
    for base, name in (
        ("backend/vidgen/x", "model"),
        ("backend/foo", "a"),
        ("frontend/public", "clip"),
    )
]

MUST_BE_INCLUDED = [
    "backend/vidgen/api/app.py",
    "backend/vidgen/assets/fonts/NotoSansDevanagari-Bold.ttf",
    "backend/migrations/versions/0003_render_providers.py",
    "backend/alembic.ini",
    "backend/modal_app/app.py",
    "backend/scripts/whisper_size_test.py",
    "pyproject.toml",
    "uv.lock",
    "frontend/package.json",
    "frontend/package-lock.json",
    "frontend/src/main.tsx",
    "frontend/docker/nginx.conf",
    f"{DOTENV_NAME}.example",
]


@pytest.mark.parametrize("path", MUST_BE_IGNORED + MEDIA_PATHS)
def test_dockerignore_excludes_heavy_or_private_path(path: str) -> None:
    assert ignored(path), f"{path} would be sent to the Docker daemon"


@pytest.mark.parametrize("path", MUST_BE_INCLUDED)
def test_dockerignore_keeps_needed_file_in_context(path: str) -> None:
    assert not ignored(path), f"{path} is needed by the image but is ignored"


def _copy_sources() -> list[str]:
    sources: list[str] = []
    for name in ("Dockerfile.backend", "Dockerfile.frontend"):
        for line in (ROOT / name).read_text().splitlines():
            parts = line.split()
            if not parts or parts[0].upper() != "COPY":
                continue
            if any(a.startswith("--from") for a in parts[1:]):
                continue  # copies from another build stage, not from the context
            args = [a for a in parts[1:] if not a.startswith("--")]
            sources += [a.rstrip("/") for a in args[:-1]]
    return sources


def test_copy_sources_were_parsed() -> None:
    assert {"backend", "pyproject.toml", "uv.lock", "frontend"} <= set(_copy_sources())


@pytest.mark.parametrize("source", sorted(set(_copy_sources())))
def test_every_dockerfile_copy_source_is_not_ignored(source: str) -> None:
    assert not ignored(source)


def _tracked_kept_files() -> list[tuple[str, int]]:
    out = subprocess.run(
        ["git", "ls-files", "-z"],  # noqa: S607
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    files = []
    for rel in filter(None, out.split("\0")):
        full = ROOT / rel
        if full.is_file() and not ignored(rel):
            files.append((rel, os.path.getsize(full)))
    return files


def test_tracked_files_sent_to_docker_stay_small() -> None:
    files = _tracked_kept_files()
    assert files, "git ls-files returned nothing"
    assert sum(size for _, size in files) < MAX_CONTEXT_BYTES
    big = [rel for rel, size in files if size > MAX_FILE_BYTES]
    assert big == [], f"files over 5 MB inside the build context: {big}"


def test_dockerignore_comment_explains_why_spikes_are_excluded() -> None:
    lines = (ROOT / ".dockerignore").read_text().splitlines()
    assert any(ln.lstrip().startswith("#") and "spikes" in ln for ln in lines)
