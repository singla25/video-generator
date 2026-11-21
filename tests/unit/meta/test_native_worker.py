"""Native local-AI worker next to the Docker app (docs/plans/docker-and-cloud-setup.md P2, P3).

Static only: parses files, runs ``scripts/setup.py native-worker --print`` with temp dirs and an
injected platform. No Docker, no model, no worker is started. Secrets here are made-up values.

Contract for the developer: ``setup.host_platform() -> tuple[str, str]`` returns
``(platform.system(), platform.machine())`` and is the platform seam tests monkeypatch.
The ``--print`` output has one ``KEY=value`` line per variable and the two command steps.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml  # transitive dev dependency (no direct pin); compose file is parsed with it

from tests.unit.meta.conftest import DOTENV_NAME, ROOT

FAKE_PASSWORD = "Fake-Db-Pass-9x"  # noqa: S105
FAKE_KEY = "fake-key-0123456789abcdef"
FAKE_TOKEN = "fake-modal-token-secret"  # noqa: S105
INSTALL_STEP = "uv pip install --no-deps chatterbox-tts==0.1.7"
WORKER_STEP = "uv run --extra local-ai python -m vidgen.worker"
COMMAND = "python3 scripts/setup.py native-worker"
ENV_LINE = re.compile(r"^(?:export\s+)?(VIDGEN_[A-Z_]+)=(.*)$", re.MULTILINE)


def write_env(root: Path, **extra: str) -> Path:
    """A settings file in local mode with fake secrets, plus any extra ``KEY=value`` lines."""
    values = {
        "VIDGEN_AI_MODE": "local",
        "VIDGEN_ENCRYPTION_KEY": FAKE_KEY,
        "MODAL_TOKEN_SECRET": FAKE_TOKEN,
        **extra,
    }
    path = root / DOTENV_NAME
    path.write_text("".join(f"{k}={v}\n" for k, v in values.items()), encoding="utf-8")
    return path


def run_print(
    mod: ModuleType,
    root: Path,
    capsys: pytest.CaptureFixture[str],
    env_file: Path | None = None,
    *,
    extra: list[str] | None = None,
) -> tuple[int, str, dict[str, str]]:
    """Run ``native-worker --print``; return exit code, all output and the parsed variables."""
    argv = ["--root", str(root), "native-worker", "--print", *(extra or [])]
    if env_file is not None:
        argv += ["--env-file", str(env_file)]
    code = mod.main(argv)
    captured = capsys.readouterr()
    text = captured.out + captured.err
    return code, text, dict(ENV_LINE.findall(text))


@pytest.fixture(autouse=True)
def mac_arm64(monkeypatch: pytest.MonkeyPatch, setup_mod: ModuleType) -> None:
    """Pretend to be an Apple silicon Mac unless a test overrides it."""
    monkeypatch.setattr(setup_mod, "host_platform", lambda: ("Darwin", "arm64"), raising=False)


@pytest.fixture
def no_subprocess(monkeypatch: pytest.MonkeyPatch, setup_mod: ModuleType) -> None:
    """Any attempt to start a process fails the test."""

    def boom(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("subprocess must not be used with --print")

    for name in ("run", "Popen", "call", "check_call", "check_output"):
        monkeypatch.setattr(subprocess, name, boom)
    monkeypatch.setattr(setup_mod.subprocess, "run", boom)


# ---------------------------------------------------------------- environment: positive


def test_native_worker_print_builds_defaults(
    setup_mod: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, _, env = run_print(setup_mod, tmp_path, capsys, write_env(tmp_path))
    assert code == 0
    assert env["VIDGEN_AI_MODE"] == "local"
    assert env["VIDGEN_DATABASE_URL"] == "postgresql+psycopg://vidgen:***@127.0.0.1:5432/vidgen"
    assert env["VIDGEN_REDIS_URL"] == "redis://127.0.0.1:6379/0"
    assert env["VIDGEN_WORKER_THREADS"] == "1"
    assert env["VIDGEN_STORAGE_ROOT"] == str(tmp_path / "media")
    weights = ROOT / "backend/spikes/m2_mac/work/local_ai_weights"
    assert env["VIDGEN_LOCAL_AI_WEIGHTS_DIR"].endswith(
        "backend/spikes/m2_mac/work/local_ai_weights"
    )
    assert Path(env["VIDGEN_LOCAL_AI_WEIGHTS_DIR"]).is_absolute()
    assert weights.name in env["VIDGEN_LOCAL_AI_WEIGHTS_DIR"]


def test_native_worker_print_follows_custom_ports_and_names(
    setup_mod: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    env_file = write_env(
        tmp_path,
        VIDGEN_DB_PORT="15432",
        VIDGEN_REDIS_PORT="16379",
        VIDGEN_DB_USER="alice",
        VIDGEN_DB_PASSWORD=FAKE_PASSWORD,
        VIDGEN_DB_NAME="clips",
        VIDGEN_LOCAL_AI_WEIGHTS_DIR=str(tmp_path / "weights"),
    )
    _, text, env = run_print(setup_mod, tmp_path, capsys, env_file)
    assert env["VIDGEN_DATABASE_URL"] == "postgresql+psycopg://alice:***@127.0.0.1:15432/clips"
    assert env["VIDGEN_REDIS_URL"] == "redis://127.0.0.1:16379/0"
    assert env["VIDGEN_LOCAL_AI_WEIGHTS_DIR"] == str(tmp_path / "weights")
    assert FAKE_PASSWORD not in text


def test_native_worker_default_env_file_is_dot_env_in_root(
    setup_mod: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_env(tmp_path)
    code, _, env = run_print(setup_mod, tmp_path, capsys)
    assert code == 0
    assert env["VIDGEN_AI_MODE"] == "local"


@pytest.mark.parametrize(
    "media",
    ["./media", "data/clips", "my media dir", "médïa/видео/视频", "emoji-🎬 folder"],
)
def test_native_worker_media_dir_is_absolute_host_path(
    setup_mod: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str], media: str
) -> None:
    env_file = write_env(tmp_path, VIDGEN_MEDIA_DIR=f'"{media}"')
    _, _, env = run_print(setup_mod, tmp_path, capsys, env_file)
    storage = Path(env["VIDGEN_STORAGE_ROOT"].strip("'\""))
    assert storage.is_absolute()
    assert storage == (tmp_path / media).resolve() or storage == (tmp_path / media)


def test_native_worker_absolute_media_dir_is_kept(
    setup_mod: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    media = tmp_path / "elsewhere" / "media"
    env_file = write_env(tmp_path, VIDGEN_MEDIA_DIR=str(media))
    _, _, env = run_print(setup_mod, tmp_path, capsys, env_file)
    assert Path(env["VIDGEN_STORAGE_ROOT"].strip("'\"")) in (media, media.resolve())


def test_native_worker_print_shows_both_command_steps_in_order(
    setup_mod: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, text, _ = run_print(setup_mod, tmp_path, capsys, write_env(tmp_path))
    assert INSTALL_STEP in text
    assert WORKER_STEP in text
    assert text.index(INSTALL_STEP) < text.index(WORKER_STEP)


# ---------------------------------------------------------------- redaction and no process


def test_native_worker_print_never_shows_passwords_or_keys(
    setup_mod: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    env_file = write_env(tmp_path, VIDGEN_DB_PASSWORD=FAKE_PASSWORD, VIDGEN_API_KEY=FAKE_KEY)
    _, text, _ = run_print(setup_mod, tmp_path, capsys, env_file)
    for secret in (FAKE_PASSWORD, FAKE_KEY, FAKE_TOKEN):
        assert secret not in text
    assert "***" in text


def test_native_worker_default_password_is_redacted_too(
    setup_mod: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, text, _ = run_print(setup_mod, tmp_path, capsys, write_env(tmp_path))
    assert "devpassword" not in text


def test_native_worker_print_never_calls_subprocess(
    setup_mod: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    no_subprocess: None,
) -> None:
    code, _, env = run_print(setup_mod, tmp_path, capsys, write_env(tmp_path))
    assert code == 0
    assert env  # real output came back, so the subcommand exists and ran


def test_native_worker_print_writes_nothing(
    setup_mod: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    env_file = write_env(tmp_path)
    before = env_file.read_bytes()
    run_print(setup_mod, tmp_path, capsys, env_file)
    assert env_file.read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == [DOTENV_NAME]


# ---------------------------------------------------------------- refusals


@pytest.mark.parametrize(
    "host", [("Darwin", "x86_64"), ("Linux", "x86_64"), ("Linux", "aarch64"), ("Windows", "AMD64")]
)
def test_native_worker_refuses_other_platforms(
    setup_mod: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    host: tuple[str, str],
) -> None:
    monkeypatch.setattr(setup_mod, "host_platform", lambda: host)
    code, text, env = run_print(setup_mod, tmp_path, capsys, write_env(tmp_path))
    assert code == 2
    assert "arm64" in text or "Apple silicon" in text
    assert not env


def test_native_worker_refuses_missing_env_file(
    setup_mod: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, text, env = run_print(setup_mod, tmp_path, capsys, tmp_path / DOTENV_NAME)
    assert code == 2
    assert "setup.py" in text
    assert not env


@pytest.mark.parametrize("mode", ["fake", "modal", "real", ""])
def test_native_worker_refuses_when_mode_is_not_local(
    setup_mod: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str], mode: str
) -> None:
    code, text, env = run_print(
        setup_mod, tmp_path, capsys, write_env(tmp_path, VIDGEN_AI_MODE=mode)
    )
    assert code == 2
    assert "local" in text
    assert not env


def test_native_worker_refuses_env_file_without_mode_line(
    setup_mod: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / DOTENV_NAME
    path.write_text("VIDGEN_CREATOR_ENTITY='x'\n", encoding="utf-8")
    code, _, _ = run_print(setup_mod, tmp_path, capsys, path)
    assert code == 2


def test_native_worker_refuses_unreadable_env_file(
    setup_mod: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write_env(tmp_path)
    path.chmod(0o000)
    try:
        code, text, env = run_print(setup_mod, tmp_path, capsys, path)
    finally:
        path.chmod(0o600)
    assert code == 2
    assert not env
    assert FAKE_KEY not in text


def test_native_worker_refuses_directory_as_env_file(
    setup_mod: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, _, env = run_print(setup_mod, tmp_path, capsys, tmp_path)
    assert code == 2
    assert not env


def test_native_worker_refusal_never_starts_a_process(
    setup_mod: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    no_subprocess: None,
) -> None:
    code, _, _ = run_print(setup_mod, tmp_path, capsys, tmp_path / "missing")
    assert code == 2


# ---------------------------------------------------------------- installer summary


def test_installer_local_mode_summary_names_the_native_worker_command() -> None:
    source = (ROOT / "scripts" / "setup.py").read_text(encoding="utf-8")
    assert COMMAND in source


# ---------------------------------------------------------------- compose file


@pytest.fixture(scope="module")
def services() -> dict[str, Any]:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    return dict(compose["services"])


@pytest.mark.parametrize(
    ("service", "var", "default", "inner"),
    [
        ("postgres", "VIDGEN_DB_PORT", "5432", "5432"),
        ("redis", "VIDGEN_REDIS_PORT", "6379", "6379"),
    ],
)
def test_compose_publishes_data_services_on_loopback_only(
    services: dict[str, Any], service: str, var: str, default: str, inner: str
) -> None:
    assert services[service]["ports"] == [f"127.0.0.1:${{{var}:-{default}}}:{inner}"]


def test_compose_every_published_port_is_loopback(services: dict[str, Any]) -> None:
    for name, svc in services.items():
        for port in svc.get("ports", []):
            assert str(port).startswith("127.0.0.1:"), f"{name} publishes beyond loopback"


def test_compose_api_and_worker_share_the_host_media_folder(services: dict[str, Any]) -> None:
    expected = "${VIDGEN_MEDIA_DIR:-./media}:/data/media"
    assert expected in services["api"]["volumes"]
    assert expected in services["worker"]["volumes"]


def test_compose_app_services_are_opt_in_and_data_services_are_not(
    services: dict[str, Any],
) -> None:
    for name in ("api", "worker", "dashboard"):
        assert services[name]["profiles"] == ["app"]
    for name in ("postgres", "redis"):
        assert "profiles" not in services[name]


def test_compose_worker_scale_defaults_to_one_and_follows_the_setting(
    services: dict[str, Any],
) -> None:
    assert services["worker"]["scale"] == "${VIDGEN_DOCKER_WORKERS:-1}"


def test_compose_api_blanks_the_modal_tokens(services: dict[str, Any]) -> None:
    env = services["api"]["environment"]
    assert env["MODAL_TOKEN_ID"] == ""
    assert env["MODAL_TOKEN_SECRET"] == ""


def test_compose_no_container_gets_local_ai_weights_gpu_or_local_mode(
    services: dict[str, Any],
) -> None:
    for name, svc in services.items():
        env = svc.get("environment", {})
        pairs = env.items() if isinstance(env, dict) else (e.split("=", 1) for e in env)
        for key, value in pairs:
            assert key != "VIDGEN_LOCAL_AI_WEIGHTS_DIR", name
            assert not (key == "VIDGEN_AI_MODE" and value == "local"), name
        assert "deploy" not in svc and "devices" not in svc and "runtime" not in svc, name
        assert "gpus" not in svc, name


def test_compose_containers_keep_internal_service_addresses(services: dict[str, Any]) -> None:
    api = services["api"]["environment"]
    assert "@postgres:5432/" in api["VIDGEN_DATABASE_URL"]
    assert api["VIDGEN_REDIS_URL"] == "redis://redis:6379/0"
    assert api["VIDGEN_STORAGE_ROOT"] == "/data/media"


# ---------------------------------------------------------------- docs


def test_readme_names_the_native_worker_command() -> None:
    assert COMMAND in (ROOT / "README.md").read_text(encoding="utf-8")


def test_plan_names_the_native_worker_command() -> None:
    plan = ROOT / "docs" / "plans" / "docker-and-cloud-setup.md"
    assert COMMAND in plan.read_text(encoding="utf-8")
