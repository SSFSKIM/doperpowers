# case3 — answer key (never show to reviewers)

**Scenario.** A framework-free Python document service: `auth.py` (bearer token
to `Session` with user/tenant/role), `store.py` (one JSON file per document
under `data/<tenant>/`, strict name pattern, revision per save), `render.py`
(rows to csv/text), and `app.py` (handlers plus a hand-rolled router). The patch
adds an export API (`GET /exports/<name>` and a bulk `GET /exports/all`), moves
the repeated inline auth checks into `@authenticated` / `@admin_only`
decorators, adds conditional writes via `expected_revision`, and paginates the
document list.

**Seeded classes: L4, L2, L1.** `case3-b1` (L4) is the missing authorization on
a new path: `handle_export_all` walks every tenant's documents and returns their
contents, but carries `@authenticated` rather than `@admin_only`, so any member
of any tenant can read every other tenant's data — verified with the globex
member token against acme's documents. It looks guarded, which is the point; the
README route table says the route is admin only, and the sibling
`handle_list_tenants` in the same diff is correctly `@admin_only`. `case3-b2`
(L2) is the cross-file contract break: `store.save_document` now returns the
number of rows written instead of the new revision (its docstring says so), and
`handle_put_document` — which the same diff edits, to pass `expected_revision` —
still binds the result to `revision` and emits it as both the response revision
and the weak ETag, so a 3-row write to a revision-1 document answers
`revision: 3` while the store holds revision 2. Both values are ints, so nothing
complains. `case3-b3` (L1) is the pagination off-by-one: `last = first + limit`
is treated as the index of the final entry and sliced as `names[first:last + 1]`,
so each page carries `limit + 1` names and the boundary name repeats on the next
page (page 1 and page 2 both contain `delta` at limit=2).

**Baits (all correct and intentional).** (1) Rendering a document with no rows
turns a 409 error into a 200 with empty `content` — an error path converted to a
success path, which reads like a swallowed failure, but it is deliberate and is
stated in the handler docstring, the README and `intent.md` (clients were
treating the 409 as retryable and looping). Missing documents still 404. (2)
Every handler loses its inline `session = session_of(request)` / `return
UNAUTHORIZED` block, which reads as three deleted authentication guards; they
are fully re-established by the `@authenticated` and `@admin_only` decorators,
which resolve the session and pass it in. (3) The router is rewritten from an
if-chain into a `STATIC_ROUTES` table, which invites a shadowing complaint about
`/exports/all` versus `/exports/<name>`; static routes are matched first, the
reservation is documented in both the export docstring and the README, and a
document genuinely named `all` is still reachable through
`GET /documents/all?format=`.
