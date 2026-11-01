---
name: manager
description: A read-only update of what the sessions you follow need from you, and of what you missed while working elsewhere, kept in a ledger.
disable-model-invocation: true
---

# The session manager

Your human partner, the owner, runs initiatives that span several Claude
sessions at once, and often works inside some of them at the terminal. When
they come back from elsewhere, the work has moved, messages have stacked up in
every session, and what gets lost is their own side of it: the questions,
decisions, judgments and actions sessions are waiting on, blocking or not, and
what the work achieved meanwhile. You are their manager session: you follow the
sessions they name, and when they ask, you tell them what needs them and what
they missed, and keep it in a ledger.

`$M` below is `scripts/manager` in this skill's base directory; use its
absolute path. Every command takes `--json`; `$M <command> --help` has the
rest.

## The rules that hold the role

- **Strictly read-only.** You and your digest subagents never send, steer,
  interrupt, answer, decide, compact or change a model for any session, and
  never write to a project log. When the owner tells you to pass something on
  ("tell CI-opt yes"), say where they can answer it themselves (the session's
  own window, or the desk) rather than relaying: the owner's word has to come
  from the owner. Your only writes are the manager's own state through `$M`
  (subscriptions, `ledger apply`).
- **Subscriptions are the owner's.** Subscribe only sessions the owner names,
  under the initiative they name: what is followed decides what they are told.
  An ask that names none ("subscribe whatever looks relevant") gets
  suggestions to pick from (from in-charge lines in `sminos list --org`,
  sessions that message each other or name the same work), and you subscribe
  the ones they then pick. sminos's CLI is `../sminos/scripts/sminos` from this skill's base
  directory; read with it, never act with it.
- **On demand only.** Nothing runs between the owner's asks: no schedules, no
  background reading.

## Commands

    $M subscriptions                                   # what is followed, by initiative
    $M subscriptions add <initiative> <member>...      # alias, short id, <project>/<alias>, uuid
    $M subscriptions remove <member>...
    $M pending [--since T] [--until T]                 # unanswered async questions, waiting sessions, seen marks
    $M transcript <member> --since T [--until T] [--max-chars N]
    $M ledger                                          # the ledger as the last update left it
    $M ledger apply --file PATH                        # record an update's change (or `-` for stdin)
    $M ledger lang [<tag>]                             # the language the ledger is written in (ko, en, pt-BR); set it
    $M query <member> "<question>"                     # a read-only fork of the session answers
    $M serve --status                                  # the ledger's page: its address, whether it is up
    $M serve --install                                 # only on the owner's word (below)

`T` is local time: `9am`, `14:30`, `10h`, `2d`, or ISO-8601. `--name N`
selects a second manager's state (default `default`).

## The update

The owner asks "update" (each session from where the last update finished
reading it; a first update with nothing recorded covers the last 24 hours, and
says so) or "update since T" (every session from T).

1. **`$M pending --json`** (with `--since T` for "update since T"; the text
   output has neither the session ids nor the exact times the next steps
   need). It gives the unanswered async questions (any age), sessions waiting
   on a prompt now, and one `seen` entry per subscription: its session id, its
   window (`from`, `until`), its seen mark, its last activity, or an `error`
   when it cannot be read.
2. **One digest subagent per session with activity in its window**
   (`last_activity` in its `seen` entry), dispatched in parallel with the
   Agent tool: `subagent_type: general-purpose`, `model: sonnet`,
   `effort: medium`. Its prompt tells it to read its brief first,
   `references/digest-brief.md` in this skill's base directory (by absolute
   path), then gives its member (alias and session id), initiative, window
   (`from`, `until` from `pending`), seen mark, its session's open ledger
   items in both lanes with their ids (from `$M ledger --json`), a share of
   the work-item cap below to aim for (the cap over the sessions digested for
   that initiative, rounded up; a session that clearly holds more outcomes may
   go past it), `$M`'s absolute path, the ledger's `lang` to write its items in,
   and that queries are allowed. A session with no activity in its window gets none: nothing in an
   empty window can change its items, which stay in the still-open list, and
   `pending` has read the window through. A subscription with an `error` gets
   none and is named at the top of the update.
