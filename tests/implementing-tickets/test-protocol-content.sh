#!/usr/bin/env bash
#
# Structural invariants over the implement-worker protocol + skill doctrine.
# Prose is behavior here: these asserts pin the load-bearing clauses so a
# future edit cannot silently drop the gate, resurrect the proposal block,
# or reintroduce retired vocabulary.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
# The skill IS the protocol: SKILL.md carries the Implement Worker Protocol
# (mirroring reviewing-prs); the operator doctrine lives in
# references/operation-manual.md; spawn goes through references/worker-bootstrap.md.
PROTO="$REPO_ROOT/skills/implementing-tickets/SKILL.md"
SKILL="$REPO_ROOT/skills/implementing-tickets/SKILL.md"
MANUAL="$REPO_ROOT/skills/implementing-tickets/references/operation-manual.md"
BOOTSTRAP="$REPO_ROOT/skills/implementing-tickets/references/worker-bootstrap.md"

FAILURES=0
pass() { echo "  [PASS] $1"; }
fail() { echo "  [FAIL] $1"; FAILURES=$((FAILURES + 1)); }
assert_contains() {
    if printf '%s' "$1" | grep -Fq -- "$2"; then pass "$3"; else
        fail "$3"; echo "    expected to find: $2"; fi
}
assert_not_contains() {
    if printf '%s' "$1" | grep -Fq -- "$2"; then
        fail "$3"; echo "    expected NOT to find: $2"; else pass "$3"; fi
}

echo "protocol content:"
[ -f "$PROTO" ] || { echo "missing $PROTO"; exit 1; }
proto="$(cat "$PROTO")"
assert_contains "$proto" "THE GATE comes before everything" "gate precedes everything"
assert_contains "$proto" "WELL-DEFINED" "check 1 named"
assert_contains "$proto" "WELL-SCOPED" "check 2 named"
assert_contains "$proto" "/../references/ticket-gate.md" "gate definitions route to the schema file (BOARD_SCRIPTS-relative)"
assert_not_contains "$proto" "internal naming" "fork taxonomy not re-vendored in the protocol"
assert_contains "$proto" "VERDICT IS YOUR FIRST BOARD WRITE" "verdict-first-write present"
assert_contains "$proto" "WHO UNPARKS IT" "park discriminant present"
assert_contains "$proto" "{{DECOMPOSE_DOC}}" "decompose procedure pointer present (runtime-opened)"
assert_contains "$proto" "FOLLOW-UPS: none" "follow-ups contract present"
assert_contains "$proto" "A follow-up not registered does not exist" "direct registration doctrine"
assert_contains "$proto" "doperpowers:issue-tracker" "registration routes through the issue-tracker skill"
assert_contains "$proto" "author its body at register time" "follow-up body is authored at register time"
assert_contains "$proto" "Closes #{{ISSUE_NUMBER}}" "merge-closes contract present"
assert_contains "$proto" "NO orchestrator" "no-orchestrator doctrine"
assert_contains "$proto" "EXECUTION (gate passed)" "execution doctrine lives inline in the protocol (no binding indirection)"
assert_contains "$proto" "A fork discovered mid-build" "post-gate park clause present"
assert_contains "$proto" "ASK EARLY" "ask-early clause present (no assumption-building past human-grade forks)"
assert_contains "$proto" "a pause, not a death" "park-pause doctrine present"
assert_contains "$proto" "IF RESUMED WITH ANSWERS" "answer-relay resume clause present"
assert_contains "$proto" "[gate] re-pass" "re-verdict guard present"
assert_contains "$proto" "CLOSING ARTIFACT" "PR body is the closing artifact (FD-7: no live workpad)"
assert_contains "$proto" "## Validation Evidence" "validation-evidence section mandated"
assert_contains "$proto" "## Confusions" "confusions section (conditional) mandated"
assert_contains "$proto" "ORIENTATION SUMMARY" "park orientation summary mandated"
assert_contains "$proto" "no live progress mirror" "no-mirror doctrine stated in the protocol"
assert_not_contains "$proto" "land on main independently" "landability criterion lives in the gate file, not the protocol"
assert_contains "$proto" "single home" "park discriminant routes to issue-tracker (single-source)"
assert_not_contains "$proto" "Knowledge work anyone could do" "needs-info definition not re-vendored in the protocol"
assert_contains "$proto" "doperpowers:reviewing-prs" "handoff to the review loop named"
assert_not_contains "$proto" '"ticket":' "the JSON proposal block is dead"
assert_not_contains "$proto" "→ blocked" "no retired blocked vocabulary"
assert_not_contains "$proto" "status:blocked" "no retired blocked label"

