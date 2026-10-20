"""Writes dx4-stream.json: the shared parity fixture of DX4's streaming layer
(the desk open-fast spec, §9 and M1), which the reference consumer
(dx4_consumer.py, its test in test_session_plane.py) and the web's
`apps/desk-web/src/depth/stream/layer.test.ts` (a copy beside it) both
replay, so the two prove the same rule.

Every expected drawing here is written by hand from the rules — the web's
streaming layer with §9's amendment (a block the fresh snapshot carries is
drawn from it, named or not) — never computed by the consumer: the file is
the contract both are held to.

    python3 dx4-stream.gen.py > dx4-stream.json
"""

import json
import sys

PROJECT = "0d9e8f7a-6b5c-4d3e-a2f1-0e9d8c7b6a59"
MACHINE = "testhost"
SESSION = "d0c8a000-0000-4000-8000-0000000d4c45"
NAMED_AT = 1760000000000

ABOUT = (
    "DX4's streaming layer, the desk open-fast spec's parity fixture (docs/doperpowers/specs/"
    "2026-10-20-desk-open-fast-design.md, section 9), written by sminos/tests/dx4-stream.gen.py: every expected "
    "drawing by hand. Each sequence is one session view's messages in order; a step's `message` is a DX4 envelope, "
    "or \"resubscribe\" (the subscription is over and a new one starts: `n` from 0, and its first snapshot is "
    "resumed over what is drawn, not loaded). `drawn` is the streaming layer's blocks after the message: agentId "
    "(\"main\" for null) to that agent's blocks in drawing order, an agent with none left out. The store's side, "
    "for a replay of the layer alone: `settle` lists the rows whose landing settles blocks after the message, in "
    "order (a held row a drawn block awaits; another loop's block-row on a main view); a resumed snapshot's step "
    "gives `landing` (the newest row the snapshot brought, null for none) and `lands` (the named rows `lands` "
    "answers true for). A sequence's `errors` are the reference consumer's error kinds, in order (gap, dup, "
    "watermark, differs, vanished, after-end, marks); `inventory`, where present, is the transcript on disk and "
    "the DX5 events the session emitted, and what checking the consumer against them names: holes (rows never "
    "delivered), partial (a block drawn while its row was held), vanished (a block gone before its row landed), dups "
    "(a row delivered twice, a block drawn again after it settled), undrawn (a block whose request this view followed, "
    "never drawn before its row arrived live), residual (the same for a request that had ended before the view "
    "followed it: the snapshot between a step's end and its rows' flush, an accepted hole).")


def assistant(uuid, kind, value):
    block = {"text": {"type": "text", "text": value}, "thinking": {"type": "thinking", "thinking": value},
             "tool": {"type": "tool_use", "id": "toolu_01", "name": "Bash", "input": value}}[kind]
    return {"type": "assistant", "uuid": uuid, "message": {"role": "assistant", "content": [block]}}


def user(uuid, text):
    return {"type": "user", "uuid": uuid, "message": {"role": "user", "content": text}}


def blk(turn, agent, step, index, kind, text, settled_by=None):
    """A block as drawn."""
    return {"turnId": turn, "agentId": agent, "step": step, "index": index, "kind": kind, "text": text,
            "settledBy": settled_by}


def entry(turn, agent, step, up_to, *blocks):
    return {"turnId": turn, "agentId": agent, "step": step, "model": "m", "upTo": up_to, "blocks": list(blocks)}


def sblk(index, kind, text, up_to, uuid=None, at=None, **more):
    """A snapshot's streaming block; `uuid` (and `namedAt`) once its block-row was applied."""
    b = {"index": index, "kind": kind, "text": text, "upTo": up_to, **more}
    if uuid is not None:
        b.update(uuid=uuid, namedAt=NAMED_AT + (at or 0))
    return b


