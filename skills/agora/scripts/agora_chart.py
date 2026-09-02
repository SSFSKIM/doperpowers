#!/usr/bin/env python3
"""agora_chart — the seat fleet drawn as a box organisation chart.

Three pure layers over the registry that `agora.py` exposes:

  snapshot()     reads seats + live state into a tree of NODES and applies the
                 hide rule (dead seats fold into a "+N retired" note);
  layout()       places one box per node left-to-right — roots in the first
                 column, children one column to the right, siblings stacked
                 vertically, a parent centred on its children — and computes
                 the connector cells between them;
  paint_chart()  draws boxes and connectors onto a Screen.

GridScreen renders to text (backs `agora chart` and the tests); the curses TUI
supplies its own Screen subclass. Nothing here writes to the registry.
"""

import glob
import os
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import agora  # noqa: E402

GLYPH = {"busy": "●", "idle": "○", "blocked": "◐", "stopped": "■", "vacant": "◌", "gone": "✕", "unknown": "?"}
DEAD_STATUSES = ("retired", "failed", "error")
BOX_LINES = 3

# ------------------------------------------------------------- display width


def cwidth(ch):
    """Cells one character occupies: 0 for combining marks, 2 for East Asian
    wide/fullwidth characters (Korean, CJK), 1 otherwise."""
    if unicodedata.combining(ch):
        return 0
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def dwidth(s):
    return sum(cwidth(ch) for ch in s)


def fit(s, n, collapse=True):
    """`s` on one line, truncated to `n` display cells (ending in … when cut),
    then padded with spaces to exactly `n` cells — so a Korean status line and
    an ASCII one fill a box to the same border column. Runs of whitespace are
    collapsed unless `collapse` is False (columnar text)."""
    if n <= 0:
        return ""
    s = " ".join(str(s).split()) if collapse else str(s).replace("\n", " ")
    w = dwidth(s)
    if w <= n:
        return s + " " * (n - w)
    out, w = "", 0
    for ch in s:
        cw = cwidth(ch)
        if w + cw > n - 1:
            break
        out += ch
        w += cw
    out += "…"
    w += 1
    return out + " " * (n - w)


# ------------------------------------------------------------------ snapshot


def is_dead(seat, live):
    """A dead seat is history: retired/failed/errored on record, or a seat whose
    session the harness no longer knows (gone). `stopped` is NOT dead — attach
    wakes it. `vacant` is a position waiting to be filled."""
    return seat.get("status") in DEAD_STATUSES or live == "gone"


def seat_node(s, live, node_id):
    return {"kind": "seat", "id": node_id, "label": s["alias"], "role": s["role"], "live": live,
            "status": s["status"], "now": agora.now_or_reply(s), "dead": is_dead(s, live),
            "children": [], "hidden": 0, "seat": agora.public_seat(s)}


def count_nodes(nodes):
    return sum(1 + count_nodes(n["children"]) for n in nodes)


def group_tree(group, show_all=False):
    """One group's seats as a forest after the hide rule.

    Returns (roots, hidden, n_seats, n_live). `hidden` is how many seats were
    folded away in total; each kept node's own `hidden` counts the folded seats
    beneath it (whole subtrees, so "+N retired" is the full count).
    """
    gs = sorted(agora.seats(group), key=lambda s: (s["alias"], s["seat_id"]))
    aliases = {s["alias"] for s in gs}
    nodes, ids = {}, set()
    for s in gs:
        nid = "%s/%s" % (s["group"], s["alias"])
        if nid in ids:  # a duplicate alias in one group still gets its own box
            nid += "#" + s["seat_id"][:8]
        ids.add(nid)
        nodes[s["seat_id"]] = seat_node(s, agora.live_state(s), nid)
    n_live = sum(1 for n in nodes.values() if n["live"] in agora.FILLED)
    visited = set()

    def walk(s):
        node = nodes[s["seat_id"]]
        visited.add(s["seat_id"])
        for c in gs:
            if c["parent"] == s["alias"] and c["seat_id"] not in visited and c["seat_id"] != s["seat_id"]:
                node["children"].append(walk(c))
        return node

    roots = []
    for s in gs:
        if s["seat_id"] in visited:
            continue
        if not s["parent"] or s["parent"] not in aliases or s["parent"] == s["alias"]:
            roots.append(walk(s))
    for s in gs:  # members of a parent cycle are reachable from no root: break it here
        if s["seat_id"] not in visited:
            roots.append(walk(s))

    def prune(node):
        kept = []
        for c in node["children"]:
            if prune(c):
                kept.append(c)
            else:
                # c is folded away: it, whatever is still hanging off it, and
                # everything prune() already folded away beneath it — else a
                # parent says "+1 retired" over a whole dead subtree while the
                # summary counts every seat in it.
                node["hidden"] += 1 + count_nodes(c["children"]) + c["hidden"]
        node["children"] = kept
        return show_all or not node["dead"] or bool(kept)

    kept_roots = [r for r in roots if prune(r)]
    return kept_roots, len(gs) - count_nodes(kept_roots), len(gs), n_live


