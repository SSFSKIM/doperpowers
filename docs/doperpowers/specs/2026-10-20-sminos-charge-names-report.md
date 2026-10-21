# Report: sminos charge names — execution of the living spec

Spec: `docs/doperpowers/specs/2026-10-20-sminos-charge-names-design.md` (its Progress, Surprises, Decision Log and Outcomes & Retrospective are the full record; this report is the account of the run).
Branch: `worktree-sminos-charge-names`, unmerged, at the commit that adds this report (code final at 9283421c).
Commit range: `17cf35d6..HEAD` (merge base with main `862b23e6`).

## Status

DONE. All five milestones were reviewed clean, and the whole-branch review at medium (`doperpowers:reviewer-medium`) was run twice, with every finding fixed. The branch is left unmerged, as the brief asked.

## What was built

- **M1** (53f0b667, fix 6c54c52a). Derive's fork proposes a 2–4 word kebab charge name with the in-charge line, for an eligible member. Eligibility comes from the running engine record: a `derived`/`auto` name, or one of the member's own proposals. Details:
  - the name is checked before and after the fork;
  - it is validated, and recorded on the `in-charge` event as `name`;
  - it is handed over in `$SMINOS_HOME/names/<session>.json`;
  - `sminos name-due` answers whether the pending name is due;
  - `derive --all` sweeps stale pending files.

  M1 also built a `charge` name source; M4 removed it.
- **M2** (9386dbdc, fixes 5cfac89b, c4c1fda3). The name mod, first built on the `UserPromptSubmit` `sessionTitle` path. M5 reworked it.
- **M3** (4c8176ae, fix 2240f707). A former alias still reaches its member, with a `note: @old is now @new#short` on stderr. A current alias wins. Among former holders, the latest one wins. A retired member answers to none. sminos was bumped (now 1.6.0, see M5).
- **First branch review** (b1169e2d, d9dbbdb0):
  - `name-due` rechecks eligibility;
  - a former-alias seat hit binds its session;
  - the fix for cross-project `charge` provenance was dropped, because the owner then removed the `charge` source.
