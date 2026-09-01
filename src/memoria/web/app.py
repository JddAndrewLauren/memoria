"""The FastAPI app: lifespan, dependency injection, and route registration.

ADR-0004: no module holds an open SQLite connection, because FastAPI runs
``def`` routes in a threadpool and a connection cannot cross threads -
``memoria.index.search`` already connects and closes per call. What *is*
resolved once is the ``Repository`` value itself, at ``lifespan``, and
injected into every route through ``get_repository`` - "no route builds a
root" (#64's acceptance criteria).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from memoria.repository import Repository, from_env
from memoria.web.routes import router


def create_app(repository: Repository | None = None) -> FastAPI:
    """Build the app.

    ``repository``, when given, is used as-is rather than discovered - what
    lets a test serve a ``tmp_path`` repository without an environment
    variable or a real ``pyproject.toml`` to walk up to. Left ``None`` (the
    default, and what a real run uses), the app discovers it from the
    environment at ``lifespan``, the same as the MCP server's ``main()``.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.repository = repository if repository is not None else from_env()
        yield

    app = FastAPI(
        title="Memoria",
        # No auth, HTTPS or remote-access code (#64's acceptance criteria):
        # this app is served on localhost, one machine, per
        # docs/adr/0002-ui-is-a-react-client.md and poc-plan.md §5.
        lifespan=lifespan,
    )
    app.include_router(router, prefix="/api")
    return app
