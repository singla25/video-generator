"""Builders and doubles for the render-providers tests (docs/test-tree/render-providers.md).

Only fake providers: the ``fake`` ai_mode, made-up env var names and values, no network.
"""

from __future__ import annotations

from typing import Any

from vidgen.domain.providers import DataRule, Provider, ProviderKind

MODAL_ENV = {"MODAL_TOKEN_ID": "test-token-id", "MODAL_TOKEN_SECRET": "test-token-secret"}


def local_provider(**overrides: Any) -> Provider:
    """A valid local provider ("This Mac"); override any field."""
    fields: dict[str, Any] = {
        "id": "local-mac",
        "name": "This Mac",
        "kind": ProviderKind.LOCAL,
        "queue": "vidgen.local-mac",
        "ai_mode": "fake",
        "data_rule": DataRule.REAL_ALLOWED,
    }
    fields.update(overrides)
    return Provider(**fields)


def remote_provider(**overrides: Any) -> Provider:
    """A valid demo-only remote_function provider with a 5 USD cap and 0.001 USD per second."""
    fields: dict[str, Any] = {
        "id": "modal-demo",
        "name": "Modal (demo)",
        "kind": ProviderKind.REMOTE_FUNCTION,
        "queue": "vidgen.modal-demo",
        "ai_mode": "fake",
        "data_rule": DataRule.DEMO_ONLY,
        "spend_cap_usd": 5.0,
        "rate_per_second": 0.001,
        "requires_env": tuple(MODAL_ENV),
    }
    fields.update(overrides)
    return Provider(**fields)


REGISTRY_TOML = """
[[provider]]
id = "local-mac"
name = "This Mac"
kind = "local"
ai_mode = "fake"

[[provider]]
id = "modal-demo"
name = "Modal (demo)"
kind = "remote_function"
ai_mode = "fake"
spend_cap_usd = 5.0
rate_per_second = 0.001
requires_env = ["MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET"]
"""


class FakeQueueHeartbeats:
    """Per-queue heartbeat double: ``alive`` holds the queues with a running worker."""

    def __init__(self, alive: set[str] | None = None) -> None:
        self.alive: set[str] = set(alive or ())

    def beat(self, queue: str) -> None:
        """A worker on ``queue`` reports in."""
        self.alive.add(queue)

    def is_alive(self, queue: str) -> bool:
        """True while a worker is alive on ``queue``."""
        return queue in self.alive
