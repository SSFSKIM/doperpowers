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
forked copy of the session writes or edits the page in the background. When
the page is written the human is shown its address in their report and
notified, without the session spending a turn on it. The page always states
what holds now; where an update changes something the human has already
seen, a small note sits at that place, in the manner of a comment in Google
Docs, and disappears for good once the human checks it off.

To see it working: in a to-human session in a terminal, have the session
present something (a design with two options, say). The row of that call in
the report reads `writing…`, and a few minutes later carries a link of the
form `https://s.tail112c3f.ts.net:4777/b4d10f41/`, which opens the page from
the machine the session runs on or from any other device of the human's on
their tailnet. Have the session change one of the options: the open page
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
- [x] (2026-11-14 03:05Z) Trials reported (Claude Code 2.1.325, haiku); spec written (e657e818).
- [x] (2026-11-14 04:10Z) Design review and execution-section review absorbed (Decision Log).
- [x] (2026-11-14 04:45Z) Second review round absorbed (four findings, all taken; Decision Log).
- [x] (2026-11-14 04:35Z) M1 — the panel server and the base (ebc15016..47bce689; reviewed clean after three fix rounds; acceptance 11, 12, 13 live).
- [x] (2026-11-14 07:27Z) M2 — the tool and the fork (7b75c023..3670dfe0; reviewed clean after three fix waves; acceptance 1 to 10 and 14 live, 3, 4, 5 and 8 on fable).
- [ ] M3 — the rule, its evaluation, and the documents.
- [ ] Whole-branch review, retrospective, merge; the owner's two files.

## Terms

- **Panel**: one HTML page a session keeps for its human, at most one per
  session, stored on the machine the session runs on.
- **Fork**: a subagent of type `fork`: a copy of the session that starts
  with the session's whole conversation and runs on the session's model and
  in its permission mode. A plugin starts one with
  `$.agent.spawn({ subagentType: 'fork', ... })`; the sminos bridge's
  `manager query` is the existing example (`sminos/hooks/mods/bridge-ask.tsx`).
- **Brief**: the one input of the tool: what to put on the panel or change
  on it.
- **Standing prompt**: the fixed text the tool puts before the brief in the
  fork's prompt (`STANDING_PROMPT`, in Interfaces).
- **Draft**: the file a fork edits, `draft.html` in the panel's directory.
  It becomes the page only when the fork has ended well (**published**).
- **Note**: a short text anchored at a place on the page, saying what
  changed there and why. The human removes it with its check button.
- **Base**: the stylesheet, the script and the optional blocks the plugin
  ships and the server serves, which every panel links. It fixes how a panel
  looks and behaves, and nothing about what it holds or in what order.
- **Panel server**: one process per machine that serves every panel on it
  and the base, and is the only writer of a panel's records.
- **Short id**: the first 8 characters of a session's id, as sminos shows a
  session (`[b4d10f41]`); a panel's place in the server's addresses.
- **Address**: a panel's URL, `<origin>/<short id>/`, where the origin is
  the machine's tailnet one (`https://<tailnet name>:<port>`) when the
  server is exposed there, else `http://127.0.0.1:<port>`.
- **Tailnet**: the human's private Tailscale network, on which each of
  their machines has a name (`s.tail112c3f.ts.net` is the MacBook).
  `tailscale serve` has the machine's Tailscale daemon accept HTTPS on a
  port of that name, from the tailnet's devices only, and pass each request
  to a local port. It adds the headers `X-Forwarded-For` and
  `X-Forwarded-Host` to every request it passes, and `Tailscale-User-Login`
  with the login of the requesting device's user (none for a tagged device,
  which has no user; a copy a client sends is replaced). It passes the
  client's `Host` header on unchanged. The session manager's page is served
  this way (`sminos/skills/manager/scripts/manager_serve.py`).
- **Configuration directory**: `CLAUDE_CONFIG_DIR`, else `~/.claude`.
- **Report**: what the human reads of a session under the to-human style:
  its messages and the few rows the view keeps in sight, with the rest
  folded (`to-human/hooks/mods/to-human.tsx`).

## What the human sees

The session says it is putting something on the panel, and the row of its
`present` call stays in the report: the brief's first line and `writing…`.
When the page is written, that row carries the page's address as a link and
a notification is raised; when it could not be written, the row says so and
why. Nothing here waits on the session: the address reaches the human from
the tool, not from a message the session has to remember to send.

The page opens in the browser. It is about three screens long. At its top is
what is new or what awaits the human; older, settled material is gone, or
sits at the bottom folded behind a one-line summary. No two panels need look
alike in structure: one is a comparison of options under a "needs you"
block, another a diagram with a table of findings. They share type, spacing,
colours and the behaviour of notes.

When the session updates the panel, the open page reloads by itself, once,
when the update is whole. Each place whose statement changed since the human
last saw it carries a highlighted phrase and, beside it in the margin (under
it on a narrow window), a note: what changed and why. The top of the page
counts the notes still open and jumps to the next. A click on a note's check
button removes the note and its highlight; it stays gone on reload and in
every browser, and the next update deletes it from the page's file. A page
the human never looked at gets no notes: there is nothing they could have
read differently.

The panel is read-only apart from the check buttons. A decision it lays out
is asked through the ask dialog (`mcp__sminos__AskUserQuestion`), whose
question points at the panel.

With `PANEL_LOCALE=ko` the page is written in Korean, its `lang` is `ko`,
and the base's own words (the count, the check button's label) are Korean.

## What the session does

The session calls `mcp__to-human__present` with `{ brief }`. The call
returns within seconds with the panel's address and says what happens next
(`STARTED`): the human is shown the address when the page is written; the
session is not woken for it and learns the outcome at its next step or its
next prompt; so if a decision is due, it asks now, pointing at the panel.

The rule for when to call it is one sentence, in the `to-human` output style
and in the human's own `CLAUDE.md` (`RULE`, in Interfaces): what the human
must read closely and plain text carries poorly goes on the panel; routine
reports stay text. The rule is deliberately narrow. Each call costs a fork's
requests over the session's whole context (cache reads while the session's
cache is warm, trial 6), so a panel has to earn its call; and the human
ruled that most sessions should never need one.

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
for and gives the fork the facts it cannot derive: the file to edit, the
language, the update's number, whether the human has looked at the page
since its last update, which notes they checked off, the markup of a note,
and where the base's blocks are listed. Its rules are few, and each is the
human's ruling or a lesson of the prototype runs:

- Compose for the content; no section or order is required. Write content
  only, on the base.
- About three screens. The first prototype draft, told "a few scrolls", came
  out a third too long; a number prevents the overshoot. Without a browser
  the fork cannot measure a rendered height, so the prompt gives a measure it
  can count: 600 to 900 words of the page's running text in English, or
  1,800 to 2,700 characters in Korean, not counting notes, the labels inside
  figures, or material folded at the bottom. (The approved page: about 860
  such words.)
- The body states what holds now, edited in place.
- What is new or awaits the human is at the top; what is older and settled
  is cut once it no longer serves, or moved to the bottom, folded behind a
  one-line summary. An explanation keeps its own order: the human's rule is
  about what they meet first, and an account of how something works, sorted
  by date, is harder to follow than one sorted by its logic.
- Where an edit changes what the human has seen, one note for that change,
  at the first place it shows, with each other place it changed marked
  under the same id. A note still unchecked whose statement changes again is replaced by one note
  carrying both steps. Notes the human checked are deleted from the file.
- Plain and legible is the design care expected. The prototype's fork loaded
  the `designer` skill, whose workflow is out of proportion for a panel.
- No credential on the page.

