"""Fixtures that build the FastAPI app with explicit settings and test doubles.

Contract used by every API test:
- ``create_app(settings, *, deps=AppDeps(clock=..., speech_to_text=..., video_probe=...,
  storage=...))``; ``AppDeps`` fields default to the real adapters when left as ``None``.
- Session cookie ``vidgen_session`` (HttpOnly, SameSite=strict), CSRF cookie ``vidgen_csrf``
  and header ``X-CSRF-Token`` (double submit). Settings gain ``cookie_secure`` (default True),
  ``session_ttl_minutes`` (480) and ``session_version`` (1).
- The word to replace is per template: ``original_name`` (the spoken voter name, e.g.
  "Krishan"), a required field of the template upload.
- Keys in settings are hex strings of 32 bytes.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from argon2 import PasswordHasher
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine

from tests.fixtures.doubles import FakeClock, FakeSpeechToText, FakeVideoProbe, InMemoryStorage
from vidgen.api.app import create_app
from vidgen.api.deps import AppDeps
from vidgen.settings import Settings

PASSWORD = "correct horse battery staple"  # noqa: S105 - test value, not a secret
HASHER = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)  # fast for tests


@dataclass
class Env:
    """The app, its client and every double, for one test."""

    app: FastAPI
    client: TestClient
    settings: Settings
    clock: FakeClock
    storage: InMemoryStorage
    probe: FakeVideoProbe
    stt: FakeSpeechToText
    csrf: dict[str, str]

    def login(self, password: str = PASSWORD) -> Any:
        """POST /auth/login and remember the CSRF header on success."""
        response = self.client.post("/auth/login", json={"password": password})
        if response.status_code == 200:
            self.csrf = {"X-CSRF-Token": response.json()["csrf_token"]}
        return response


def make_settings(db_url: str, tmp_path: Path, **overrides: Any) -> Settings:
    """Explicit fake settings: random keys, an argon2 hash of PASSWORD, the throwaway DB."""
    values: dict[str, Any] = {
        "creator_entity": "Test Creator Org",
        "encryption_key": SecretStr(secrets.token_hex(32)),
        "index_key": SecretStr(secrets.token_hex(32)),
        "session_secret": SecretStr(secrets.token_hex(32)),
        "admin_password_hash": SecretStr(HASHER.hash(PASSWORD)),
        "database_url": db_url,
        "storage_root": tmp_path / "media",
        "cookie_secure": False,
    }
    values.update(overrides)
    return Settings(**values)


EnvFactory = Callable[..., Env]


@pytest.fixture
def make_env(db: Engine, test_db_url: str, tmp_path: Path) -> EnvFactory:
    """Factory for an app with custom settings; ``login=False`` skips the initial login."""

    def factory(
        *, login: bool = True, raise_server_exceptions: bool = True, **settings_overrides: Any
    ) -> Env:
        settings = make_settings(test_db_url, tmp_path, **settings_overrides)
        clock, storage = FakeClock(), InMemoryStorage()
        probe, stt = FakeVideoProbe(), FakeSpeechToText()
        deps = AppDeps(clock=clock, speech_to_text=stt, video_probe=probe, storage=storage)
        app = create_app(settings, deps=deps)
        client = TestClient(app, raise_server_exceptions=raise_server_exceptions)
        env = Env(app, client, settings, clock, storage, probe, stt, csrf={})
        if login:
            assert env.login().status_code == 200
        return env

    return factory


@pytest.fixture
def env(make_env: EnvFactory) -> Env:
    """A logged-in environment with default settings."""
    return make_env()


@pytest.fixture
def anon(make_env: EnvFactory) -> Env:
    """An environment where nobody has logged in yet."""
    return make_env(login=False)
