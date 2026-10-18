"""Parity fixtures for sminos_marks.parse: the `parse` cases of
to-human/tests/mods/to-human.test.ts ("register" and "tags in code"), ported with
their expected values unchanged. Prints one `ok <name>` or `FAIL <name>`
line per case, for run-sminos-tests.sh to count.

    python3 marks_parity.py <skills/sminos/scripts>
"""

import sys

sys.path.insert(0, sys.argv[1])
import sminos_marks  # noqa: E402

E = "\u001b"


def span(text, is_open=False):
    return {"kind": "message", "text": text, "isOpen": is_open}


CASES = []


def case(name, text, spans=None, has_record=None):
    CASES.append((name, text, spans, has_record))


# ---- describe('register')
case("parse splits marked spans from the working record",
     "Reading the file.\n<message>Done.</message>\n<insight>Tests fail.</insight>",
     [span("Done."), span("Tests fail.")], True)
case("parse reads old to-human marks as messages", "<to-human>Done.</to-human>\nWorking.", [span("Done.")], True)
case("parse reads old essential marks as messages", "<essential>Tests fail.</essential>\nWorking.", [span("Tests fail.")], True)
case("parse closes nested aliases by the tag the model wrote",
     "<to-human>Done.\n<essential>Tests fail.</to-human>\nWorking.", [span("Done."), span("Tests fail.")], True)
case("parse leaves an unclosed span open while it streams", "<message>Which branch", [span("Which branch", True)], False)
QUESTION = "Which backend?\n<choice recommended>Postgres: already running</choice>\n<choice>SQLite</choice>"
case("parse reads old need-input marks as messages, their choice lines as text",
     "<need-input>\n%s\n</need-input>\nWorking." % QUESTION, [span(QUESTION)], True)
case("an unclosed need-input runs to the end", "<need-input>Which branch", [span("Which branch", True)])
case("parse lifts a mark nested inside another into a span of its own",
     "<message>\nDone.\n\n<insight>\nTests fail.\n</insight>\nMore.\n</message>",
     [span("Done."), span("Tests fail."), span("More.")], False)
case("parse does not let an unclosed mark swallow the marks after it",
     "<message>Done.\n<insight>Tests fail.</insight>\n<need-input>Which",
     [span("Done."), span("Tests fail."), span("Which", True)])
STREAMED = ("Notes: formatting-only request, no tools needed.\n\n\n"
            + E + "[1;36mto human" + E + "[0m\n\n\nRivers carry water downhill.\n\n\n"
            + E + "[1;32messential" + E + "[0m\n\n\nNo files were changed.\n\n\n"
            + E + "[2mDone — nothing else pending." + E + "[0m\n")
case("parse reads the old headers the streaming hook drew as messages", STREAMED,
     [span("Rivers carry water downhill."), span("No files were changed.")], True)
case("parse ends a span at the record that follows it",
     E + "[1;36mmessage" + E + "[0m\n\nKept.\n" + E + "[2mDropped from the span." + E + "[0m\n", [span("Kept.")], True)
case("parse reads an old insight as a message (marks)", "Editing.\n<insight>The cache key is the path.</insight>",
     [span("The cache key is the path.")])
case("parse reads an old insight as a message (header)", E + "[1;33minsight" + E + "[0m\n\nThe cache key is the path.\n",
     [span("The cache key is the path.")])
case("parse finds no spans in an unmarked message", "Plain reply.", [], True)


# ---- describe('tags in code')
def rendered_fence_record(fence, close, blank=False):
    return ("\n" + E + "[1;38;2;215;119;87mmessage" + E + "[0m\n\nReport.\n"
            + E + "[2m" + fence + E + "[0m\n" + ("\n" if blank else "")
            + E + "[2m<need-input>" + E + "[0m" + E + "[2mExample</need-input>" + E + "[0m\n"
            + ((E + "[2m" + fence + E + "[0m\n") if close else ""))


SENTENCE = "The style now asks for three marks: `<message>`, `<need-input>`, `<insight>`."
for fence, close, blank in (("~~~", True, False), ("```", True, True), ("```", False, True)):
    case("rendered headers win over literal raw tags in ANSI-dimmed fenced record (%s %s %s)" % (fence, close, blank),
         rendered_fence_record(fence, close, blank), [span("Report.")], True)
