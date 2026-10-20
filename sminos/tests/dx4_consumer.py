"""dx4_consumer — the reference DX4 consumer and the inventory (the desk
open-fast spec, docs/doperpowers/specs/2026-10-20-desk-open-fast-design.md,
M1), for tests and the instruments only.

`Consumer` applies one subscription's DX4 messages as the desk's web does:
its streaming layer (MAWS `apps/desk-web/src/depth/stream/layer.ts`, with
the spec's §9 rule: a block the fresh snapshot carries is drawn from it,
named or not) and the rows it holds (`depth/source/desk-transcript.ts`:
the snapshot's rows, live rows once each by uuid, older pages before them,
a fresh snapshot after a disruption merged into the held rows where its
oldest row is held, else replacing them). A row lands when it is held: the
blocks it settles are dropped then, as `settleLanded` does once the store
has the row. `n` starts over with every subscription; a re-subscribe is a
new Consumer handed the old one (`previous`), whose drawing it resumes.

It records what would be wrong on screen, each error a string whose first
word is its kind: `gap` (an `n` out of sequence), `dup` (a row twice on one
subscription), `watermark` (a chunk at or below the subscription's own
watermark), `differs` (a block whose drawn text is not its row's, when its
own row settles it; a tool call cut to its tail is not checked here, since
its row holds the input parsed and the tail is of the JSON as it streamed:
the inventory checks it), `vanished` (a named block dropped before its row
landed), `after-end` (a message after `end`), `marks` (offChain naming rows
the message does not carry, or a row's marks present and empty).

`Inventory` is built from the sources of truth — every row of the
transcript on disk, delivered or not, and the DX5 events the session
emitted (every block that streamed, its final text, the row its block-row
named) — and `check(consumer)` names each row never drawn (`holes`), each
block drawn while its row was held, or a tool call drawn with a tail that
is not the end of the input the source streamed (`partial`), each block
that left the drawing before its row landed (`vanished`), each row
delivered twice or
block drawn again after it settled (`dups`), and each block that streamed
whose row arrived live (a `row`, not history or a page) without the block
ever drawn before it: `residual` when the view never followed the block's
request (its snapshot streamed none of it, and no chunk, block-row or
step-end of it came) and the source shows that request's step ended before
the snapshot of the subscription the row came on — the snapshot fell
between the step's end and its rows' flush, the one hole the design
accepts (the spec's section 2) — else `undrawn`: the block was lost. In
the DX5 events a `snapshot` event is the bridge's snapshot line as it
served a subscription, carrying that subscription's DX4 `sub`; a
subscription no `snapshot` event names has no evidence its request's step
ended first, and the block is `undrawn`.

The merge leaves out the web's offChain vouching (desk-transcript's
`merged`): a fresh snapshot whose oldest row is held merges here whatever
its marks say. The chain is the plane's tests' to prove, not this module's.
A page holding a row twice is held once and said (`dup`); the web's `older`
would draw it twice.
"""

import json
import time


def kind_of(name):
    """DX4 names a block's kind as the bridge does: text, thinking, else a tool call's input."""
    return name if name in ("text", "thinking") else "tool"


def ref(key):
    return {"turnId": key[0], "agentId": key[1], "step": key[2], "index": key[3]}


class Block:
    """A drawn block, as the web's StreamBlock: `settled_by` the row whose
    landing drops it; `own` whether that row is the block's own (named by its
    block-row or the snapshot's uuid), not a `landing` stand-in."""

    __slots__ = ("turn", "agent", "step", "index", "kind", "text", "tool", "settled_by", "own", "truncated")

    def __init__(self, turn, agent, step, index, kind, text="", tool=None, settled_by=None, truncated=False):
        self.turn, self.agent, self.step, self.index = turn, agent, step, index
        self.kind, self.text, self.tool = kind, text, tool
        self.settled_by, self.own, self.truncated = settled_by, settled_by is not None, truncated

    @property
    def key(self):
        return (self.turn, self.agent, self.step, self.index)

    def drawn(self):
        """The fixture's shape of a drawn block (dx4-stream.json's `drawn`)."""
        return {"turnId": self.turn, "agentId": self.agent, "step": self.step, "index": self.index,
                "kind": self.kind, "text": self.text, "settledBy": self.settled_by}


