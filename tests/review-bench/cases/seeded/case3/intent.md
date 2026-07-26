# Exports, conditional writes, and auth as decorators

Three things the warehouse team and the desktop client have both been asking
for, plus the cleanup that makes them fit.

* **`GET /exports/<name>`** renders one of the caller's documents in `csv` or
  `text`, and **`GET /exports/all`** renders every document on the node in one
  response for the nightly warehouse loader. `all` is reserved as an export
  name; a document that really is called `all` is still reachable through
  `GET /documents/all?format=`.

* **Auth moves into decorators.** Every handler used to open with the same four
  lines resolving a session and returning 401. That is now `@authenticated`
  (session required) and `@admin_only` (session plus the admin role), and the
  session arrives as a handler argument instead of being fetched inside the
  body. Nothing about who may call what changes.

* **Conditional writes.** `PUT /documents/<name>` accepts an
  `expected_revision`: the revision the client believes it is replacing, or `0`
  to require that the document is new. A mismatch is a 409 and nothing is
  written, which is what the desktop client needs to stop clobbering edits made
  in another window. `save_document` now reports how many rows it stored rather
  than the resulting revision — the writer already knows which revision it is
  replacing, and anything that needs the current one reads it back with
  `load_document`.

* **The document list is paginated** with 1-based `page` and a `limit` capped at
  200. The largest tenant now has four thousand documents and the unpaginated
  list was the slowest endpoint we serve.

* **Empty documents export cleanly.** Rendering a document with no rows used to
  be a 409; clients read that as retryable and retried in a loop. An empty
  document is a legitimate export, so it is now a 200 with an empty `content`.

* **The router keeps a table** of fixed routes which is matched before any route
  with a variable segment, so `/exports/all` can never be swallowed by
  `/exports/<name>`.
