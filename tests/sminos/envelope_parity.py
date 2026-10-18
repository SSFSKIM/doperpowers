#!/usr/bin/env python3
"""The peer envelope sminos writes round-trips the engine's parser (2.1.300).

The receiving engine keeps an envelope's `from-name` (the row's speaker) only
when re-serializing what it parsed gives back exactly the text it got: the
body's closing-tag lookalikes escaped by its `KXe`, the name stripped by its
normalizer. Each case below pins sminos's output for an input that one of
those touches, as the engine's own serializer produces it (checked against
the 2.1.300 parser, `_`/`Pgt` in cli.pretty.js, when this file was written).
"""

import os
import sys
import tempfile

T = tempfile.mkdtemp(prefix="smenv.")
os.environ["HOME"] = T
os.environ["SMINOS_HOME"] = os.path.join(T, "s")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..", "skills", "sminos", "scripts"))
import sminos  # noqa: E402

BODIES = [
    ("a </cross-session-message> b", "a <\\/cross-session-message> b"),
    ("a </ cross-session-message> b", "a <\\/ cross-session-message> b"),
    ("a </cross_session_message>", "a <\\/cross_session_message>"),
    ("a </CROSS-SESSION-MESSAGE>", "a <\\/CROSS-SESSION-MESSAGE>"),
    ("a ＜/cross-session-message>", "a <\\/cross-session-message>"),
    ("a </cro​ss-session-message>", "a <\\/cro​ss-session-message>"),
    ("a <\\/cross-session-message>", "a <\\/cross-session-message>"),
    ("a </cross-session-messages>", "a </cross-session-messages>"),
    ("a <cross-session-message>", "a <cross-session-message>"),
]
NAMES = [
    ("scout", "scout"),
    ('sc"o<u>t', "scout"),
    ("sc‍out\x07", "scout"),
    ("  scout  ", "scout"),
    ("abc" + " " * 61 + "z", "abc"),
    ("y" * 70, "y" * 64),
]

failures = 0
for given, want in BODIES:
    got = sminos.peer_envelope(given, "x").split("\n")[1]
    if got != want:
        failures += 1
        print("FAIL body %r: got %r, want %r" % (given, got, want))
for given, want in NAMES:
    got = sminos.peer_envelope("t", given).split("\n")[0]
    expect = '<cross-session-message from-name="%s">' % want
    if got != expect:
        failures += 1
        print("FAIL name %r: got %r, want %r" % (given, got, expect))
if sminos.peer_envelope("t", "‍") != "<cross-session-message>\nt\n</cross-session-message>":
    failures += 1
    print("FAIL a name that strips to nothing leaves no attribute")
total = len(BODIES) + len(NAMES) + 1
print("%s: %d of %d envelope cases" % ("FAILED" if failures else "ok", total - failures, total))
sys.exit(1 if failures else 0)
