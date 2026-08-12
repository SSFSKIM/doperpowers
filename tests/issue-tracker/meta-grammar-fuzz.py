#!/usr/bin/env python3
"""Property fuzz over the board:meta opener walk (_board.meta_match).

Which opener starts the real block is decided by content, and that rule was
hand-corrected three times — each time by a body shape the previous
formulation missed, and twice by a shape an EARLIER formulation had handled.
The case pins in test-board-scripts.sh are therefore a record of what was
found, not evidence of coverage. This is the coverage: bodies composed from a
component grammar with the intended opener recorded at generation time.

It has teeth. Against the three superseded implementations, at the default
seed and size, it reports:

    7daa2122 (rightmost walk)                        2004 / 5000
    dc896415 (adjacent-candidate gap)                 182 / 5000
    c71a8670 (whole interior, \\n-split, last-cand.)   954 / 5000

Run against another implementation with BOARD_SCRIPTS=<dir>; that is how a
candidate rewrite of the rule should be judged before it lands.

Properties, per body:
  P1  meta_match picks the opener the generator intended
  P2  strip_meta returns the generated prose
  P3  the rewrite (compose_body over strip+parse) lands on one block, keeps
      the prose, and is idempotent
  P4  the block's bytes survive verbatim from the match offset — what
      board-body.sh's raw splice carries through

Two regions are excluded because the body genuinely does not determine the
answer, not because the rule is weak there:

  - A quoted example that is all-legal `key: value` lines with no closer, no
    blank line and no prose before the real opener is byte-indistinguishable
    from a legacy block whose value carried a nested marker (spec v1.2.4).
    The generator always closes the prose with a colon-free guard line.
  - A block whose illegal interior line PRECEDES a nested marker in the same
    block — `<!-- board:meta / weird: x / <!-- board:meta / pr: v / -->` — is
    equally indistinguishable from a block starting at the nested opener. The
    generator emits nested markers before any illegal interior line.
"""
import os
import random
import sys
import traceback

_HERE = os.path.dirname(os.path.abspath(__file__))
_DEFAULT = os.path.join(_HERE, "..", "..", "skills", "issue-tracker", "scripts")
sys.path.insert(0, os.environ.get("BOARD_SCRIPTS", _DEFAULT))
import _board as B  # noqa: E402

SEPS = ["\n", "\r", "\r\n", "\v", "\f", "\x1c", "\x1d", "\x1e", "\x85",
        "\u2028", "\u2029"]
WORDS = ["board", "ticket", "prose", "docs", "review", "relay", "lane"]
UNKNOWN_KEYS = ["weird-key", "x-legacy", "Note", "TODO", "spawned_by", "PR"]
OPENER = "<!-- board:meta"


def words(rng, lo=1, hi=3):
    return " ".join(rng.choice(WORDS) for _ in range(rng.randint(lo, hi)))


def known_kv(rng):
    """Legal block interior — and the dangerous kind of prose line."""
    return "%s:%s%s" % (rng.choice(B.META_KEYS), rng.choice([" ", "  "]),
                        words(rng))


def illegal_kv(rng):
    """`key: value` with a key that is not ours: noncanonical block content
    inside a block, ordinary prose outside one."""
    return "%s: %s" % (rng.choice(UNKNOWN_KEYS), words(rng))


def guard(rng):
    """A line that can never be block interior — no colon at all."""
    return words(rng, 2, 5)


def prose_element(rng):
    """A prose line, or a whole quoted example. Returns (lines, self_guarding),
    where a quoted example guards itself only by supplying its own `-->`."""
    r = rng.random()
    if r < 0.22:
        return [guard(rng)], True
    if r < 0.36:
        return [""], True
    if r < 0.48:
        return ["%s:" % guard(rng)], True            # "Docs about the block:"
    if r < 0.60:
        return [illegal_kv(rng)], True
    if r < 0.68:
        return [known_kv(rng)], False                # legal-looking prose
    lines = [OPENER, known_kv(rng)]
    if rng.random() < 0.35:                          # quoted legacy-nested
        lines += [OPENER, known_kv(rng)]
    if rng.random() < 0.3:
        lines.append(illegal_kv(rng))
    closed = rng.random() < 0.7
    if closed:
        lines.append("-->")
    indent = rng.choice(["", "", "  ", "    "])
    lines = [indent + ln for ln in lines]
    sep = rng.choice(SEPS) if rng.random() < 0.45 else "\n"
    if sep != "\n":                                  # folds onto one \n-line
        return [sep.join(lines)], closed
    return lines, closed


