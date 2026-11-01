# The manager's page: design law

The page (`page.html` beside this file) is the session manager's ledger, read on the owner's phone over their
tailnet. One file, its CSS and script inline, no external asset; it renders `/ledger.json` and refetches on
`/events`. This file is the law the page is checked against; the token block at the top of `page.html` holds the
values.

## 0. Stance

**Commitment.** A clerk's ledger: the owner's debts written in serif on pale-green columnar paper, the metadata
stamped in mono in the margin, and the one thing that stops work, a blocking item, inked in red. It is not a
dashboard: no cards, no metric tiles, no charts, no badges in a rainbow.

*If a decision is ever ambiguous, choose the more legible-at-a-glance option.*

**Axis position.**
- Density: standard. Items are sentences (a need, a reason, a quote), read on a 375 px phone; nothing is operated on.
- Criticality: transactional. The page acts on nothing, but a misread blocking item costs hours of stalled work, so no state is told by hue alone.
- Energy: quiet. It is glanced at between other things; nothing may ask for attention that a blocking item has not earned.
- Type: humanist serif for words, mono for metadata. Criteria: a text serif with open counters and a large x-height at 17 px; a mono with tabular figures for times and ids. System faces only (the page loads with nothing reachable but the Mac).
- Material model: printed. A ledger is paper; nothing floats over changing content.
- Color commitment: restrained. Chromatic surface under 5%: the red ink and nothing else.
- Accent job: status-only. Red means exactly "blocking: a session waits on you".
- Ground lightness: light and dark, following the system setting (scene below); one role set, two grounds.
- Ground temperature: cool, pale green. Accountants' columnar paper.

**Rejected vector.** Quiet / neutral sans / tonal / restrained / directional / light / neutral gray: the modal
status-dashboard position. Lost because it carries nothing of what the page is (an account of what is owed) and
would land on the gray card stack every console lands on.

**Derivation.**
- Accent hue: red ink, oklch hue 27. A ledger writes what is owed in red; the owner's blocking items are exactly what they owe. *Rejected:* amber (h 75), the "waiting" signal, which reads as caution and would make blocking look optional.
- Ground: the scene is one person, away from the desk, taking out a phone on a train, in a café or in bed at night, to see whether a session is stuck on them; both a lit room and a dark one are real, so the page follows `prefers-color-scheme`. Light ground: pale green-gray paper (L 0.975, C 0.010, h 160). *Rejected:* warm cream paper (L 0.95, h 85), the reflex "paper" answer in the cream band. Dark ground: green-black (L 0.19, C 0.012, h 160), the same paper with the light off.
- Type: Iowan Old Style (iOS and macOS ship it; a humanist text serif) falling back to Palatino, `ui-serif`, Georgia; mono is `ui-monospace` (SF Mono), Menlo. A web font would be an external asset or a base64 blob larger than the page.

**Signature.** The margin: every item is a ledger line with a narrow mono margin (time raised, type) and the
serif need to its right; a blocking item's margin carries the red stamp `blocking`. The rest stays quiet.

**Clone test.** A different status page in this category may share standard / transactional / quiet; it must not
share red-ink-on-green-paper, the margin stamp, or serif needs.

## 1. Palette

Roles (tokens in `page.html` `:root`): `--ground`, `--ink` (text), `--ink-muted` (secondary text, the margin),
`--rule` (hairlines, `--ink` at an alpha), `--rule-strong`, `--red` (the accent), `--red-ground` (the stamp's
fill, `--red` at a low alpha). `--red` is the accent and carries one job: blocking. It appears on the blocking
stamp, the blocking count in the summary, and the double rule under a blocking group; nowhere else. No other hue.
Unseen, new, stalled and unverified are told by words and glyphs in `--ink`, never by color. No color literal
outside `:root` and its dark-mode block.

## 2. Typography

- `--serif`: needs, work titles, quotes, the brief, headings. Body 17 px / 1.45; a need line 17 px regular; an initiative heading 26 px semibold; a section heading 19 px semibold.
- `--mono`: times, the type word, session aliases and ids, refs, the stamp, counts. 12.5 px, tabular figures; lowercase, never tracked all-caps.
- Quotes are serif italic. Prose runs at most 68ch. No third family; no sans.

## 3. Canvas and material

Printed: `--ground` flat at the root, no texture, no gradient, no shadow anywhere (there is no modal).
Structure is hairlines (`--rule`) and whitespace; the one heavier mark is the double rule closing a blocking group.

## 4. Layout

