"""The one place a route reaches the ``Repository`` value from, and the
session id a direct run ledgers under.

Split out from ``app.py`` so routes can depend on it without importing the
app module that constructs them - a route file importing the app it is
registered into would be a cycle.
"""

from __future__ import annotations

from fastapi import Request

from memoria.repository import Repository


def get_repository(request: Request) -> Repository:
    """The ``Repository`` this app serves, resolved once at ``lifespan``.

    Never built here and never built in a route (#64's acceptance criteria:
    "no route builds a root") - ``app.create_app``'s ``lifespan`` is the one
    place that happens.
    """
    return request.app.state.repository


def get_session_id(request: Request) -> str:
    """The session this app's direct runs ledger under (ADR-0010), minted
    once at ``lifespan`` the way the stdio MCP server mints one per
    process: one server run is one session, and ``MEMORIA_SESSION_ID`` in
    the environment names it explicitly."""
    return request.app.state.session_id