class Seq:
    def __init__(self, n, name, about, agent=None):
        self.case = n
        self.out = {"name": name, "about": about, "agent": agent, "steps": [], "errors": []}
        self.sub = 0
        self.n = 0

    def u(self, i):
        return "%08x-0000-4000-8000-%012x" % (0xd4c4000 + self.case, i)

    def env(self, kind, body, n=None):
        n = self.n if n is None else n
        self.n = n + 1
        return {"project": PROJECT, "machine": MACHINE, "session": SESSION, "kind": kind,
                "sub": "sub-%d-%d" % (self.case, self.sub), "n": n, "body": body}

    def step(self, message, drawn, settle=(), note=None, **replay):
        s = {"message": message}
        if note:
            s["note"] = note
        if settle:
            s["settle"] = list(settle)
        s.update(replay)
        s["drawn"] = drawn
        self.out["steps"].append(s)

    def snapshot(self, rows, streaming, drawn, more=False, **kw):
        body = {"rows": rows, "more": more, "subagents": [], "presence": {"record": {"status": "busy"}, "bridge": True},
                "streaming": streaming, "jobs": [], "mcp": [], "offChain": []}
        if self.out["agent"] is None:
            body["usage"] = None
        self.step(self.env("snapshot", body, n=0), drawn, **kw)

    def chunk(self, turn, agent, step, index, block, kind, drawn, n=None, **kw):
        text = kw.pop("text", None)
        c = {"kind": kind, "index": block}
        if kind in ("text", "thinking"):
            c["text"] = text
        elif kind == "input":
            c["json"] = text
        elif kind == "tool":
            c.update(id="toolu_01", name=text)
        body = {"turnId": turn, "agentId": agent, "step": step, "chunkIndex": index, "chunk": c, "t": NAMED_AT + index}
        self.step(self.env("chunk", body, n), drawn, **kw)

    def block_row(self, uuid, turn, agent, step, index, drawn, **kw):
        body = {"uuid": uuid, "turnId": turn, "agentId": agent, "step": step, "index": index}
        self.step(self.env("block-row", body), drawn, **kw)

    def step_end(self, turn, agent, step, drawn, **kw):
        self.step(self.env("step-end", {"turnId": turn, "agentId": agent, "step": step}), drawn, **kw)

    def row(self, row, drawn, n=None, **kw):
        self.step(self.env("row", {"row": row, "agentId": self.out["agent"]}, n), drawn, **kw)

    def end(self, drawn, reason="machine-offline", n=None, **kw):
        self.step(self.env("end", {"reason": reason}, n), drawn, **kw)

    def resubscribe(self, drawn):
        self.sub += 1
        self.n = 0
        self.step("resubscribe", drawn, note="the subscription is over; a new one starts and resumes the drawing")


R = ("turn-1", None, 0)