class Request:
    __slots__ = ("turn", "agent", "step", "up_to", "blocks", "named", "ended")

    def __init__(self, turn, agent, step):
        self.turn, self.agent, self.step = turn, agent, step
        self.up_to = -1
        self.blocks = {}      # index → Block
        self.named = set()    # indices whose block-row came: they take no more chunks
        self.ended = False


def snapshot_blocks(entry, ids):
    """One snapshot `streaming` entry's blocks (layer.ts `snapshotEntry`, reading `uuid` as §9 says)."""
    out = []
    for b in entry.get("blocks") or []:
        if not isinstance(b, dict) or type(b.get("index")) is not int:
            continue
        uuid = b.get("uuid") if isinstance(b.get("uuid"), str) else None
        out.append(Block(*ids, b["index"], kind_of(b.get("kind")),
                         b["text"] if isinstance(b.get("text"), str) else "",
                         b["name"] if isinstance(b.get("name"), str) else None, uuid, b.get("truncated") is True))
    return out


class Layer:
    """The web's streaming layer (layer.ts), with §9's carried-block rule.
    Requests keep the order they first appeared in, blocks by index."""

    def __init__(self):
        self.requests = {}

    def request(self, turn, agent, step):
        key = (turn, agent, step)
        r = self.requests.get(key)
        if r is None:
            r = self.requests[key] = Request(turn, agent, step)
        return r

    def load(self, streaming):
        self.requests = {}
        for e in streaming:
            ids = (e.get("turnId"), e.get("agentId"), e.get("step"))
            r = self.request(*ids)
            r.up_to = e["upTo"] if type(e.get("upTo")) is int else -1
            for b in snapshot_blocks(e, ids):
                r.blocks[b.index] = b
                if b.settled_by is not None:
                    r.named.add(b.index)

    def resume(self, streaming, landing, lands):
        """A fresh snapshot over what was drawn (layer.ts `resume`, §9): a
        block the snapshot carries is drawn from it — its text the
        snapshot's, named by the snapshot's uuid else by what named it
        before, its identity the old one's; a block it does not carry stays
        until the row that named it lands where that row will land, else
        until `landing`, else goes. A request the snapshot holds less of is
        kept as drawn; an ended one stays ended. Returns the blocks dropped."""
        before = self.requests
        self.load(streaming)
        loaded = self.requests
        self.requests = {}
        dropped = []
        for key, old in before.items():
            snap = loaded.get(key)
            if snap is not None and old.up_to > snap.up_to:
                self.requests[key] = old
                continue
            request = snap if snap is not None else (Request(*key) if old.ended else None)
            if request is not None:
                for index in old.named:
                    fresh = request.blocks.get(index)
                    # An unnamed copy of a block whose row already landed here is stale.
                    if fresh is not None and fresh.settled_by is None and index not in old.blocks:
                        del request.blocks[index]
                    request.named.add(index)
                if old.ended:
                    request.ended = True
                    request.blocks.clear()   # the snapshot's copies of the blocks the step-end dropped
            for index, block in old.blocks.items():
                fresh = request.blocks.get(index) if request is not None else None
                if fresh is not None:
                    block.kind, block.text, block.tool, block.truncated = fresh.kind, fresh.text, fresh.tool, fresh.truncated
                    if fresh.settled_by is not None:
                        block.settled_by, block.own = fresh.settled_by, True
                    request.blocks[index] = block
                    continue
                settled_by = block.settled_by if block.settled_by is not None and lands(block.settled_by) else landing
                if settled_by is None:
                    dropped.append(block)
                    continue
                into = request if request is not None else self.request(*key)
                into.named.add(index)
                if settled_by != block.settled_by:
                    block.settled_by, block.own = settled_by, False
                into.blocks[index] = block
            if request is not None:
                self.requests[key] = request
        for key, request in loaded.items():
            self.requests.setdefault(key, request)
        return dropped

    def chunk(self, body):
        """One live chunk (layer.ts `chunk`)."""
        r = self.request(body.get("turnId"), body.get("agentId"), body.get("step"))
        index = body.get("chunkIndex")
        if r.ended or type(index) is not int or index <= r.up_to:
            return
        r.up_to = index
        c = body.get("chunk") if isinstance(body.get("chunk"), dict) else {}
        bi = c.get("index")
        if type(bi) is not int or bi in r.named:
            return
        kind = c.get("kind")
        if kind not in ("text", "thinking", "tool", "input"):
            return   # `stop`, and any kind the layer does not draw
        block = r.blocks.get(bi)
        if block is None:
            block = r.blocks[bi] = Block(r.turn, r.agent, r.step, bi, kind_of("tool" if kind == "input" else kind))
        if kind in ("text", "thinking"):
            block.text += c["text"] if isinstance(c.get("text"), str) else ""
        elif kind == "tool":
            block.tool = c["name"] if isinstance(c.get("name"), str) else block.tool
        else:
            block.text += c["json"] if isinstance(c.get("json"), str) else ""

    def block_row(self, body):
        r = self.request(body.get("turnId"), body.get("agentId"), body.get("step"))
        r.named.add(body.get("index"))
        block = r.blocks.get(body.get("index"))
        if block is not None:
            block.settled_by, block.own = body.get("uuid"), True

    def step_end(self, body):
        """The request ended: its blocks no block-row named go. Returns them."""
        r = self.request(body.get("turnId"), body.get("agentId"), body.get("step"))
        r.ended = True
        gone = [b for b in r.blocks.values() if b.settled_by is None]
        for b in gone:
            del r.blocks[b.index]
        return gone

    def settle(self, uuid):
        """The row `uuid` landed: the blocks it settles go. Returns them."""
        gone = []
        for r in self.requests.values():
            for b in [b for b in r.blocks.values() if b.settled_by == uuid]:
                del r.blocks[b.index]
                gone.append(b)
        return gone

    def awaited(self):
        """The rows named for blocks still drawn, in drawing order, once each."""
        return list(dict.fromkeys(b.settled_by for b in self.all() if b.settled_by is not None))

    def all(self):
        for r in self.requests.values():
            for i in sorted(r.blocks):
                yield r.blocks[i]

    def blocks(self, agent):
        return [b for b in self.all() if b.agent == agent]


