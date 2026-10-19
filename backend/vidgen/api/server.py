"""The deployable ASGI app: the API served under ``/api`` (DD-21).

Run it with ``uvicorn vidgen.api.server:create_server_app --factory``. The existing
``create_app`` is unchanged; this module only mounts it below ``/api``, so nothing of the API
answers at the root and a browser can load single-page-app routes (``/batches/...``) there.
"""

from __future__ import annotations

from fastapi import FastAPI

from vidgen.api.app import create_app
from vidgen.api.container import AppDeps
from vidgen.logging import configure_logging
from vidgen.settings import Settings, get_settings

API_PREFIX = "/api"


def create_server_app(settings: Settings | None = None, deps: AppDeps | None = None) -> FastAPI:
    """Build the API app and mount it at ``/api``; settings default to the environment."""
    configure_logging()  # JSON logs; the uvicorn access log loses its query strings (C5)
    server = FastAPI(title="Dynamic Video Generator server", docs_url=None, redoc_url=None)
    server.mount(API_PREFIX, create_app(settings or get_settings(), deps=deps))
    return server