def first_snapshot_every_kind():
    s = Seq(1, "first-snapshot-every-kind",
            "A first snapshot (loaded) carrying a named thinking block and unnamed text and tool blocks; the plane's "
            "block-row for the named one right after it; chunks of text, a named block's late chunk ignored, a tool "
            "call's input; block-rows; a step-end dropping the one block no block-row named; each row landing "
            "settles its block.")
    P, T, X, Y = s.u(1), s.u(2), s.u(3), s.u(4)
    s.snapshot([user(P, "write a story")],
               [entry(*R, 6, sblk(0, "thinking", "Plot first.", 2, uuid=T, at=1),
                      sblk(1, "text", "Once", 4), sblk(2, "tool", '{"command":', 6, id="toolu_01", name="Bash"))],
               {"main": [blk(*R, 0, "thinking", "Plot first.", T), blk(*R, 1, "text", "Once"),
                         blk(*R, 2, "tool", '{"command":')]})
    d = lambda once, cmd, x=None, y=None: {"main": [  # noqa: E731
        blk(*R, 0, "thinking", "Plot first.", T), blk(*R, 1, "text", once, x), blk(*R, 2, "tool", cmd, y)]}
    s.block_row(T, *R, 0, d("Once", '{"command":'), note="the plane's block-row for a block the snapshot carried named")
    s.chunk(*R, 7, 1, "text", d("Once upon", '{"command":'), text=" upon")
    s.chunk(*R, 8, 0, "thinking", d("Once upon", '{"command":'), text=" More.",
            note="a chunk for a named block: ignored, its row holds the block whole")
    s.chunk(*R, 9, 2, "input", d("Once upon", '{"command":"ls"}'), text='"ls"}')
    s.chunk(*R, 10, 1, "text", d("Once upon a time.", '{"command":"ls"}'), text=" a time.")
    s.block_row(X, *R, 1, d("Once upon a time.", '{"command":"ls"}', X))
    s.block_row(Y, *R, 2, d("Once upon a time.", '{"command":"ls"}', X, Y))
    full = d("Once upon a time.", '{"command":"ls"}', X, Y)
    s.chunk(*R, 11, 3, "text", {"main": full["main"] + [blk(*R, 3, "text", "Unfinished")]}, text="Unfinished")
    s.step_end(*R, full, note="the block no block-row named goes; the named ones wait for their rows")
    s.row(assistant(T, "thinking", "Plot first."), {"main": full["main"][1:]}, settle=[T])
    s.row(assistant(X, "text", "Once upon a time."), {"main": full["main"][2:]}, settle=[X])
    s.row(assistant(Y, "tool", {"command": "ls"}), {}, settle=[Y])
    return s.out


def reconnect_carried_named():
    s = Seq(2, "reconnect-empty-history-carries-the-named-block",
            "A2 and A8: a block is named, the subscription is lost, and the fresh snapshot — its history empty, the "
            "row not yet on disk — carries the block with its uuid. The block stays drawn with the snapshot's text "
            "until its row lands, then goes once. (Today's web dropped it here: no row would land, no newer row "
            "came.)")
    A = s.u(1)
    s.snapshot([], [entry(*R, 1, sblk(0, "text", "Hello", 1))], {"main": [blk(*R, 0, "text", "Hello")]})
    s.chunk(*R, 2, 0, "text", {"main": [blk(*R, 0, "text", "Hello world")]}, text=" world")
    named = {"main": [blk(*R, 0, "text", "Hello world", A)]}
    s.block_row(A, *R, 0, named)
    s.end(named)
    s.resubscribe(named)
    s.snapshot([], [entry(*R, 2, sblk(0, "text", "Hello world", 2, uuid=A, at=2))], named, landing=None, lands=[],
               note="resumed: the snapshot carries the named block, so it is drawn from it")
    s.block_row(A, *R, 0, named, note="the plane's block-row for the carried named block: idempotent")
    s.row(assistant(A, "text", "Hello world"), {}, settle=[A])
    s.step_end(*R, {})
    s.out["inventory"] = {
        "transcript": [assistant(A, "text", "Hello world")],
        "dx5": [{"type": "chunk", "turnId": "turn-1", "agentId": None, "step": 0, "chunkIndex": i,
                 "chunk": {"kind": "text", "index": 0, "text": t}, "t": NAMED_AT + i}
                for i, t in enumerate(("Hel", "lo", " world"))]
        + [{"type": "block-row", "uuid": A, "turnId": "turn-1", "agentId": None, "step": 0, "index": 0, "t": NAMED_AT}],
        "check": {"holes": [], "partial": [], "vanished": [], "dups": [], "undrawn": [], "residual": []}}
    return s.out