def group_names():
    names = {s["group"] for s in agora.seats()}
    for gp in glob.glob(os.path.join(agora.root(), "groups", "*")):
        if os.path.isdir(gp):
            names.add(os.path.basename(gp))
    return sorted(names)


def snapshot(group=None, show_all=False):
    """(roots, meta). With a group: that group's seat forest. Without: one
    rounded GROUP node per group, its children the group's roots; a group with
    nothing visible is dropped (counted in meta["hidden_groups"]) unless
    show_all. meta = {"groups", "seats", "live", "hidden", "hidden_roots",
    "hidden_groups"}."""
    if group is not None:
        roots, hidden, n, live = group_tree(group, show_all)
        return roots, {"groups": 1, "seats": n, "live": live, "hidden": hidden,
                       "hidden_roots": hidden, "hidden_groups": 0}
    roots, meta = [], {"groups": 0, "seats": 0, "live": 0, "hidden": 0, "hidden_roots": 0, "hidden_groups": 0}
    for g in group_names():
        gr, hidden, n, live = group_tree(g, show_all)
        meta["groups"] += 1
        meta["seats"] += n
        meta["live"] += live
        meta["hidden"] += hidden
        if not gr and not show_all:
            meta["hidden_groups"] += 1
            continue
        roots.append({"kind": "group", "id": g, "label": g, "role": "", "live": "", "status": "", "now": "",
                      "dead": False, "children": gr, "hidden": hidden, "seats": n, "alive": live})
    meta["hidden_roots"] = meta["hidden"]
    return roots, meta


# -------------------------------------------------------------------- layout


def node_lines(node, collapsed=()):
    """The box's three content lines as (left, right) pairs; `right` is
    right-aligned on the same line (a seat's ROLE)."""
    if node["kind"] == "group":
        counts = "%d seats · %d live" % (node["seats"], node["alive"])
        if node["id"] in collapsed and node["children"]:
            counts = "▸ " + counts
        return [(node["label"], ""), (counts, ""), (("+%d retired" % node["hidden"]) if node["hidden"] else "", "")]
    live = node["live"] or "unknown"
    state = "%s %s" % (GLYPH.get(live, "?"), live)
    tail = node["now"] or (("+%d retired" % node["hidden"]) if node["hidden"] else "")
    return [(node["label"], (node["role"] or "").upper()), (state, ""), (tail, "")]


def line_need(left, right):
    return dwidth(left) + (dwidth(right) + 2 if right else 0)


def render_line(left, right, inner):
    if not right:
        return fit(left, inner)
    rw = dwidth(right)
    if rw + 2 >= inner:
        return fit(left, inner)
    return fit(left, inner - rw - 1) + " " + right


def layout(roots, box_lines=BOX_LINES, gap=4, min_w=16, max_w=30, collapsed=()):
    """Boxes and connector cells for a forest.

    Column `d` holds every node at depth d; its width is the widest content line
    at that depth plus 4 (borders and padding), clamped to [min_w, max_w].
    Vertical placement is post-order: a leaf takes the next free row band, a
    parent is centred on its children's span — sibling bands never overlap
    because children bands are disjoint and ordered. Children of a node in
    `collapsed` are not laid out.

    Returns {"boxes": [{node, x, y, w, h, depth, kids}], "by_id": {id: box},
    "edges": [(y, x, text)], "width", "height"}.
    """
    h = box_lines + 2
    depth_w = {}

    def measure(n, d):
        need = max(line_need(l, r) for l, r in node_lines(n, collapsed)) + 4
        depth_w[d] = max(depth_w.get(d, 0), need)
        if n["id"] not in collapsed:
            for c in n["children"]:
                measure(c, d + 1)

    for r in roots:
        measure(r, 0)
    cols = [min(max(depth_w[d], min_w), max_w) for d in range(len(depth_w))]
    xs, x = [], 0
    for w in cols:
        xs.append(x)
        x += w + gap
    boxes, order, cursor = {}, [], [0]

    def place(n, d):
        kids = n["children"] if n["id"] not in collapsed else []
        for c in kids:
            place(c, d + 1)
        if kids:
            y = (boxes[kids[0]["id"]]["y"] + boxes[kids[-1]["id"]]["y"]) // 2
        else:
            y = cursor[0]
            cursor[0] += h + 1
        b = {"node": n, "x": xs[d], "y": y, "w": cols[d], "h": h, "depth": d, "kids": kids}
        boxes[n["id"]] = b
        order.append(b)

    for r in roots:
        place(r, 0)
    order.sort(key=lambda b: (b["depth"], b["y"]))

    edges = []
    mid = h // 2
    for b in order:
        kids = [boxes[k["id"]] for k in b["kids"]]
        if not kids:
            continue
        pm = b["y"] + mid
        xr = b["x"] + b["w"] - 1
        child_x = kids[0]["x"]
        if len(kids) == 1:
            edges.append((pm, xr + 1, "─" * (child_x - xr - 1)))
            continue
        bus = xr + 2
        edges.append((pm, xr + 1, "─"))
        top, bot = kids[0]["y"] + mid, kids[-1]["y"] + mid
        kid_rows = {k["y"] + mid for k in kids}
        for row in range(top, bot + 1):
            here = row in kid_rows
            if row == top:
                ch = "┬" if row == pm else "┌"
            elif row == bot:
                ch = "┴" if row == pm else "└"
            elif here:
                ch = "┼" if row == pm else "├"
            else:
                ch = "┤" if row == pm else "│"
            edges.append((row, bus, ch))
            if here:
                edges.append((row, bus + 1, "─" * (child_x - bus - 1)))
    width = (xs[-1] + cols[-1]) if cols else 0
    height = max((b["y"] + b["h"] for b in order), default=0)
    return {"boxes": order, "by_id": boxes, "edges": edges, "width": width, "height": height}


