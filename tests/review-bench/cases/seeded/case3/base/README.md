# docsvc

A framework-free document service. A `Request` goes in, a `Response` comes out;
`app.handle` is the whole router. Nothing but the standard library.

## Modules

* `auth.py` — bearer tokens resolve to a `Session` carrying the caller's user,
  tenant and role (`member` or `admin`).
* `store.py` — documents live one JSON file per document under
  `data/<tenant>/<name>.json` and carry a revision that increments on save.
  Document names are validated against a strict pattern.
* `render.py` — turns document rows into `csv` or `text`.
* `app.py` — the request handlers and the router.

## Routes

| Route | Who | What |
|-------|-----|------|
| `GET /documents` | any session | names of the caller's own documents |
| `GET /documents/<name>` | any session | one document; `?format=csv\|text` renders it |
| `PUT /documents/<name>` | any session | replace the rows, bump the revision |
| `GET /admin/tenants` | admin only | every tenant on this node |

## Tenancy

A session may only ever touch its own tenant's documents. The tenant is taken
from the session, never from the request, and any route that can see across
tenants is an admin route.