def row_text(row, kind):
    """What a block's row says it streamed, for its kind: the text, the
    thinking, a tool call's input; None when the row says nothing of it."""
    content = (row.get("message") or {}).get("content") if isinstance(row.get("message"), dict) else None
    if not isinstance(content, list) or not content or not isinstance(content[0], dict):
        return None
    c = content[0]
    if kind == "text" and c.get("type") == "text":
        return c.get("text")
    if kind == "thinking" and c.get("type") in ("thinking", "redacted_thinking"):
        return c.get("thinking")
    if kind == "tool" and c.get("type") in ("tool_use", "server_tool_use"):
        return c.get("input")
    return None


def same_text(block, said):
    """Whether a block's drawn text is what its row says: whole, or, for a
    text or thinking block the producer cut to its tail (`truncated`), the
    end of it; a tool call's input whole is compared as JSON."""
    if block.kind != "tool":
        return said.endswith(block.text) if block.truncated else said == block.text
    try:
        return json.loads(block.text) == said
    except ValueError:
        return False


def spans_overlap(a, b):
    """Whether two lists of closed message spans [first, last] share a message
    (an open span's last is None: up to now)."""
    for lo, hi in a:
        for lo2, hi2 in b:
            if (hi is None or lo2 <= hi) and (hi2 is None or lo <= hi2):
                return True
    return False


