"""Reads the render-provider registry from a TOML file (stdlib ``tomllib``).

The file holds no secrets: unknown keys are refused, so a token or password can never sit in it,
and ``requires_env`` only names environment variables. A missing file gives exactly one provider
equal to today's behaviour. Error messages name the entry and never echo values.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from vidgen.domain.providers import (
    SECONDS_PER_HOUR,
    DataRule,
    InvalidProviderError,
    Provider,
    ProviderKind,
    ProviderRegistry,
)

DEFAULT_ID = "default"
DEFAULT_NAME = "This computer"
TABLE_KEY = "provider"
QUEUE_PREFIX = "vidgen."
ALLOWED_KEYS = frozenset(
    {
        "id",
        "name",
        "kind",
        "queue",
        "ai_mode",
        "data_rule",
        "spend_cap_usd",
        "rate_per_second",
        "rate_per_hour",
        "requires_env",
    }
)


def load_registry(path: Path | None, *, ai_mode: str, queue_name: str) -> ProviderRegistry:
    """The registry from ``path``; no file means one provider built from today's settings."""
    if path is None or not path.exists():
        return ProviderRegistry([_fallback(ai_mode, queue_name)])
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError, OSError):
        raise InvalidProviderError(f"providers file {path.name} cannot be read as TOML") from None
    entries = data.get(TABLE_KEY, [])
    if set(data) - {TABLE_KEY} or not isinstance(entries, list):
        raise InvalidProviderError(f"providers file {path.name}: expected [[provider]] tables only")
    return ProviderRegistry([_provider(n, raw) for n, raw in enumerate(entries, start=1)])


def _fallback(ai_mode: str, queue_name: str) -> Provider:
    return Provider(
        id=DEFAULT_ID,
        name=DEFAULT_NAME,
        kind=ProviderKind.LOCAL,
        queue=queue_name,
        ai_mode=ai_mode,
        data_rule=DataRule.REAL_ALLOWED,
    )


def _typed(raw: dict[str, Any], key: str, kind: type | tuple[type, ...], label: str) -> Any:
    value = raw.get(key)
    if value is not None and (isinstance(value, bool) or not isinstance(value, kind)):
        raise InvalidProviderError(f"{label}: '{key}' has the wrong type")
    return value


def _provider(position: int, raw: Any) -> Provider:
    """One validated provider from a table; the message names its id or its position."""
    if not isinstance(raw, dict):
        raise InvalidProviderError(f"entry #{position}: expected a table")
    provider_id = raw.get("id")
    label = f"provider '{provider_id}'" if isinstance(provider_id, str) else f"entry #{position}"
    unknown = sorted(set(raw) - ALLOWED_KEYS)
    if unknown:
        raise InvalidProviderError(f"{label}: unknown key '{unknown[0]}' (not allowed)")
    if not isinstance(provider_id, str) or not provider_id.strip():
        raise InvalidProviderError(f"{label}: id is required")
    text = {k: _typed(raw, k, str, label) for k in ("name", "kind", "queue", "ai_mode", "data_rule")}
    cap = _typed(raw, "spend_cap_usd", (int, float), label)
    per_second = _typed(raw, "rate_per_second", (int, float), label)
    per_hour = _typed(raw, "rate_per_hour", (int, float), label)
    needs = _typed(raw, "requires_env", list, label) or []
    if per_second is not None and per_hour is not None:
        raise InvalidProviderError(f"{label}: give rate_per_second or rate_per_hour, not both")
    if not all(isinstance(item, str) for item in needs):
        raise InvalidProviderError(f"{label}: requires_env must list variable names")
    kind = text["kind"] or ProviderKind.LOCAL.value
    default_rule = DataRule.REAL_ALLOWED if kind == ProviderKind.LOCAL else DataRule.DEMO_ONLY
    rate = per_second if per_hour is None else per_hour / SECONDS_PER_HOUR
    return Provider(
        id=provider_id,
        name=text["name"] or provider_id,
        kind=kind,  # type: ignore[arg-type]  # coerced and validated by Provider
        queue=text["queue"] or f"{QUEUE_PREFIX}{provider_id}",
        ai_mode=text["ai_mode"] or "fake",
        data_rule=text["data_rule"] or default_rule,  # type: ignore[arg-type]
        spend_cap_usd=None if cap is None else float(cap),
        rate_per_second=0.0 if rate is None else float(rate),
        requires_env=tuple(needs),
    )