def real_block(rng):
    """The one intended trailing block."""
    interior = [known_kv(rng) for _ in range(rng.randint(1, 3))]
    if rng.random() < 0.4:                           # a legacy nested marker
        interior.append(OPENER)
        interior += [known_kv(rng) for _ in range(rng.randint(1, 2))]
    fallback = rng.random() < 0.45
    if fallback:                                     # …then noncanonical lines
        for _ in range(rng.randint(1, 2)):
            interior.append(rng.choice([illegal_kv(rng), "# %s" % guard(rng),
                                        "<!-- %s -->" % guard(rng)]))
    return interior, fallback


def make_body(rng):
    lines = []
    for _ in range(rng.randint(0, 6)):
        el, self_guarding = prose_element(rng)
        lines += el
        if not self_guarding:
            lines.append(guard(rng))
    if lines:
        lines.append(guard(rng))                     # the structural guard
    prose = ""
    for i, ln in enumerate(lines):
        if i:
            prose += rng.choice(SEPS) if rng.random() < 0.3 else "\n"
        prose += ln
    interior, fallback = real_block(rng)
    block = "%s\n%s\n-->\n" % (OPENER, "\n".join(interior))
    attach = rng.choice(["\n\n", "\n"]) if prose else ""
    return {"body": prose + attach + block, "opener": len(prose) + len(attach),
            "prose": prose + attach, "block": block, "fallback": fallback}


def check(c):
    body, want = c["body"], c["opener"]
    bad = []
    m = B.meta_match(body)
    if m is None or m.start() != want:
        return [("P1", "opener %s, wanted %d" % (m and m.start(), want))]
    base = B.strip_meta(body)
    if base != c["prose"].rstrip("\n"):
        bad.append(("P2", "strip=%r wanted %r" % (base, c["prose"].rstrip("\n"))))
    if body[m.start():].strip("\n") != c["block"].strip("\n"):
        bad.append(("P4", "block bytes not verbatim"))
    meta = B.parse_meta(body)
    if not meta:
        return bad                       # an all-unknown block is dropped, by design
    b2 = B.compose_body(base, meta)
    # compose_body always writes `base.rstrip("\n") + "\n\n" + block`, an empty
    # base included (the block then carries two leading newlines — cosmetic,
    # and idempotent).
    want2 = len(base.rstrip("\n")) + 2
    m2 = B.meta_match(b2)
    if m2 is None or m2.start() != want2:
        bad.append(("P3", "rewrite opener %s, wanted %d" % (m2 and m2.start(), want2)))
    elif B.strip_meta(b2) != base.rstrip("\n"):
        bad.append(("P3", "rewrite dropped prose"))
    elif B.compose_body(B.strip_meta(b2), B.parse_meta(b2)) != b2:
        bad.append(("P3", "rewrite not idempotent"))
    return bad


def main():
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 20260813
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 5000
    rng = random.Random(seed)
    kinds, shown = {}, []
    for i in range(n):
        c = make_body(rng)
        try:
            bad = check(c)
        except Exception:
            bad = [("EXC", traceback.format_exc().strip().splitlines()[-1])]
        for prop, detail in bad:
            kinds[prop] = kinds.get(prop, 0) + 1
            if len(shown) < 5:
                shown.append((i, prop, detail, c))
    print("seed=%d n=%d divergences=%d %s"
          % (seed, n, sum(kinds.values()), kinds or "(none)"))
    for i, prop, detail, c in shown:
        print("\n--- iter %d %s: %s\nbody=%r\nwant_opener=%d fallback=%s"
              % (i, prop, detail, c["body"], c["opener"], c["fallback"]))
    return 1 if kinds else 0


if __name__ == "__main__":
    sys.exit(main())
