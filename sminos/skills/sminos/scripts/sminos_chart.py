#!/usr/bin/env python3
"""sminos_chart — the project families drawn as boxes.

Three pure layers over the registry that `sminos.py` exposes:

  snapshot()     reads the projects' members and their state words into
                 NODES — flat: one project's members are roots, or, for
                 several projects, each project is a box with its members
                 beside it — and applies the hide rule (hidden members fold
                 into a "+N hidden" note); there is no tree of seats;
  layout()       places one box per node left-to-right — roots in the first
                 column, children one column to the right, siblings stacked
                 vertically, a parent centred on its children — and computes
                 the connector cells between them;
  paint_chart()  draws boxes and connectors onto a Screen.

GridScreen renders to text (backs `sminos chart` and the tests); the curses TUI
supplies its own Screen subclass. Nothing here writes to the registry.
"""

import os
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import sminos  # noqa: E402

GLYPH = {"busy": "●", "idle": "○", "waiting": "◐", "stopped": "■", "gone": "✕", "vacant": "◌", "retired": "⊘"}
BOX_LINES = 4

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


def is_dead(st):
    """Display-hidden and dimmed when shown, not ineligible for actions:
    stopped members can resume. `list` folds the same words (sminos.HIDDEN)."""
    return st in sminos.HIDDEN


def member_node(project, m, label):
    """One member's box, carrying the facts `list` prints (§7): the in-charge
    line, `now:` the status, `by` the spawner, and for a member on another
    machine `@machine age` beside its word. `id` keys the box by the
    project's id and the seat's (or the session's) — names repeat across
    projects; `name` is the qualified one shown. `ref` is what `sminos send`
    takes for it: exactly the seat's id, else the session's — a seat's
    group/alias can name a seat-less member too."""
    seat = m.seat
    return {"kind": "seat", "id": "%s/%s" % (project.id, seat["seat_id"] if seat else m.session),
            "name": "%s/%s" % (project.name, label), "label": label,
            "role": (seat or {}).get("role") or "", "state": m.state, "word": sminos.state_column(m),
            "charge": sminos.charge_shown(m), "now": m.status, "by": m.by, "dead": is_dead(m.state),
            "children": [], "hidden": 0, "seat": sminos.public_seat(seat) if seat else None,
            "member": sminos.member_json(m), "project": project,
            "ref": seat["seat_id"] if seat else m.session}


def project_members(project, show_all=False, show_stopped=False):
    """One project's members as flat nodes, newest join first, after the hide
    rule: (nodes, hidden, n_members, n_live)."""
    rows = sminos.project_rows(project)
    nodes = [member_node(project, m, sminos.member_label(m, rows)) for m in rows]
    kept = [n for n in nodes if show_all or not n["dead"] or (show_stopped and n["state"] == "stopped")]
    return kept, len(nodes) - len(kept), len(nodes), sum(1 for n in nodes if n["state"] in sminos.FILLED)


def snapshot(projects, show_all=False, boxed=True, show_stopped=False):
    """(roots, meta). Unboxed: the projects' members, flat, as roots. Boxed:
    one rounded PROJECT node per project, its children its members; a project
    with nothing visible is dropped (counted in meta["hidden_projects"])
    unless show_all. meta = {"projects", "members", "live", "hidden",
    "hidden_projects"}."""
    roots, meta = [], {"projects": 0, "members": 0, "live": 0, "hidden": 0, "hidden_projects": 0}
    names = [p.name for p in projects]
    for p in projects:
        nodes, hidden, n, live = project_members(p, show_all, show_stopped)
        meta["projects"] += 1
        meta["members"] += n
        meta["live"] += live
        meta["hidden"] += hidden
        if not boxed:
            roots += nodes
            continue
        if not nodes and not show_all:
            meta["hidden_projects"] += 1
            continue
        name = p.name if names.count(p.name) == 1 else "%s#%s" % (p.name, p.id[:8])
        roots.append({"kind": "project", "id": p.id, "name": name, "label": p.name, "role": "", "state": "", "word": "",
                      "charge": "", "now": "", "by": "", "dead": False, "children": nodes, "hidden": hidden, "members": n, "alive": live,
                      "project": p})
    return roots, meta


# -------------------------------------------------------------------- layout


def node_lines(node, collapsed=()):
    """The box's four content lines as (left, right) pairs; `right` is
    right-aligned on the same line (a seat's ROLE). A member: its name, its
    word, its in-charge line, then `now:` its status and `by` its spawner."""
    if node["kind"] == "project":
        counts = "%d members · %d live" % (node["members"], node["alive"])
        if node["id"] in collapsed and node["children"]:
            counts = "▸ " + counts
        return [(node["label"], ""), (counts, ""), (("+%d hidden" % node["hidden"]) if node["hidden"] else "", ""),
                ("", "")]
    tail = " · ".join(x for x in (("now: " + node["now"]) if node["now"] else "",
                                  ("by " + node["by"]) if node["by"] else "") if x)
    return [(node["label"], (node["role"] or "").upper()), (glyph_line(node), ""), (node["charge"], ""), (tail, "")]


def glyph_line(node):
    """The state glyph and the word as `list` prints it: for a member on
    another machine, `@machine age` beside its last published word ("?"
    before it published one)."""
    return "%s %s" % (GLYPH.get(node["state"], "?"), node.get("word") or node["state"] or "?")


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
    `styles` maps names — focus, dim, project, edge, and the state words —
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
        elif n["kind"] == "project":
            tl, tr, bl, br, hz, vt = ROUND
            attr = st.get("project", 0)
        else:
            tl, tr, bl, br, hz, vt = PLAIN
            attr = st.get("dim", 0) if n["dead"] else 0
        inner = b["w"] - 4
        y0, x0 = b["y"] - oy, b["x"] - ox
        screen.put(y0, x0, tl + hz * (b["w"] - 2) + tr, attr)
        for i, (left, right) in enumerate(node_lines(n, collapsed)):
            line_attr = attr
            if i == 1 and n["kind"] == "seat" and not n["dead"]:
                line_attr = attr | st.get(n["state"], 0)
            screen.put(y0 + 1 + i, x0, vt + " ", attr)
            screen.put(y0 + 1 + i, x0 + 2, render_line(left, right, inner), line_attr)
            screen.put(y0 + 1 + i, x0 + b["w"] - 2, " " + vt, attr)
        screen.put(y0 + b["h"] - 1, x0, bl + hz * (b["w"] - 2) + br, attr)
