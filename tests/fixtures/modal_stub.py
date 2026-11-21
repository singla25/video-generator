"""A recording stand-in for the ``modal`` package, to import ``backend/modal_app/app.py`` offline.

Decorators return the function unchanged and note its name and signature, so the tests can check
what the app defines without Modal installed. Nothing here touches the network.
"""

from __future__ import annotations

import importlib.util
import inspect
import sys
import types
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PIN_METHODS = ("pip_install", "uv_pip_install")


class _Anything:
    """Accepts any attribute or call and returns itself (Volume, Secret, env, ...)."""

    def __getattr__(self, name: str) -> Any:
        if name.startswith("__"):
            raise AttributeError(name)
        return self

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self


@dataclass
class Recorder:
    """What the app asked ``modal`` to do."""

    app_names: list[str] = field(default_factory=list)
    functions: dict[str, Callable[..., Any]] = field(default_factory=dict)
    pins: list[str] = field(default_factory=list)
    classes: list[type] = field(default_factory=list)
    gpu_requests: list[Any] = field(default_factory=list)
    image_steps: list[tuple[str, tuple[Any, ...]]] = field(default_factory=list)

    def signature(self, name: str) -> list[tuple[str, Any]]:
        """``(parameter name, default)`` pairs without ``self``; default is ``inspect._empty``."""
        params = inspect.signature(self.functions[name]).parameters
        return [(n, p.default) for n, p in params.items() if n != "self"]


class _Image(_Anything):
    def __init__(self, rec: Recorder) -> None:
        self._rec = rec

    def __getattr__(self, name: str) -> Any:
        if not name.startswith("__"):
            return self._step(name)
        return super().__getattr__(name)

    def _step(self, name: str) -> Any:
        """Record every image-chain call in order, then keep chaining."""
        if name in PIN_METHODS:

            def collect(*packages: Any, **_kw: Any) -> _Image:
                flat: list[Any] = []
                for item in packages:
                    flat.extend(item if isinstance(item, list | tuple) else [item])
                self._rec.pins.extend(str(p) for p in flat)
                self._rec.image_steps.append((name, tuple(packages)))
                return self

            return collect

        def other(*args: Any, **_kw: Any) -> _Image:
            self._rec.image_steps.append((name, args))
            return self

        return other


class _ImageFactory(_Anything):
    def __init__(self, rec: Recorder) -> None:
        self._rec = rec

    def __getattr__(self, name: str) -> Any:
        if name.startswith("__"):
            raise AttributeError(name)

        def start(*args: Any, **_k: Any) -> _Image:
            self._rec.image_steps.append((name, args))
            return _Image(self._rec)

        return start


class _App(_Anything):
    def __init__(self, rec: Recorder, name: str = "", **_kw: Any) -> None:
        self._rec = rec
        rec.app_names.append(name)

    def function(self, *_a: Any, **kw: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorate(fn: Callable[..., Any]) -> Callable[..., Any]:
            self._rec.functions[fn.__name__] = fn
            self._rec.gpu_requests.append(kw.get("gpu"))
            return fn

        return decorate

    def cls(self, *_a: Any, **kw: Any) -> Callable[[type], type]:
        def decorate(klass: type) -> type:
            self._rec.classes.append(klass)
            self._rec.gpu_requests.append(kw.get("gpu"))
            return klass

        return decorate

    def local_entrypoint(self, *_a: Any, **_k: Any) -> Callable[[Callable[..., Any]], Any]:
        return lambda fn: fn


def build_stub(rec: Recorder) -> types.ModuleType:
    """A module that looks enough like ``modal`` for the app source."""
    stub = types.ModuleType("modal")

    def method(*_a: Any, **_k: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorate(fn: Callable[..., Any]) -> Callable[..., Any]:
            rec.functions[fn.__name__] = fn
            return fn

        return decorate

    def identity_decorator(*_a: Any, **_k: Any) -> Callable[[Any], Any]:
        return lambda fn: fn

    stub.App = lambda name="", **kw: _App(rec, name, **kw)  # type: ignore[attr-defined]
    stub.Image = _ImageFactory(rec)  # type: ignore[attr-defined]
    stub.method = method  # type: ignore[attr-defined]
    for attribute in ("enter", "exit", "web_endpoint", "fastapi_endpoint", "concurrent"):
        setattr(stub, attribute, identity_decorator)
    stub.__getattr__ = lambda _name: _Anything()  # type: ignore[attr-defined]  # Volume, Secret
    return stub


@contextmanager
def stub_modal() -> Iterator[Recorder]:
    """Install the stub as ``modal`` for the ``with`` block and restore ``sys.modules`` after."""
    rec = Recorder()
    saved = sys.modules.get("modal")
    sys.modules["modal"] = build_stub(rec)
    try:
        yield rec
    finally:
        if saved is None:
            sys.modules.pop("modal", None)
        else:
            sys.modules["modal"] = saved


def load_app(path: Path) -> Recorder:
    """Import the app file under the stub and return what it registered (fresh import each time)."""
    with stub_modal() as rec:
        spec = importlib.util.spec_from_file_location("modal_app_under_test", path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        # inspect.getsource needs the module registered; always removed afterwards
        sys.modules[spec.name] = module
        try:
            spec.loader.exec_module(module)
        finally:
            sys.modules.pop(spec.name, None)
    return rec
