"""Shared fakes for the scripts/setup.py installer tests.

Nothing here touches Docker, uv, the network, a terminal or a browser: every outside effect of the
installer goes through the injectable ``Seams`` object, and these fakes script them.
All secrets are made-up demo values.
"""

from __future__ import annotations

import importlib.util
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
DOTENV_NAME = "." + "env"

DEMO_PASSWORD = "DemoPass-123"  # noqa: S105
DEMO_TOKEN_ID = "demo-id"  # noqa: S105
DEMO_TOKEN_SECRET = "demo-secret"  # noqa: S105
DEMO_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c29tZXNhbHQ$ZGVtby1oYXNo"
SECRETS = (DEMO_PASSWORD, DEMO_TOKEN_ID, DEMO_TOKEN_SECRET)
BACKEND_SETTINGS = Path("backend") / "vidgen" / "settings.py"


def settings_source(
    modes: tuple[str, ...], *, backend_modes: tuple[str, ...] = ("fake", "real")
) -> str:
    """A minimal backend settings.py whose ``ai_mode`` Literal accepts ``modes``."""
    quoted = ", ".join(f'"{m}"' for m in modes)
    legacy = ", ".join(f'"{m}"' for m in backend_modes)
    return (
        "from typing import Literal\n\n\nclass Settings:\n"
        f'    ai_backend: Literal[{legacy}] = "fake"\n'
        f'    ai_mode: Literal[{quoted}] = "fake"\n'
    )


def load_setup() -> ModuleType:
    """Import scripts/setup.py by file path (scripts/ is not a package)."""
    spec = importlib.util.spec_from_file_location("installer_setup", ROOT / "scripts" / "setup.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def setup_mod() -> ModuleType:
    """The installer module (fails with FileNotFoundError until scripts/setup.py exists)."""
    return load_setup()


@dataclass
class Call:
    """One recorded subprocess call."""

    argv: list[str]
    child_vars: dict[str, str] | None
    input_text: str | None
    dotenv_existed: bool


@dataclass
class Harness:
    """Scripted answers plus recorders for every seam of ``setup.Seams``."""

    mod: ModuleType
    root: Path
    answers: dict[str, list[str]] = field(
        default_factory=lambda: {"mode": ["fake"], "migrat": ["n"]}
    )
    password: str = DEMO_PASSWORD
    password_again: str | None = None
    token_id: str = DEMO_TOKEN_ID
    token_secret: str = DEMO_TOKEN_SECRET
    missing_tools: set[str] = field(default_factory=set)
    interactive: bool = True
    docker_rc: int = 0
    hash_rc: int = 0
    modal_rc: int = 0
    modal_stderr: str = ""
    migrate_rc: int = 0
    calls: list[Call] = field(default_factory=list)
    prompts: list[str] = field(default_factory=list)
    secret_prompts: list[str] = field(default_factory=list)
    opened: list[str] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """By default the fixture backend accepts modal, so the Modal flow is reachable."""
        self.write_backend_settings(settings_source(("fake", "local", "modal")))

    def write_backend_settings(self, text: str | None) -> None:
        """Write (or, with None, remove) the fixture backend/vidgen/settings.py under the root."""
        path = self.root / BACKEND_SETTINGS
        if text is None:
            path.unlink(missing_ok=True)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def top_level(self) -> list[str]:
        """Names directly in the project root, without the fixture ``backend`` folder."""
        return sorted(p.name for p in self.root.iterdir() if p.name != "backend")

    @property
    def dotenv(self) -> Path:
        """Where the installer must write the settings file."""
        return self.root / DOTENV_NAME

    def _which(self, name: str) -> str | None:
        return None if name in self.missing_tools else f"/fake/bin/{name}"

    def _run(
        self,
        argv: Sequence[str],
        *,
        extra_vars: Mapping[str, str] | None = None,
        input_text: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        args = list(argv)
        child = dict(extra_vars) if extra_vars is not None else None
        self.calls.append(Call(args, child, input_text, self.dotenv.exists()))
        if args[:2] == ["docker", "info"]:
            return subprocess.CompletedProcess(args, self.docker_rc, "", "")
        if "hash-password" in args:
            return subprocess.CompletedProcess(args, self.hash_rc, DEMO_HASH + "\n", "")
        if "alembic" in args:
            return subprocess.CompletedProcess(args, self.migrate_rc, "", "")
        if "modal" in args and "--with" in args:
            return subprocess.CompletedProcess(args, self.modal_rc, "", self.modal_stderr)
        raise AssertionError(f"unexpected subprocess call: {args}")

    def _ask(self, prompt: str) -> str:
        self.prompts.append(prompt)
        low = prompt.lower()
        for key, queue in self.answers.items():
            if key in low:
                if not queue:
                    raise AssertionError(
                        f"prompt {key!r} asked more often than scripted: {prompt!r}"
                    )
                return queue.pop(0)
        raise AssertionError(f"unexpected prompt: {prompt!r}")

    def _getpass(self, prompt: str) -> str:
        self.secret_prompts.append(prompt)
        low = prompt.lower()
        if "token id" in low:
            return self.token_id
        if "token secret" in low:
            return self.token_secret
        if "again" in low:
            return self.password if self.password_again is None else self.password_again
        if "password" in low:
            return self.password
        raise AssertionError(f"unexpected hidden prompt: {prompt!r}")

    def _open(self, url: str) -> bool:
        self.opened.append(url)
        return True

    def seams(self) -> Any:
        """Build the injectable ``setup.Seams`` from the fakes."""
        return self.mod.Seams(
            which=self._which,
            run=self._run,
            getpass=self._getpass,
            ask=self._ask,
            open_url=self._open,
            echo=self.lines.append,
            is_interactive=lambda: self.interactive,
        )

    def run_main(self) -> int:
        """Run ``setup.main`` against the temp project root; Ctrl-C is reported as 130."""
        try:
            return int(self.mod.main(["--root", str(self.root)], self.seams()))
        except KeyboardInterrupt:
            return 130

    def calls_with(self, word: str) -> list[Call]:
        """Subprocess calls whose argv contains ``word``."""
        return [c for c in self.calls if word in c.argv]

    def all_text(self, capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture) -> str:
        """Everything the installer showed or logged."""
        seen = capsys.readouterr()
        return "\n".join([*self.lines, seen.out, seen.err, caplog.text])

    def assert_nothing_written(self) -> None:
        """No settings file and no temp leftovers in the project folder."""
        assert not self.dotenv.exists()
        assert self.top_level() == []


@pytest.fixture
def harness(setup_mod: ModuleType, tmp_path: Path) -> Harness:
    """A harness rooted in a fresh temp project folder."""
    return Harness(setup_mod, tmp_path)
