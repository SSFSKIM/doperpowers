# The panel: `present`, a richer form of a message

Under the `to-human` output style a session reaches its human only through
messages: Markdown text, one after another. That is right for routine
reports and wrong for two kinds of content. The first is what the human has
to read closely: a decision with its options, an architecture, the direction
of a design. Plain text carries these poorly, which is why a company's
executives ask for a document or a presentation before a high-stakes
decision instead of deciding from talk. The second is a body of findings
that keeps being revised through a large or complex piece of work: each
message amends the ones before it, and the human has to read the whole trail
to learn what holds now.

After this change a session has one more way to reach its human: its
**panel**, one HTML page per session, read in a browser. The session calls
one small tool, `mcp__to-human__present`, with a brief, and keeps working. A
forked copy of the session writes or edits the page in the background, and
the session is told when it is ready, so it can send the message that links
it. The page is edited in place and always states what holds now; where an
edit changes something the human has already seen, a small note sits at that
place, in the manner of a comment in Google Docs, and disappears for good
once the human checks it off.

To see it working: in a to-human session in a terminal, have the session
present something (a design with two options, say). A link of the form
`https://s.tail112c3f.ts.net:4777/b4d10f41/` arrives in a message a few
minutes later; it opens the page, from the machine the session runs on or
from any other device of the human's on their tailnet. Have the session change one of the options: the open page
reloads by itself, the changed place carries a note, and a click on the
note's check button removes it.

The human partner approved this design on 2026-11-13 from a prototype panel
that two forks of the designing session wrote
(`~/.local/share/present-panel/prototype/`, version 1 kept as
`panel.v1.html`), ruling: the panel is an optional extension of a message,
used only where it is distinctly more effective than text; agents compose it
freely, with no required structure; it stays compact and is edited in place;
changes show as notes with a check button and nothing else accumulates; it
is read in a browser on the Mac; a decision is answered through the existing
ask dialog; one small local server serves every panel on a machine, each
under its session's id; every machine's panels are reachable from the
MacBook over Tailscale; a shipped base (stylesheet, notes script, optional
blocks) shortens a fork's work without fixing a layout; `PANEL_LOCALE` sets
the page's language to English or Korean; and what is recent sits at the top
of a page, with older material pruned or moved to the bottom.

## Progress

- [x] (2026-11-14 01:30Z) Design approved from the prototype; engine trials dispatched.
- [x] (2026-11-14 03:05Z) Trials reported (Claude Code 2.1.325, haiku); spec written.
- [ ] Spec review and execution-section review absorbed.
- [ ] M1 — the panel server and the base.
- [ ] M2 — the tool and the fork.
- [ ] M3 — the rule, its evaluation, and the documents.
- [ ] Whole-branch review, retrospective, merge.

## Terms

- **Panel**: one HTML page a session keeps for its human, at most one per
  session, stored on the machine the session runs on.
- **Fork**: a subagent of type `fork`: a copy of the session that starts
  with the session's whole conversation and runs on the session's model. A
  plugin starts one with `$.agent.spawn({ subagentType: 'fork', ... })`; the
  sminos bridge's `manager query` is the existing example
  (`sminos/hooks/mods/bridge-ask.tsx`).
- **Brief**: the one input of the tool: what to put on the panel or change
  on it.
- **Standing prompt**: the fixed text the tool puts before the brief in the
  fork's prompt (`STANDING_PROMPT`, in Interfaces).
- **Note**: a short text anchored at a place on the page, saying what
  changed there and why. The human removes it with its check button.
- **Base**: the stylesheet, the script and the optional blocks the plugin
  ships and the server serves, which every panel links. It fixes how a panel
  looks and behaves, and nothing about what it holds or in what order.
- **Panel server**: one process per machine that serves every panel on it,
  the base, and the two things a page reports back (it was opened, a note
  was checked).
- **Short id**: the first 8 characters of a session's id, as sminos shows a
  session (`[b4d10f41]`); a panel's place in the server's addresses.
- **Address**: a panel's URL, `<origin>/<short id>/`, where the origin is
  the machine's tailnet one (`https://<tailnet name>:<port>`) when the
  server is exposed there, else `http://127.0.0.1:<port>`.
- **Tailnet**: the human's private Tailscale network, on which each of
  their machines has a name (`s.tail112c3f.ts.net` is the MacBook).
  `tailscale serve` has the machine's Tailscale daemon accept HTTPS on a
  port of that name, from the tailnet's devices only, and pass each request
  to a local port, adding the header `Tailscale-User-Login` with the login
  of the requesting device's user (none for a tagged device, which has no
  user). The session manager's page is served this way
  (`sminos/skills/manager/scripts/manager_serve.py`).
- **Configuration directory**: `CLAUDE_CONFIG_DIR`, else `~/.claude`.

## What the human sees

A message says something is on the panel and links it. The page opens in the
browser. It is about three screens long. At its top is what is new or what
awaits the human; older, settled material is gone, or sits at the bottom
folded behind a one-line summary. No two panels need look alike in
structure: one is a comparison of options under a "needs you" block, another
a diagram with a table of findings. They share type, spacing, colours and
the behaviour of notes.

When the session updates the panel, the open page reloads by itself. Each
place whose statement changed since the human last saw it carries a
highlighted phrase and, beside it in the margin (under it on a narrow
window), a note: what changed and why. The top of the page counts the notes
still open and jumps to the next. A click on a note's check button removes
the note and its highlight; it stays gone on reload and in every browser,
and the next update deletes it from the page's file. A page the human never
opened gets no notes: there is nothing they could have read differently.

The panel is read-only apart from the check buttons. A decision it lays out
is asked through the ask dialog (`mcp__sminos__AskUserQuestion`), whose
question points at the panel.

