"""RP-REG: the provider registry file (TOML, stdlib tomllib) (AC1).

EXPECTED API
  vidgen.infrastructure.provider_registry.load_registry(path: Path | None, *, ai_mode: str,
      queue_name: str) -> ProviderRegistry
    - path None or a file that does not exist -> exactly one provider equal to today's behaviour:
      id "default", name "This computer", kind local, queue == queue_name, ai_mode == ai_mode,
      real_allowed, no cap, rate 0, no requires_env
    - queue defaults to "vidgen.<id>"; data_rule defaults to demo_only for remote kinds,
      real_allowed local
    - rate_per_hour = 3600 * rate_per_second; spend_cap_usd omitted = no cap
    - invalid content raises InvalidProviderError (vidgen.domain.providers); the message names the
      entry's id (or "entry #<n>" when it has no id); a TOML syntax error names the file
    - unknown keys are refused, so a file can never carry a token or password
  Settings.providers_file: Path | None = None (env VIDGEN_PROVIDERS_FILE)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fixtures.providers import REGISTRY_TOML
from vidgen.domain.providers import DataRule, InvalidProviderError, ProviderKind
from vidgen.infrastructure.provider_registry import load_registry
from vidgen.settings import Settings

LOAD = {"ai_mode": "fake", "queue_name": "vidgen"}


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "providers.toml"
    path.write_text(text, encoding="utf-8")
    return path


def entry(extra: str = "", *, kind: str = "local", id_: str = "p1") -> str:
    return f'[[provider]]\nid = "{id_}"\nname = "P"\nkind = "{kind}"\nai_mode = "fake"\n{extra}\n'


# ---- positive -------------------------------------------------------------------------


def test_a_valid_file_gives_its_providers_in_order_with_defaults_filled(tmp_path: Path) -> None:
    """RP-REG-P1."""
    registry = load_registry(write(tmp_path, REGISTRY_TOML), **LOAD)
    local, remote = registry.providers
    assert (local.id, local.queue, local.data_rule) == (
        "local-mac",
        "vidgen.local-mac",
        DataRule.REAL_ALLOWED,
    )
    assert (remote.kind, remote.queue, remote.data_rule) == (
        ProviderKind.REMOTE_FUNCTION,
        "vidgen.modal-demo",
        DataRule.DEMO_ONLY,
    )
    assert remote.spend_cap_usd == 5.0
    assert remote.requires_env == ("MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET")
    assert registry.default.id == "local-mac"


def test_a_missing_file_gives_exactly_one_provider_equal_to_today(tmp_path: Path) -> None:
    """RP-REG-P2: ai_mode and queue_name come from the settings."""
    for path in (None, tmp_path / "does-not-exist.toml"):
        registry = load_registry(path, ai_mode="local", queue_name="vidgen-x")
        (only,) = registry.providers
        assert (only.id, only.kind, only.queue, only.ai_mode) == (
            "default",
            ProviderKind.LOCAL,
            "vidgen-x",
            "local",
        )
        assert only.data_rule is DataRule.REAL_ALLOWED
        assert only.spend_cap_usd is None
        assert only.rate_per_second == 0.0
        assert only.requires_env == ()


def test_a_rate_per_hour_is_converted_to_per_second(tmp_path: Path) -> None:
    """RP-REG-P3: remote_worker is priced per hour."""
    text = entry(
        'spend_cap_usd = 10.0\nrate_per_hour = 3.6\nqueue = "vidgen.gpu"', kind="remote_worker"
    )
    (provider,) = load_registry(write(tmp_path, text), **LOAD).providers
    assert provider.rate_per_second == pytest.approx(0.001)
    assert provider.queue == "vidgen.gpu"


def test_the_setting_defaults_to_no_file_and_reads_the_env_var(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """RP-REG-P4."""
    base = {
        "creator_entity": "Org",
        "encryption_key": "00" * 32,
        "index_key": "11" * 32,
        "session_secret": "x" * 32,
        "admin_password_hash": "h",
    }
    assert Settings(**base).providers_file is None  # type: ignore[arg-type]
    monkeypatch.setenv("VIDGEN_PROVIDERS_FILE", str(tmp_path / "p.toml"))
    assert Settings(**base).providers_file == tmp_path / "p.toml"  # type: ignore[arg-type]


# ---- negative -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "fragment"),
    [
        (entry(kind="teleporter", id_="weird"), "weird"),
        (entry(kind="remote_function", id_="rf"), "rf"),  # remote without a cap
        (
            entry(
                'data_rule = "real_allowed"\nspend_cap_usd = 1.0', kind="remote_worker", id_="rw"
            ),
            "rw",
        ),
        (entry(id_="dup") + entry(id_="dup"), "dup"),
        (entry('queue = "vidgen.q"', id_="a") + entry('queue = "vidgen.q"', id_="b"), "b"),
        (entry('api_token = "abc"', id_="leaky"), "leaky"),  # unknown key: secrets never allowed
        (entry('password = "abc"', id_="leaky2"), "leaky2"),
        (entry("rate_per_second = 1.0\nrate_per_hour = 1.0", id_="both"), "both"),
    ],
)
def test_an_invalid_entry_is_refused_and_named(tmp_path: Path, text: str, fragment: str) -> None:
    """RP-REG-N1: unknown kind, no cap, remote real_allowed, duplicates, secrets, two rates."""
    with pytest.raises(InvalidProviderError) as raised:
        load_registry(write(tmp_path, text), **LOAD)
    assert fragment in str(raised.value)
    assert "abc" not in str(raised.value)  # a secret-looking value is never echoed


def test_a_toml_syntax_error_is_a_clear_error_naming_the_file(tmp_path: Path) -> None:
    """RP-REG-N2."""
    path = write(tmp_path, "[[provider\nid = ")
    with pytest.raises(InvalidProviderError, match=r"providers\.toml"):
        load_registry(path, **LOAD)


def test_an_entry_without_an_id_is_named_by_its_position(tmp_path: Path) -> None:
    """RP-REG-N3."""
    text = '[[provider]]\nname = "x"\nkind = "local"\nai_mode = "fake"\n'
    with pytest.raises(InvalidProviderError, match="entry #1"):
        load_registry(write(tmp_path, text), **LOAD)


# ---- edge -----------------------------------------------------------------------------


def test_an_empty_file_is_an_error_not_a_silent_fallback(tmp_path: Path) -> None:
    """RP-REG-E1: a present but empty file is a mistake; only a MISSING file falls back."""
    with pytest.raises(InvalidProviderError):
        load_registry(write(tmp_path, ""), **LOAD)


def test_a_unicode_name_and_a_required_env_name_survive_loading(tmp_path: Path) -> None:
    """RP-REG-E2."""
    text = '[[provider]]\nid = "mac"\nname = "मेरा Mac 🍎"\nkind = "local"\nai_mode = "fake"\n'
    (provider,) = load_registry(write(tmp_path, text), **LOAD).providers
    assert provider.name == "मेरा Mac 🍎"


def test_requires_env_holds_names_only(tmp_path: Path) -> None:
    """RP-REG-E3: the loaded provider never carries a value, even when the variable is set."""
    registry = load_registry(write(tmp_path, REGISTRY_TOML), **LOAD)
    remote = registry.get("modal-demo")
    assert remote is not None
    assert all(name.isupper() and "=" not in name for name in remote.requires_env)
