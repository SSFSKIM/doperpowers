---
name: present
description: Use when your human partner wants to understand something end to end — work an agent shipped, a design you discussed, a spec, code someone else wrote, or any idea — and invokes /present.
disable-model-invocation: true
---

# Present

Write your human partner an explainer article, as an HTML page, that
leaves them understanding its subject end to end. The subject is what
they named; named nothing, it is what the conversation has been about —
the work just shipped, the design just discussed. It can be anything:
work an agent did while they were not watching, a design, a spec, code
someone else wrote, an idea from any field.

The article succeeds when, having read it once from top to bottom
without stopping to look anything up, they could explain the subject to
someone else in their own words — why it exists, what happens from
start to finish, why it is built that way, where it stops — and predict
what it does in a case the article never walked through. When the
subject is theirs to steer (work shipped for them, a design they will
build on), they can also make the next decision about it without asking
you.

## Thorough

Thorough means the chain has no gap: every step from the problem to the
outcome is there, and every part is explained before the reader needs
it. It does not mean everything the source contains. A detail off that
chain goes in when it changes what the reader would predict or decide.

## Understandable

Write from where the reader stands, not from where your source does.
What they already see of the subject — a command they type, what it
prints back, a behavior they have noticed — is where the explanation
attaches: account for each thing they see, so the article explains their
own experience of it. Before drafting, list for yourself what the
article will lean on that this reader does not have yet — the source's
vocabulary, names coined in the session, the field's jargon — and
explain each in plain words before its first use, inline or in a short
vocabulary ahead of the walkthrough. Name a function, flag or file only
together with what it does, and give its location (`file:line`) once,
beside the prose — a line closing each part, or one table — rather than
inside the sentence. Articles that traced the real code and checked
every fact still lost to plainer ones on the same subject: they used the
source's terms undefined and threaded call chains with line numbers
through every step, so the reader could not follow the depth they
carried.

Simplify by removing the incidental, never the mechanism. A comparison
to something the reader already knows is the shortest way in when its
structure matches: the same parts, acting on each other the same way,
so reasoning about the familiar thing gives right answers about the new
one ("a hash table is a coat check: the ticket number says which hook,
so nobody searches the room — until two coats get the same number").
Say where the match ends. A comparison that only sounds alike teaches
the wrong mechanism: asked to "explain like I'm five", agents produced
emoji headers, cartoon framing ("a magic notebook"), and an analogy that
left the reader unable to predict anything.

## The order the reader meets things

1. **The whole picture** — what it is and the problem it exists to
   solve, short enough that a reader who stops there still holds a
   correct, coarse model. Name the idea the rest follows from, so each
   later detail reads as a consequence rather than one more fact.
2. **One concrete case, traced from start to finish** through the real
   parts: what each part does to it and hands on. Keep it one case all
   the way through, so every value, log line and output shown belongs to
   it; a real event from a different case breaks the thread the reader
   is following. Use real values where you have them (a run you made, a
   log entry of this case) and label invented ones.
3. **The parts and the choices** — how each works and why it is built
   this way, against the alternative it beat.
4. **The boundaries** — what it guarantees and what it does not, where
   it breaks, what it is commonly confused with.

That is the order, not a set of section titles: title each section by
what it says about this subject ("The index is rebuilt, never
patched"), so the contents list alone tells its story. Organize by how
the subject works, not by the shape of your source. Writing from a spec,
agents followed its section order and carried its process history
(review rounds, finding tallies, amendments); writing from commits, they
gave each commit its own section. History earns a place only where it
explains why the thing is built the way it is.

What the subject adds:

- **Work shipped for them:** what behaves differently from where they
  stand; each decision made on their behalf that had a real alternative,
  with the reason, so they can overrule it; what is unverified and what
  would break it; how to see it for themselves.
- **A design or spec:** what is still open, and, once it is built,
  where the built thing has moved on from the document.
- **Code someone else wrote:** the path from entry point to effect, and
  where each part lives.
- **An idea:** when they named their situation, what the idea means for
  it.

## Getting it right

The article is only as complete and correct as your own understanding,
so read the subject through before writing: the code path end to end,
the whole spec, the conversation that settled the design. Check a fact
you are unsure of — a default, a version detail, who uses what — at its
source (the code, the docs, the web) before it goes in. Writing about a
general idea from memory, agents flagged the details they doubted for
the reader to check; that hands the verification to the one person who
cannot do it, and a plausible wrong fact corrupts the model you are
building for them.

A run you make to see the subject work happens on its own copy — a
scratch directory, its own state and ports — and stops only the
processes it started, by the PIDs it holds. The machine around it is
your human partner's live environment: a run that simulated two
machines stopped one with `pkill -f "daemon uplink" -n`, macOS `pkill`
read the trailing `-n` as a second pattern, and every login shell whose
command line held `--noprofile` died, closing all their terminal tabs
and the sessions in them.

## The page

One self-contained HTML file — inline CSS and SVG, no CDN or external
assets — so it renders from disk: a document in a plain register, not a
styled landing page. Draw a diagram where the structure is spatial or
temporal (data flow, a sequence, state over time, before and after), in
SVG or CSS rather than ASCII; draw each SVG on a `viewBox` about the
column's width and give it a width of 100%, so it fits the column
without spilling past it or shrinking its text. Write the file outside
the working tree, since it is for reading rather than committing.

Before handing it over, render it (a headless Chrome screenshot you
Read is enough) and look: hand-drawn SVG came back with labels running
past their boxes, text crossing lines, and arrows missing their heads.
Then open it in their browser. The reply is a few sentences of the gist
and a link to the page.
