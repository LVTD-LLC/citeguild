"""
ASGI config for citeguild project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/asgi/
"""

import os
from contextlib import asynccontextmanager

from django.core.asgi import get_asgi_application
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import RedirectResponse
from starlette.routing import Mount, Route

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "citeguild.settings")

django_application = get_asgi_application()

from apps.mcp_server.auth import McpAuthMiddleware  # noqa: E402
from apps.mcp_server.server import mcp, mcp_analytics  # noqa: E402

raw_mcp_application = mcp.http_app(path="/")
mcp_application = McpAuthMiddleware(raw_mcp_application)


def redirect_mcp(request: Request) -> RedirectResponse:
    return RedirectResponse(str(request.url.replace(path="/mcp/")), status_code=307)


@asynccontextmanager
async def application_lifespan(app):
    async with raw_mcp_application.lifespan(app):
        try:
            yield
        finally:
            if mcp_analytics is not None:
                await mcp_analytics.shutdown()


application = Starlette(
    routes=[
        Route("/mcp", endpoint=redirect_mcp, methods=["GET", "POST", "DELETE"]),
        Mount("/mcp", app=mcp_application),
        Mount("/", app=django_application),
    ],
    lifespan=application_lifespan,
)
