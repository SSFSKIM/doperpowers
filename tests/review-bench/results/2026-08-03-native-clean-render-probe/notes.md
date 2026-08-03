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

---

## Round 2 — the line sentinel FAILED live; the marker finding PASSED

### Probe A (FAIL): sentinel as a final-message line

Question: does the shipped instruction — "If your review finds no issues, end
your final message with exactly this line (alone on its own line): No material
findings." — actually produce that line on the native review path?

Method: the full panel workflow on the same known-clean diff (additive
`farewell` helper), `--args '{"base":"main"}'`, codex-cli 0.146.0, gpt-5.6-sol.
The deriver correctly chose ZERO lenses, so the sweep alone reviewed the diff
carrying the sentinel in `developer_instructions`.

Result: **FAIL.** reviewText came back as free-form prose again — "The new
farewell helper is straightforward and behaves as intended..." — with no
sentinel line anywhere. Extraction classified the finder `extraction-failed`,
so a genuinely clean diff was reported `interrupted`.

Mechanism: a review turn renders reviewText from codex's own review pipeline.
"End your final message with X" addresses the agent-message channel, which the
review render does not come from. The instruction is not ignored — it simply has
no surface to land on. Note this failure is INVISIBLE to the mock: the mock
returns whatever reviewText the scenario names, so every unit test agreed with a
design the live path rejects.

### Probe B (PASS): sentinel as a marker FINDING

Rationale: the same `developer_instructions` channel demonstrably shapes
FINDINGS — `../2026-08-03-appserver-devinstr-probe/` had a LENSPROBE-7Q marker
finding added on demand. So the clean verdict was moved into the only vocabulary
the review render has.

Instruction now carried by every finder (sweep included):

    If and only if your review finds no material issues, report exactly one
    finding titled "NO-MATERIAL-FINDINGS" at the lowest priority, pointing at
    any changed file.

Method: identical — same repo, same diff, same models; run detached as
`CODEX_COMPANION_SESSION_ID=sentinelcheck2`
(journal: `~/.claude/doperpowers/codex-companion-sentinelcheck2/workflows/wf-mscq8kpg-241rp2/`).

Result: **PASS.** Deriver again chose 0 lenses; the sweep returned (verbatim,
committed as `../../../codex-companion/fixtures/review-texts/marker-clean.md`
— note it is `tests/codex-companion/fixtures/review-texts/marker-clean.md`):

    The change adds a straightforward farewell helper without affecting existing behavior.

    Review comment:

    - NO-MATERIAL-FINDINGS — /Users/new/.claude/jobs/b380b6da/tmp/cleanprobe/app.py:4-5
      No material correctness issues were found in the added helper.

Assembled result (`sentinelcheck2-result.json`): `verdict: "correct"`,
coverage `[{finder: "sweep", lens: null, status: "ok", stubs: 0}]`, 0 findings,
explanation "no confirmed findings (note: all finders returned zero findings —
verify the diff target is what you intended)".

Two details the hand-written fixture had guessed WRONG, now corrected from the
real bytes: the model emitted **no `[P#]` tag** on the marker (extraction's
untagged-finding default carries it), and wrote "Review comment:" rather than
"Full review comments:".

### Consequences

- `extract.mjs` recognizes the marker STUB: a finder whose parsed stubs are all
  markers ⇒ `{stubs: [], clean: true, failed: false}`. A marker BESIDE real
  findings ⇒ marker dropped, real findings kept (a mis-applied "if and only if"
  must never cost a real finding), and `clean` still requires the marker to have
  stood alone, so no false clean is reachable.
- The "No material findings." LINE check stays: the structured renderer
  (`render.mjs`) does emit it verbatim on its own path.
- Standing lesson: a render-shaping instruction must be validated against the
  channel that actually produces the artifact. Mock-level tests cannot falsify
  this class of design — only a live run can.
