"""Fixtures for the worker tests."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import Engine

from tests.integration.worker.world import World, build_world

WorldFactory = Callable[..., World]


@pytest.fixture
def make_world(db: Engine) -> WorldFactory:
    """Factory for a fresh world on the (emptied) test database."""

    def factory(*args: Any, **kwargs: Any) -> World:
        return build_world(db, *args, **kwargs)

    return factory


@pytest.fixture
def world(make_world: WorldFactory) -> World:
    """A running batch with one row, 'Asha Verma' / 'A1'."""
    return make_world()