With `PANEL_LOCALE=ko` the page is written in Korean, its `lang` is `ko`,
and the base's own words (the count, the check button's label) are Korean.

## What the session does

The session calls `mcp__to-human__present` with `{ brief }`. The call
returns at once with the panel's address. Minutes later the session is told
the panel is written, with the address and the fork's two lines on what the
page now holds and what changed; it then sends the human the message that
links the page, and asks if a decision is due.

The rule for when to call it is one sentence, in the `to-human` output style
and in the human's own `CLAUDE.md` (`RULE`, in Interfaces): what the human
must read closely and plain text carries poorly goes on the panel, and a
message points to it; routine reports stay text. The rule is deliberately
narrow. Each call costs requests over the session's whole context (the
prototype's two runs: 147k and 154k tokens in the fork, at a parent context
near 100k), so a panel has to earn its call; and the human ruled that most
sessions should never need one.

## The design

### One tool, and why a fork writes the page

The tool is `mcp__to-human__present`, registered by the to-human plugin
beside the message tool, always loaded, with a one-line description
(`DESCRIPTION`); when to use it is the rule's business, as it is for the
message tool. Its input is one field.

The page is written by a fork of the session, not by the session itself and
not by a fresh subagent. Written by the session, a page would hold the
session for minutes and fill its context with HTML. A fresh subagent would
need the content restated in its prompt, which is the work the tool exists
to remove, and would lose detail in the restating. A fork holds the whole
conversation, so the brief only has to say what to present.

A fork a plugin starts from a tool's handler inherits the conversation up to
the call itself: the calling response's text and thinking, and the calls
made earlier in that response with their results (trial 3 in Surprises &
Discoveries). It does not see the call's own input, which is why the brief
is repeated in its prompt, or anything the session does after the call. So
a session can write its conclusion and call the tool in one response, and
the brief stays short.

### The fork's work

The tool's handler prepares the panel (below), then spawns the fork with the
standing prompt and the brief. The standing prompt says what the panel is
for and gives the fork the facts it cannot derive: the file to write, the
address, the language, the update's number, whether the human has opened the
page since its last update, which notes they checked off, the markup of a
note, and where the base's blocks are listed. Its rules are few, and each is
the human's ruling or a lesson of the prototype runs:

- Compose for the content; no section or order is required. Write content
  only, on the base.
- About three screens. The first prototype draft, told "a few scrolls", came
  out a third too long; a number prevents the overshoot. Without a browser
  the fork cannot measure a rendered height, so the prompt gives the measure
  it can check: 600 to 900 words with its figures.
- The body states what holds now, edited in place.
- What is new or awaits the human is at the top; what is older and settled
  is cut once it no longer serves, or moved to the bottom, folded behind a
  one-line summary. An explanation keeps its own order: the human's rule is
  about what they meet first, and an account of how something works, sorted
  by date, is harder to follow than one sorted by its logic.
- Where an edit changes what the human has seen, a note at that place. A
  note still unchecked whose statement changes again is replaced by one note
  carrying both steps. Notes the human checked are deleted from the file.
- Plain and legible is the design care expected. The prototype's fork loaded
  the `designer` skill, whose workflow is out of proportion for a panel.

The fork is held to reading, plus `Write` and `Edit` inside its panel's
directory (the guard, in Interfaces). The hold is needed, not a precaution.
A fork starts in the middle of the session's turn with the session's task
in its context, and goes on with it when nothing stops it: in the trials 4
of 6 forks (haiku) did the session's remaining work, re-running its
commands and calling the tool again, and a sentence in the prompt telling
them not to did not stop them; only a tool policy did (trial 3). The
standing prompt opens by saying the fork is not the session and does not
continue its task, as the sminos bridge's fork frame does (`ASK_FRAME`), and
the guard makes that true of everything but its words. The guard also keeps
every fork call from a permission prompt: with no hook deciding, the write
of a panel asks in the `default` and `acceptEdits` modes, because the
configuration directory is a protected location, and the fork blocks on a
dialog in the main session's pane (trial 2).

