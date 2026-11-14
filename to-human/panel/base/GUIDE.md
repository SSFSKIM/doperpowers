# The panel's base

A panel is one HTML page on this base. The page holds content only: `panel.css` gives it type, spacing, colours
(light and dark), tables and `details`; `panel.js` draws the notes, the count at the top and the reload. Compose
with plain HTML (headings, paragraphs, lists, tables, `details`, `code`, `pre`) and any of the blocks below,
or with your own inline styles and SVG where they lack something. None is required.

## The page

- Keep the two base links in `<head>` as the starter has them: `<link rel="stylesheet" href="/base/panel.css">`
  and `<script src="/base/panel.js" defer></script>`.
- `<html lang>` is the page's language: `en` or `ko`.
- Set `<title>` to what the page is about.
- Content goes straight in `<body>`. No scripts of your own (they do not run), nothing loaded from another site
  (it does not load), and no `<meta http-equiv>`, `<base>` or `<link>` beyond the stylesheet (publishing cuts
  them).

## A note

Where an update changes something the human has seen, mark the changed phrase and write the note after the
block that holds it (an `<aside>` inside a `<p>` ends the paragraph), or at the end of the list item or table
cell that holds it:

```html
<p>The server runs <mark data-note="u3-1">on every machine</mark>.</p>
<aside class="note" id="u3-1" data-label="Changed by your answer">Was: the MacBook only. You asked for the hosts.</aside>
```

The id is `u<update>-<k>`, one per change. `data-label` is optional: a few words on what made the change. The script places the
note beside its mark in the margin, or under it on a narrow window, and adds its check button; a note the human
checked off never draws.

One change is one note, however many places it touched: write its `<aside>` once, at the first place it shows,
and mark every other place it changed (a figure repeated in a table, a total derived from it) with a `<mark>` of
the same id. The script draws the note at its first mark, highlights every mark, counts it once, and one check
clears them all. Deleting a checked note deletes its `<aside>` and every `<mark>` of its id.

```html
<p>Osprey costs <mark data-note="u3-1">about 120 dollars a month</mark>.</p>
<aside class="note" id="u3-1" data-label="Osprey's cost changed">Was: about 90. The vendor's new price.</aside>
<p>The gap is <mark data-note="u3-1">80 dollars a month</mark>.</p>
```

## Blocks

**Needs you**: what awaits the human, at the top. The label is yours to write, in the page's language.

```html
<section class="ask"><p class="label">Needs you</p>
  <h2>Approve the design, or say what to correct</h2><p>The session asks in the dialog.</p></section>
```

**Callout**: one point set apart from the text around it.

```html
<div class="callout">
  <p><strong>Measured:</strong> an edit took 4.7 minutes.</p>
</div>
```

**Option comparison**: side by side where the window has room; `pick` marks the one recommended.

```html
<div class="options">
  <section class="option pick"><p class="tag">Recommended</p><h3>A. One server</h3><ul><li>…</li></ul></section>
  <section class="option"><h3>B. One per session</h3><ul><li>…</li></ul></section></div>
```

**Diagram frame**: an inline SVG; `data-min` keeps a wide one from shrinking below 620px (it scrolls instead).
Classes for its parts: `box`, `bg`, `line`, `dash`, `accent`, `fill-accent`; text `soft`, `lane`.

```html
<figure class="diagram"><svg viewBox="0 0 720 120" role="img" aria-label="…" data-min>
  <rect class="box" x="10" y="40" width="140" height="40" rx="3"/><text x="80" y="65" text-anchor="middle">present</text>
</svg><figcaption>One call, over time.</figcaption></figure>
```

**Quoted wording**: text exactly as it would be written (a prompt, a description, a rule), headed by what it is;
as `details` it folds.

```html
<div class="wording"><h3>The tool's description</h3>
  <pre>Put something on this session's panel for the human.</pre>
</div>
```

**Older material**: settled content kept for reference goes at the bottom, folded behind a one-line summary.

```html
<details class="older"><summary>Settled earlier: the transport and the port</summary>
  <p>…</p>
</details>
```

Smaller pieces: `p.meta` (a dim line under the title), `p.lead` (the opening sentence), `.soft` (dim text),
`td.k` (a bold first cell), `footer`.
