"""FastAPI application factory (thin HTTP layer)."""

from __future__ import annotations

from fastapi import FastAPI

from vidgen.api import routes_audit, routes_auth, routes_templates
from vidgen.api.container import AppDeps, build_container
from vidgen.api.errors import install_error_handlers
from vidgen.settings import Settings


def create_app(settings: Settings, *, deps: AppDeps | None = None) -> FastAPI:
    """Build the app from explicit settings; ``deps`` replaces adapters (tests)."""
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
    ):
        # Mounted flat (not via include_router) so ``app.routes`` lists every endpoint and the
        # "every route needs a session" test can walk it.
        app.router.routes.extend(router.routes)
    return app