def reconnect_no_longer_carried():
    s = Seq(3, "reconnect-snapshot-no-longer-carries-the-block",
            "The fresh snapshot no longer streams the blocks the old subscription drew: their rows were written in "
            "the gap and the snapshot brings them. The named block waits for its own row (it lands: the snapshot "
            "merged into the held rows), the unnamed one for the newest row the snapshot brought; both are held, "
            "so both settle at once.")
    P, B, C = s.u(1), s.u(2), s.u(3)
    s.snapshot([user(P, "hi")], [entry(*R, 1, sblk(0, "text", "Hi", 0), sblk(1, "text", "By", 1))],
               {"main": [blk(*R, 0, "text", "Hi"), blk(*R, 1, "text", "By")]})
    s.chunk(*R, 2, 0, "text", {"main": [blk(*R, 0, "text", "Hi there"), blk(*R, 1, "text", "By")]}, text=" there")
    drawn = {"main": [blk(*R, 0, "text", "Hi there", B), blk(*R, 1, "text", "By")]}
    s.block_row(B, *R, 0, drawn)
    s.end(drawn)
    s.resubscribe(drawn)
    s.snapshot([assistant(C, "text", "Bye"), assistant(B, "text", "Hi there"), user(P, "hi")], [], {},
               settle=[B, C], landing=C, lands=[B],
               note="resumed: merged (its oldest row is held); block 0 settles by its row, block 1 by the landing")
    s.step_end(*R, {})
    return s.out


def older_snapshot():
    s = Seq(4, "reconnect-older-snapshot-changes-nothing",
            "A fresh snapshot older than what was drawn (its watermark below the drawn one: a producer that went "
            "back) changes nothing of that request; the live chunks the drawing holds are dropped at the drawn "
            "watermark, the later ones appended.")
    D = s.u(1)
    s.snapshot([], [entry(*R, 3, sblk(0, "text", "Hello", 3))], {"main": [blk(*R, 0, "text", "Hello")]})
    s.chunk(*R, 4, 0, "text", {"main": [blk(*R, 0, "text", "Hello,")]}, text=",")
    drawn = {"main": [blk(*R, 0, "text", "Hello, world")]}
    s.chunk(*R, 5, 0, "text", drawn, text=" world")
    s.end(drawn)
    s.resubscribe(drawn)
    s.snapshot([], [entry(*R, 3, sblk(0, "text", "Hello", 3))], drawn, landing=None, lands=[],
               note="resumed: its watermark 3 is below the drawn 5")
    s.chunk(*R, 4, 0, "text", drawn, text=",", note="at or below the drawn watermark: dropped")
    s.chunk(*R, 5, 0, "text", drawn, text=" world")
    s.chunk(*R, 6, 0, "text", {"main": [blk(*R, 0, "text", "Hello, world!")]}, text="!")
    s.block_row(D, *R, 0, {"main": [blk(*R, 0, "text", "Hello, world!", D)]})
    s.row(assistant(D, "text", "Hello, world!"), {}, settle=[D])
    return s.out


def another_loop():
    s = Seq(5, "main-view-carries-a-subagents-named-block",
            "A main view carries every agent's streaming. A subagent's block the snapshot carries named is drawn "
            "until the plane's block-row for it, which settles it at once (its row comes on the agent's own "
            "subscription, never here); the main loop's block waits for its row.")
    A1 = ("t-a1", "a1", 0)
    S, S2, M = s.u(1), s.u(2), s.u(3)
    s.snapshot([], [entry(*R, 0, sblk(0, "text", "Main", 0)), entry(*A1, 1, sblk(0, "text", "Sub done", 1, uuid=S, at=1))],
               {"main": [blk(*R, 0, "text", "Main")], "a1": [blk(*A1, 0, "text", "Sub done", S)]})
    main = {"main": [blk(*R, 0, "text", "Main")]}
    s.block_row(S, *A1, 0, main, settle=[S], note="another loop's block-row: settled at once")
    s.chunk(*A1, 2, 1, "text", {**main, "a1": [blk(*A1, 1, "text", "more")]}, text="more")
    s.block_row(S2, *A1, 1, main, settle=[S2])
    s.block_row(M, *R, 0, {"main": [blk(*R, 0, "text", "Main", M)]})
    s.row(assistant(M, "text", "Main"), {}, settle=[M])
    return s.out