echo "placeholders:"
# The protocol keeps only the tokens its own clauses use; the worker reads
# its ticket and the repo-facts manifest itself (no inlined bodies).
want="{{BOARD_SCRIPTS}} {{DECOMPOSE_DOC}} {{ENGINE_NAME}} {{ISSUE_NUMBER}} {{ISSUE_URL}} {{REPO}}"
got="$(grep -o '{{[A-Z_]*}}' "$PROTO" | sort -u | tr '\n' ' ' | sed 's/ $//')"
if [ "$got" = "$want" ]; then pass "protocol placeholder set is exactly: $want"; else
    fail "protocol placeholder set drifted"; echo "    expected: $want"; echo "    actual:   $got"; fi

echo "skill-as-protocol shape:"
assert_contains "$proto" "name: implementing-tickets" "frontmatter survives on the protocol skill file"
assert_contains "$proto" "references/operation-manual.md" "operator-routing line points at the operation manual"
if [ -e "$REPO_ROOT/skills/implementing-tickets/references/implement-worker-protocol.md" ]; then
    fail "the old separate protocol file is retired (the skill IS the protocol)"
else
    pass "the old separate protocol file is retired (the skill IS the protocol)"
fi

echo "worker bootstrap:"
[ -f "$BOOTSTRAP" ] || { echo "missing $BOOTSTRAP"; exit 1; }
bootstrap="$(cat "$BOOTSTRAP")"
assert_contains "$bootstrap" "dispatcher-pinned copy" "bootstrap: protocol comes from the dispatcher-pinned file"
assert_contains "$bootstrap" "{{PROTOCOL_FILE}}" "bootstrap: dispatcher-owned protocol path token"
assert_contains "$bootstrap" "open it first and follow it" "bootstrap: protocol-before-work instruction"
assert_contains "$bootstrap" "{{ROLE}}" "bootstrap: one parameterized bootstrap for both lanes"
assert_not_contains "$bootstrap" "ISSUE_BODY" "bootstrap: no inlined ticket body (the worker reads its ticket via gh)"
assert_not_contains "$bootstrap" "REPO_FACTS" "bootstrap: no inlined repo-facts (the worker reads the manifest from its worktree)"
assert_not_contains "$bootstrap" "EXECUTION_BLOCK" "bootstrap: no execution-block binding (the doctrine lives in the protocol)"
want_boot="{{BOARD_SCRIPTS}} {{DECOMPOSE_DOC}} {{ENGINE_NAME}} {{ISSUE_NUMBER}} {{ISSUE_URL}} {{PROTOCOL_FILE}} {{REPO}} {{ROLE}}"
got_boot="$(grep -o '{{[A-Z_]*}}' "$BOOTSTRAP" | sort -u | tr '\n' ' ' | sed 's/ $//')"
if [ "$got_boot" = "$want_boot" ]; then pass "bootstrap placeholder set is exactly: $want_boot"; else
    fail "bootstrap placeholder set drifted"; echo "    expected: $want_boot"; echo "    actual:   $got_boot"; fi

echo "operation manual:"
[ -f "$MANUAL" ] || { echo "missing $MANUAL"; exit 1; }
manual="$(cat "$MANUAL")"
assert_contains "$manual" "SKILL.md" "manual: names the skill file as the protocol"
assert_contains "$manual" "worker-bootstrap.md" "manual: names the spawn bootstrap"
assert_contains "$manual" "repo-facts" "manual: repo-facts doctrine present"
assert_contains "$manual" "board-answer.sh" "manual: names the answer relay (park = pause)"
assert_contains "$manual" "doperpowers:issue-tracker" "manual: points at the board schema"
assert_not_contains "$manual" "status:blocked" "manual: no retired vocabulary"

echo "spike protocol:"
SPIKE="$REPO_ROOT/skills/implementing-tickets/references/spike-worker-protocol.md"
[ -f "$SPIKE" ] || { echo "missing $SPIKE"; exit 1; }
spike="$(cat "$SPIKE")"
# The brief/facts tails ride the bootstrap's binding sections for both lanes.
want_spike="{{BOARD_SCRIPTS}} {{ENGINE_NAME}} {{ISSUE_NUMBER}} {{ISSUE_URL}} {{REPO}}"
got_spike="$(grep -o '{{[A-Z_]*}}' "$SPIKE" | sort -u | tr '\n' ' ' | sed 's/ $//')"
if [ "$got_spike" = "$want_spike" ]; then pass "spike placeholder set is exactly: $want_spike"; else
    fail "spike placeholder set drifted"; echo "    expected: $want_spike"; echo "    actual:   $got_spike"; fi