# What a re-subscribe hands on: the drawing and everything the inventory reads.
SHARED = ("layer", "rows", "held", "row_of", "off", "served", "errors", "t", "ever", "reached_first",
          "drawn_spans", "held_spans", "settled", "settled_at", "redrawn", "left", "vanished", "dup_rows",
          "dropped", "other", "live_rows", "followed", "tails")


class Consumer:
    """One subscription's DX4, applied as the web applies it (module doc).
    `scope_agent` is the subscription's agentId (None: the main loop)."""

    def __init__(self, scope_agent=None, previous=None):
        self.agent = scope_agent
        # This subscription's own.
        self.n = -1
        self.end = None
        self.snapshot = None
        self.got = set()              # rows delivered on this subscription (a second is a `dup`)
        self.upto = {}                # (turnId, agentId, step) → this subscription's watermark
        self.kinds = []
        self.stamps = []              # each chunk's `t`, the bridge's stamp
        self.step_ends = []
        self.pages = []
        self.outputs = []
        self.usage = []
        self.diff = None
        self.subagents = None
        self.body = None              # the last widened `subagents` body: {subagents, jobs, mcp}
        self.changes = []             # (when it came, body) per `subagents` message
        self.marked = {}              # a `row` that carried marks: its uuid → (offChain, onChain)
        # What the store side did after the last message (for the fixture's replay keys).
        self.last_settle = []         # rows that settled blocks
        self.last_landing = None      # a resumed snapshot's `landing`
        self.last_lands = None        # the uuids its `lands` answered true for
        self.sub_id = None            # this subscription's DX4 `sub`, from its first envelope
        if previous is not None:
            for k in SHARED:
                setattr(self, k, getattr(previous, k))
            return
        self.layer = Layer()
        self.rows = []                # the rows held, oldest first
        self.held = set()             # the held rows' uuids
        self.row_of = {}              # uuid → row, every row ever held
        self.off = set()              # rows marked off the live chain
        self.served = False           # a snapshot was drawn: the next one resumes
        self.errors = []
        self.t = 0                    # messages taken, across re-subscribes: the inventory's clock
        self.ever = set()             # every row delivered, on any subscription
        self.reached_first = False    # a snapshot or page said no older rows are left
        self.drawn_spans = {}         # block key → [[first, last], ...] messages it was drawn after
        self.held_spans = {}          # uuid → [[first, last or None], ...] messages its row was held after
        self.settled = set()          # blocks settled by their own row, or by another loop's block-row
        self.settled_at = {}          # block key → the message that settled it
        self.redrawn = []             # blocks drawn again after they settled
        self.left = {}                # block key → the message it left the drawing in, unsettled
        self.vanished = []            # named blocks dropped before their row landed
        self.dup_rows = []
        self.dropped = {}             # a block a step-end dropped (no block-row named it): its text
        self.other = {}               # another loop's block settled by its block-row: uuid → its text
        self.live_rows = {}           # uuid → (the message whose `row` brought it first, not held before,
                                      #         the `sub` of the subscription it came on)
        self.followed = set()         # (turnId, agentId, step): requests the view saw streaming, named or ended
        self.tails = {}               # a truncated tool block settled by its own row: key → the tail drawn

    # ---------------------------------------------------- reading

    def uuids(self):
        """The held rows' uuids, oldest first."""
        return [r["uuid"] for r in self.rows]

    def drawn(self):
        """The held rows on the chain, in order: what the desk draws as read."""
        return [u for u in self.uuids() if u not in self.off]

    def blocks(self, agent):
        """One agent's drawn blocks, in drawing order."""
        return self.layer.blocks(agent)

    def texts(self):
        """Every drawn block's text by (turnId, agentId, step, index)."""
        return {b.key: b.text for b in self.layer.all()}

    def drawn_by_agent(self):
        """The drawing as dx4-stream.json's `drawn`: agentId (or "main") → its blocks."""
        out = {}
        for b in self.layer.all():
            out.setdefault("main" if b.agent is None else b.agent, []).append(b.drawn())
        return out

    def error_kinds(self):
        return [e.split(" ", 1)[0] for e in self.errors]

    # ---------------------------------------------------- applying

    def error(self, kind, what):
        self.errors.append("%s %s" % (kind, what))

    def take(self, env):
        n, kind, body = env.get("n"), env.get("kind"), env.get("body") or {}
        self.t += 1
        self.kinds.append(kind)
        if self.sub_id is None:
            self.sub_id = env.get("sub")
        self.last_settle, self.last_landing, self.last_lands = [], None, None
        if self.end is not None:
            # The web's subscription is closed once it ended: it applies nothing more.
            self.error("after-end", "a %s after end" % kind)
            return
        if n != self.n + 1:
            self.error("gap", "n went %s → %s (%s)" % (self.n, n, kind))
        self.n = n if type(n) is int else self.n
        before = {b.key: b for b in self.layer.all()}
        gone = {}                     # block key → why it may leave the drawing this message
        if kind == "snapshot":
            self.take_snapshot(body, gone)
        if kind in ("chunk", "block-row", "step-end"):
            self.followed.add((body.get("turnId"), body.get("agentId"), body.get("step")))
        if kind == "chunk":
            self.stamps.append(body.get("t"))
            key = (body.get("turnId"), body.get("agentId"), body.get("step"))
            index = body.get("chunkIndex")
            if type(index) is int:
                if index <= self.upto.get(key, -1):
                    self.error("watermark", "chunk %s %d at or below its watermark" % (key, index))
                self.upto[key] = max(index, self.upto.get(key, -1))
            self.layer.chunk(body)
        elif kind == "block-row":
            self.layer.block_row(body)
            if body.get("agentId") != self.agent:
                # Another loop's block (a subagent's, on the main subscription): its row never
                # comes here, so it settles now (desk-transcript's `receive`).
                for b in self.layer.settle(body.get("uuid")):
                    gone[b.key] = "settled"
                    self.settled.add(b.key)
                    self.settled_at[b.key] = self.t
                    self.other[body.get("uuid")] = b.text
                self.other.setdefault(body.get("uuid"), None)
                self.last_settle.append(body.get("uuid"))
        elif kind == "step-end":
            self.step_ends.append((body.get("turnId"), body.get("agentId"), body.get("step")))
            for b in self.layer.step_end(body):
                gone[b.key] = "step-end"
                self.dropped[b.key] = b.text
        elif kind == "row":
            row = body.get("row") if isinstance(body.get("row"), dict) else {}
            for k in ("offChain", "onChain"):
                if k in body and not body[k]:
                    self.error("marks", "a row's %s present and empty" % k)
            self.off |= set(body.get("offChain", ()))
            self.off -= set(body.get("onChain", ()))
            if "offChain" in body or "onChain" in body:
                self.marked[row.get("uuid")] = (body.get("offChain", []), body.get("onChain", []))
            self.deliver(row)
            if isinstance(row.get("uuid"), str) and row["uuid"] not in self.held:
                self.live_rows.setdefault(row["uuid"], (self.t, self.sub_id))
                self.rows.append(row)
                self.hold(row)
        elif kind == "rows":
            self.pages.append(body)
            rows = [r for r in reversed(body.get("rows") or []) if isinstance(r, dict) and isinstance(r.get("uuid"), str)]
            once = {}
            for r in rows:
                if r["uuid"] in once:
                    self.error("dup", "row %s twice in one page" % r["uuid"])
                    self.dup_rows.append(r["uuid"])
                once.setdefault(r["uuid"], r)
                self.ever.add(r["uuid"])
            older = [r for u, r in once.items() if u not in self.held]
            self.check_marks(rows, body.get("offChain") or [])
            if older:
                # desk-transcript's `older`: the marks are applied to the rows it newly holds.
                self.apply_marks(older, body.get("offChain") or [])
                self.rows[:0] = older
                for r in older:
                    self.hold(r)
            if not body.get("more"):
                self.reached_first = True
        elif kind == "end":
            self.end = body
        elif kind == "subagents":
            self.subagents = body.get("subagents")
            self.body = body
            self.changes.append((time.monotonic(), body))
        elif kind == "output":
            self.outputs.append(body)
        elif kind == "usage":
            self.usage.append(body)
        elif kind == "diff":
            self.diff = body
        self.settle_landed(gone)
        self.account(before, gone)

    def take_snapshot(self, body, gone):
        self.snapshot = body
        self.subagents = body.get("subagents")
        self.body = {k: body.get(k) for k in ("subagents", "jobs", "mcp")}
        fresh = [r for r in reversed(body.get("rows") or []) if isinstance(r, dict) and isinstance(r.get("uuid"), str)]
        for r in fresh:
            self.deliver(r)
        for e in body.get("streaming") or []:
            if not isinstance(e, dict):
                continue
            self.followed.add((e.get("turnId"), e.get("agentId"), e.get("step")))
            if type(e.get("upTo")) is int:
                self.upto[(e.get("turnId"), e.get("agentId"), e.get("step"))] = e["upTo"]
        if not body.get("more"):
            self.reached_first = True
        if not self.served:
            self.off = set()
            self.mark(fresh, body.get("offChain") or [])
            self.set_rows(fresh)
            self.layer.load(body.get("streaming") or [])
        else:
            merged = self.merged(fresh)
            if merged is None:
                self.off = set()
            before = set(self.held)
            self.mark(fresh, body.get("offChain") or [])
            self.set_rows(merged if merged is not None else fresh)
            landing = next((r["uuid"] for r in reversed(self.rows) if r["uuid"] not in before), None)
            asked = {}

            def lands(uuid):
                asked[uuid] = merged is not None or uuid in self.held
                return asked[uuid]

            for b in self.layer.resume(body.get("streaming") or [], landing, lands):
                gone[b.key] = "resume"
            self.last_landing = landing
            self.last_lands = [u for u, yes in asked.items() if yes]
        self.served = True

    def merged(self, fresh):
        """The held rows with a fresh snapshot merged in where its oldest row
        is held (desk-transcript's `merged`, less its offChain vouching); None:
        it replaces them."""
        if not fresh:
            return None
        at = next((i for i, r in enumerate(self.rows) if r["uuid"] == fresh[0]["uuid"]), -1)
        if at < 0:
            return None
        inside = {r["uuid"] for r in fresh}
        return self.rows[:at] + fresh + [r for r in self.rows[at:] if r["uuid"] not in inside]

    def mark(self, rows, off):
        self.check_marks(rows, off)
        self.apply_marks(rows, off)

    def check_marks(self, rows, off):
        carried = {r["uuid"] for r in rows}
        if not set(off) <= carried:
            self.error("marks", "offChain names rows the message does not carry: %s" % sorted(set(off) - carried))

    def apply_marks(self, rows, off):
        """Each of `rows` on the chain unless `off` names it (desk-transcript's `mark`)."""
        self.off = (self.off - {r["uuid"] for r in rows}) | set(off)

    def deliver(self, row):
        """A row this subscription was sent: twice is a `dup`."""
        u = row.get("uuid")
        if not isinstance(u, str):
            return
        if u in self.got:
            self.error("dup", "row %s twice" % u)
            self.dup_rows.append(u)
        self.got.add(u)
        self.ever.add(u)

    def set_rows(self, rows):
        for u in self.held - {r["uuid"] for r in rows}:
            spans = self.held_spans.get(u)
            if spans and spans[-1][1] is None:
                spans[-1][1] = self.t - 1
        self.rows = list(rows)
        self.held = set()
        for r in self.rows:
            self.hold(r)

    def hold(self, row):
        u = row["uuid"]
        self.held.add(u)
        self.row_of[u] = row
        spans = self.held_spans.setdefault(u, [])
        if not spans or spans[-1][1] is not None:
            spans.append([self.t, None])

    def settle_landed(self, gone):
        """The store side after a message (desk-transcript's settleLanded):
        each row a drawn block awaits that is held settles it."""
        for u in self.layer.awaited():
            if u not in self.held:
                continue
            self.last_settle.append(u)
            for b in self.layer.settle(u):
                gone[b.key] = "settled"
                if not b.own:
                    continue   # settled by the newest row a resume brought, not its own
                self.settled.add(b.key)
                self.settled_at[b.key] = self.t
                if b.kind == "tool" and b.truncated:
                    self.tails[b.key] = b.text   # the inventory checks it against what streamed
                    continue
                said = row_text(self.row_of[u], b.kind)
                if said is None:
                    continue
                if not same_text(b, said):
                    self.error("differs", "block %s drew %r, its row says %r" % (b.key, b.text, said))

    def account(self, before, gone):
        """What left the drawing and what is drawn, for the inventory."""
        now = {b.key: b for b in self.layer.all()}
        for key, b in before.items():
            if key in now or gone.get(key) == "settled":
                continue
            if b.settled_by is not None and b.settled_by not in self.held:
                self.error("vanished", "block %s left before its row %s landed" % (key, b.settled_by))
                self.vanished.append(key)
            self.left[key] = self.t
        for key in now:
            spans = self.drawn_spans.setdefault(key, [])
            if spans and spans[-1][1] == self.t - 1:
                spans[-1][1] = self.t
            else:
                spans.append([self.t, self.t])
            if key in self.settled_at and key not in self.redrawn:
                self.redrawn.append(key)


