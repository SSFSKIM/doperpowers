#!/usr/bin/env python3
"""transcript-compare.py — the transcript-diff drill's judge.

Reads two capture files (one step per line, JSON: {i, argv, argv_raw, rc, out})
produced by running THE SAME verb sequence under the two bindings, and reports,
per step, whether the worker-visible surface is the same.

Two levels, and the split is the whole point:

  STRICT   the argv and the exit status must match, step for step. "Same
           scripts, same arguments, same refusal vocabulary" (spec § Purpose)
           begins here: if the two bindings disagree about whether a call is
           legal, nothing downstream is comparable. The argv compared is
           `argv_raw` — the step as WRITTEN, `%T` unsubstituted — because each
           walk registers its own ticket and the two ids are never equal. The
           alternative, normalizing digits out of the executed argv, would also
           erase step 6's literal 4242, and that step is precisely the known
           ticket / unknown ticket distinction.

  NORMALIZED  stdout/stderr is compared after transport tokens are erased —
           urls, timestamps, ids, session uuids. What survives that is content,
           not transport, so a difference is either a real divergence or a bug.
           Each surviving difference must be named in PINNED below, with the
           reason it is transport-bound. An UNPINNED difference fails the
           drill, and so does a PINNED one that stopped happening: the table
           is a claim about the current adapter, and a stale claim is worse
           than none.

Prints one line per step (`STEP n IDENTICAL` / `STEP n DIVERGES(tag)` /
`STEP n UNEXPECTED-DIVERGENCE` / `STEP n PINNED-BUT-IDENTICAL(tag)`), the
offending text for anything unexpected, and a trailing VERDICT line.
"""
import json
import re
import sys

# Transport tokens. Everything here is a value the two substrates cannot agree
# on by construction — where the board lives, what it numbers things, what
# time it is — and NOTHING here is content the worker would act on.
NORMALIZERS = [
    (re.compile(r"https?://\S+"), "<URL>"),
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"), "<UUID>"),
    (re.compile(r"\b\d{4}-\d{2}-\d{2}T[0-9:.+]+Z?\b"), "<TIME>"),
    (re.compile(r"\b\d{4}-\d{2}-\d{2}\b"), "<DATE>"),
    (re.compile(r"#\d+"), "#N"),
    (re.compile(r"\banswer \d+\b"), "answer <N>"),
    (re.compile(r"\b[0-9a-f]{8}\b"), "<HEX8>"),
    (re.compile(r"^\d+(?= <URL>)", re.M), "<N>"),
    (re.compile(r"^\d+$", re.M), "<N>"),
]

# The pinned divergence table: step index → (tag, why it is transport-bound).
PINNED = {
    2: ("list-row-shape",
        "gh mode derives ELIGIBLE/waiting tags from a whole-board snapshot; the API "
        "list is the server's own ordered rows and says so in its header"),
    3: ("transition-echo-omits-from-state",
        "the API transition response carries only the state WRITTEN — the client has "
        "no snapshot to name the state it came from, and reading one back would be a "
        "second round trip for an echo"),
    4: ("comment-echo-event-id-vs-url",
        "a gh comment is addressable by URL; an API comment is a ledger event and its "
        "id is the only handle that exists"),
    5: ("refusal-wording-pr-required",
        "the PR requirement is adjudicated client-side in gh mode and server-side in "
        "API mode, so the sentence is written by whichever holds the rule"),
    6: ("refusal-wording-unknown-ticket",
        "gh mode resolves the ticket against its snapshot before any call; the API "
        "learns of it from the server's 404"),
    7: ("transition-echo-omits-from-state", "see step 3"),
    8: ("relay-report-shape",
        "gh mode relays by resuming a registry-resolved session and reports that "
        "session; API mode records the answer server-side and reports the delivery "
        "the sweep made, keyed by the answer's own id"),
    9: ("refusal-wording-illegal-transition",
        "the legality table lives client-side in gh mode and server-side in API mode; "
        "both name the same edge (asserted separately by the drill)"),
    10: ("transition-echo-omits-from-state", "see step 3"),
    11: ("transition-echo-omits-from-state", "see step 3"),
    12: ("show-shape",
         "gh mode prints the snapshot node as JSON; the API ticket's history IS its "
         "server-side timeline, and there is no node to print"),
    13: ("list-row-shape", "see step 2"),
}


def norm(text):
    for pat, rep in NORMALIZERS:
        text = pat.sub(rep, text)
    return text.strip()


def load(path):
    with open(path) as f:
        return {int(json.loads(l)["i"]): json.loads(l) for l in f if l.strip()}


def main(gh_path, api_path):
    gh, api = load(gh_path), load(api_path)
    steps = sorted(set(gh) | set(api))
    bad = 0
    for i in steps:
        g, a = gh.get(i), api.get(i)
        if g is None or a is None:
            print("STEP %d MISSING (gh=%s api=%s)" % (i, g is not None, a is not None))
            bad += 1
            continue
        if g["argv_raw"] != a["argv_raw"]:
            print("STEP %d ARGV-MISMATCH\n  gh : %s\n  api: %s"
                  % (i, g["argv_raw"], a["argv_raw"]))
            bad += 1
            continue
        if g["rc"] != a["rc"]:
            print("STEP %d RC-MISMATCH (gh=%s api=%s)\n  gh : %s\n  api: %s"
                  % (i, g["rc"], a["rc"], g["out"].strip(), a["out"].strip()))
            bad += 1
            continue
        same = norm(g["out"]) == norm(a["out"])
        pin = PINNED.get(i)
        if same and not pin:
            print("STEP %d IDENTICAL  %s" % (i, " ".join(g["argv_raw"])))
        elif same and pin:
            print("STEP %d PINNED-BUT-IDENTICAL(%s) — the table is stale, drop the entry"
                  % (i, pin[0]))
            bad += 1
        elif pin:
            print("STEP %d DIVERGES(%s) — %s" % (i, pin[0], pin[1]))
        else:
            print("STEP %d UNEXPECTED-DIVERGENCE  %s\n  gh : %s\n  api: %s"
                  % (i, " ".join(g["argv_raw"]), norm(g["out"]), norm(a["out"])))
            bad += 1
    print("VERDICT: %s (%d step(s) unaccounted for)"
          % ("accounted" if not bad else "UNACCOUNTED", bad))


main(sys.argv[1], sys.argv[2])