**The draft.** The fork does not edit the page the server serves. It edits
`draft.html`, which `open-panel` makes as a copy of the published page (or
of the starter, for a new panel), and when the fork ends well the server
publishes the draft over the page in one rename. A fork takes minutes and
edits in many steps; edited live, an open tab would reload into each
half-written state, and a fork that died midway (an API error, an
interrupt, the session's exit) would leave a broken page with nothing to
restore it from, since no version is kept. With a draft the page changes
once per update, a failed fork leaves it as it was, and "written" has one
meaning. "Edited in place" is the human's ruling about the content, which
this keeps: the draft starts as the page.

**The guard.** The fork is held to reading, plus `Write` and `Edit` of its
draft (the guard, in Interfaces). The hold is needed, not a precaution. A
fork starts in the middle of the session's turn with the session's task in
its context, and goes on with it when nothing stops it: in the trials 4 of 6
forks (haiku) did the session's remaining work, re-running its commands and
calling the tool again, and a sentence in the prompt telling them not to did
not stop them; only a tool policy did (trial 3). The standing prompt opens
by saying the fork is not the session and does not continue its task, as the
sminos bridge's fork frame does (`ASK_FRAME`), and the guard makes that true
of everything but its words. The guard also keeps every fork call from a
permission prompt: with no hook deciding, a write under the configuration
directory asks in the `default` and `acceptEdits` modes, because the
directory is a protected location, and the fork blocks on a dialog in the
main session's pane (trial 2).

The guard is the plugin's own. A plugin's hooks run on the calls of a fork
it spawned, all but the one registration whose frame made the spawn (the
tool's handler), so the guard is registered apart from the handler; its
`tool.check` answer of allow overrides the protected-location ask and its
deny stands, with no prompt, in the `default`, `acceptEdits` and `auto`
modes (trial 2). It holds as long as no plugin outside to-human overrides
its answer; to-human is the outermost plugin by the owner's
`prependPlugins`. In plan mode a hook can only tighten a call that is not a
read (the engine's declaration of `ToolCheckResult.decision`), and a fork
inherits the session's mode, so there the write cannot be opened: the tool
refuses the call in plan mode, before any fork is spawned.

The guard also refuses a write whose text holds a secret's handle
(`[secret:…]`, `[redacted:…]`), and refuses it at `tool.call`, before the
call is passed on. The devcloud plugin's secrets guard, seated inside
to-human, restores a handle to the secret's bytes in a `Write` or an `Edit`
in its own `tool.call` hook before it calls `next`
(`devcloud/hooks/mods/secrets.tsx`), so by the permission check the handle
is gone and the secret is in its place; only the outermost `tool.call` hook
sees what the fork wrote. A panel is served to other devices.

**One fork at a time.** A call made while this session's fork is writing is
refused (`BUSY`): the session calls again once it has been told the panel is
written. Two other ways were considered. Delivering the brief to the running
fork as a message (`$.session.send`) works while the fork still has a step
to take, as the prototype's first run did by hand; but a message that lands
as the fork writes its last reply is not read, and the engine then resumes
the fork for another turn, sends the main session a task notification
nobody asked for, and wakes it (trial 4). Holding the brief for a second
fork started at the first one's end needs the held briefs to survive a
reload of the plugin, a second place that spawns (from a `turn.complete`
hook, where a denied spawn would lose the brief silently), and a
reservation across both. Overlap is rare, the refusal costs the session one
more call, and that call is made from the tool's handler, the one spawn path
the trials exercised.

**The end.** The engine sends no notification for a fork a plugin started,
neither into a running turn nor to an idle session (trial 1). The fork's own
`turn.complete` reaches the plugin's hook with the fork's agent id, its
final text and the reason it ended. The plugin then:

1. publishes the draft, when the reason is `answer`; the page is **written**
   if the server published a draft that differed from the page, and **not
   written** otherwise (the fork ended `aborted`, `refusal` or `error`, or
   changed nothing), with that as the reason;
2. shows the human: the call's row in the report turns from `writing…` to
   the address, or to `not written` and why, and a notification is raised
   where the session notifies (`notify.tsx`'s `isNotifying`);
3. tells the session, without waking it: `FINISHED` or `FAILED` rides as
   hook context beside the main loop's next tool result when a turn is
   running, else beside its next prompt, the way the sminos ask delivers an
   answer mid-turn and the reminder rides a prompt
   (`sminos/hooks/mods/ask.tsx`, `to-human/hooks/mods/reminder.tsx`). The
   two attach from opposite sides of `next`: on a tool call the context is
   added to the result `next` returned; on a prompt it is added to the input
   passed to `next`, since a prompt has already entered the conversation by
   the time `next` resolves and context added to its result attaches to
   nothing (the engine's declaration of `PromptSubmitResult`). A prompt
   dropped beneath gives the notice back for the next one, as the reminder's
   does.

The human's sketch had the session notified when the page is done, and the
first version of this design woke the session with a prompt so it could send
the link. Three facts moved it. A prompt a plugin submits runs only once the
session is idle, so a session still working would not send the link for the
rest of its turn. A turn that a plugin's prompt opens is the kind the
transcript audit found ending on unsent prose in 75% of cases
(`to-human/CLAUDE.md`, on `reminder.tsx`), so the link would often not be
sent at all. And a prompt to-human submits is not drawn by to-human's own
view (the engine runs none of a plugin's render hooks on a row that plugin
submitted), so it could not be folded. Showing the human directly needs no
turn, costs no request over the whole context, and cannot be forgotten; the
session still learns the outcome before it next acts.

### The panel's files

Each panel is a directory under the configuration directory,
`to-human/panels/<short id>/`, beside the plugin's `dumps/` and `folds/`
(the directory is outside what the owner's `~/.claude` syncs between
machines, a git allow-list):

| File | Writer | What it holds |
|---|---|---|
| `panel.html` | the server, at publish | The page as served. |
| `draft.html` | the server at `open-panel`; then the fork | The page being edited. |
| `meta.json` | the server | `{ "session": "<full id>", "updates": <n>, "locale": "en" \| "ko", "seenAtOpen": <ms> \| null }`: `seenAtOpen` is `state.json`'s `seen` as the last `open-panel` read it, kept so `lookedMeanwhile` survives a server replaced between `open-panel` and `publish` |
| `state.json` | the server | `{ "seen": <ms> \| null, "written": <ms> \| null, "checked": ["<note id>", ...] }`: `written` is the page's publish time, `seen` the publish time of the newest publication the human looked at |

The server is the only writer of everything but the draft, inside one
process and under one lock, so a check the human makes while `open-panel`
runs cannot be lost between two writers. The command line (`open-panel`,
`publish`) is a client of the running server and writes nothing itself.

A short id that another session's panel holds (`meta.json` names a
different session) is refused by `open-panel` with a sentence. Two ids share
8 characters about once in four billion pairs; a longer directory name for
the second would give one session an address unlike every other's for an
event that will not happen.

A panel whose `panel.html` and `draft.html` are both older than 30 days is
removed when a server starts, as the fold summaries' files are.

### The base

`to-human/panel/base/` holds what every panel shares:

- `panel.css`: type, spacing, colours in light and dark
  (`prefers-color-scheme`), tables, `details`, and under `:lang(ko)` a Korean
  font stack with `word-break: keep-all` (the default breaks Korean inside a
  word).
- `panel.js`: draws each note at the height of its anchor in the margin, or
  under the anchor's block on a narrow window; gives it a check button; shows
  the count of open notes at the top with a jump to the next; reports a check
  and a look to the server; reloads the page when it is published anew,
  keeping the scroll position. Its words come in English and Korean, chosen
  by the page's `lang`.
- `starter.html`: a page with the two base links, a title and an empty body:
  a new panel's first draft, so a fork edits a page instead of writing one
  from nothing.
- `GUIDE.md`: the note markup and the optional blocks, each with a three-line
  example, for the fork to read on a first write. Blocks: a "needs you" block,
  a callout, an option comparison, a diagram frame, a quoted wording block.
  (Not `README.md`: `.version-bump.json` counts `*/README.md` as unshipped,
  and this file is behaviour the fork runs on.)

A change to the base stays compatible with a page written up to 30 days
earlier: classes and the note markup are added to, never renamed.

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
another), so an address in an old report still opens after the server
restarts.

**Reach.** The human reads at the MacBook, and sessions also run on the Mac
mini and the devcloud hosts, whose localhost the MacBook cannot open. The
human ruled that every machine's panels are reachable over Tailscale. The
server does not listen on the tailnet itself: the Mac's application firewall
is on and would stop or prompt for a listener of Python's, and a listener
bound to the Tailscale address has to follow that address as Tailscale
restarts. `tailscale serve` does it instead, as it does for the session
manager's page: with `PANEL_REACH=tailnet` in the session's environment the
server runs `tailscale serve --bg --https=<port> http://127.0.0.1:<port>`
when Tailscale is running and `tailscale serve status --json` shows no such
mapping, and, where that fails, the same under `sudo -n` (a devcloud host
joins the tailnet with
`tailscale up --advertise-tags=tag:devcloud` and names no operator, so its
session user has the right only through sudo; `-n` fails at once where sudo
would ask for a password). The mapping is the Tailscale daemon's and
outlasts the server and a restart of the machine;
`tailscale serve --https=<port> off` removes it. Once any command has asked
a server for the tailnet, it keeps the mapping for the rest of its life, and
an ask to a server that has not yet tried starts a refresh at once. A port
whose HTTPS the daemon already maps to another target is left alone: that is
someone else's mapping, and the reach is local. Where the mapping cannot be
made the address is the localhost one and `OpenPanel`'s `reach` is `"local"`, which
the tool passes on, so the session can say the panel opens only on that
machine.

Exposure is asked for by the environment variable, not made by default: the
plugin is published, and a tool that reconfigured a stranger's Tailscale
daemon under sudo, unasked, would be a bad neighbour. The owner sets
`PANEL_REACH=tailnet` once in `~/.claude/settings.json` under `env`, which
their machines share. The manager's `serve --install` goes further and
leaves the command itself to the owner; here a manual step on each host
before its first use would mean the tool is not used on them.

`tailscale` is never run on a request's path. The server holds the
machine's tailnet identity (its name, its user's login, whether it is
tagged) and whether the mapping stands, refreshed by a background thread
when the server starts and when `open-panel` or `ensure` asks, at most every
30 seconds, each `tailscale` command limited to 5 seconds. `open-panel`
waits at most 2 seconds for the first refresh after a cold start and reports
`"local"` when it has not settled; the address the human is shown is asked
for again at publish, by which time it has.

**Requests.**

| Request | Answer |
|---|---|
| `GET /<short id>/` | The page, with a small inline script the server appends to the page's source carrying the page's publish time and the checked notes, so a checked note never draws. Before a panel's first publish: a page that says the panel is being written, which reloads when it is. |
| `GET /<short id>/written` | `{ "written": <ms> \| null }`; the script asks every 2 seconds while the tab is visible and reloads when it differs from the page's own. |
| `POST /<short id>/seen` with `{ "written": <ms> }` | Records that the publication of that time was looked at, when it is the current one or newer than the one recorded; 204. The script sends the publish time of the page it is showing, when the page is drawn in a visible tab and when a hidden tab that reloaded becomes visible. |
| `POST /<short id>/check` with `{ "note": "<id>" }` | Adds the id to `checked` when it matches `u<digits>-<digits>` whole and is not there; 204. Anything else is 400. |
| `GET /base/<file>` | A base file. |
| `GET`, `POST /control/…` | The command line's requests (below). |
| anything else | 404. |

A look is a `POST` the page's script sends, not the `GET` of the page: a
`curl` of the address by the session, a tab the browser restores in the
background, and a prefetch all get the page without anyone reading it, and
would each have the next update owe notes to a human who saw nothing. It
names the publication it saw, so a report that arrives late from a page
since replaced does not mark the new one looked at.

The fork is told what the human has seen when it starts, and writes for
minutes while the old page stays readable. A human who first opens that page
in those minutes gets an update with no notes for it. The server knows: at
publish it compares the look it holds with the one `open-panel` answered,
and says so (`Published.lookedMeanwhile`), which the session reads in
`FINISHED` and can make good in a message. Re-running the fork for it would
cost minutes for a case that needs the human to open, for the first time, a
page already being rewritten.

**Who may ask.** A page's contents are the session's work and can be
confidential. Every request is checked before anything is read:

- A request that carries `X-Forwarded-For` or `X-Forwarded-Host` came
  through `tailscale serve`, whatever its `Host` says: it must carry exactly
  one `Tailscale-User-Login`, not empty, and equal to this machine's own
  user's login when the machine has one. The test is the forwarding headers
  and not the `Host` because `tailscale serve` chooses its handler by the TLS
  name and passes the client's `Host` through unchanged
  (`ipn/ipnlocal/serve.go`: `r.Out.Host = r.In.Host`), so a tailnet client
  can send `Host: 127.0.0.1:4777`; the forwarding headers it cannot leave
  out, since the proxy adds them.
- A request without them is local, and its `Host` must be
  `127.0.0.1:<port>` or `localhost:<port>`, which defeats DNS rebinding from
  a page in the browser. A local process of this user could read the files
  anyway.
- A `POST` whose `Content-Type` is not `application/json`, or whose `Origin`
  is present and not one of the server's own, is refused, which defeats a
  form or a script on another site.
- `/control/…` is local only and needs the header `X-Panel-Token` equal to
  the token in `server.json` (mode 0600, in the panels directory, written
  when the server starts).

A refusal is 403 with no body.

What this admits is stated here so it is a decision and not an accident:
any process on any untagged device that carries the owner's login reads
every panel of a machine with a user (the Macs), as it reads the manager's
page today; on a tagged machine (a devcloud host), which has no user to
compare with, any user's login passes, and a tagged device is refused. The
address travels in reports and project logs, so the short id is no secret.
The owner's tailnet is one person's; narrowing it further is the tailnet
ACL's work, not the server's.

**What a page may do.** A panel is HTML a model wrote from a context that
can hold fetched web content, and every panel on a machine shares one
origin, so a script that reached one page could read the others and send
them out. Every response carries:

    Content-Security-Policy: default-src 'none'; script-src <origin>/base/ 'nonce-<per response>'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'
    X-Content-Type-Options: nosniff
    Referrer-Policy: no-referrer
    Cache-Control: no-store

so only the base's script and the server's own inserted one run, and no
resource loads from another site. Inline styles and inline SVG stay open,
which is what a fork composes with. The inserted script carries the
response's nonce and its JSON with `<` escaped. The server serves no file of
a panel's directory but the page, and the guard lets the fork write none but
the draft.

The policy governs what a page loads, not where it goes: a
`<meta http-equiv="refresh" content="0;url=https://elsewhere/?…">` sends the
reader, and whatever the address carries, to another site as the page opens
(the second review reproduced it under this policy), and a
`<link rel="dns-prefetch">` or `preconnect` names another host with no load
at all. So publishing is also a boundary. The server finds every `<meta`,
`<link` and `<base` in the draft's source, wherever it stands, ends each tag
by the HTML tokenizer's attribute rules (quotes count only around a value; a
tag left open runs to the end of the source), and cuts by position every
`<meta>` that has `http-equiv`, every `<link>` but one whose `rel` is
`stylesheet` and whose `href` is under `/base/`, and every `<base>`,
repeating until nothing is left to cut so that the text around a cut cannot
join into a new tag. It does not use `html.parser`, which reads `<!-->` as
the start of a comment that runs to the next `-->` where a browser closes the
comment at once, so `<!--><meta http-equiv=refresh …><!-- -->` would pass it
with the `meta` live; a match inside a comment, a script or an attribute
value is cut too, which nothing on a panel needs. What it cut is in
`Published.removed`, and the session reads it in `FINISHED`. It cuts and
does not refuse, because the fork has ended by then and the rest of the page
is good. A link the human clicks is their own act and stays.

**The command line** is the mod's whole interface to the server, so the mod
holds no logic about processes, ports or files:

    python3 <plugin root>/panel/server.py open-panel --session <id> [--locale en|ko]
    python3 <plugin root>/panel/server.py publish --session <id>
    python3 <plugin root>/panel/server.py ensure

Each first makes sure a server of its own answers `GET /control/health`
with the token: starting one detached from the session, in its own process
session, when none does (and asking again once if the port turned out to be
taken, since another session's command may have started one in the same
moment); replacing one whose version is lower than its own through
`POST /control/shutdown`; leaving a newer one alone, so two sessions on
different plugin versions do not take turns killing each other's server. A
port that answers but not with this configuration directory's token (another
program, or a panel server of another configuration directory) is an error
the tool passes to the session as its refusal.