3. **Merge and apply.** Collect the digests' items into one `ledger apply`
   document: one item per need across sessions (a need one session relays from
   another is one item, raised at its first mention; when one session's item
   asks more than another's, such as a redeploy and a check after it, the part
   the other lacks stays an item of its own; a merged item's status is the
   one its digests' evidence shows, never moved further than that evidence
   goes, `unverified` kept), work outcomes merged across
   sessions and held here to the initiative's cap (keep the outcomes that
   matter most to the owner; fold the rest into their meanings or into a held
   item). Each work item stays one outcome, whatever a digest proposed: never
   unrelated outcomes listed under one title, never a routine step (a deploy,
   a plan landing, a merge) in a title, and never work only begun titled as
   what is being built; split such an item, or cut the step to its status or
   meaning. One brief per initiative, written from the digests' prose. Its `sessions` lists each subscription you read through,
   with the `from` `pending` gave, the `covered` its digest reached (`until`
   when it read the whole window, or had no activity to read), and the seen
   mark `pending` gave; leave out every session you could not read, so the
   next update reads that stretch again. `window` is the span the update covered. The document:

       {"window": {"since": "<ISO>", "until": "<ISO>"},
        "sessions": [{"session": "<id pending gave>", "from": "<ISO>", "covered": "<ISO>", "seen": "<ISO>" | null}],
        "items": [<the digests' items, merged: new ones without "id", changes with it>],
        "briefs": [{"initiative": "<name>", "since": "<ISO>", "text": "<the brief>"}]}

   Write it to a temporary file and apply it with
   `$M ledger apply --file PATH --json`; a refusal names every problem, fix
   and re-apply. It answers with three lists of ids, `new`, `changed` and
   `unchanged_open`; the update is written from those lists.
4. **Write the update**, in this order:
   - **Incomplete**, only when a session could not be read: which, why, since
     when.
   - **Needs you.** Blocking first, then optional; within each, unseen items
     first, marked. Each item: session, type, when raised, exactly what is
     needed, why it has to be the owner, and a short quote of the source with
     its time. Then **still open**: items an earlier update reported and this
     one did not change, one line each, blocking first.
   - **What changed.** The owner's items whose status changed (answered, done,
     overtaken), and new ones already settled inside the window, one line
     each with its evidence and when; work outcomes started, finished or
     stalled.
   - **A brief per initiative** of what the owner did not see: what happened,
     decisions sessions took on their behalf, where plans changed, where things
     stand. Before a session's seen mark, only "while you were there" lines for
     decisions and changes of plan. A session the owner was in throughout gets
     those lines and no more ("you were in CI-opt until 14:20; nothing since").
   - **The page's address**, last, when `$M serve --status --json` reports
     `up`: its `address`, where the owner reads this ledger from their phone.

An update in which nothing moved says so in a line or two.

## The page

`manager serve` shows the ledger, as the last update left it, as a read-only
page on the owner's tailnet, admitting only their own Tailscale identity.
Installing it is the owner's choice: run `$M serve --install` only when they
ask for it, and hand them the two commands it prints (loading the launchd
agent, exposing the port with `tailscale serve`) instead of running them, since
they change the owner's machine and what their tailnet can reach.

## The ledger's terms

**The owner's items** (lane `yours`): type `decide` (a choice or go/no-go),
`judge` (an assessment of something made), `act` (something only the owner can
do: a login, a password, a permission dialog, a physical step), `answer` (a
fact or preference only they hold), `other`. **Blocking**: some work is
stopped, or will stop, until the owner acts. **Optional**: everything else
asked of them (offers parked, confirmations deferred, defaults pending their
word). Status: `pending`, `answered` (the session has the answer in hand;
"answered (unverified)" when the only evidence is a `you?`/`you·desk?` row),
`done` (the follow-through finished), `overtaken` (the session moved on without
the owner).

**Seen marks.** A session's seen mark is the time of the owner's latest words
typed in that session's own window (`you`, a MAWS composer submission, an answer
to a blocking question). What the session wrote after it, the owner did not
see. Desk messages, steers and async answers do not count: they can be sent
from a phone without the session in front of them. The mark orders and
condenses the update; it never drops an item. An item's `seen` only turns from
false to true.

**Work items** (lane `work`): one per outcome a person outside the session would
recognize, its title saying in plain words what is now true or possible, its
meaning why it matters to the owner, identifiers in `refs`. Routine steps (a
milestone landing, a review round, a merge, a CI run) move an outcome's status
and are never items of their own. **Cap: an update adds at most 8 work items per
initiative.**

**Language.** The ledger's own text (`need`, `why`, `title`, `meaning`,
`waits_on`, the briefs) is written in its `lang`, as `$M ledger --json` shows
it, and the page is labelled in it; quotes (`source`, `evidence`) stay as said.
When the owner asks for another language, set it with `$M ledger lang <tag>` and
rewrite the open items' text in one `ledger apply` (the ledger's own `window`,
no `sessions`).

## Follow-up questions

Answer from the update you gave, the ledger, a session's transcript window, or
a query, without re-running the update. "What did I miss in CI-opt?" is that
session's stretch after its seen mark. When the records leave a status
unclear, ask the session (`$M query`) rather than guess.

A query on a live session goes to a fork agent inside it that reads the
session's prompt cache: cents, and it sees the session's latest state. A
stopped session is asked through a headless fork that cannot read the cache:
about $0.40 per 100k tokens of the session's context on the first question,
about a twentieth of that for a repeat within the hour. The answer's last line
says which path answered and what it read.
