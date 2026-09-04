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
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from memoria.ledger import session_id_from_env
from memoria.repository import Repository, from_env
from memoria.web.routes import router

# `ui/`'s build output, built to `static/` inside this package and
# gitignored there (docs/adr/0002-ui-is-a-react-client.md's "Layout"
# consequence: "build output gitignored into the package") - resolved
# relative to this file with no walk back out of the package, so it holds
# under a non-editable install too. Mounted only when it exists, so
# `create_app` still works with no `npm run build` having ever run - the
# API-only tests never need it - and README.md's one-command run gets a
# single process serving both the API and the client from one origin.
_UI_DIST = Path(__file__).resolve().parent / "static"


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
        # The session a direct run (ADR-0010) ledgers its model calls and
        # served text under - one per server process, the same rule the
        # stdio MCP server keeps (#13), and `MEMORIA_SESSION_ID` names it.
        app.state.session_id = session_id_from_env()
        yield

    app = FastAPI(
        title="Memoria",
        # No auth, HTTPS or remote-access code (#64's acceptance criteria):
        # this app is served on localhost, one machine, per
        # docs/adr/0002-ui-is-a-react-client.md and poc-plan.md §5.
        lifespan=lifespan,
    )
    app.include_router(router, prefix="/api")
    if _UI_DIST.is_dir():
        # The hashed JS/CSS bundle serves as plain static files...
        app.mount("/assets", StaticFiles(directory=_UI_DIST / "assets"), name="ui-assets")

        # ...but every other path - "/", "/sources/SRC-000184", anything
        # React Router owns - has no file on disk of its own, so it falls
        # back to `index.html` and the client resolves the route. This is
        # the SPA fallback `StaticFiles(html=True)` does not provide by
        # itself: it 404s a path with no matching file or directory rather
        # than serving the app shell for it. Registered after the API
        # router, so an unmatched `/api/...` path still 404s as an API
        # error rather than being served the app shell.
        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa_fallback(full_path: str) -> FileResponse:
            # An unmatched `/api/...` path is a real 404, not a client
            # route to hand the app shell to - otherwise a typo'd or
            # removed endpoint would come back 200 with HTML and confuse
            # whatever called it far more than a clean 404 would.
            if full_path.startswith("api/"):
                raise HTTPException(status_code=404, detail=f"no such route: /{full_path}")
            return FileResponse(_UI_DIST / "index.html")

    return app