assert_contains "$spike" "DRAFT" "spike: evidence PR is draft-only"
assert_not_contains "$spike" "{{EXECUTION_BLOCK}}" "spike: no engine execution block (exploration, not TDD)"
assert_contains "$spike" 'NEVER "Closes #{{ISSUE_NUMBER}}"' "spike: Closes is forbidden"
assert_contains "$spike" 'needs-human "findings ready:' "spike: findings-ready handoff park"
assert_contains "$spike" "terminal states" "spike: terminal states stay the human's"
assert_contains "$spike" "[findings]" "spike: structured findings comment mandated"
assert_contains "$spike" "doperpowers:issue-tracker" "spike: graduation registration routes through the issue-tracker skill"
assert_contains "$spike" "author its body at register time" "spike: graduated ticket body authored at register time"
assert_not_contains "$spike" "no exploring" "spike: the decompose verdict states its deliverable, not an exploration ban"

echo "decompose procedure (runtime-opened):"
DECOMP="$REPO_ROOT/skills/implementing-tickets/references/implement-decompose.md"
[ -f "$DECOMP" ] || { echo "missing $DECOMP"; exit 1; }
decomp="$(cat "$DECOMP")"
assert_contains "$decomp" "a chain IS" "decompose doc: serialization-as-edges present"
assert_contains "$decomp" "## Roadmap" "decompose doc: JIT roadmap escape hatch present"
assert_contains "$decomp" "NO code" "decompose doc: write-no-code clause present"
assert_contains "$decomp" "grants no authority beyond your prompt" "decompose doc: no-extra-authority framing"
assert_not_contains "$decomp" "{{" "decompose doc: placeholder-free (opened at runtime, never rendered)"

echo "execution doctrine (inline — no engine-blocks indirection):"
# One harness, one doctrine: both model routes (gateway "codex" / plain
# "claude") are Claude-harness sessions, and the execution text lives in
# the protocol's own Execution section.
if [ -e "$REPO_ROOT/skills/implementing-tickets/references/engine-blocks" ]; then
    fail "engine-blocks dir is retired (execution doctrine lives in the protocol)"
else
    pass "engine-blocks dir is retired (execution doctrine lives in the protocol)"
fi
assert_contains "$proto" "EXECPLAN:" "execution: execplan mode wired (not bare PLAN)"
assert_contains "$proto" "doperpowers:execplan" "execution: routes to the execplan doctrine"
assert_not_contains "$proto" ".agents/skills" "execution: no vendored-doctrine pointer (plugin skills resolve natively on the Claude harness)"
assert_not_contains "$proto" "work ALONE" "execution: no blanket work-alone constraint (subagents are the worker's call)"
assert_not_contains "$proto" "YOURSELF" "execution: no solo-execution emphasis (delegation inside the thread is the worker's call)"
assert_contains "$proto" "writing-plans" "execution: names writing-plans as interactive-only"
assert_contains "$proto" "subagent-driven-development" "execution: names the forbidden interactive skills"
assert_contains "$proto" "claim completion on reasoning alone" "execution: no-evidence-no-done clause"
assert_contains "$proto" "big-but-atomic" "execution: atomic execplan trigger"

echo "skill doctrine:"
[ -f "$SKILL" ] || { echo "missing $SKILL"; exit 1; }
skill="$(cat "$SKILL")"
assert_contains "$skill" "name: implementing-tickets" "frontmatter name"
assert_contains "$skill" "doperpowers:issue-tracker" "skill points at the board schema"
assert_not_contains "$skill" "status:blocked" "no retired vocabulary in doctrine"
assert_not_contains "$skill" ".agents/skills" "skill: no vendored-doctrine pointer (one Claude harness, plugin skills native)"

echo "dispatch ritual (issue-tracker):"
TRACKER="$REPO_ROOT/skills/issue-tracker/SKILL.md"
[ -f "$TRACKER" ] || { echo "missing $TRACKER"; exit 1; }
tracker="$(cat "$TRACKER")"
assert_not_contains "$tracker" "codex-spawn.sh" "ritual: codex-CLI spawn path retired (no new codex-CLI workers)"
assert_contains "$tracker" "DAEMON_CLAUDE_SETTINGS" "ritual: gateway route rides daemon-spawn via settings env"
assert_contains "$tracker" "daemon-spawn.sh" "ritual: one spawn command for both routes"
assert_contains "$tracker" "model route" "ritual: engine resolution states route semantics"
assert_contains "$tracker" "worker-bootstrap.md" "ritual: renders the bootstrap, not the protocol"
assert_not_contains "$tracker" "embedded verbatim" "ritual: verbatim-embed spawn retired"
assert_not_contains "$tracker" "implement-worker-protocol.md" "ritual: no reference to the retired protocol file"

