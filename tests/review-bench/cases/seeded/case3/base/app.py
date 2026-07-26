"""The request handlers and the router. No framework: Request in, Response out."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import auth
import render
import store


@dataclass(frozen=True)
class Request:
    method: str
    path: str
    query: Dict[str, str] = field(default_factory=dict)
    headers: Dict[str, str] = field(default_factory=dict)
    body: Optional[dict] = None


@dataclass(frozen=True)
class Response:
    status: int
    body: dict


UNAUTHORIZED = Response(401, {"error": "unauthorized"})
FORBIDDEN = Response(403, {"error": "admin only"})


def session_of(request: Request) -> Optional[auth.Session]:
    return auth.session_for(auth.bearer_token(request.headers))


def handle_list_documents(request: Request) -> Response:
    """GET /documents — the caller's own documents."""
    session = session_of(request)
    if session is None:
        return UNAUTHORIZED
    return Response(200, {"documents": store.list_documents(session.tenant)})


def handle_get_document(request: Request, name: str) -> Response:
    """GET /documents/<name> — one document, optionally rendered."""
    session = session_of(request)
    if session is None:
        return UNAUTHORIZED

    try:
        document = store.load_document(session.tenant, name)
    except store.BadDocumentName as exc:
        return Response(400, {"error": str(exc)})
    if document is None:
        return Response(404, {"error": "no such document"})

    fmt = request.query.get("format")
    if fmt is None:
        return Response(
            200,
            {
                "name": document.name,
                "revision": document.revision,
                "rows": document.rows,
            },
        )

    if fmt not in render.FORMATS:
        return Response(400, {"error": "format must be one of: %s" % ", ".join(render.FORMATS)})
    if not document.rows:
        return Response(409, {"error": "document has no rows to render"})
    return Response(
        200,
        {
            "name": document.name,
            "revision": document.revision,
            "content": render.render(document.rows, fmt),
        },
    )


def handle_put_document(request: Request, name: str) -> Response:
    """PUT /documents/<name> — replace the rows and bump the revision."""
    session = session_of(request)
    if session is None:
        return UNAUTHORIZED

    body = request.body or {}
    rows = body.get("rows")
    if not isinstance(rows, list):
        return Response(400, {"error": "rows must be a list"})

    try:
        revision = store.save_document(session.tenant, name, rows)
    except store.BadDocumentName as exc:
        return Response(400, {"error": str(exc)})

    return Response(200, {"name": name, "revision": revision, "etag": 'W/"%d"' % revision})


def handle_list_tenants(request: Request) -> Response:
    """GET /admin/tenants — every tenant on this node."""
    session = session_of(request)
    if session is None:
        return UNAUTHORIZED
    if session.role != auth.ADMIN:
        return FORBIDDEN
    return Response(200, {"tenants": store.list_tenants()})


def handle(request: Request) -> Response:
    """Route a request to its handler."""
    parts: List[str] = [part for part in request.path.split("/") if part]

    if request.method == "GET" and parts == ["documents"]:
        return handle_list_documents(request)
    if request.method == "GET" and parts == ["admin", "tenants"]:
        return handle_list_tenants(request)
    if len(parts) == 2 and parts[0] == "documents":
        if request.method == "GET":
            return handle_get_document(request, parts[1])
        if request.method == "PUT":
            return handle_put_document(request, parts[1])

    return Response(404, {"error": "no such route"})
