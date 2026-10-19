"""FastAPI application factory (thin HTTP layer)."""

from __future__ import annotations

import logging

from fastapi import FastAPI

from vidgen.api import (
    routes_audit,
    routes_auth,
    routes_batch_files,
    routes_batches,
    routes_templates,
)
from vidgen.api.container import AppDeps, build_container
from vidgen.api.errors import install_error_handlers
from vidgen.settings import Settings


def create_app(settings: Settings, *, deps: AppDeps | None = None) -> FastAPI:
    """Build the app from explicit settings; ``deps`` replaces adapters (tests)."""
    # HTTP client libraries log full URLs, and URLs can carry search text (personal data, C5).
    logging.getLogger("httpx").setLevel(logging.WARNING)
    app = FastAPI(title="Dynamic Video Generator", docs_url=None, redoc_url=None)
    app.state.container = build_container(settings, deps or AppDeps())
    install_error_handlers(app)

    @app.get("/health")
    def health() -> dict[str, str]:
        """Liveness probe; open to everyone."""
        return {"status": "ok"}

    for router in (
        routes_auth.open_router,
        routes_auth.protected_router,
        routes_templates.router,
        routes_audit.router,
        routes_batches.router,
        routes_batch_files.router,
        routes_batches.stats_router,
    ):
        # Mounted flat (not via include_router) so ``app.routes`` lists every endpoint and the
        # "every route needs a session" test can walk it.
        app.router.routes.extend(router.routes)
    return app