class Inventory:
    """What should have been drawn, from the sources of truth: `rows` every
    row of the transcript on disk in file order; `blocks` every block that
    streamed — (turnId, agentId, step, index) → {"kind", "text", "uuid"}, its
    final text and the row its block-row named (None: none did); `snapshots`
    a subscription's `sub` → the position in the DX5 events of the snapshot
    served to it; `ended` each request's (turnId, agentId, step) → the
    position of its first step end."""

    def __init__(self, rows, blocks, snapshots=None, ended=None):
        self.rows, self.blocks = rows, blocks
        self.snapshots, self.ended = dict(snapshots or {}), dict(ended or {})

    @classmethod
    def from_sources(cls, transcript_path, dx5_events):
        """A transcript not written yet holds no rows; any other failure to
        read it raises: an inventory that read nothing must not pass a run."""
        rows = []
        order = order_of(dx5_events)
        try:
            f = open(transcript_path, "rb")
        except FileNotFoundError:
            return cls(rows, blocks_of(dx5_events), *order)
        with f:
            for line in f:
                if not line.endswith(b"\n"):
                    break
                try:
                    row = json.loads(line)
                except ValueError:
                    continue   # a line that is no row: the engine's bookkeeping, as the plane passes it over
                if isinstance(row, dict) and isinstance(row.get("uuid"), str) and row["uuid"]:
                    rows.append(row)
        return cls(rows, blocks_of(dx5_events), *order)

    def check(self, consumer):
        """{"holes", "partial", "vanished", "dups", "undrawn", "residual"} for
        the consumer's own loop (module doc)."""
        order = [r["uuid"] for r in self.rows]
        if consumer.reached_first:
            start = 0
        else:
            start = next((i for i, u in enumerate(order) if u in consumer.ever), len(order))
        holes = [u for u in order[start:] if u not in consumer.ever]
        mine = {k: v for k, v in self.blocks.items() if k[1] == consumer.agent}
        partial, vanished, undrawn, residual = [], [], [], []
        for key, b in mine.items():
            spans = consumer.drawn_spans.get(key)
            held = consumer.held_spans.get(b["uuid"], []) if b["uuid"] else []
            landed, on = consumer.live_rows.get(b["uuid"], (None, None)) if b["uuid"] else (None, None)
            if landed is not None and not any(lo < landed for lo, _ in spans or ()):
                (residual if self.ended_before(key, on) and key[:3] not in consumer.followed
                 else undrawn).append(ref(key))
            tail = consumer.tails.get(key)
            if (spans and held and spans_overlap(spans, held)) or (tail is not None and not b["text"].endswith(tail)):
                partial.append({**ref(key), "text": b["text"]})
            if key in consumer.vanished:
                vanished.append(ref(key))
            elif key in consumer.left and b["uuid"] is not None:
                at = consumer.left[key]
                if not spans_overlap([[at, at]], held):
                    vanished.append(ref(key))
        dups = list(consumer.dup_rows) + [ref(k) for k in consumer.redrawn if k[1] == consumer.agent]
        return {"holes": holes, "partial": partial, "vanished": vanished, "dups": dups, "undrawn": undrawn,
                "residual": residual}

    def ended_before(self, key, sub):
        """Whether the source shows the block's request ended before the
        snapshot served to subscription `sub`; not when no snapshot names it."""
        ended, served = self.ended.get(key[:3]), self.snapshots.get(sub)
        return ended is not None and served is not None and ended < served