# ------------------------------------------------------------------- screens


class Screen:
    """A w×h cell grid. put() clips to the grid and walks display cells, so a
    wide character advances two columns; subclasses store one cell at a time."""

    def __init__(self, w, h):
        self.w, self.h = w, h

    def put(self, y, x, text, attr=0):
        if y < 0 or y >= self.h:
            return
        for ch in text:
            cw = cwidth(ch)
            if cw == 0:
                continue
            if x >= self.w or x + cw > self.w:
                return
            if x >= 0:
                self.cell(y, x, ch, cw, attr)
            x += cw

    def cell(self, y, x, ch, cw, attr):
        raise NotImplementedError


class GridScreen(Screen):
    """Text renderer. A wide character occupies its cell and leaves "" in the
    next one; text() drops those markers so each row prints at true width."""

    def __init__(self, w, h):
        super().__init__(w, h)
        self.rows = [[" "] * w for _ in range(h)]

    def cell(self, y, x, ch, cw, attr):
        row = self.rows[y]
        if row[x] == "" and x > 0:  # overwriting the right half of a wide char
            row[x - 1] = " "
        elif x + 1 < self.w and row[x + 1] == "":  # overwriting the left half
            row[x + 1] = " "
        if cw == 2:
            if x + 2 < self.w and row[x + 2] == "":  # the next cell held a wide char's left half
                row[x + 2] = " "
            row[x], row[x + 1] = ch, ""
        else:
            row[x] = ch

    def text(self):
        return "\n".join("".join(c for c in r if c != "").rstrip() for r in self.rows)


# --------------------------------------------------------------------- paint

PLAIN = ("┌", "┐", "└", "┘", "─", "│")
ROUND = ("╭", "╮", "╰", "╯", "─", "│")
HEAVY = ("┏", "┓", "┗", "┛", "━", "┃")


def paint_chart(screen, lay, focus_id=None, ox=0, oy=0, styles=None, collapsed=()):
    """Draw connectors, then boxes, shifted by the viewport offsets (ox, oy).
    `styles` maps names — focus, dim, group, edge, and the live-state words —
    to screen attributes; missing names draw plain."""
    st = styles or {}
    for y, x, text in lay["edges"]:
        screen.put(y - oy, x - ox, text, st.get("edge", 0))
    for b in lay["boxes"]:
        n = b["node"]
        focused = n["id"] == focus_id
        if focused:
            tl, tr, bl, br, hz, vt = HEAVY
            attr = st.get("focus", 0)
        elif n["kind"] == "group":
            tl, tr, bl, br, hz, vt = ROUND
            attr = st.get("group", 0)
        else:
            tl, tr, bl, br, hz, vt = PLAIN
            attr = st.get("dim", 0) if n["dead"] else 0
        inner = b["w"] - 4
        y0, x0 = b["y"] - oy, b["x"] - ox
        screen.put(y0, x0, tl + hz * (b["w"] - 2) + tr, attr)
        for i, (left, right) in enumerate(node_lines(n, collapsed)):
            line_attr = attr
            if i == 1 and n["kind"] == "seat" and not n["dead"]:
                line_attr = attr | st.get(n["live"] or "unknown", 0)
            screen.put(y0 + 1 + i, x0, vt + " ", attr)
            screen.put(y0 + 1 + i, x0 + 2, render_line(left, right, inner), line_attr)
            screen.put(y0 + 1 + i, x0 + b["w"] - 2, " " + vt, attr)
        screen.put(y0 + b["h"] - 1, x0, bl + hz * (b["w"] - 2) + br, attr)