**Six lines.**
1. Posture: transient. A glance, passed through, on a phone: one column, no secondary pane.
2. Activity: monitor. The first read answers "is anything stuck on me"; success is knowing in seconds.
3. Unit and relation: the unit is the owner's item (and the work outcome); the relation is a sequence inside a hierarchy (initiative, then status group, then items ordered blocking, unseen, raised).
4. Co-visibility: on demand. An item expands in place to its reason, quote, session and times.
5. Temporal: live. Updates arrive over `/events`; the header carries the freshness (update time, age, connection).
6. Volume and homogeneity: few pending (typically under 15) heterogeneous across lanes; done can run to 80+, so older done sits behind a disclosure.

**Compiled.** Dominant region: the first initiative's blocking items, first in DOM order after a slim header.
Reading order: header (freshness, one summary line per initiative), then per initiative: Needs you (blocking,
then optional), Roadmap (when the initiative has one), Answered, Work in progress (stalled first), Done (7 days;
older disclosed), Brief (collapsed).
Columns: one, max 40rem, the margin column 4.5rem inside each item line. Density lives in the done list and the
roadmap (one row per item or part). Repeats: item lines within a group, part rows within the roadmap.

**Roadmap.** The initiative's whole plan, which can run to 30 parts or more on a phone, so every part is a compact
row (its id in the margin, title, status stamp, owner) and expands, never the section. Ids stay aligned in the
margin column at every depth; nesting indents the title (16 px, then 32 px), so a third-level title keeps its width.
Top-level titles are semibold; done, deferred and dropped titles are `--ink-muted`, a dropped one struck through,
with the status always said by the stamp. A part's changes dated after the last update's window start are its
news: the row counts them (`2 new`) and the expanded list marks each, so movement shows without opening anything.

**Ledger.**
| Brief evidence | Relationship | Constraint | Rendered assertion | Forbidden |
|---|---|---|---|---|
| "the owner's items before everything" | blocking debts lead | Needs you is the first section of each initiative | `section.needs` precedes every other section in DOM order | a stats row above it |
| "type and blocking legible at a glance" | each item is a ledger line | margin column with time and type, stamp for blocking | every pending item has `.margin` with a type word | colored chips, icons without words |
| "unseen items marked" | a property of an item | glyph plus word | `●` and `unseen` in the meta line | color alone |
| "Done, the last 7 days, older behind a disclosure" | a long tail | compact rows, `details` for older | done rows have no expansion; older behind one `details` | a card per done item |

**Chosen.** Per-initiative stacked sections in one column, with a summary line per initiative in the header
linking to it. *Rejected:* all Needs you across initiatives first, then each initiative's work (splits an item from
its initiative's brief and work; the spec reads the page per initiative, and most owners run one or two).

**Defaults overridden by name.** No stat row, no card grid, no sidebar, no tab bar, no sticky footer.

**Collapse.** Phone first at 375 px. From 48rem the column centers at 40rem with wider margins; nothing else changes.
Spacing scale: 4, 8, 12, 16, 24, 32, 48.

## 5. Component canon

- `item` (a `details`): `.margin` (mono: time over type) and `.body` (serif need or title; a mono meta line: member, stamp, marks). Expanded: why, quote, session, raised, status and evidence.
- `stamp`: mono word in a 1 px box, radius 2 px; `blocking` in `--red` on `--red-ground`. The only boxed element.
- `doneRow`: one line, mono date in the margin, serif text, a mono status word (`done`, `overtaken`).
- `group heading`: serif 19 px with a mono count.
- The brief: one `details`, summary in mono metadata, prose in serif paragraphs.
- `step` (a roadmap part, a compact `item`): `.margin` the part's id; `.body` the serif title and a meta line
  (status stamp, owner, the count of new changes). Expanded: what it is, now, what it waits on, owner, refs, then
  its changes newest first (mono date and `new` over the serif text). Its children follow it, indented.
- The roadmap's head: purpose and done-when in serif with mono labels, then the source and when it was written in
  mono.

## 6. Voice

Plain, short, second person ("Nothing needs you in P5"). Sentence case. Times as the phone's local clock, `14:32`
today, `Oct 30 14:32` otherwise. Empty states name what is absent and what will change it. No em dashes.

Every word the page itself says comes from its per-language table, picked by the ledger's `lang` (English when it
has no table); dates follow that locale, times stay on the 24-hour clock (`10월 30일 14:32`). Korean is plain 해요체
for sentences and bare nouns for labels, the owner's own side said from their view (`내 차례`), never `당신`.

## 7. Motion

None. An update re-renders in place; open disclosures stay open across a re-render (kept by item id).

## 8. Hard don'ts

- No `box-shadow`, `backdrop-filter`, gradient or texture.
- No hue other than `--red`, and `--red` only on blocking.
- No `border-left`/`border-right` heavier than 1 px on any item.
- No all-caps tracked labels, no icons, no emoji.
- No control that sends anything: the only interactive elements are `details` disclosures and in-page links.
- Every piece of ledger text is set with `textContent`; no `innerHTML` with data.