def order_of(events):
    """Where the snapshot served to each subscription and each request's
    first step end fall in the DX5 events: (`sub` → snapshot position,
    (turnId, agentId, step) → step end position)."""
    snapshots, ended = {}, {}
    for i, e in enumerate(events):
        if not isinstance(e, dict):
            continue
        if e.get("type") == "snapshot" and isinstance(e.get("sub"), str):
            snapshots.setdefault(e["sub"], i)
        elif e.get("type") == "step" and e.get("phase") == "end":
            ended.setdefault((e.get("turnId"), e.get("agentId"), e.get("step")), i)
    return snapshots, ended


def blocks_of(events):
    """Every block the DX5 events streamed, with its final text and the row
    its block-row named: from chunks (folded as the bridge folds them), a
    snapshot's or resync's streaming entries (a probe that came in late),
    and block-rows."""
    blocks, upto = {}, {}
    for e in events:
        if not isinstance(e, dict):
            continue
        t = e.get("type")
        if t in ("snapshot", "resync"):
            for entry in e.get("streaming") or []:
                ids = (entry.get("turnId"), entry.get("agentId"), entry.get("step"))
                if type(entry.get("upTo")) is int:
                    upto[ids] = max(upto.get(ids, -1), entry["upTo"])
                for b in entry.get("blocks") or []:
                    key = ids + (b.get("index"),)
                    held = blocks.setdefault(key, {"kind": kind_of(b.get("kind")), "text": "", "uuid": None})
                    if len(b.get("text") or "") > len(held["text"]):
                        held["text"] = b["text"]
                    if isinstance(b.get("uuid"), str):
                        held["uuid"] = b["uuid"]
        elif t == "chunk":
            ids = (e.get("turnId"), e.get("agentId"), e.get("step"))
            index = e.get("chunkIndex")
            if type(index) is not int or index <= upto.get(ids, -1):
                continue
            upto[ids] = index
            c = e.get("chunk") or {}
            kind = c.get("kind")
            if type(c.get("index")) is not int or kind not in ("text", "thinking", "tool", "input"):
                continue
            held = blocks.setdefault(ids + (c["index"],), {"kind": kind_of("tool" if kind == "input" else kind),
                                                           "text": "", "uuid": None})
            if kind in ("text", "thinking"):
                held["text"] += str(c.get("text") or "")
            elif kind == "input":
                held["text"] += str(c.get("json") or "")
        elif t == "block-row":
            key = (e.get("turnId"), e.get("agentId"), e.get("step"), e.get("index"))
            held = blocks.setdefault(key, {"kind": "text", "text": "", "uuid": None})
            held["uuid"] = e.get("uuid")
    return blocks
