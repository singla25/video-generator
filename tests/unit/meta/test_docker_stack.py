"""Docker app stack, static checks (AC1, P2, P4, P7, P9): compose file, ignore file, Dockerfiles.

No Docker and no YAML library needed: pyyaml is not a direct dependency, so the files are checked
as text. Real container behaviour is covered by tests/e2e/test_docker_stack_e2e.py.
"""

from __future__ import annotations

import re

import pytest

from tests.unit.meta.conftest import DOTENV_NAME, ROOT

APP_SERVICES = ("api", "worker", "dashboard")
BASE_SERVICES = ("postgres", "redis")
HEADER = re.compile(r"^  ([A-Za-z][\w-]*):\s*$")


def code_lines(text: str) -> str:
    """The text without full-line comments (comments may legitimately mention forbidden words)."""
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def read(name: str) -> str:
    """A root file as text."""
    return (ROOT / name).read_text(encoding="utf-8")


def service(name: str) -> str:
    """The text block of one compose service (comments removed)."""
    in_services, found, block = False, False, []
    for line in code_lines(read("docker-compose.yml")).splitlines():
        if re.match(r"^\S", line):
            in_services = line.startswith("services:")
            if found:
                break
            continue
        match = HEADER.match(line) if in_services else None
        if match:
            if found:
                break
            found = match.group(1) == name
            continue
        if found:
            block.append(line)
    assert found, f"service {name!r} is missing from docker-compose.yml"
    return "\n".join(block)


def in_profile_app(block: str) -> bool:
    """True when the block declares profile ``app`` (inline or list form)."""
    return bool(re.search(r"profiles:\s*(\[[^\]]*\bapp\b|\n\s*-\s*['\"]?app\b)", block))


# --- profiles ---------------------------------------------------------------------------------


@pytest.mark.parametrize("name", BASE_SERVICES)
def test_postgres_and_redis_keep_no_profile_so_dev_up_still_starts_them(name: str) -> None:
    assert "profiles:" not in service(name)


@pytest.mark.parametrize("name", APP_SERVICES)
def test_api_worker_and_dashboard_are_in_profile_app(name: str) -> None:
    assert in_profile_app(service(name))


def test_services_build_from_the_expected_dockerfiles() -> None:
    assert "Dockerfile.backend" in service("api") and "Dockerfile.backend" in service("worker")
    assert "Dockerfile.frontend" in service("dashboard")


# --- ports ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "var"), [("api", "VIDGEN_API_PORT"), ("dashboard", "VIDGEN_DASHBOARD_PORT")]
)
def test_host_port_is_parameterised_and_bound_to_loopback(name: str, var: str) -> None:
    assert re.search(rf"127\.0\.0\.1:\$\{{{var}:-\d+\}}:\d+", service(name))


@pytest.mark.parametrize("name", APP_SERVICES)
def test_no_app_service_publishes_a_port_on_all_interfaces(name: str) -> None:
    published = re.findall(r"^\s*-\s*['\"]?([^'\"\n]+:\d+)['\"]?\s*$", service(name), re.MULTILINE)
    ports = [p for p in published if re.search(r":\d+$", p) and "/" not in p.split(":")[0]]
    assert all(p.startswith("127.0.0.1:") for p in ports if re.match(r"^[\d$]", p))


def test_worker_publishes_no_port() -> None:
    assert "ports:" not in service("worker")


# --- media bind mount (P2) --------------------------------------------------------------------


@pytest.mark.parametrize("name", ["api", "worker"])
def test_media_is_a_parameterised_bind_mount_of_the_host_folder(name: str) -> None:
    assert re.search(r"\$\{VIDGEN_MEDIA_DIR:-\./media\}:/[^\s:'\"]+", service(name))


def test_only_postgres_and_redis_use_named_volumes() -> None:
    top = code_lines(read("docker-compose.yml")).split("\nvolumes:", 1)[1]
    names = re.findall(r"^  (\w+):", top, re.MULTILINE)
    assert sorted(names) == ["vidgen_pgdata", "vidgen_redisdata"]


@pytest.mark.parametrize("name", ["api", "worker"])
def test_storage_root_inside_the_container_is_the_mount_path(name: str) -> None:
    block = service(name)
    mount = re.search(r"\$\{VIDGEN_MEDIA_DIR:-\./media\}:(/[^\s:'\"]+)", block)
    root = re.search(r"VIDGEN_STORAGE_ROOT['\"]?[:=]\s*['\"]?(/[^\s'\"]+)", block)
    assert mount and root and mount.group(1) == root.group(1)


# --- reaching services by name (P4 wiring) ----------------------------------------------------