- **M4** (412f4690, 89aa7a11, fixes 35121486, b6378732), after two owner design changes on 2026-10-21:
  - derive runs for every member, owner-named ones included (line only, no naming);
  - `charge_of` order is `set` > `derived` > name > title;
  - there is no `charge` source;
  - the threshold is 10 tool calls in the main conversation;
  - the daemon runs `derive --all` every 5 minutes (measured: about 1 s for a run that refuses everyone on the MacBook's 39 projects);
  - first-timers go before refreshes, with at most 2 refreshes per daemon run;
  - a failed fork is held out of `--all` for an hour;
  - a re-derive is refused while the transcript is unchanged since the last line (owner request).
- **M5** (0524dcc0, fixes b308a87c, fda1210d, b25a53fa, 9283421c). The mod checks the pending file on a 15 s timer. When the session is between turns with no ask dialog up, it runs `name-due` and applies the name with the engine's own `/rename` (`$.command.run`), once per pending file text.
  - Measured on engine 2.1.306: interactive, `--bg` and SDK sessions (as MAWS launches them) all take the command, register it as `user`, and start no turn. So no `sessionTitle` fallback was built.
  - Its final gate reads only synchronous state after its last await: the dialog, through `ask.tsx`'s exported `isAskDialogUp()`; the turn generation; the session-end count; and whether the session id changed.
  - sminos is at 1.6.0.

## Validation evidence

- Full `ci-gate`, all 8 gates, GREEN on b53342d4: https://github.com/SSFSKIM/doperpowers/actions/runs/39574596249
- After that: `ci-gate --gates sminos,sminos-mods,mods-types` GREEN on b25a53fa (https://github.com/SSFSKIM/doperpowers/actions/runs/39581718592), and `--gates sminos-mods,mods-types` GREEN on 9283421c (https://github.com/SSFSKIM/doperpowers/actions/runs/39583469659).
- Full `ci-gate` on 73e48988 (code identical to 9283421c plus the spec's last commit), 9 of 9 gates PASS: GREEN https://github.com/SSFSKIM/doperpowers/actions/runs/39583690608
- Local runs at the end:
  - core sminos suite: 2310 assertions passed (b25a53fa);
  - mods suite: 416 pass, 0 fail (9283421c);
  - `sminos/tests/mods/live-name-check.py` by hand: 6/6 on 9283421c. Checked: an idle session renamed as `user` with the meta row; no model turn started, observed on the bridge's stream; an owner's `/rename` is kept; `--bg` and SDK sessions renamed.
- Per-milestone RED/GREEN evidence and every command's output are in the SDE task reports under `.doperpowers/sde/2026-10-20-sminos-charge-names-design/` (gitignored; `task-1-report.md` … `task-5-report.md`).

## Reviews

- **Task reviews** (task-reviewer, sol/xhigh). Each milestone was reviewed clean after fixes.
  - M1: remote rows overrode a published source.
  - M2: a stale record read in the live check.
  - M3: a retired seat was reachable by a former alias.
  - M4: a serial batch delayed first derives. Also a Minor: dedup test.
  - M5: a dialog race, a throw path, and live-check fidelity; then a turn race in the awaited dialog read.
- **Branch review 1** (reviewer-medium): verdict "incorrect", 3 P2s. (a) and (c) were fixed; (b) was made moot by the design change.
- **Branch review 2** (reviewer-medium): verdict "incorrect", 3 P2s:
  - a turn starting during the first dialog read;
  - `/clear` during the check renaming the new session;
  - the idle check truncating timestamps to the second.

  All three were fixed in b25a53fa. The re-review confirmed all six await boundaries for turn and session changes, and found one more instance: the dialog opening during the final session-id read. It was fixed in 9283421c. I verified that fix by reading the final tick myself: nothing is awaited between the gate and the command, and the dialog is read synchronously from the ask's own state. I stopped the loop there rather than run a third round, since the class it kept finding is closed by construction.

## Unresolved review findings

None. Two deferrals:
- M2's Minor about the pre-existing `appeal.tsx` typecheck error under locally copied types: dismissed. The `mods-types` gate is GREEN, and the error comes from types laid by a session without the appeal tool.
- M4's Minor about fractional-second idle detection: fixed in b25a53fa, after branch review 2 raised it to P2.

## Integration notes

- **Version.** sminos on this branch is 1.6.0. `origin/main` is now 1.5.3. Merging main will conflict on that number in `sminos/.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json`. Keep 1.6.0 or higher, and check with `scripts/bump-version.sh --check`.
- The daemon's first run after install forks every member that has ≥10 tool calls and no derived line (9 on the MacBook at M4's measurement), one after another. The refresh cap does not limit first-timers.

## Decisions I made as controller (all in the spec's Decision Log)

- The `charge` relabel was made only from a running engine record. Later removed with the source.
- `name-due` is bounded at 10 s, as `who` is.
- If a main turn starts while `name-due` runs, its answer is dropped and the text left for the next idle tick. This is the one exception to "one attempt per file text".
- First-timers go before refreshes, and a daemon run is capped at 2 refreshes.
- The final gate of the tick is fully synchronous.

## Friction (for the dispatching session to log; the brief rules out `gh issue edit`)

- **Messages to the caller reach the main session.** A `doperpowers:task-executor` dispatched by this plan-executor that sends a mid-run message "to its caller" delivers it to the main session, not to the plan-executor. M4's and M5's mid-run messages did. Cost: the controller missed an instruction the coordinator gave M4 (the failed-fork hold) and learned of it from M4's report. The coordinator logged this in #304. The workaround used: executors put facts in their return.
- **A plan-executor waiting on its own subagents gets `[handback-send-enforce]` nudges.** When this controller ended a turn while an executor or reviewer ran (and even with a Monitor armed), the harness demanded the handback four times. The workaround: foreground `until …; do sleep; done` waits (each bounded at 10 minutes) on the subagent's report file or commit, which keep the turn open. Cost: a few dozen tool calls of waiting, and the risk of ending the run early. Check: dispatch a subagent from a plan-executor, end the turn, and see whether the nudge arrives.
- **The worktree-isolation guard is stricter than its message says.** It refused a Monitor script that used a shell variable for a path containing "GitHub" ("names git in a form too complex"). Reviewers reported refused read-only Python inspections and HOME-isolated helper checks. Workaround: plain single commands with absolute paths, scripts written to /tmp and run with a path argument.

## Residue

- **MAWS desk name resolution ignores former aliases.** The desk resolves names on its own side, so an `@old` typed at the desk does not reach a renamed session the way `sminos say` does. The spec scoped this out (M3).
- **Why derive forks time out at 120 s.** 27 of 28 fork failures on the MacBook, 2026-10-17 to 10-21, were timeouts (Surprises). The one-hour hold bounds the cost, but the cause (a large context rebuilding its prompt cache, say) is not established, and a timed-out fork gives no line or name.
- **The first daemon run after install can fork many first-timers serially** (9 on the MacBook), each up to 120 s, because the refresh cap does not apply to first lines. A cap or spread for first-timers on that first run may be wanted if it proves disruptive.