def planted_continuity():
    s = Seq(6, "planted-gap-dup-watermark-after-end",
            "Planted errors: a chunk at the subscription's own watermark (the layer drops it), an n that skips one, "
            "a row delivered twice, and a message after end (the closed subscription applies nothing).")
    P = s.u(1)
    s.snapshot([user(P, "go")], [entry(*R, 2, sblk(0, "text", "ab", 2))], {"main": [blk(*R, 0, "text", "ab")]})
    s.chunk(*R, 2, 0, "text", {"main": [blk(*R, 0, "text", "ab")]}, text="c", note="planted: at the watermark")
    drawn = {"main": [blk(*R, 0, "text", "abd")]}
    s.chunk(*R, 3, 0, "text", drawn, n=3, text="d", note="planted: n skips 2")
    s.row(user(P, "go"), drawn, note="planted: the snapshot's row again")
    s.end(drawn)
    s.chunk(*R, 4, 0, "text", drawn, text="e", note="planted: after end")
    s.out["errors"] = ["watermark", "gap", "dup", "after-end"]
    return s.out


def planted_vanished():
    s = Seq(7, "planted-vanished-and-a-hole",
            "Planted: the fresh snapshot after a disruption carries neither the named block nor its row (what the "
            "plane's open gate existed to prevent), and the row is never delivered. The block vanishes before its "
            "row landed; the row is a hole.")
    P, L = s.u(1), s.u(2)
    s.snapshot([user(P, "go")], [entry(*R, 0, sblk(0, "text", "Lost", 0))], {"main": [blk(*R, 0, "text", "Lost")]})
    named = {"main": [blk(*R, 0, "text", "Lost", L)]}
    s.block_row(L, *R, 0, named)
    s.end(named)
    s.resubscribe(named)
    s.snapshot([], [], {}, landing=None, lands=[], note="planted: no block, no row; the held rows are replaced")
    s.step_end(*R, {})
    s.out["errors"] = ["vanished"]
    s.out["inventory"] = {
        "transcript": [user(P, "go"), assistant(L, "text", "Lost")],
        "dx5": [{"type": "chunk", "turnId": "turn-1", "agentId": None, "step": 0, "chunkIndex": 0,
                 "chunk": {"kind": "text", "index": 0, "text": "Lost"}, "t": NAMED_AT},
                {"type": "block-row", "uuid": L, "turnId": "turn-1", "agentId": None, "step": 0, "index": 0, "t": NAMED_AT}],
        "check": {"holes": [L], "partial": [],
                  "vanished": [{"turnId": "turn-1", "agentId": None, "step": 0, "index": 0}], "dups": [],
                  "undrawn": [], "residual": []}}
    return s.out


def planted_partial_and_twice():
    s = Seq(8, "planted-partial-and-drawn-twice",
            "Planted: a block's row lands before its block-row (the block is drawn beside its row: partial), then "
            "a fresh snapshot replaces the held rows and carries the settled block named again (drawn twice).")
    P, W = s.u(1), s.u(2)
    s.snapshot([user(P, "go")], [entry(*R, 0, sblk(0, "text", "Twice", 0))], {"main": [blk(*R, 0, "text", "Twice")]})
    s.row(assistant(W, "text", "Twice"), {"main": [blk(*R, 0, "text", "Twice")]},
          note="planted: the row before its block-row; the unnamed block stays drawn beside it")
    s.block_row(W, *R, 0, {}, settle=[W])
    s.end({})
    s.resubscribe({})
    again = {"main": [blk(*R, 0, "text", "Twice", W)]}
    s.snapshot([], [entry(*R, 0, sblk(0, "text", "Twice", 0, uuid=W))], again, landing=None, lands=[],
               note="planted: no rows, and the settled block carried again")
    s.block_row(W, *R, 0, again)
    s.row(assistant(W, "text", "Twice"), {}, settle=[W])
    s.out["inventory"] = {
        "transcript": [user(P, "go"), assistant(W, "text", "Twice")],
        "dx5": [{"type": "chunk", "turnId": "turn-1", "agentId": None, "step": 0, "chunkIndex": 0,
                 "chunk": {"kind": "text", "index": 0, "text": "Twice"}, "t": NAMED_AT},
                {"type": "block-row", "uuid": W, "turnId": "turn-1", "agentId": None, "step": 0, "index": 0, "t": NAMED_AT}],
        "check": {"holes": [], "partial": [{"turnId": "turn-1", "agentId": None, "step": 0, "index": 0, "text": "Twice"}],
                  "vanished": [], "dups": [{"turnId": "turn-1", "agentId": None, "step": 0, "index": 0}],
                  "undrawn": [], "residual": []}}
    return s.out


