# PR #43 dogfood loop — three panel rounds over the fix campaign

The code-review panel workflow reviewing its own PR (base `main` @ 6765c244),
run after each fix wave. Command per round:

    workflow --script skills/codex-companion/workflows/code-review.mjs \
      --args '{"base":"main"}' --cwd <branch worktree>

| round | HEAD reviewed | verdict | findings | agents | duration |
|-------|--------------|---------|----------|--------|----------|
| 1 (`wf-msdiwn5d-867muh`) | ec2c2669 (v7.37.0 release tip) | incorrect | 17 (11 P1) | 8 | 22.5 min |
| 2 (`wf-msdooldi-76t1t2`) | 1be1794d (after 5 fix waves) | incorrect | 18 (9 P1) | 7 | 22.4 min |
| 3 (`wf-msdrar6d-vh70jn`) | cf5771fb (after round-2 waves) | **interrupted** | 18 attached (13 P1) | 8 | 20.7 min |

Round 3's `interrupted` is the head-drift gate (added in round 2) firing
correctly: a docs commit (`aae0d81e`) landed on the branch mid-run, the
assembly re-resolution caught it, and the verdict was withheld with findings
attached as partial evidence — an accidental live validation of the gate.

Trajectory: round 1's findings were load-bearing (shell injection, path
traversal, mid-turn hangs, false-clean extraction, group-kill on pid reuse).
Round 2's were overwhelmingly against round-1 fix code. Round 3's are
overwhelmingly against round-2 fix code and are narrower still — TOCTOU
windows between lease/ledger writes, exit-drain ordering refinements,
fingerprint-completeness nits — plus re-flags of two limitations already
accepted and documented (runtime code outside the fingerprint, ignored files
outside the fingerprint). The loop was stopped here by the predeclared rule:
a round that still confirms new P1s in the previous round's code means the
process is excavating an asymptote, not converging.

Round-3 findings are UNFIXED as of this note — they are the triage backlog
for a deliberate hardening pass, not silent debt: see round3-out.json.
Priority reading of that backlog: the cheap mechanical ones (workers.json
atomic write, `--` boundary on the merge-base call, handleExit draining
buffered responses before rejecting pending RPCs, completed-review salvage on
transport close) are worth a small wave; the generation/tombstone-shaped
ledger races deserve a designed pass over the job lifecycle rather than spot
fixes; the fingerprint-completeness items are candidates for accept+document.

Caveat for scoring use: rounds 2-3 reviewed a diff that includes the panel's
own extraction/verifier changes — the panel under test changed between
rounds. These runs are evidence about the fix campaign, not a stability
measurement (that is the still-tracked X1 stability re-run).