`open-panel` then has the server create the panel's directory when it is
missing, copy the page (or the starter) to the draft, increment `updates`,
drop from `checked` the ids the page no longer holds, and answer `OpenPanel`
(in Interfaces). `publish` has it copy the draft over the page in one
rename, when the draft differs from the page, set `written`, and answer
`Published`. `ensure` does nothing more when the panels directory holds no
panel, so the mod can call it at every session's start without starting a
server nobody needs.

The server outlives the session that started it. After a restart of the
machine nothing serves until a session starts: the mod runs
`server.py ensure` at each interactive session's start, not awaited, so an
old link opens again as soon as any session runs.

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
word to its human, and the registered agents' definitions withhold the tool
as they withhold the message tool (`disallowedTools`, the root `CLAUDE.md`'s
rule for the mods' session-only tools).

### The rule

`RULE` goes in two places: `output-styles/to-human.md`, in the part that
says what to report; and the human's `~/.claude/CLAUDE.md` under Reporting.
Both copies open with the condition that the tool is among the reader's
tools, since subagents and headless sessions read the second and have no
such tool. It is authored agent behaviour, so M3 measures it before it
ships: a replay of real turns from the owner's transcripts, some where a
panel is warranted and some routine, with the tool offered and both copies
in place.

### What this version leaves out

- Answering on the page. The human chose the ask dialog; a control on the
  page that reaches the session needs a channel this version does not build.
- MAWS. Its artifact viewer is the natural surface there; a later ticket.
- Kept versions and a change log. The human ruled that the notes are the log.
- A subagent's panel.
- A guard while the plugin's own module reloads. The engine keeps an
  unchanged module as loaded across `/reload-plugins`, so the guard is absent
  only for the moments an update of to-human itself lands while a fork runs;
  the fork's calls then fall to the session's own permission mode. Closing
  that needs a guard in a second plugin that knows the draft's path
  (doperpowers' `fork-guard.tsx` is read-only by design); it is a ticket,
  with the reload mod's hold on a reload while a fork writes as the likelier
  fix.

## Acceptance

Each is a behaviour to observe on a machine with the branch's plugins
loaded (`claude --plugin-dir` for to-human, sminos and doperpowers), in an
interactive session under the `doperpowers:to-human` style, unless it names
the server alone.

1. The session, asked to present a design with two options, calls
   `mcp__to-human__present`; the call returns in under 5 seconds with the
   panel's address, and the session goes on working. The call's row in the
   report reads the brief's first line and `writing…`.
2. Within minutes the row carries the address as a link and a notification
   is raised, with no turn of the session in between. The address serves a
   page with the two options, styled by the base, with no note on it. At the
   session's next tool call or prompt, it reads `FINISHED`.
3. With the page open and visible, the session is asked to change one option
   and presents again. The page does not change while the fork works; it
   reloads once, within 5 seconds of the publish; the changed place carries
   a highlighted phrase and a note, and the top of the page counts one open
   note.
4. A click on the note's check button removes the note and the highlight. A
   reload, and the same address in another browser, show no note.
   `state.json` lists its id. After the next update, `panel.html` no longer
   holds its markup.
5. In a new session, two calls, one after the other's end, with the page
   never opened in a browser (a `curl` of the address in between does not
   count as a look), leave a page with no note.
6. With `PANEL_LOCALE=ko` in the environment, a new session's panel is in
   Korean, its `<html lang>` is `ko`, and the count of notes reads in Korean.
7. A brief that asks the fork to edit a file of the repository changes no
   file but the draft and raises no permission prompt, in the `default`,
   `acceptEdits`, `auto`, `bypassPermissions` and `dontAsk` modes. In plan
   mode the call is refused with `PLAN_REFUSAL` and no fork starts.
8. A second call made while the fork runs is refused with `BUSY`; the first
   fork's page is published as if the call had not been made.
9. A fork that ends without changing its draft, and a fork interrupted
   midway, leave the page as it was; the row reads `not written` and why,
   and the session reads `FAILED`.
10. After the session exits, the address still serves the page. After the
    server is stopped (`server.py`'s own `POST /control/shutdown`), starting
    any interactive session brings the address back.
11. The server alone, local requests:
    `curl -H 'Host: evil.example' http://127.0.0.1:4777/<short id>/` is 403;
    a `POST /<short id>/check` with `Content-Type: text/plain` is 403; a
    `GET /control/health` without the token is 403; a check of a note id
    that is not `u<digits>-<digits>` is 400; a response's headers hold the
    policy above; a draft holding
    `<meta http-equiv="refresh" content="0;url=https://example.com/">` is
    published without it, and the page stays at its address when opened.
12. With `PANEL_REACH=tailnet`, a panel written by a session on a devcloud
    host opens in the MacBook's browser at that host's
    `https://<tailnet name>:4777/<short id>/`, and a check made there is in
    that host's `state.json`.
13. From a tagged device (`curl` on a devcloud host against the MacBook's
    tailnet address) the page is 403, with the honest `Host` and with
    `-H 'Host: 127.0.0.1:4777'`, and so is `/control/health` with a made-up
    token.
14. A subagent's call of the tool is refused with a sentence that tells it
    to put the content in its report; an empty brief is refused; a headless
    session and a MAWS session are not offered the tool.
15. The rule's replay (M3) meets its bar: of 30 runs over the routine turns
    at most 3 call the tool, and of 30 over the warranted turns at least 21.

## Execution

### What this builds on

- `to-human/hooks/mods/message.tsx`: the pattern for a tool the plugin
  registers (`$.tool.register`, `tool.describe` to keep it loaded,
  `tool.call` to serve it, `getsTool` for where it is offered).
- `to-human/hooks/mods/register.tsx`: where a module of the plugin is
  registered.
- `to-human/hooks/mods/to-human.tsx`: the report view, which decides what a
  row draws as and what folds into the working record; `folds.tsx` publishes
  to `$.state` what the view reads back, the pattern for the call's row.
- `hooks/mods/fork-guard.tsx` and `sminos/hooks/mods/bridge-ask.tsx`: a fork
  a plugin starts, how its end is learned, a guard that holds it to reading
  (its `tool.call` and `tool.check` hooks, each registration's denying
  `.catch`), the reservation taken before the first await
  (`isAskStarting`), the record of an open fork kept in `$.state` across a
  reload, and the grace given a list that lags an end (`isForkRunning`).
- `sminos/hooks/mods/ask.tsx`: context added to a tool result mid-turn
  (`context` on the `tool.call` hook's result) and to a prompt (`context` on
  the input the `prompt.submit` hook passes to `next`);
  `to-human/hooks/mods/reminder.tsx`: a prompt's context given back when the
  prompt is dropped beneath.
- `sminos/skills/manager/scripts/manager_serve.py` and
  `sminos/tests/test_manager_serve.py`: a `ThreadingHTTPServer` on localhost
  behind `tailscale serve`, its response headers (`common_headers`), its
  reading of the tailnet identity (`tailnet_self`), and tests with a stub
  `tailscale` on the path.
- `to-human/tests/mods/`: the kit tests (`*.test.ts`, run by
  `claude plugin test`) and the live checks (`live-*-check.py`, an isolated
  session in a tmux pane, run by hand since they spend model calls).
- `tests/output-styles/to-human-*-eval.py`: the hand-run evaluations of the
  style, the pattern for M3's replay.
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
  `output-styles/to-human.md` or `agents/` changes);
  `scripts/bump-version.sh --since origin/main` checks it.
- The message tool's name, input and result are a contract MAWS builds on;
  nothing here changes them, or the style's `maws-to-human-contract` number.
- The server uses the Python standard library only.
- Detail goes in `to-human/CLAUDE.md`; `docs/whats-inside.md` gains the
  tool's row in the same change that ships it.
- Gates run on GitHub Actions (`ci-gate` from the worktree), not on this
  machine; one focused test file while iterating is fine.
- A live check or a trial runs in an isolated configuration directory with
  its own `PANEL_PORT`, never against the owner's `~/.claude` or port 4777.

### M1 — the panel server and the base

At its end a hand-written panel can be served, read, annotated and checked
off with no session involved: `server.py open-panel` creates a panel and
prints its address, a draft edited by hand and published is served under
the base, notes show placed at their anchors with the count, a check
persists, a publish reloads the open page once, a Korean page reads right,
and the page opens from another machine of the tailnet.

It touches `to-human/panel/` (new: `server.py`, `base/`), the tests for it
under `to-human/tests/panel/`, and `.github/ci-kit.yml` (the `to-human-mods`
gate runs the new tests too).

It exposes `OpenPanel`, `Published`, the server's requests and the note
markup; it consumes nothing.

Decisions that are this milestone's alone:

- The server is a `ThreadingHTTPServer`; `state.json` and `meta.json` are
  written whole through a temporary file and a rename, every read-modify-
  write under one lock in the process.
- The inserted script is
  `<script nonce="…">window.PANEL={"written":<ms>,"checked":[...]}</script>`,
  appended to the end of the page's source; the server parses no HTML.
  The end of a well-formed page stands outside every comment, tag and
  raw-text element, which no textual match inside the page does (a head
  comment that mentions `</head>` took the first insertion, by
  `</head>`, into the comment). The base script is linked `defer`, so it
  runs after the appended script, and notes are hidden until it opens
  them, so a checked note never draws. A page left open at its end (an
  unterminated comment or raw-text element) leaves the script inert: the
  base script then draws the notes with no checked list, reports no look
  and does not poll, until the next update replaces the page; a draft
  tag left open does not take the nonce (CSP3's nonceable check refuses
  an element with `<script` in an attribute).
- Detaching: the server is started through a double fork with `os.setsid`,
  its output to `<configuration directory>/to-human/panels/server.log`. A
  process started so from a mod outlived a reload of the module, the
  session's exit and a hangup of its terminal; one left in the engine's
  process group survived a hangup only under `nohup` (trial 5).
- The command line's own budget: `open-panel` answers within 4 seconds of a
  cold start (2 to start the server, 2 for the first reach), so the tool
  keeps acceptance 1's 5.
- Tests are Python `unittest` against a server on a free port and a
  temporary panels directory, with a stub `tailscale` on the path: each
  request of the table; the refusals of acceptance 11 and, with forwarding
  headers set by the test, of 13; both reaches, a stub that stalls (the
  command still answers in its budget, `"local"`), and a stub that refuses
  until run under `sudo -n`; a check made between `open-panel`'s read and
  its write surviving; two `open-panel` commands started together on a cold
  port; the version rule; another configuration directory's server on the
  port; the short-id refusal; the 30-day removal; publish of an unchanged
  draft answering `published: false`; publish cutting a refresh `meta`, a
  `dns-prefetch` link and a `base` and leaving the base's stylesheet link
  and the rest of the source byte for byte; a look that names an older
  publication leaving the newer one unseen; a first look between
  `open-panel` and `publish` answering `lookedMeanwhile`. The base's script is tested in a
  browser through `playwright-cli` by a check script run by hand
  (`to-human/tests/panel/live-base-check.sh`): placement at 1280 and 600
  wide, the count, a check surviving a reload, one reload on a publish
  keeping the scroll position, a look reported only from a visible tab, the
  Korean words, and what a page may do: published from a draft with an
  inline `<script>`, an external image, a refresh `meta` and a
  `dns-prefetch` link, the page runs no such script, shows no such image,
  stays at its address, and makes no request to another host (the check
  intercepts every request, so none leaves the machine).

It does not touch the mods, the style, or any document but the tests' own.

It proves acceptance 4 (the server's half), 10 (the server's half), 11, 12
and 13. For 12 and 13 the second machine is a devcloud host that is online
on the tailnet (`tailscale status` lists them; the `devcloud:vm` skill
reaches one): copy `to-human/panel/` there, run `open-panel` with
`PANEL_REACH=tailnet` and its own configuration directory, publish a
hand-written draft, and open the address it prints from this Mac. These two
items block the milestone. If neither `tailscale serve` nor its `sudo -n`
form is permitted on the host, the executor stops and returns `BLOCKED`
with the commands' output: whether devcloud's boot program then names the
session user as the daemon's operator inside this work, or devcloud hosts
are left out of this version, is the spec author's call with the human.

### M2 — the tool and the fork

At its end a session presents: acceptance 1 to 10 and 14 hold in a live
session.

It touches `to-human/hooks/mods/present.tsx` (new), `register.tsx`,
`to-human.tsx` (the call's row), `to-human/types/to-human.d.ts` (the
`$.state` entries), `agents/*.md` and their Codex ports as
`tests/codex/test-native-agents.py` requires (each definition's
`disallowedTools` gains `mcp__to-human__present`), the kit tests and a live
check under `to-human/tests/mods/`.

It consumes `OpenPanel`, `Published` and the note markup; it exposes the
tool's contract (`PRESENT_TOOL`, `DESCRIPTION`, `INPUT_SCHEMA`, the results
and refusals, `STANDING_PROMPT`, `FINISHED`, `FAILED`).

Decisions that are this milestone's alone:

- The handler, in order: refuse a subagent's call, an empty brief, plan
  mode, and a call while a run is open (`BUSY`); take the reservation (a
  module variable set before the first await, released in a `finally` when
  no fork was spawned); run `open-panel` (`$.process.run`); spawn the fork;
  record the run; return `STARTED`. A spawn the engine denies (`deny` in its
  answer; past an interrupt the engine spawns nothing until the session
  takes input, `bridge-ask.tsx`) returns that as the call's refusal.
- The run's record, `{ agentId, toolUseId, session, dir, draft, address,
  update, startedAt, phase }`, is kept in the module and in `$.state`, so a
  module that starts over mid-run (a plugin update) still guards the fork
  and still hears its end. `phase` is `writing` until the fork's end is
  heard with reason `answer`, and is set to `publishing`, and kept, before
  `publish` is called: a module that starts over and finds a record in
  `publishing` calls `publish` again (the fork ended well, so publishing its
  draft is what was due) and counts the page written when `Published`
  says `published`, or its `written` is at or after `startedAt`, since a
  first `publish` that committed before the reload leaves the second with
  nothing to change. The ids of every fork the module spawned are kept in
  `$.state` beside the record and outlive it, so a fork whose run has
  closed stays held after a reload; while the module has not yet read them
  back, the guard denies the calls of any fork whose description is the
  panel's (`$.agent.list()`), and refuses rather than passes when it cannot
  tell. A record in `writing` whose agent `$.agent.list()` no longer lists, after the
  grace `isForkRunning` gives a lagging list, is a fork whose end was not
  heard: it is closed as not written (`its end was not heard`), without
  publishing, since a draft whose fork's ending is unknown may be half
  edited. The list is no record of an end (an entry turns `completed` about
  a second after `turn.complete`, carries no text, and is gone about 30
  seconds later, trial 1); it is read only to reconcile a record after a
  reload.
- At the fork's `turn.complete` (the hook matched on the recorded agent id):
  the steps of "The end" above, in that order, then the record is cleared.
- The guard's two hooks, registered apart from the handler and each with a
  `.catch` that denies: `tool.call` refuses by name every tool but `Read`,
  `Grep`, `Glob`, `Bash`, `Write` and `Edit`, and refuses a `Write` or
  `Edit` that holds a secret's handle; `tool.check` answers each of those
  six (the rules are in Interfaces) and never leaves one to core. The
  engine runs a plugin's `$.agent.spawn` as an `Agent` call and checks it
  like any call (in `auto` and `plan` it asked, and the `present` call
  waited on a dialog), so the guard's `tool.check` also allows this
  plugin's own spawn: origin this plugin, no `agentId`, `subagent_type`
  `fork`, `description` `panel`. A `.catch` denies only a call of a fork
  the module spawned, so a failure beneath a main-loop call is not
  reported as the guard's. The guard holds every fork the module spawned
  in its process, not only the open run's, so a fork whose run closed
  unheard stays held.
- The mode: neither a call's input nor `$.config.list()` carries it, so
  the module reads it from `classic.UserPromptSubmit`'s `permission_mode`
  and `telemetry.log`'s `permission_mode_changed` (`attributes.to_mode`),
  main loop only, as sminos' bridge does; before any prompt it is taken as
  not plan.
- `server.py ensure` runs at the start of every interactive session, not
  only where the tool registers, so any session brings an old address back
  (acceptance 10) and replaces an older server.
- The call's row: the view draws a `present` call as one line that stays in
  the report, as an agent's spawn does: the brief's first line, then the
  run's state read from `$.state` by the call's id: `writing…`, the address
  as a link, or `not written` and why. A row with no state (a resumed
  session) reads the address out of the call's result. The session's reading
  of `FINISHED` is hook context and draws nothing.
- A `present` call beside a final message keeps the turn's next request, as
  any other tool's call does (`message.tsx`'s `endsOnFinal` already treats
  it so; a test pins it).
- The standing prompt is authored agent behaviour. Its wording in Interfaces
  is the starting text; the live check's pages are its test, and a change to
  it is recorded in the Decision Log with the page that prompted it.
- Untried in the trials, so the live check covers each first: a fork's
  `Edit` of an existing draft; hook context reaching the session mid-turn
  and at its next prompt; the engine's report of plan mode at a tool's call
  (if the call's input does not carry the mode, `$.config.list()` or the
  session surface that does is the executor's to find; if none does, the
  executor reports it and plan mode is left to the guard's deny and
  `FAILED`).
- The live check also records, for the Surprises section: the billed tokens
  summed over a fork's requests (the trials' figures are the notification's
  `subagent_tokens`, not that sum); a fork started after the session sat
  idle past its cache's lifetime; and two runs on the models the owner
  runs, not haiku, one with the session on opus and one on fable
  (`claude-fable-5-2`, the owner's default since 2026-11-13, so the model
  most forks inherit), to see whether each fork stays on the panel.
  It notes which session id a `/clear` and a resume keep, since the panel
  follows the id.

It does not touch the style, the human's `CLAUDE.md`, or the server.

It proves acceptance 1 to 10 and 14, by a live check
(`to-human/tests/mods/live-present-check.py`, haiku, an isolated
configuration directory and its own `PANEL_PORT`) for what a session does,
and by kit tests for the handler's refusals, the reservation (a second call
arriving while `open-panel` runs is `BUSY`), the registration rule, the
prompt's assembly from an `OpenPanel`, the guard's answers (each allowed
name, a path outside the draft, a path that reaches the draft through `..`
or a symbolic link elsewhere, the fork's own `present` call), the handle's
refusal with a hook beneath that rewrites the input before the permission
check, as devcloud's does (the refusal has to come before it), a record
surviving a reload, a notice put back when the prompt that carried it is
dropped beneath, and the view's row in each state.

### M3 — the rule, its evaluation, and the documents

At its end the rule is in the style, measured, and the feature is
documented and released: acceptance 15 holds and every earlier item is run
once more as written.

It touches `output-styles/to-human.md`, `to-human/CLAUDE.md`,
`docs/whats-inside.md`, `to-human/.claude-plugin/plugin.json` (the
description), and the versions. The owner's files (`~/.claude/CLAUDE.md`:
the rule line; `~/.claude/settings.json`: `PANEL_REACH` and, if they want
it, `PANEL_LOCALE`) are outside the repository and are the designing
session's to edit after the merge, not the executor's.

The replay: from the owner's transcripts
(`~/.claude/projects/*/*.jsonl`), take 10 turns whose content warrants a
panel by the rule's own terms (a decision put to the human with options, a
design presented for approval, a third or later revision of the same
findings in one session) and 10 routine ones (a merge, a green run, a
problem met and resolved, a short answer). Replay each context up to the
point the session wrote to its human, three times, on the model that
session ran on, with the tool offered (its call answered `STARTED`, no fork
spawned) and the rule in both the style and the `CLAUDE.md` the replay
carries, and count the runs that call the tool. The bar is acceptance 15.
The harness follows `tests/output-styles/to-human-*-eval.py` and lives
beside them. The turns chosen, with why each is in its class, are listed in
the evaluation's report
(`docs/doperpowers/specs/2026-11-13-present-panel-eval.md`) so the human can
dispute a label. A miss is met by rewording the rule, with each wording's
counts kept in the report; `doperpowers:writing-skills` governs the edit.

Before the replay launches, the session running this milestone reports up
its dispatch chain which models, at which efforts, how many runs and for
what, so the main session can tell the human, as the output style requires
of any programmatic fan-out.

It does not touch the server or the mod except to fix what the acceptance
run finds.

It proves acceptance 15, and runs 1 to 14 as written.

### Concrete Steps

In the worktree `/Users/new/Developer/GitHub/doperpowers/.claude/worktrees/present-panel`:

    python3 -m unittest discover -s to-human/tests/panel        # M1: the server
    bash to-human/tests/panel/live-base-check.sh                 # M1: the base, in a browser
    bash to-human/tests/mods/run.sh                              # M2: the kit tests
    python3 to-human/tests/mods/live-present-check.py            # M2: a session presents (spends haiku calls)
    tests/mods/typecheck.sh                                      # the mods-types gate's check
    scripts/bump-version.sh --since origin/main                  # the version rule
    ci-gate                                                      # every gate, on the committed HEAD

By hand, M1 (an isolated directory and port):

    export CLAUDE_CONFIG_DIR=$(mktemp -d) PANEL_PORT=4791
    python3 to-human/panel/server.py open-panel --session 00000000-aaaa-bbbb-cccc-000000000000
    {"address": "http://127.0.0.1:4791/00000000/", "reach": "local", "dir": ".../to-human/panels/00000000", "draft": ".../draft.html", "guide": ".../to-human/panel/base/GUIDE.md", "update": 1, "isNew": true, "locale": "en", "seen": "never", "checked": []}
    python3 to-human/panel/server.py publish --session 00000000-aaaa-bbbb-cccc-000000000000
    {"published": false, "address": "http://127.0.0.1:4791/00000000/", "reach": "local", "written": null}

(`published` is false there because the draft is still the starter.)

### Interfaces and Dependencies

The server's command line, `to-human/panel/server.py`:

    server.py serve                      # run in the foreground (tests, debugging)
    server.py ensure                     # make sure a server answers, when a panel exists; print {"address": "<origin>/", "reach": ...} or {}
    server.py open-panel --session <id> [--locale en|ko]
    server.py publish --session <id>

`open-panel` prints one JSON line, `OpenPanel`:

    {
      "address": "https://s.tail112c3f.ts.net:4777/b4d10f41/",
      "reach":   "tailnet",         // or "local": http://127.0.0.1:<port>/..., this machine only
      "dir":     "<configuration directory>/to-human/panels/b4d10f41",
      "draft":   "<dir>/draft.html",
      "guide":   "<plugin root>/panel/base/GUIDE.md",
      "update":  3,
      "isNew":   false,             // true: the draft is the starter
      "locale":  "en",
      "seen":    "current",         // "never": no look yet; "current": the current publication was looked at; "stale": only an earlier one
      "checked": ["u2-1"]           // notes checked off and still in the page
    }

`publish` prints `Published`:

    {
      "published": true,
      "address":   "...",
      "reach":     "tailnet",
      "written":   1794620000000,
      "removed":   [],              // what publishing cut: "meta http-equiv", "link", "base"
      "lookedMeanwhile": false      // true: the human first looked at the page this update replaced after open-panel answered
    }

Each exits non-zero with one line on stderr when it cannot (the port held
by another program or another configuration directory's server, the short
id held by another session, the directory not writable).

The control requests behind them, local and with the token:
`GET /control/health` → `{ "server": "to-human-panel", "version": "<plugin
version>", "root": "<panels directory>" }`; `POST /control/open-panel` with
`{ "session", "locale", "reach" }` → `OpenPanel`; `POST /control/publish`
with `{ "session" }` → `Published`; `POST /control/reach` with `{ "reach" }`
→ `{ "address", "reach" }`, by which `ensure` passes the session's
`PANEL_REACH` on; `POST /control/shutdown`.

Environment: `PANEL_PORT` (default 4777), `PANEL_LOCALE` (`en`, `ko`),
`PANEL_REACH` (`tailnet`; anything else is local), `CLAUDE_CONFIG_DIR`.

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
    export const STARTED = (address: string) =>
      `Writing the panel in the background: ${address} The human is shown the address in their report when it is written. You are not woken for it: you learn the outcome at your next step or prompt, so if a decision is due, ask now and point at the panel.`
    export const LOCAL_ONLY = ' This address opens only on the machine this session runs on: its panel server is not exposed on the tailnet.'  // appended to STARTED and FINISHED when reach is "local"
    export const FINISHED = (address: string, said: string) => `The panel is written and the human has been shown its address: ${address}\n${said}`
    export const REMOVED = (what: string[]) => ` Publishing cut from the page what a panel may not hold: ${what.join(', ')}.`  // appended to FINISHED when Published.removed is not empty
    export const LOOKED_MEANWHILE = ' The human first opened the page while it was being rewritten, so this update carries no notes for what it changed: tell them what changed if it matters.'  // appended when Published.lookedMeanwhile
    export const FAILED = (address: string, why: string) => `The panel was not written (${why}); ${address} holds what it held before, and the human has been told. Call present again to retry.`
    export const BUSY = (address: string) => `The panel is being written now: ${address} Go on with your work: you are told at your next step once it is written, and can call present again then with what to change.`
    export const PLAN_REFUSAL = 'present writes a file, which plan mode does not allow: call it once the plan is approved.'
    export const SUBAGENT_REFUSAL = 'present is for the main conversation; a subagent reaches the human through the session that dispatched it: put this in your report.'
    export const EMPTY_REFUSAL = 'present needs its brief: what to put on the panel or change on it.'
    export const GUARD_REFUSAL = "Refused: this fork writes the panel and nothing else; that step is the session's, and the session takes it. Go on editing the draft, and end with your two-line reply once it holds the panel."
    export function registerPresent(on: On): void

`$.state`, published by the module for the view (`to-human/types/to-human.d.ts`):
`present`: the open run's record, or absent; `presented`: by the call's id,
`{ state: 'writing' | 'written' | 'failed', address: string, why?: string }`.

`RULE`, the sentence for the style and the human's `CLAUDE.md`:

> Where `mcp__to-human__present` is among your tools: what I must read
> closely and plain text carries poorly (a decision with its options, an
> architecture, findings that keep being revised through a large or complex
> piece of work) goes on the session's panel with it. Routine reports stay
> text.

(In the style, "the human" for "I".)

`STANDING_PROMPT`, with its slots filled from `OpenPanel` and the brief:

    You are a fork of this session, started by its `present` call to write the session's panel for the human: one HTML page, the richer form of a message, which they read closely in a browser. You are not the session: do not continue its task, answer its human, or call `present`. The session goes on with its own work; yours is the panel, and it ends when the panel is written.

    Edit {draft}: it is the panel as it stands{, a starter with nothing on it yet}, and it is published when you end. This is update {update}. Write it in {English|Korean}.

    Compose it for what this content needs; no section or order is required. Write content only, on the base the page links: {guide} lists its blocks and the markup of a note. Add your own inline styles or SVG where the base lacks something; nothing loads from another site. Plain and legible is the care expected. No credential goes on the page.

    Keep it to about three screens: {600 to 900 words|1,800 to 2,700 characters} of running text, not counting notes, labels inside figures, or what is folded at the bottom. Select and show (a diagram, a comparison, a table) instead of transcribing the conversation.

    The body states what holds now; edit it in place. What is new or awaits the human goes at the top. What is older and settled is cut once it no longer serves, or moved to the bottom and folded behind a one-line summary. An explanation keeps its own order.

    {seen}
    Where an edit changes what they have seen, write one note for that change, saying what changed and why, at the first place it shows, and mark each other place it changed with the same id; ids u{update}-1, u{update}-2, and so on, one per change. A note still on the page whose statement you change again is replaced by one note carrying both steps.{checked}

    You can read anything and write only {draft}. Reply with two lines: what the panel now holds, and what changed.

    Brief: {brief}

`{seen}` by `OpenPanel.seen`: `never`: `The human has not looked at the
panel: it owes them no notes.`; `current`: `The human has looked at the
panel since its last update: they have seen what it holds.`; `stale`: `The
human has not looked at the panel since its last update: what that update
wrote, they have not seen.` `{checked}` is empty, or ` Delete these notes,
which they checked off, with every mark of their ids: u2-1, u2-3.`

The guard, on every call of the fork a run's record names:

| Call | Answer |
|---|---|
| `Read`, `Grep`, `Glob` | allow |
| `Bash` | allow when the engine holds the input read-only (`isReadOnly` at `tool.check`), else deny |
| `Write`, `Edit` | deny at `tool.call` when `content` or `new_string` holds `[secret:` or `[redacted:` (the input as the fork wrote it, before any hook beneath restores a handle); at `tool.check`, allow when `file_path`, with symbolic links and `..` resolved (`$.fs.stat(path, { resolve: true })`), is the record's `draft`, else deny |
| any other tool | deny at `tool.call`, by name |

Every deny is `GUARD_REFUSAL`. No call of the fork reaches a permission
prompt.

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
- Observation: a first write took 8.4 minutes and an edit 4.7; the
  notifications report 147k and 154k `subagent_tokens`, which is not the
  billed sum over the forks' requests.
  Evidence: the two runs' task notifications (`duration_ms` 504,839 and
  278,567).
- Observation: a correction sent to a running fork reached it and was
  applied.
  Evidence: the human's server ruling, sent to the first fork mid-run, is in
  version 1 of the page as settled.
- Observation (M2): a plugin's `$.agent.spawn` is run as an `Agent` tool
  call and goes through the permission check; in `auto` (the engine's
  default mode now) and `plan` it asked, in `default` and `acceptEdits` it
  did not.
  Evidence: debug log `$.tool.call (to-human): Agent (prompt, description,
  run_in_background, subagent_type)`, `tool.check nested in to-human#31`,
  `executePermissionRequestHooks called for tool: Agent`.
- Observation (M2): haiku forks often re-enact the session's last steps
  before or instead of the panel: across four haiku main runs 16 of 26
  forks made a call off the panel (`present`, the message tool, the
  session's commands), about 8 of 26 ended without writing; the guard
  refused every call and nothing outside the draft changed. One opus and
  one fable fork made no call off the panel, and wrote pages of 488 and
  661 running words (haiku 572). A rewording of the standing prompt's
  opening did not change haiku's behaviour and was reverted.
  Evidence: `~/.local/share/present-panel/m2/`, runs main-3 to main-6,
  stay-opus, stay-fable.
- Observation (M2): owner models stay on the panel. With the parent
  mid-task and steps of its own pending (the condition under which haiku
  re-enacted them), opus 5 of 5 forks stayed on the panel and wrote the
  page, fable (`claude-fable-5-2`) 5 of 5, on top of one earlier run each.
  On the acceptance runs: fable held 3 (after the one-note rewording: one
  note with 6 marks, counted once), 4, 5 (0 notes on an unseen page after a
  `curl`) and 8; opus held 4 and 8, and 3 partly before the rewording (5
  notes for one change, one per place); haiku failed 3, 4, 5 and 8 through
  its forks (no note on a seen page, three on an unseen one, a wandering
  fork that wrote nothing), which this version records as the limit beside
  its wandering. With `BUSY` reworded, haiku's retry loop fell from 5 calls
  and 3 to 4 forks a turn to 3 calls and 1 fork; the reworded
  `GUARD_REFUSAL` did not bring haiku forks back to the draft (1 of 5).
  Evidence: task-2-report's fix-stay-opus.log, fix-stay-fable.log,
  fix-main.log, fix-unseen.log and the fable reruns under
  `~/.local/share/present-panel/m2/`; the fable edit fork
  `/tmp/thpresent.b8dyjnl5/…/agent-a988894c8032c5bd6.jsonl`.
- Observation (M2): a model's own `Agent` call shaped like the panel's
  spawn (`fork`, `description` `panel`) does not match the guard's allow:
  its origin is the engine's, and it takes the ordinary path (in `auto`,
  no prompt), unheld by the guard, which holds only forks it spawned.
  Evidence: fix-lookalike.log, one allow line, for the `present` spawn.
- Observation (M2): `BUSY`'s first wording, "Call present again once you
  are told it is written", led haiku to call `present` four more times in
  the same turn.
  Evidence: main-4.
- Observation (M2): a fork's billed requests. haiku, a first panel: 4
  requests, cache write 13,137, read 90,814, output 4,807; an Edit of an
  existing draft: 6 requests, write 10,664, read 162,880, output 5,283.
  opus: 3 requests, write 5,890, read 66,290, output 3,207. fable: 3
  requests, write 7,044, read 71,276, output 3,743. A fork started after
  the session sat idle 6 minutes, past the cache's lifetime, still read
  from the cache (first request read 35,254, wrote 1,312): the session's
  own request that makes the call rewrites the cache first.
  Evidence: the forks' transcripts in main-3, main-4, stay-opus,
  stay-fable; the spawn row, a synthetic `Agent` call with zero usage, is
  not a request.
- Observation (M2): `/clear` starts a new session id, so a panel after it
  is a new panel at a new address; `--resume` keeps the id. Hook context
  reaches the session at its next prompt (an attachment after the prompt)
  and mid-turn (after a tool result). A fork's `Edit` of an existing draft
  works.
  Evidence: main-4 (`3334f4eb…`, rows 66 and 97), main-3.
- Observation: `tailscale serve` forwards the client's `Host` unchanged and
  adds `X-Forwarded-For` and `X-Forwarded-Host` to every proxied request; a
  `Tailscale-User-Login` a tagged device sends is stripped and none added.
  Evidence: Tailscale's `ipn/ipnlocal/serve.go`, `r.Out.Host = r.In.Host`
  and `addProxyForwardedHeaders`; run live in M1 (acceptance 13): from the
  tagged `dc-c53-g1a-980a` against the MacBook's mapping, the page with the
  honest `Host`, with `Host: 127.0.0.1:<port>`, with a forged login, and
  `/control/health` with a made-up token or the local `Host`, all 403.
- Observation (M1): the standard library's `html.parser` reads `<!-->` as
  an open comment that runs to the next `-->`; a browser closes it at once.
  Evidence: `html.parser` reported `comment '><meta http-equiv=refresh …'`
  for `<!--><meta http-equiv=refresh …><!-- -->`; the base's browser check
  publishes that draft and sees no navigation.
- Observation (M1): on a devcloud host (tailscale 1.104.6) the session user
  cannot configure serve; `sudo -n` can, so that path is the one that runs
  there, both to map and to remove a mapping.
  Evidence: `tailscale serve --https=4793 off` → `Access denied: serve
  config denied`; `sudo -n tailscale serve …` → rc 0; acceptance 12 passed
  with the server making the mapping itself.

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
- Decision: the input's description no longer tells the session to restate
  what the turn just concluded.
  Rationale: that lesson came from a fork started with the `Agent` tool; a
  plugin's fork inherits the calling response up to the call (trial 3).
  Date/Author: 2026-11-13, the designing session, on the trials' report.
- Decision: a call made while a fork runs is refused (`BUSY`). The prototype
  panel the human read had the brief delivered to the running fork; the
  spec's first writing (e657e818) held it for a second fork.
  Rationale: trial 4 ruled out delivery (a late message resumes the fork and
  wakes the session); the design review showed the held pass needs state
  that survives a reload, a second spawn site and a reservation across both,
  for a rare overlap. Both are described where the decision is made.
  Date/Author: 2026-11-13, the designing session, on the reviews.
- Decision: the human is shown the written panel by the call's row and a
  notification, and the session is told by hook context without being woken.
  The human's sketch, and e657e818, had the session woken to send the link.
  Rationale: in "The end". The human's intent was that the main session is
  interrupted least and that they learn when the page is ready; both hold.
  Date/Author: 2026-11-13, the designing session, on the design review.
- Decision: the fork edits a draft that the server publishes at its end;
  the server is the only writer of a panel's records and the command line is
  its client; a look is a `POST` from the page's script; requests are told
  local from proxied by the forwarding headers; a content policy on every
  response, and publishing cuts what navigates or names another host by
  itself; control requests carry a token; the guard refuses a secret's
  handle at `tool.call`, before devcloud's hook restores it; a look names
  the publication it saw, and a first look during a rewrite is reported;
  hook context is added to a tool call's result and to a prompt's input;
  plan mode refused; exposure on the tailnet asked for by
  `PANEL_REACH`; the base's guide named `GUIDE.md`; a clashing short id
  refused; acceptance 12 and 13 block M1; the replay runs each turn three
  times with both copies of the rule; the registered agents withhold the
  tool.
  Rationale: findings of the two reviews of e657e818 and of the second
  round on 288dc26e, each taken; the reason for each is in the section that
  now states it. Review of the document stops here: the second round's
  findings were local to mechanisms the first round introduced, and the
  server and the guard are read again, with their code, at each milestone's
  review and by the branch's.
  Date/Author: 2026-11-13, the designing session, on the reviews.

- Decision: publishing finds the tags it cuts by its own scan of the
  source, not with `html.parser`; `meta.json` keeps `seenAtOpen`; a control
  request `POST /control/reach` carries `ensure`'s reach; a tailnet ask
  keeps the mapping for the server's life and forces a refresh; a port the
  daemon maps elsewhere is left alone with the reach local. Each now stands
  in the section that states the interface.
  Rationale: M1's executor. `html.parser` and a browser disagree on `<!-->`
  (Surprises), so a parser-based cut let a refresh `meta` through; the scan
  over-cuts inside comments and scripts, which a panel never needs, and
  repeats to a fixed point so a cut cannot assemble a new tag. `seenAtOpen`
  lets `lookedMeanwhile` survive a version replacement mid-update; the four
  control requests had no place for `ensure`'s reach; a mapping to another
  target is someone else's, by the design's own "bad neighbour" reasoning.
  The designing session read the scan and accepted all five.
  Date/Author: 2026-11-13, the executing session, on M1.
- Decision: M2's live check runs the owner's-model fork check twice, on opus
  and on fable, and records both.
  Rationale: the owner's default model became Fable 5.2 on 2026-11-13, so
  most forks will inherit it.
  Date/Author: 2026-11-13, the designing session, relayed to the executing
  session.

- Decision: the server's script is appended to the end of the page, not
  put before the first `</head>`; no guard string precedes it; a page
  without `window.PANEL` is left static.
  Rationale: M1's review. A textual `</head>` can stand inside a comment;
  a guard that closed open states (`<!--"'>-->`) then broke the comment of
  a well-formed page (R5), and a fallback that took the server's latest
  publication time for the page shown could mark an unseen publication
  seen and bring checked notes back (R6, R7). The end of a well-formed page
  is the one position no authored state can hold open.
  Date/Author: 2026-11-13, the executing session, on M1's review.

- Decision: the guard allows this plugin's own fork spawn at `tool.check`;
  the mode is read from the prompt hook and the mode-change event;
  `ensure` runs in every interactive session; the guard holds every fork
  the module spawned; a second call arriving during the reservation waits
  on it and then reads `BUSY`. Each stands where M2's decisions are stated.
  Rationale: M2's executor, from the live runs; the engine checks a
  plugin's spawn as an `Agent` call, which the spec had assumed could be
  denied but never ask.
  Date/Author: 2026-11-13, the executing session, on M2.
- Decision: haiku's wandering forks are accepted as a limit of that model
  for this version, not designed around; `BUSY` and `GUARD_REFUSAL` are
  reworded to the two observed failures (a retry loop on `BUSY`; a fork
  stopping or carrying on after a bare refusal), and one more haiku main
  run checks them.
  Rationale: a fork inherits the session's model; the owner runs fable
  and opus, whose forks stayed on the panel; the guard made every wander
  harmless, so the cost on haiku is a `FAILED` and a second call. The
  standing prompt's own rewording did not help haiku and stays reverted;
  the two refusal texts are where the failures showed.
  Date/Author: 2026-11-13, the executing session, on M2.

- Decision: the run's record gains `startedAt` and `phase`; the guarded
  forks' ids persist apart from the record; the guard fails closed while
  it cannot establish who a fork is; a notice rides only a result that
  reaches the main conversation (by the dispatch's origin as well as the
  loop, since a plugin's own `$.tool.call` has no `agentId` and its
  result's context enters nothing).
  Rationale: M2's review. A reload after a run closed left that fork
  unguarded, and a failed restore left an open run's fork unguarded; a
  reload between a committed publish and the record's close reported
  `FAILED` for a written page; an internal call of another plugin took the
  notice and dropped it.
  Date/Author: 2026-11-13, the executing session, on M2's review.

- Decision: one note per change, at its first place, with every place it
  changed marked under the note's id; acceptance 3 stays as written. A note
  per changed place was considered and rejected.
  Rationale: asked to change one figure, the fable fork anchored 6 notes
  and the opus fork 5, one wherever the figure or one derived from it
  appeared, reading "a note at that place" per place. The human asked of
  notes that they stay compact and go with one check each; six checks for
  one thing to know is the accumulation they ruled out. The base already
  draws a note at its first anchor and highlights every mark of its id.
  Date/Author: 2026-11-13, the designing session, on M2's owner-model runs.
- Decision: acceptance 3, 4, 5 and 8 are judged on owner-model runs (fable
  and opus); haiku's result is recorded beside its wandering forks as the
  same limit of this version. The server's enforcement of acceptance 5
  (recording at publish that an update owes no notes, `window.PANEL`
  carrying those update numbers, the base drawing none of their notes) was
  considered and not taken.
  Rationale: fable held acceptance 5 (0 notes on an unseen page); the
  failure it would prevent is a few notes on a page read for the first
  time, dismissed with a click, shown only on a model the version already
  declares unreliable, which does not justify reopening M1's reviewed
  interface. A later version can take it up if an owner model misses.
  Date/Author: 2026-11-13, the designing session, on M2's runs.

## Outcomes & Retrospective

Pending — written at finish.
