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

## Concurrency

There is none, by construction. `docsvc` is a single-threaded, single-process
library: `app.handle` is called by one caller, one request at a time, and the
service ships no server, no thread pool, no `asyncio` loop and no `fork`.
Nothing else on the node writes `data/`. Every read-then-write sequence in
`store.py` therefore runs to completion with no other writer in existence, and
none of them takes a lock — deliberately. Introducing concurrent dispatch is a
change to this contract and would have to revisit those sequences first; until
then, treat "two concurrent requests" as a scenario this service cannot reach.
