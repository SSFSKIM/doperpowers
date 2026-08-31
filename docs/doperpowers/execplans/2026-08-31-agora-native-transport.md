# agora v2 — native transport: messaging leaves the CLI

This ExecPlan is a living document maintained under the ExecPlan contract
vendored at `skills/execplan/references/PLANS.md`. It supersedes the transport
layer of `2026-08-27-agora.md` (the group layer of that plan — groups,
topology, board, views — carries forward unchanged in spirit).

## Purpose / Big Picture

Agora v1 built its own delivery machinery — per-member inbox files, cursors,
an `agora listen` tail that every member had to arm as a persistent Monitor —
because at design time the native cross-session `SendMessage` tool was judged
unrideable as a transport (no shell access, dual-write drift). Living with v1
surfaced the machinery's real costs: every agent had to remember to arm (and
re-arm) a listener or it was deaf; a dead listener failed silently; an armed
listener pinned the session at `state=working` forever, which forced the
`--no-wait` spawn rule and made harness status views lie.

A live probe run (2026-08-31, this repo's main session against a `--bg`
daemon) established that native SendMessage covers the whole delivery
problem: it wakes an idle session into a new turn, queues to a busy one, and
even revives a session whose process was killed — and `--bg` daemons appear
in ListAgents under their spawn name, so the daemon name IS the address.

After this change, agora owns only what the native tool lacks — named groups,
spawn topology, the alias→addr registry, and the durable communal board —
and every message between members rides `SendMessage`. The listener, inboxes,
cursors, `send`/`listen`/`log`, edge enforcement, and the `--no-wait` rule
are gone (net −339 lines).

## Progress

- [x] (2026-08-31) Feasibility probes, run live from the main session:
  ListAgents lists a `--bg` daemon under its spawn name (`bg · idle`);
  SendMessage to it while idle woke it within seconds (witness file + reply
  round-trip); a SendMessage to the same name after `kill` of its process
  revived the session and delivered ("DEAD-TEST-RECEIVED" reply from a fresh
  socket). Same-user local sessions needed no inbound-approval configuration.
- [x] (2026-08-31) CLI slimmed (commit 827e7d27): `send`/`listen`/`log`,
  inboxes, cursors, unread counts, off-edge marking removed; nodes gain
  `addr` (SendMessage target, default = alias; `--addr` for interactive
  sessions whose harness name differs); `post` prints the other members'
  addrs as the nudge list; removed commands refuse with a pointer at
  SendMessage. Preamble and SKILL.md rewritten (no arming, no `--no-wait`).
  29 test assertions green, shell lint clean.
- [x] (2026-08-31) Live fleet proof on the new protocol: main session joined
  as `orchestrator` (`--addr doperpowers-b7`), spawned `scout-native`
  (sonnet) through the patched spawn path WITHOUT `--no-wait`. The blocking
  watcher returned normally (`state=done` — the v1 hang is structurally
  gone), scout resolved its parent's addr from `agora topology`, its direct
  SendMessage and its board-post nudge both arrived as
  `<cross-session-message>` events, and board post #1 rendered with
  branch/cwd snapshot intact. Probe daemon and dogfood group retired.
- [ ] Exit gate, review half: codex whole-branch review (gpt-5.6-sol,
  xhigh), findings verified, fix wave if warranted, fixes re-verified.
- [ ] Finish: version bump, execplan cross-links, PR.

## Surprises & Discoveries

- Observation: (probe, 2026-08-31) SendMessage to a session whose OS process
  was killed does not fail — the harness notes "messaging a new session for
  the first time under a previously used name" and revives the session from
  its transcript; the message is delivered to the revived process. This
  retires v1's strongest argument for durable inboxes (queue-for-dormant).
  Evidence: probe daemon `agora-msg-probe`, killed at socket 89717, replied
  "DEAD-TEST-RECEIVED" from socket 99157.
- Observation: (probe, 2026-08-31) The v1 `state=working` distortion is
  listener-caused, not daemon-caused: the same `--bg` spawn path with no
  Monitor armed shows `bg · idle` in ListAgents and lets the blocking spawn
  watcher return. The `--no-wait` rule was compensating for the listener.
- Observation: replies to a cross-session message arrive stamped
  `from-name="<session name>"` by the harness — transport-level sender
  identity that v1's self-reported `--from` never had. The masquerade
  warning now applies only to board posts (the one surface still stamped
  from a CLI flag).
- Observation: hooks cannot substitute for any of this: every Claude Code
  hook event either fires inside an active turn or (async events) fires
  while idle but cannot start a turn. Wake belongs to messages, not hooks —
  confirmed against the hooks reference before this design was chosen.

## Decision Log

- Decision: REVERSAL of v1's "file-based transport" decision. v1 rejected
  native SendMessage as transport because shell senders can't ride it and a
  dual-written log would drift. What changed: the probe results above
  (revival covers dormant members; names are stable addresses), plus the
  accumulated operational cost of the listener (arming ceremony, silent
  deafness, state distortion). The shell-sender gap is accepted: a terminal
  operator posts to the board or messages via any Claude session / Remote
  Control; scripts that must wake an agent can be built on `claude --resume
  -p` later if the need materializes.
- Decision: DMs are ephemeral and unlogged; the board is the group's only
  durable record. Rejected: dual-writing native messages into a group log
  (the drift v1 predicted is real — the CLI cannot see native traffic, so
  any log it kept would be the subset agents remembered to mirror, worse
  than no log).
- Decision: `addr` field on nodes, default = alias. Daemons spawned under
  their alias need nothing; an interactive session passes `--addr` with its
  harness name or is unreachable. Rejected: a separate alias→addr mapping
  command (the registry already is that mapping).
- Decision: soft-edge routing enforcement dropped entirely; the topology is
  information, and the preamble says "prefer your parent and children."
  With no CLI in the message path there is nothing to enforce at, and the
  repo's Golden Rule wants outcomes over gates anyway. The ⚡ off-edge
  visibility dies with the log; accepted.
- Decision: board notify becomes a poster-side SendMessage nudge (post
  prints the addr list). Rejected: keeping inboxes alive only for board
  markers (retains the whole listener problem for one marker type).
- Decision: removed commands (`send`/`listen`/`log`) refuse with a pointer
  at SendMessage rather than vanishing into "unknown command" — long-lived
  sessions still carry v1 preambles in their transcripts.

## Outcomes & Retrospective

(To be written at finish, after the exit gate.)
