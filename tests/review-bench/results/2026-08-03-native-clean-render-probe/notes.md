# Native clean-review render probe

Question: what does the runtime render for a native review that finds
NOTHING? (Determines whether panel extraction can recognize a clean
finder deterministically.)

Method: trivial clean diff (pure additive helper) in a scratch repo;
`with-effort.mjs --effort low -- review --base main --wait`;
codex-cli 0.146.0, gpt-5.6-sol.

Result: free-form prose — header + "The new farewell helper is valid,
self-contained, and does not alter the existing greet behavior. No
functional defects were identified." No "Full review comments:" section,
no [P#] tags, NO stable phrasing. The structured renderer's
"No material findings." line never appears on the native path.

Consequence (spec 2026-08-03-codex-workflow-engine-design.md): panel
finders carry a format-only developer_instructions sentinel — end a
clean review with exactly "No material findings." — sweep included
(output convention, not a content lens). Extraction stays strict; the
unsentineled prose render is a committed FAILED fixture.