def fresh_text_wins():
    s = Seq(9, "reconnect-fresh-text-and-the-old-name",
            "Blocks the fresh snapshot carries unnamed are drawn with its text: one still streaming takes the "
            "snapshot's newer text and goes on; one the old subscription had named keeps that name, so its row "
            "settles it.")
    E, E2 = s.u(1), s.u(2)
    s.snapshot([], [entry(*R, 1, sblk(0, "text", "Str", 0), sblk(1, "text", "Done", 1))],
               {"main": [blk(*R, 0, "text", "Str"), blk(*R, 1, "text", "Done")]})
    drawn = {"main": [blk(*R, 0, "text", "Str"), blk(*R, 1, "text", "Done", E2)]}
    s.block_row(E2, *R, 1, drawn)
    s.end(drawn)
    s.resubscribe(drawn)
    s.snapshot([], [entry(*R, 2, sblk(0, "text", "Stre", 2), sblk(1, "text", "Done", 1))],
               {"main": [blk(*R, 0, "text", "Stre"), blk(*R, 1, "text", "Done", E2)]}, landing=None, lands=[],
               note="resumed: block 0 the snapshot's text; block 1 carried unnamed keeps the old name")
    s.block_row(E2, *R, 1, {"main": [blk(*R, 0, "text", "Stre"), blk(*R, 1, "text", "Done", E2)]})
    s.chunk(*R, 3, 0, "text", {"main": [blk(*R, 0, "text", "Stream"), blk(*R, 1, "text", "Done", E2)]}, text="am")
    s.block_row(E, *R, 0, {"main": [blk(*R, 0, "text", "Stream", E), blk(*R, 1, "text", "Done", E2)]})
    s.row(assistant(E2, "text", "Done"), {"main": [blk(*R, 0, "text", "Stream", E)]}, settle=[E2])
    s.row(assistant(E, "text", "Stream"), {}, settle=[E])
    s.step_end(*R, {})
    return s.out