QUOTED = E + "[1;35mneed input" + E + "[0m"
for example in ("~~~\n<need-input>Example</need-input>\n%s\n~~~" % QUOTED, "Use `%s` literally." % QUOTED):
    body = "Example:\n%s\nDone." % example
    case("rendered headers quoted in code remain part of the real message (%r)" % example[:12],
         E + "[1;38;2;215;119;87mmessage" + E + "[0m\n\n" + body, [span(body)], False)
case("a quoted header in a fence alone is record", "~~~\n%s\n~~~" % QUOTED, [], True)
case("a quoted header inline in a real message", "<message>Use `%s` literally.</message>" % QUOTED,
     [span("Use `%s` literally." % QUOTED)], False)
case("quoted vocabulary is working record, not three empty reports", SENTENCE, [], True)
case("a real message keeps its backticked vocabulary without nested marks", "<message>%s</message>" % SENTENCE,
     [span(SENTENCE)], False)
for fence in ("```", "~~~~"):
    example = "%smd\n<need-input>Which?\n<choice recommended>A</choice>\n<choice>B</choice>\n</need-input>\n%s" % (fence, fence)
    case("fenced questions and choices are literal (%s)" % fence, example, [], True)
    case("a fenced example inside a message stays its text (%s)" % fence, "<message>Example:\n%s\nDone.</message>" % example,
         [span("Example:\n%s\nDone." % example)], False)
Q2 = "Which form?\nWrite `<choice>A</choice>` lines.\n```\n</need-input>\n<choice>B</choice>\n```"
case("quoted closers do not end a mark", "<need-input>%s\n<choice recommended>Yes</choice>\n</need-input>" % Q2,
     [span("%s\n<choice recommended>Yes</choice>" % Q2)], False)
case("fences close only with the same character and sufficient length",
     "````\n```\n~~~~\n<message>quoted</message>\n````\n<message>Shown.</message>", [span("Shown.")], True)
case("an unclosed fence runs to the end", "Intro\n```\n<message>quoted</message>", [], True)
for i, text in enumerate(("Use ``a ` <message>x</message>`` ok", "```<message>x</message>```",
                          "Use ``` x `` <message>x</message> ``")):
    case("inline spans pair equal-length runs (%d)" % i, text, [], True)
for i, text in enumerate(("A stray ` then <message>Done.</message>", "A ` start\n\n<message>Done.</message> and ` end")):
    case("an unpaired run is literal (%d)" % i, text, [span("Done.")], True)
for info in ("\r", " ", " "):
    case("JavaScript line terminators in fence info leave the line in its inline paragraph (%r)" % info,
         "Use `\n<need-input>Example</need-input>\n~~~%s\n x`\n" % info, [], True)
for blank in (" ", " ", "\f"):
    case("JavaScript trim whitespace ends an inline-code paragraph (%r)" % blank,
         "stray `\n%s\nUse `<need-input>Example</need-input>`\n" % blank, [], True)
for fence in ("```", "~~~"):
    case("a glued fence recovers balanced marks (%s)" % fence,
         "<message>Run this:\n%sbash\nnpm test\n%s</message>\n<need-input>Go?</need-input>" % (fence, fence),
         [span("Run this:\n%sbash\nnpm test\n%s" % (fence, fence)), span("Go?")], False)
case("a strict-balanced report never reads through the glued recovery",
     "<message>```bash\nnpm test\n```\n</message>\n<need-input>Go?</need-input>",
     [span("```bash\nnpm test\n```"), span("Go?")])
EXAMPLE = "Example syntax:\n```text\n```</message>\n<need-input>Example only?</need-input>\n```\nEnd of example."
case("a glued-looking example inside a balanced message stays its text", "<message>%s</message>" % EXAMPLE,
     [span(EXAMPLE)], False)
case("rendered orange messages keep quoted tags", E + "[1;38;2;215;119;87mmessage" + E + "[0m\n\n%s\n" % SENTENCE,
     [span(SENTENCE)], False)
case("an old need-input header reads as a message with its markers as text",
     E + "[1;35mneed input" + E + "[0m\n\nExample:\n```\n◇ literal\n```\n◆ Yes\n",
     [span("Example:\n```\n◇ literal\n```\n◆ Yes")])

for name, text, spans, has_record in CASES:
    got = sminos_marks.parse(text)
    bad = []
    if spans is not None and got["spans"] != spans:
        bad.append("spans %r != %r" % (got["spans"], spans))
    if has_record is not None and got["hasRecord"] != has_record:
        bad.append("hasRecord %r != %r" % (got["hasRecord"], has_record))
    print(("FAIL %s: %s" % (name, "; ".join(bad))) if bad else ("ok %s" % name))