The guard is the plugin's own. A plugin's hooks run on the calls of a fork
it spawned, all but the one registration whose frame made the spawn (the
tool's handler), so the guard is registered apart from the handler; its
`tool.check` answer of allow overrides the protected-location ask and its
deny stands, with no prompt, in the `default`, `acceptEdits` and `auto`
modes (trial 2). It holds as long as no plugin outside to-human overrides
its answer; to-human is the outermost plugin by the owner's
`prependPlugins`.

One fork per session at a time. A call that arrives while a fork runs is
held, and when that fork ends the tool starts one more fork with every
brief held meanwhile; the session is told once, after the last. The other
way, delivering the brief to the running fork as a message
(`$.session.send`), is what the prototype's first run did by hand, and it
works while the fork still has a step to take. But a message that arrives
as the fork writes its last reply is not read: the engine then resumes the
fork for another turn, sends the main session a task notification nobody
asked for, and wakes it (trial 4). A second run costs minutes on the rare
occasion two calls overlap; it has no such window, and its fork starts from
the conversation as it then stands.

When the last fork ends, the session is told (`FINISHED`): the address and
the fork's last text. The engine sends no notification for a fork a plugin
started, neither into a running turn nor to an idle session (trial 1), so
the plugin tells the session itself: the fork's own `turn.complete` reaches
the plugin's hook with the fork's agent id and its final text, and the
plugin submits the notice as its prompt (`$.prompt.submit`), which the
engine runs as a turn once the session is idle, behind anything the human
queued, as it runs the compact mod's offer (`hooks/mods/compact.tsx`). A
fork that ended without changing `panel.html` is told as a failure
(`FAILED`), so the session does not link a page that is not there.

### The panel's files

Each panel is a directory under the configuration directory,
`to-human/panels/<short id>/`, beside the plugin's `dumps/` and `folds/`:

| File | Writer | What it holds |
|---|---|---|
| `panel.html` | the fork | The page: content, and the two lines that link the base. |
| `meta.json` | the server's `open-panel` command | `{ "session": "<full id>", "updates": <n>, "locale": "en" \| "ko" }` |
| `state.json` | the server | `{ "opened": <ms> \| null, "checked": ["<note id>", ...] }` |

The directory is named by the short id because the address is. Two sessions
whose ids share 8 characters would share a panel, so `open-panel` compares
`meta.json`'s `session` with the caller's and, on a mismatch, uses the first
12 characters instead (and so on by 4).

The server never writes `panel.html`, and the fork never writes the other
two: with one writer per file there is no lock. The human's check reaches
disk in `state.json` at once; the server hides the note in what it serves
from then on; the fork deletes the note's markup at its next edit, so the
file itself stays compact.

A panel untouched for 30 days is removed when a server starts, as the fold
summaries' files are.

### The base

`to-human/panel/base/` holds what every panel shares:

- `panel.css`: type, spacing, colours in light and dark
  (`prefers-color-scheme`), tables, `details`, and under `:lang(ko)` a Korean
  font stack with `word-break: keep-all` (the default breaks Korean inside a
  word).
- `panel.js`: draws each note at the height of its anchor in the margin, or
  under the anchor's block on a narrow window; gives it a check button; shows
  the count of open notes at the top with a jump to the next; reports a check
  to the server; reloads the page when the file changes, keeping the scroll
  position. Its words come in English and Korean, chosen by the page's `lang`.
- `starter.html`: a page with the two base links, a title and an empty body,
  which `open-panel` copies to a new panel so a fork edits a page instead of
  writing one from nothing.
- `README.md`: the note markup and the optional blocks, each with a three-line
  example, for the fork to read on a first write. Blocks: a "needs you" block,
  a callout, an option comparison, a diagram frame, a quoted wording block.

A note's markup is the base's, fixed, so every fork writes the same one and
the script can rely on it:

    <mark data-note="u3-1">the changed phrase</mark>
    <aside class="note" id="u3-1" data-label="Changed by your answer">What changed and why.</aside>

The id is `u<update number>-<k>`, so a note of a later update never takes the
id of one the human already checked. `data-label` is optional.

In the prototype 40% of the first page's bytes were styling and script, and
about a third of each run went to checking that the page rendered and its
notes worked. The base removes both from a fork's work: the first write took
8.4 minutes and an edit 4.7, each including that share. The human asked for
this as a template and ruled against a required structure in the same
exchange; the base is the part of a template that is not structure.

### The panel server

One process per machine, `to-human/panel/server.py`, Python 3 with its
standard library alone. Python because sminos, which to-human installs with
it, already needs it on every machine; a server in TypeScript would need
`bun` or `node` at run time, which only the tests need today.

It listens on `127.0.0.1` alone, on a fixed port, 4777 (`PANEL_PORT` names
another), so an address in an old message still opens after the server
restarts.

The human reads at the MacBook, and sessions also run on the Mac mini and
the devcloud hosts, whose localhost the MacBook cannot open. The human
ruled that every machine's panels are reachable over Tailscale. The server
does not listen on the tailnet itself: the Mac's application firewall is on
and would stop or prompt for a listener of Python's, and a listener bound
to the Tailscale address has to follow that address as Tailscale restarts.
`tailscale serve` does it instead, as it does for the session manager's
page: `ensure` and `open-panel` run
`tailscale serve --bg --https=<port> http://127.0.0.1:<port>` when Tailscale
is running and `tailscale serve status --json` shows no such mapping, and,
where that is refused for want of the right to configure the daemon, the
same under `sudo -n` (a devcloud host joins the tailnet with
`tailscale up --advertise-tags=tag:devcloud` and names no operator, so its
session user has the right only through sudo; `-n` fails at once where sudo
would ask for a password). The mapping is the Tailscale daemon's and
outlasts the server and a restart of the machine. Where it cannot be made (no Tailscale, or no right to run
`serve`, as on a Linux host whose user is not the daemon's operator) the
address is the localhost one and `OpenPanel`'s `reach` is `"local"`, which
the tool passes on, so the session can say the panel opens only on that
machine. The manager's `serve --install` leaves this command to the owner;
here the human's ruling is the instruction, and a tool that needed a manual
step on each host before its first use would not be used on them.

| Request | Answer |
|---|---|
| `GET /health` | `{ "server": "to-human-panel", "version": "<plugin version>" }`; local requests only |
| `GET /base/<file>` | A base file. |
| `GET /<short id>/` | `panel.html`, with the notes in `state.json`'s `checked` removed from view and the page's write time, by a small inline script the server inserts before `</head>`; sets `opened` in `state.json` to now. |
| `GET /<short id>/written` | `{ "written": <ms> }`, the file's modification time; the script asks every 2 seconds while the tab is visible and reloads when it differs from the page's own. |
| `POST /<short id>/check` with `{ "note": "<id>" }` | Adds the id to `checked`; 204. |
| `GET /<short id>/<file>` | A file the fork put beside the page (an image). No path leaves the directory. |
| `POST /shutdown` | The server exits (a newer plugin version replacing it). |

A page's contents are the session's work and can be confidential. Every
request is checked before anything is read:

- By its `Host`. `127.0.0.1:<port>` or `localhost:<port>` is a local
  request: any process of this user, which could read the files anyway. The
  machine's tailnet name (with the port) is a request `tailscale serve`
  passed on: it must carry exactly one `Tailscale-User-Login` header, not
  empty, and equal to this machine's own user's login when the machine has
  one (a devcloud host is a tagged device and has none; there any user's
  login passes, since the tailnet is one person's, and a tagged device, which
  sends no login, is refused). Any other `Host` is refused, which defeats DNS
  rebinding from a page in the browser. `tailscale serve` replaces a copy of
  the header a client sends (checked live for the manager's page).
- A `POST` whose `Content-Type` is not `application/json`, or whose `Origin`
  is present and not one of the server's own, is refused, which defeats a
  form or a script on another site. `POST /shutdown` is local only.

A refusal is 403 with no body.

Its command line is the mod's whole interface to it, so the mod holds no
logic about processes, ports or files:

    python3 <plugin root>/panel/server.py open-panel --session <id> [--locale en|ko]

makes sure a server answers `GET /health` and is exposed on the tailnet as
above (starting one detached from the
session, in its own process session, when none does; replacing one whose
version is lower than its own through `POST /shutdown`; leaving a newer one
alone, so two sessions on different plugin versions do not take turns
killing each other's server), creates the panel's directory and its starter
page when they are missing, increments `updates`, drops from `checked` the
ids `panel.html` no longer holds, and prints one JSON line (`OpenPanel`, in
Interfaces). A port another program holds is an error the tool passes to the
session as its refusal.

The server outlives the session that started it. After a restart of the
machine nothing serves until a session starts: the mod runs
`server.py ensure` at each interactive session's start when the panels
directory holds a panel, so an old link opens again as soon as any session
runs.

### Language

`PANEL_LOCALE` is read at each call: `en` or `ko` (`english` and `korean`
accepted, any case); unset or anything else is English. It reaches the fork
in the standing prompt and the page in its `lang`. It covers the page's
prose and the base's own words; code, identifiers, paths and quoted wording
stay as written. A call under another locale than `meta.json`'s rewrites the
page in the new one. An environment variable, as the plugin's other
per-launch settings are (`TO_HUMAN_FOLD_MODEL`); set once in
`~/.claude/settings.json` under `env`.

### Where the tool is offered

Where the message tool is registered, in an interactive session, outside
MAWS (which has its own artifact viewer and whose sessions are headless) and
outside a sminos internal fork. The main conversation only: a subagent's
call is refused as its message call is, since the panel is the session's
word to its human.

### The rule

`RULE` goes in two places: `output-styles/to-human.md`, in the paragraph
that says what to report, conditioned on the tool being among the session's;
and the human's `~/.claude/CLAUDE.md` under Reporting. It is authored agent
behaviour, so M3 measures it before it ships: a replay of real turns from
the owner's transcripts, some where a panel is warranted and some routine,
with the tool offered and the rule in place.

### What this version leaves out

- Answering on the page. The human chose the ask dialog; a control on the
  page that reaches the session needs a channel this version does not build.
- MAWS. Its artifact viewer is the natural surface there; a later ticket.
- Kept versions and a change log. The human ruled that the notes are the log.
- A subagent's panel.

## Acceptance

Each is a behaviour to observe on a machine with the branch's plugins
loaded (`claude --plugin-dir` for to-human, sminos and doperpowers), in an
interactive session under the `doperpowers:to-human` style.

1. The session, asked to present a design with two options, calls
   `mcp__to-human__present`; the call returns in under 5 seconds with the
   panel's address (`https://<this machine's tailnet name>:4777/<short id>/`
   on a machine with Tailscale), and the session goes on working.
2. Within minutes the session is told the panel is written, and sends a
   message linking it. The address serves a page with the two options,
   styled by the base, with no note on it.
3. With the page open, the session is asked to change one option and
   presents again. The page reloads by itself within 5 seconds of the write,
   the changed place carries a highlighted phrase and a note, and the top of
   the page counts one open note.
4. A click on the note's check button removes the note and the highlight. A
   reload, and the same address in another browser, show no note.
   `state.json` lists its id. After the next update, `panel.html` no longer
   holds its markup.
5. In a new session, two calls in a row with the page never opened leave a
   page with no note.
6. With `PANEL_LOCALE=ko` in the environment, a new session's panel is in
   Korean, its `<html lang>` is `ko`, and the count of notes reads in Korean.
7. A brief that asks the fork to edit a file of the repository changes no
   file outside the panel's directory and raises no permission prompt, in the
   `default` permission mode; the session is told what the fork did instead.
8. A second call made while the fork runs returns saying its brief is
   applied in a second pass; one notice of a written panel follows, after
   that pass, and the page reflects both briefs.
9. After the session exits, the address still serves the page. After
   `curl -X POST -H 'Content-Type: application/json' http://127.0.0.1:4777/shutdown`,
   starting any interactive session brings the address back.
10. `curl -H 'Host: evil.example' http://127.0.0.1:4777/health` is refused
    with 403; so is a `POST /<short id>/check` with
    `Content-Type: text/plain`, and a request with the tailnet `Host` and no
    `Tailscale-User-Login`.
13. A panel written by a session on another machine of the tailnet (a
    devcloud host or the Mac mini) opens in the MacBook's browser at that
    machine's `https://<tailnet name>:4777/<short id>/`, and a check made
    there is in that machine's `state.json`. From a tagged device
    (`curl` on a devcloud host against the MacBook's address) the same
    request is refused with 403.
11. A subagent's call of the tool is refused with a sentence that tells it
    to put the content in its report; an empty brief is refused; a headless
    session and a MAWS session are not offered the tool.
12. The rule's replay (M3) meets its bar: of the routine turns at most 1 in
    10 calls the tool, and of the warranted turns at least 7 in 10.

## Execution

### What this builds on

- `to-human/hooks/mods/message.tsx`: the pattern for a tool the plugin
  registers (`$.tool.register`, `tool.describe` to keep it loaded,
  `tool.call` to serve it, `getsTool` for where it is offered).
- `to-human/hooks/mods/register.tsx`: where a module of the plugin is
  registered.
- `to-human/hooks/mods/to-human.tsx`: the report view, which decides what a
  row draws as and what folds into the working record.
- `hooks/mods/fork-guard.tsx` and `sminos/hooks/mods/bridge-ask.tsx`: a fork
  a plugin starts, how its end is learned, and a guard that holds it to
  reading.
- `to-human/tests/mods/`: the kit tests (`*.test.ts`, run by
  `claude plugin test`) and the live checks (`live-*-check.py`, an isolated
  session in a tmux pane, run by hand since they spend model calls).
- `~/.local/share/present-panel/prototype/panel.html`: the approved form.
  The base's look starts from this page's styles and its notes script; the
  page is not in the repository, so M1 reads it there.
- `~/.local/share/present-panel/trials/`: the probe plugin
  (`probe_template.tsx`), its driver (`trial.py`) and each run's logs and
  transcripts (`runs/`), behind the trial entries in Surprises &
  Discoveries. The probe is the working example of a tool whose handler
  spawns a fork, a `tool.check` policy for it, and a `turn.complete` hook
  that hears its end.

### Constraints on every milestone

- The plugin's version moves with each milestone that changes a shipped file
  (`scripts/bump-version.sh --plugin to-human`; doperpowers too when
  `output-styles/to-human.md` changes); `scripts/bump-version.sh --since
  origin/main` checks it.
- The message tool's name, input and result are a contract MAWS builds on;
  nothing here changes them, or the style's `maws-to-human-contract` number.
- The server uses the Python standard library only.
- Detail goes in `to-human/CLAUDE.md`; `docs/whats-inside.md` gains the
  tool's row in the same change that ships it.
- Gates run on GitHub Actions (`ci-gate` from the worktree), not on this
  machine; one focused test file while iterating is fine.

### M1 — the panel server and the base

At its end a hand-written panel can be served, read, annotated and checked
off with no session involved: `server.py open-panel` creates a panel and
prints its address, the address serves the starter page under the base, a
page edited by hand to hold notes shows them placed at their anchors with
the count, a check persists, an edit of the file reloads the open page, and
a Korean page reads right.

It touches `to-human/panel/` (new: `server.py`, `base/`), the tests for it
under `to-human/tests/panel/`, and `.github/ci-kit.yml` (the `to-human-mods`
gate runs the new tests too).

It exposes `OpenPanel`, the server's requests and the note markup; it
consumes nothing.

Decisions that are this milestone's alone:

- The server is a `ThreadingHTTPServer`; `state.json` and `meta.json` are
  written whole through a temporary file and a rename, under one lock in the
  process.
- Hiding checked notes is the inserted script's work, run before the body
  draws, so a checked note never flashes: the server inserts
  `<script>window.PANEL={written:<ms>,checked:[...]}</script>` by one string
  replacement before `</head>` (appending it when the page has no head) and
  parses no HTML.
- `opened` is set by `GET /<short id>/` alone, never by `/written`: a tab
  left open in the background is not the human reading an update. The reload
  the script makes after a write is a `GET /<short id>/` and counts, but only
  while the tab is visible, which is when the script asks.
- Detaching: `open-panel` and `ensure` start the server through a double
  fork with `os.setsid`, its output to
  `<configuration directory>/to-human/panels/server.log`. A process started
  so from a mod outlived a reload of the module, the session's exit and a
  hangup of its terminal; one left in the engine's process group survived a
  hangup only under `nohup` (trial 5).
- `tailscale` is run only by `ensure` and `open-panel`, never by the
  serving process, with a 15-second limit; the machine's tailnet name, its
  user's login and whether it is tagged come from `tailscale status --json`
  (`manager_serve.py`'s `tailnet_self` is the pattern), read when the server
  starts and written beside the log as `server.json` for the checks.
- Tests are Python `unittest` against a server on a free port and a
  temporary panels directory, with a stub `tailscale` on the path (as
  `sminos/tests/test_manager_serve.py` has): each request of the table, the
  refusals of acceptance 10, both reaches, the short-id clash, the version
  rule of `open-panel`, the 30-day removal. The base's script is tested in a browser through
  `playwright-cli` by a check script run by hand (`tests/panel/live-base-check.sh`):
  placement at 1280 and 600 wide, the count, a check surviving a reload, the
  reload on a write keeping the scroll position, the Korean words.

It does not touch the mods, the style, or any document but the tests' own.

It proves acceptance 4 (the server's half), 9 (the server's half), 10 and
13. For 13 the second machine is a devcloud host that is online on the
tailnet (`tailscale status` lists them; the `devcloud:vm` skill reaches
one): copy `to-human/panel/` there, run `open-panel`, and open the address
it prints from this Mac. If neither `tailscale serve` nor its `sudo -n` form
is permitted on the host, that is a finding, not a failure of the
milestone: the host's panels are `"local"`, the item is recorded as not met
for devcloud hosts in Surprises & Discoveries with the command's output,
and the residue is a ticket for devcloud's boot program to name the session
user as the daemon's operator.

### M2 — the tool and the fork

At its end a session presents: acceptance 1 to 9 and 11 hold in a live
session. That includes the server's revival: at each interactive session's
start the module runs `server.py ensure` when the panels directory holds a
panel, not awaited by the hook, so an old address opens again without a
`present` call (acceptance 9).

It touches `to-human/hooks/mods/present.tsx` (new), `register.tsx`,
`to-human.tsx` (how the call draws), `to-human/types/`, the kit tests and a
live check under `to-human/tests/mods/`, and, if trial 2 puts the guard
outside the plugin, `hooks/mods/fork-guard.tsx`.

It consumes `OpenPanel` and the note markup; it exposes the tool's contract
(`PRESENT_TOOL`, `DESCRIPTION`, `INPUT_SCHEMA`, the results and refusals,
`STANDING_PROMPT`, `FINISHED`, `FAILED`).

Decisions that are this milestone's alone:

- The handler's order: refuse a subagent's call and an empty brief; if this
  session's fork is running, hold the brief and return `HELD`; else run
  `open-panel` (`$.process.run`), spawn the fork, remember its agent id, and
  return `STARTED`. At the fork's `turn.complete`: with briefs held, run
  `open-panel` again and spawn the next fork with all of them, in order,
  under one `Brief:`; with none, submit `FINISHED` or `FAILED`.
- Whether a fork is running is read from `$.agent.list()` (type `fork`,
  `spawnedBy` this plugin, a live status), not from the module's memory, so
  a reload of the plugin mid-run neither loses the fork nor starts a second
  (the bridge's `isForkRunning` is the pattern).
- The fork is known to the guard by the agent id its spawn returned, and
  after a reload of the module by `$.agent.list()` (`type: 'fork'`,
  `spawnedBy` this plugin). The list is no record of an end: an entry turns
  `completed` about a second after `turn.complete`, carries no text, and is
  gone about 30 seconds later (trial 1); the end and the text come from
  `turn.complete` alone. A fork whose end the module missed across a reload
  is therefore found gone from the list at the next call, and the session is
  not told of it; the next call starts a fork as usual.
- A row a plugin submits is not drawn by that plugin's own render hooks
  (`to-human/CLAUDE.md`: the reason to-human is a plugin of its own), so the
  view does not fold the `FINISHED` prompt as it folds another plugin's.
  This milestone looks at how the notice draws in the report and keeps the
  engine's drawing if it is one clean line that does not break a fold's
  bounds; otherwise the notice is submitted so that it folds. Either way a
  kit test pins the run rules around it.
- `$.prompt.submit` and a fork's `Edit` of an existing panel were not tried
  in the trials (`Write` was); the live check covers both.
- In the report view the call draws as one line that stays in the report,
  as an agent's spawn does: the brief's first line and the address. The
  notice that the panel is written folds into the working record, as other
  finish notifications do; the session's own message is what the human reads.
- A `present` call beside a final message keeps the turn's next request, as
  any other tool's call does (`message.tsx`'s `endsOnFinal` already treats
  it so; a test pins it).
- The standing prompt is authored agent behaviour. Its wording in Interfaces
  is the starting text; the live check's pages are its test, and a change to
  it is recorded in the Decision Log with the page that prompted it.

It does not touch the style, the human's `CLAUDE.md`, or the server.

It proves acceptance 1 to 9 and 11, by a live check
(`to-human/tests/mods/live-present-check.py`, haiku, an isolated
configuration directory and its own `PANEL_PORT`) for what a session does,
and by kit tests for the handler's refusals, the registration rule, the
prompt's assembly from an `OpenPanel` and the view's row.

### M3 — the rule, its evaluation, and the documents

At its end the rule is in the style, measured, and the feature is
documented and released: acceptance 12 holds and every earlier item is run
once more as written.

It touches `output-styles/to-human.md`, `~/.claude/CLAUDE.md` (the owner's
file, outside the repository: the one line under Reporting, which the human
asked for), `to-human/CLAUDE.md`, `docs/whats-inside.md`,
`to-human/.claude-plugin/plugin.json` (the description), and the versions.

The replay: from the owner's transcripts
(`~/.claude/projects/*/*.jsonl`), take 10 turns whose content warrants a
panel by the rule's own terms (a decision put to the human with options, a
design presented for approval, a third or later revision of the same
findings in one session) and 10 routine ones (a merge, a green run, a
problem met and resolved, a short answer). Replay each context up to the
point the session wrote to its human, on the model that session ran on, with
the tool offered (its call answered `STARTED`, no fork spawned) and the rule
in the style, and count the calls. The bar is acceptance 12. The turns
chosen, with why each is in its class, are listed in the evaluation's report
(`docs/doperpowers/specs/2026-11-13-present-panel-eval.md`) so the human can
dispute a label. A miss is met by rewording the rule, with each wording's
counts kept in the report; `doperpowers:writing-skills` governs the edit.

Before the replay launches, the session running this milestone tells the
human which models, at which efforts, how many runs and for what, as the
output style requires of any programmatic fan-out.

It does not touch the server or the mod except to fix what the acceptance
run finds.

It proves acceptance 12, and runs 1 to 11 as written.

### Concrete Steps

In the worktree `/Users/new/Developer/GitHub/doperpowers/.claude/worktrees/present-panel`:

    python3 -m unittest discover -s to-human/tests/panel        # M1: the server
    bash to-human/tests/panel/live-base-check.sh                 # M1: the base, in a browser
    bash to-human/tests/mods/run.sh                              # M2: the kit tests
    python3 to-human/tests/mods/live-present-check.py            # M2: a session presents (spends haiku calls)
    tests/mods/typecheck.sh                                      # the mods-types gate's check
    scripts/bump-version.sh --since origin/main                  # the version rule
    ci-gate                                                      # every gate, on the committed HEAD

By hand, M1:

    python3 to-human/panel/server.py open-panel --session 00000000-aaaa-bbbb-cccc-000000000000
    {"address": "https://s.tail112c3f.ts.net:4777/00000000/", "reach": "tailnet", "dir": ".../to-human/panels/00000000", "path": ".../panel.html", "update": 1, "isNew": true, "opened": null, "written": ..., "checked": [], "locale": "en", "base": ".../to-human/panel/base/README.md"}
    curl -s http://127.0.0.1:4777/health
    {"server": "to-human-panel", "version": "0.9.0"}

### Interfaces and Dependencies

The server's command line, `to-human/panel/server.py`:

    server.py serve                      # run in the foreground (tests, debugging)
    server.py ensure                     # make sure a server answers and is exposed; print {"address": "<origin>/", "reach": "tailnet" | "local"}
    server.py open-panel --session <id> [--locale en|ko]

`open-panel` prints one JSON line, `OpenPanel`:

    {
      "address": "https://s.tail112c3f.ts.net:4777/b4d10f41/",
      "reach":   "tailnet",         // or "local": http://127.0.0.1:<port>/..., this machine only
      "dir":     "<configuration directory>/to-human/panels/b4d10f41",
      "path":    "<dir>/panel.html",
      "base":    "<plugin root>/panel/base/README.md",
      "update":  3,
      "isNew":   false,
      "locale":  "en",
      "opened":  1794620000000,     // ms, or null: never opened
      "written": 1794619000000,     // ms: panel.html's modification time
      "checked": ["u2-1"]           // notes checked off and still in the file
    }

and exits non-zero with one line on stderr when it cannot (the port held by
another program, the directory not writable).

Environment: `PANEL_PORT` (default 4777), `PANEL_LOCALE` (`en`, `ko`),
`CLAUDE_CONFIG_DIR`.

In `to-human/hooks/mods/present.tsx`:

    export const PRESENT_TOOL = 'mcp__to-human__present'
    export const DESCRIPTION = "Put something on this session's panel for the human; a fork of you writes it in the background."
    export const INPUT_SCHEMA = {
      type: 'object',
      properties: {
        brief: {
          type: 'string',
          description: 'What to put on the panel or change on it. The fork has the conversation up to this call.',
        },
      },
      required: ['brief'],
    }
    export const STARTED = (address: string) => `Writing the panel in the background: ${address} You are told when it is written.`
    export const LOCAL_ONLY = ' This address opens only on the machine this session runs on: its panel server is not exposed on the tailnet.'  // appended to STARTED and FINISHED when reach is "local"
    export const HELD = (address: string) => `The panel is being written now: ${address} This brief is applied in a second pass when that ends, and you are told once, after it.`
    export const FINISHED = (address: string, said: string) => `The panel is written: ${address}\n${said}`
    export const FAILED = (address: string, why: string) => `The panel was not written (${why}): ${address} holds what it held before.`
    export const SUBAGENT_REFUSAL = 'present is for the main conversation; a subagent reaches the human through the session that dispatched it: put this in your report.'
    export const EMPTY_REFUSAL = 'present needs its brief: what to put on the panel or change on it.'
    export function registerPresent(on: On): void

`RULE`, the sentence for the style and the human's `CLAUDE.md`:

> What I must read closely and plain text carries poorly (a decision with
> its options, an architecture, findings that keep being revised through a
> large or complex piece of work) goes on the session's panel with
> `mcp__to-human__present`, and a message points to it. Routine reports stay
> text.

(In the style, "the human" for "I", and opened by "Where
`mcp__to-human__present` is among your tools,".)

`STANDING_PROMPT`, with its slots filled from `OpenPanel` and the brief:

    You are a fork of this session, started by its `present` call to write the session's panel for the human: one HTML page, the richer form of a message, which they read closely in a browser. You are not the session: do not continue its task, answer its human, or call `present`. The session goes on with its own work; yours is the panel, and it ends when the panel is written.

    The panel is {path}, served at {address}. This is update {update}. Write it in {English|Korean}.

    Compose it for what this content needs; no section or order is required. Write content only, on the base the page links: {base} lists its blocks and the markup of a note. Add your own styles or SVG where the base lacks something. Plain and legible is the care expected.

    Keep it to about three screens, 600 to 900 words with its figures: select and show (a diagram, a comparison, a table) instead of transcribing the conversation.

    The body states what holds now; edit it in place. What is new or awaits the human goes at the top. What is older and settled is cut once it no longer serves, or moved to the bottom and folded behind a one-line summary. An explanation keeps its own order.

    {seen}
    Where an edit changes what they have seen, anchor a note at that place saying what changed and why, ids u{update}-1, u{update}-2, and so on. A note still on the page whose statement you change again is replaced by one note carrying both steps.{checked}

    You can read anything and write only inside {dir}. Reply with two lines: what the panel now holds, and what changed.

    Brief: {brief}

`{seen}` is one of: `The human has not opened the panel: it owes them no
notes.` (`opened` null); `The human opened the panel after its last update:
they have seen what it holds.` (`opened` later than `written`); `The human
has not opened the panel since its last update: what that update wrote, they
have not seen.` (otherwise). `{checked}` is empty, or ` Delete these notes,
which they checked off: u2-1, u2-3.`

The guard, on every call of a fork this plugin spawned: `Read`, `Grep`,
`Glob`, and a `Bash` input the engine holds read-only are allowed; `Write`
and `Edit` are allowed when their `file_path`, with symbolic links and `..`
resolved, is inside `{dir}`; every other call, the fork's own call of
`mcp__to-human__present` among them, is refused with `This fork writes the
panel and nothing else.` Each answer is given at `tool.check` as allow or
deny, never left to core, so no call of the fork reaches a permission
prompt (`hooks/mods/fork-guard.tsx` is the pattern for both hooks).

## Surprises & Discoveries

The trials ran on Claude Code 2.1.325 with haiku, each in an isolated
configuration directory, with a probe plugin whose tool spawns a fork
(`~/.local/share/present-panel/trials/runs/<run>/`).

- Observation (trial 1): the engine tells the main session nothing when a
  fork a plugin spawned ends, in a running turn or idle; the spawner's
  `turn.complete` hook hears the end, with the fork's agent id and its final
  text.
  Evidence: `full-default-strict-180821`: fork ended at +14.6 s, main turn at
  +97.9 s, no delivery row; debug log `[enqueueAgentNotification] skipped
  taskId=… status=completed taskPresent=true reason=already-notified`, for
  every fork's first end.
- Observation (trial 2): the spawner's `tool.call`, `tool.check`, `turn.step`
  and `turn.complete` hooks run on its fork, except the registration whose
  frame made the spawn. Unguarded, a write under the configuration directory
  asks in every mode ("which is a sensitive file"); `default` and
  `acceptEdits` raise a dialog in the main pane on which the fork blocks,
  `auto` lets it through. A `tool.check` allow from the spawner overrides
  the ask and its deny stands, with no prompt, in all three modes.
  Evidence: `hooks module probe@inline tool.call: hooks 1 left out for
  re-entry (origin probe#1)`; runs `perm-*-pass-*`, `perm-*-decide-*`,
  `full-default-decide-*` (`elsewhere/` stayed empty).
- Observation (trial 3): a plugin's fork inherits the calling response up to
  the call: its text, its thinking, and earlier calls of the same response
  with their results; not the call itself or anything after it.
  Evidence: the fork's transcript opens `{"type":"fork-context-ref",
  "parentLastUuid": …}` naming the row before the call (`175712`: the text
  row; `180315`: the result of the sibling call made before it).
- Observation (trial 3): a fork goes on with the session's unfinished task.
  Evidence: 4 of 6 forks re-called the tool, re-ran the session's commands
  and answered for it; a prompt line forbidding it did not stop them; the
  run whose policy denied every call but the panel's write contained it.
- Observation (trial 4): `$.session.send({ to: { agentId }, text })` reaches
  a running fork at its next step. Sent as the fork ends, it is unread: the
  engine resumes the fork for another turn, sends the main session a task
  notification, and wakes it.
  Evidence: fork `a976ebef` read a message sent at +18.6 s at +60 s and
  applied it; a message sent at +93.5 s, 0.8 s before the turn's end, drew a
  second `agent.spawn` (`tool_use_id: ""`), a second `turn.complete`, and a
  `prompt.submit` of origin `task-notification` in the main loop.
- Observation (trial 5): a process a mod starts through a double fork with
  `os.setsid` outlives a reload of the module, the session's exit, and a
  hangup of the terminal.
  Evidence: `daemon-default-pass-175607`, four variants; the one without
  `nohup` or `setsid` died at `/exit`.
- Observation (trial 6): a fork's first request reads the session's context
  from the cache and writes only its own suffix.
  Evidence: fork `a976ebef`: read 26,715, written 879, against the main's
  26,715 written; three more forks alike. Not tried: a fork started after
  the cache entry lapsed.
- Observation: a fork the model starts with the `Agent` tool did not see
  text written in the response that started it, unlike a plugin's (trial 3).
  Evidence: the first prototype fork (2026-11-13) reported "'My working note
  above' existed only as reasoning"; the note was text in the response that
  held the `Agent` call.
- Observation: a page written from nothing is 40% styling and script by
  bytes, and a third of a fork's run is checking the page.
  Evidence: `panel.v1.html`, 21,545 bytes, 6,663 in `<style>` and 1,857 in
  `<script>`; the forks' own reports of both runs.
- Observation: a first write took 8.4 minutes and an edit 4.7, at 147k and
  154k tokens in the fork.
  Evidence: the two runs' task notifications (`duration_ms` 504,839 and
  278,567).
- Observation: a correction sent to a running fork reached it and was
  applied.
  Evidence: the human's server ruling, sent to the first fork mid-run, is in
  version 1 of the page as settled.

## Decision Log

- Decision: verification. The spec gets one independent review of the design
  (a general-purpose subagent on the frontier model) and, having three
  milestones, the `doperpowers:adversarial-reviewer` agent's buildability
  review of the execution section. The branch gets
  `doperpowers:reviewer-high` at the end.
  Rationale: the work adds a local HTTP server that serves confidential
  content and a fork that writes with the session's permissions, so the
  frontier rung reads the branch; the design is new but was settled on a
  working prototype in front of the human, so no panel is needed.
  Date/Author: 2026-11-13, the designing session.

- Decision: a call made while a fork runs is held for a second fork, not
  delivered to the running one.
  Rationale: the design the human read on the prototype panel had the brief
  sent to the running fork. Trial 4 showed a message that lands as the fork
  ends resumes it and wakes the main session with a notification of the
  engine's own; a second run has no such case. Rejected then: steering with
  a hold on the notice while a sent brief is unread, which needs the plugin
  to track each brief's delivery row and to suppress the engine's
  notification, a prompt whose drop leaves a system notice no view can hide.
  Date/Author: 2026-11-13, the designing session, on the trials' report.
- Decision: the input's description no longer tells the session to restate
  what the turn just concluded.
  Rationale: that lesson came from a fork started with the `Agent` tool; a
  plugin's fork inherits the calling response up to the call (trial 3).
  Date/Author: 2026-11-13, the designing session, on the trials' report.

## Outcomes & Retrospective

Pending — written at finish.