def planted_undrawn():
    s = Seq(10, "planted-undrawn-and-the-residual-hole",
            "Planted: the first snapshot follows a request still streaming (block 1) but carries neither its named "
            "block 0 nor that block's row, which arrives live after its block-row: the block was never drawn (the "
            "first open's twin of the carried-block loss). Beside it, the row of a request whose step had ended "
            "before the snapshot arrives live too, its block never drawn and its request never followed: the "
            "snapshot fell between that step's end and its rows' flush, the hole the design accepts (residual).")
    R0, R1 = ("turn-1", None, 0), ("turn-1", None, 1)
    P, M, N, S = s.u(1), s.u(2), s.u(3), s.u(4)
    s.snapshot([user(P, "go")], [entry(*R1, 3, sblk(1, "text", "still", 3))], {"main": [blk(*R1, 1, "text", "still")]},
               note="planted: block 0 of the request, named, is missing; so is its row")
    s.row(assistant(M, "text", "flushed late"), {"main": [blk(*R1, 1, "text", "still")]},
          note="the residual: an ended step's row, after a snapshot that could carry neither")
    s.block_row(N, *R1, 0, {"main": [blk(*R1, 1, "text", "still")]}, note="names a block that is not drawn")
    s.chunk(*R1, 4, 1, "text", {"main": [blk(*R1, 1, "text", "still going")]}, text=" going")
    s.row(assistant(N, "text", "Gone"), {"main": [blk(*R1, 1, "text", "still going")]})
    s.block_row(S, *R1, 1, {"main": [blk(*R1, 1, "text", "still going", S)]})
    s.row(assistant(S, "text", "still going"), {}, settle=[S])
    s.step_end(*R1, {})

    def chunk(ids, index, block, text):
        return {"type": "chunk", "turnId": ids[0], "agentId": ids[1], "step": ids[2], "chunkIndex": index,
                "chunk": {"kind": "text", "index": block, "text": text}, "t": NAMED_AT + index}

    def named(ids, block, uuid):
        return {"type": "block-row", "uuid": uuid, "turnId": ids[0], "agentId": ids[1], "step": ids[2],
                "index": block, "t": NAMED_AT}

    s.out["inventory"] = {
        "transcript": [user(P, "go"), assistant(M, "text", "flushed late"), assistant(N, "text", "Gone"),
                       assistant(S, "text", "still going")],
        "dx5": [chunk(R0, 0, 0, "flushed late"), named(R0, 0, M),
                {"type": "step", "phase": "end", "turnId": "turn-1", "agentId": None, "step": 0, "t": NAMED_AT},
                chunk(R1, 0, 0, "Gone"), named(R1, 0, N), chunk(R1, 1, 1, "st"), chunk(R1, 2, 1, "il"),
                chunk(R1, 3, 1, "l"), chunk(R1, 4, 1, "l going"), named(R1, 1, S)],
        "check": {"holes": [], "partial": [], "vanished": [], "dups": [],
                  "undrawn": [{"turnId": "turn-1", "agentId": None, "step": 1, "index": 0}],
                  "residual": [{"turnId": "turn-1", "agentId": None, "step": 0, "index": 0}]}}
    return s.out


TOOL_INPUT = {"command": "echo " + "x" * 100 + " done", "description": "a long one"}
TOOL_TAIL = json.dumps(TOOL_INPUT)[-40:]
TEXT = "a long answer " * 20 + "that ends here."
TEXT_TAIL = TEXT[-30:]


def truncated_blocks():
    s = Seq(11, "truncated-blocks-settle",
            "Blocks whose catch-up copy the producer cut to its last characters (`truncated`, the spec's section 7): a "
            "text block and a tool call whose kept input is the tail of its JSON, not JSON whole. Each is drawn with "
            "the tail it carries and settles cleanly by its row, whose text, or whose input as serialized, ends with "
            "that tail.")
    T, U = s.u(1), s.u(2)
    s.snapshot([], [entry(*R, 9, sblk(0, "text", TEXT_TAIL, 4, truncated=True),
                          sblk(1, "tool", TOOL_TAIL, 9, id="toolu_01", name="Bash", truncated=True))],
               {"main": [blk(*R, 0, "text", TEXT_TAIL), blk(*R, 1, "tool", TOOL_TAIL)]})
    drawn = {"main": [blk(*R, 0, "text", TEXT_TAIL, T), blk(*R, 1, "tool", TOOL_TAIL, U)]}
    s.block_row(T, *R, 0, {"main": [blk(*R, 0, "text", TEXT_TAIL, T), blk(*R, 1, "tool", TOOL_TAIL)]})
    s.block_row(U, *R, 1, drawn)
    s.row(assistant(T, "text", TEXT), {"main": drawn["main"][1:]}, settle=[T])
    s.row(assistant(U, "tool", TOOL_INPUT), {}, settle=[U])
    s.step_end(*R, {})
    return s.out


SEQUENCES = [first_snapshot_every_kind, reconnect_carried_named, reconnect_no_longer_carried, older_snapshot,
             another_loop, planted_continuity, planted_vanished, planted_partial_and_twice, fresh_text_wins,
             planted_undrawn, truncated_blocks]


def main():
    out = []
    for i, make in enumerate(SEQUENCES):
        seq = make()
        if i == 0:
            seq["about_fixture"] = ABOUT
        out.append(seq)
    json.dump(out, sys.stdout, indent=1, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