echo "ticket gate (schema file, single copy):"
GATE="$REPO_ROOT/skills/issue-tracker/references/ticket-gate.md"
[ -f "$GATE" ] || { echo "missing $GATE"; exit 1; }
gate="$(cat "$GATE")"
assert_contains "$gate" "WELL-DEFINED" "gate: check 1 canonical here"
assert_contains "$gate" "WELL-SCOPED" "gate: check 2 canonical here"
assert_contains "$gate" "protocol violation, not caution" "gate: mechanical forks are the worker's (parking them is the violation)"
assert_contains "$gate" "never the worker's call" "gate: minor-taste rule canonical here"
assert_contains "$gate" "big-but-ATOMIC" "gate: atomic-counts-as-one-unit sizing canonical here"
assert_contains "$gate" "land on main independently" "gate: landability decompose criterion canonical here"
assert_contains "$gate" "recommendation, never inherited trust" "gate: registrar verdicts are recommendations (gate re-runs)"
assert_contains "$gate" "The human is a source too" "gate: human-as-async-answer-source clause carried over"
assert_not_contains "$gate" "{{" "gate: placeholder-free (opened at runtime, never rendered)"
assert_contains "$tracker" "ticket-gate.md" "tracker: ready-for-agent row names its bar (the gate file)"
assert_contains "$manual" "ticket-gate.md" "manual: gate section routes to the schema file"
assert_not_contains "$manual" "one obvious best answer" "manual: fork table not re-vendored"
assert_contains "$spike" "ticket-gate.md" "spike: graduation bar routes to the gate file"
assert_contains "$decomp" "ticket-gate.md" "decompose doc: child triage bar routes to the gate file"

echo "board schema single-source (issue-tracker owns the discriminant):"
assert_contains "$tracker" "Park discriminant — who unparks it?" "tracker: canonical discriminant lives here"
assert_contains "$tracker" "recommended answer" "tracker: needs-human note contract (question list with recommendations)"
assert_contains "$tracker" "ENUMERABLE" "tracker: enumerable-decisions→needs-human rule is canonical here"
assert_contains "$tracker" "Waiting on other tickets" "tracker: dependency-wait is not a park (edges + ready-for-agent)"
assert_contains "$tracker" "which no park state does" "tracker: sweep rationale recorded (why edges beat park states)"
assert_contains "$tracker" "instead of registering a duplicate" "tracker: pre-register duplicate search in the ticket contract"
daemons="$(cat "$REPO_ROOT/skills/orchestrating-daemons/SKILL.md")"
assert_contains "$daemons" "discriminant in doperpowers:issue-tracker" "daemons: discriminant pointer targets the schema owner"
assert_not_contains "$daemons" "discriminant in doperpowers:implementing-tickets" "daemons: no stale pointer at the old vendored copy"
assert_contains "$decomp" "doperpowers:issue-tracker" "decompose doc: child gate-triage routes through the ticket contract"
assert_not_contains "$manual" "Knowledge work anyone could do" "manual: discriminant not re-vendored (routes to issue-tracker)"

echo "unattended sweep (dispatch is event/cron-driven, ritual unchanged):"
assert_contains "$proto" "review loop deliberately skips drafts" "proto: worker knows the consequence — a draft gets no reviewer (live shakedown finding)"
assert_contains "$tracker" "board-sweep.sh" "tracker: toolkit names the unattended tick"
assert_contains "$tracker" "references/sweep-setup.md" "tracker: arming doc routed"
assert_contains "$tracker" "implement-dispatch.sh" "tracker: ritual names its mechanical executable"
assert_contains "$tracker" "Running the ritual by hand stays valid" "tracker: manual dispatch stays a first-class path"
sweepdoc="$(cat "$REPO_ROOT/skills/issue-tracker/references/sweep-setup.md")"
assert_contains "$sweepdoc" "launchd" "sweep-setup: launchd user agent is the macOS path"
assert_contains "$sweepdoc" "TCC" "sweep-setup: the cron-context TCC hazard is named"
assert_contains "$sweepdoc" "issue-dispatch.yml" "sweep-setup: runner-day implement template named"
assert_contains "$sweepdoc" "land-on-approve.yml" "sweep-setup: runner-day land template named"
for tpl in "$REPO_ROOT/skills/implementing-tickets/references/issue-dispatch.yml" \
           "$REPO_ROOT/skills/reviewing-prs/references/land-on-approve.yml"; do
  tname="$(basename "$tpl")"
  tbody="$(cat "$tpl")"
  assert_contains "$tbody" "permissions: {}" "$tname: zero-permission job"
  assert_not_contains "$tbody" "uses: actions/checkout" "$tname: never checks out repo code"
  assert_not_contains "$tbody" ".title" "$tname: no title/body interpolation (injection surface)"
done

echo
if [ "$FAILURES" -gt 0 ]; then echo "$FAILURES test(s) FAILED"; exit 1; fi
echo "all tests passed"