@pytest.mark.parametrize("name", ["api", "worker"])
def test_containers_reach_database_and_redis_by_service_name(name: str) -> None:
    block = service(name)
    assert re.search(r"VIDGEN_DATABASE_URL.*@postgres[:/]", block)
    assert re.search(r"VIDGEN_REDIS_URL.*redis://redis[:/]", block)
    assert not re.search(r"(DATABASE|REDIS)_URL.*127\.0\.0\.1", block)


# --- settings file and Modal tokens (P4) ------------------------------------------------------


@pytest.mark.parametrize("name", ["api", "worker"])
def test_settings_file_comes_from_a_parameter_so_tests_can_use_a_demo_file(name: str) -> None:
    assert re.search(r"env_file:.*\$\{VIDGEN_ENV_FILE:-\.env\}", service(name), re.DOTALL)


def test_worker_receives_the_modal_token_pair() -> None:
    block = service("worker")
    assert "MODAL_TOKEN_ID" in block and "MODAL_TOKEN_SECRET" in block


@pytest.mark.parametrize("name", ["api", "dashboard"])
def test_api_and_dashboard_never_get_the_modal_tokens(name: str) -> None:
    """If the shared settings file is loaded, the tokens must be blanked, not passed on."""
    lines = [ln for ln in service(name).splitlines() if "MODAL_TOKEN" in ln]
    assert all(re.search(r"MODAL_TOKEN_\w+['\"]?[:=]\s*['\"]{2}\s*$", ln) for ln in lines)


# --- workers, migrations -----------------------------------------------------------------------


def test_worker_count_is_a_parameter_defaulting_to_one() -> None:
    assert re.search(r"(scale|replicas):\s*['\"]?\$\{VIDGEN_DOCKER_WORKERS:-1\}", service("worker"))


@pytest.mark.parametrize(
    "name", ["docker-compose.yml", "Dockerfile.backend", "Dockerfile.frontend"]
)
def test_nothing_runs_migrations_on_container_start(name: str) -> None:
    assert not re.search(r"alembic|migrat", code_lines(read(name)), re.IGNORECASE)


# --- .dockerignore ----------------------------------------------------------------------------


def test_dockerignore_keeps_secrets_state_and_heavy_folders_out_of_the_build() -> None:
    entries = {ln.strip().rstrip("/") for ln in read(".dockerignore").splitlines() if ln.strip()}
    wanted = {
        DOTENV_NAME,
        f"{DOTENV_NAME}.*",
        ".dev",
        "media",
        ".venv",
        "node_modules",
        ".worktrees",
        ".git",
    }
    assert wanted - entries == set()


# --- Dockerfiles ------------------------------------------------------------------------------


def test_backend_image_installs_ffmpeg_and_fribidi_for_devanagari_labels() -> None:
    text = code_lines(read("Dockerfile.backend"))
    assert "ffmpeg" in text and "libfribidi" in text


def test_backend_image_never_copies_the_settings_file() -> None:
    copies = [
        ln
        for ln in code_lines(read("Dockerfile.backend")).splitlines()
        if re.match(r"\s*(COPY|ADD)\b", ln)
    ]
    assert copies and not any(DOTENV_NAME in ln for ln in copies)


def test_backend_image_runs_as_a_non_root_user() -> None:
    users = re.findall(r"^\s*USER\s+(\S+)", code_lines(read("Dockerfile.backend")), re.MULTILINE)
    assert users and users[-1] not in ("root", "0")


def frontend_text() -> str:
    """Dockerfile.frontend plus any web-server config shipped next to the dashboard."""
    parts = [code_lines(read("Dockerfile.frontend"))]
    for pattern in ("*nginx*", "Caddyfile*", "*.conf", "docker/*"):
        parts += [
            p.read_text(encoding="utf-8") for p in (ROOT / "frontend").glob(pattern) if p.is_file()
        ]
    return "\n".join(parts)


def test_dashboard_image_builds_the_production_bundle() -> None:
    assert re.search(r"npm run build|vite build", code_lines(read("Dockerfile.frontend")))


def test_dashboard_image_forwards_api_requests_to_the_api_service() -> None:
    assert re.search(r"(proxy_pass\s+http://api:\d+|reverse_proxy\s+api:\d+)", frontend_text())


def test_dashboard_image_does_not_start_the_vite_dev_server() -> None:
    starts = [
        ln
        for ln in code_lines(read("Dockerfile.frontend")).splitlines()
        if re.match(r"\s*(CMD|ENTRYPOINT)\b", ln)
    ]
    assert starts and not any(re.search(r"vite|npm run dev|npm start", ln) for ln in starts)


def test_backend_image_pins_uv_to_an_exact_version() -> None:
    assert re.search(r"uv==\d+\.\d+\.\d+", code_lines(read("Dockerfile.backend")))
