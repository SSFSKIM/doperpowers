#!/usr/bin/env python3
"""sminos_tui — the organisation chart as an interactive terminal screen.

The chart (sminos_chart) is drawn in the middle of the screen; a header carries
the fleet counts and refresh time, a panel under the chart describes the
focused seat (or lists the group's board), and a footer shows the keys, the
send line being typed, or a short flash message.

Everything that decides is a pure function over one `state` dict:
handle_key() is the whole keymap, paint() draws a state onto any Screen.
Effects live behind an Actions object — RealActions opens tmux windows and
runs `sminos send`; HeadlessActions records what it would have done — so the
same code runs under curses and under `sminos tui --headless --keys …` (the
test surface). Nothing here writes to the registry.
"""

import os
import queue
import shutil
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import sminos  # noqa: E402
import sminos_chart as chart  # noqa: E402

PANEL_H = 7  # one separator row + six content rows
MIN_ROWS_FOR_PANEL = 16
FLASH_SECONDS = 5
KEY_HINTS = "↑↓←→ move · enter attach · s send · b board · a all · r refresh · ? help · q quit"
HELP_LINES = [
    "keys",
    "",
    "↑ ↓ (k j) — move between boxes in the same column",
    "→ (l) — into the first child · ← (h) — back to the parent",
    "home / end — first / last root box",
    "enter — on a seat: open its conversation (claude attach) in a new tmux window, or switch to that window if it is open",
    "enter — on a group: collapse / expand its seats",
    "s — type a message for the focused seat; enter sends it over the seat's inbox socket (sminos send), esc cancels",
    "b — toggle the bottom panel: seat detail ↔ group board",
    "tab — move the keys into the board list (enter opens a post, tab back)",
    "a — show / hide retired, failed and gone seats",
    "r — refresh from the harness now (it also refreshes every few seconds)",
    "? — this help · q — quit (tmux windows opened by enter stay open)",
    "",
    "glyphs: ● busy · ○ idle · ◐ blocked (needs input) · ■ stopped · ◌ vacant · ✕ gone",
]
SPECIAL = {"enter", "esc", "tab", "backspace", "space", "up", "down", "left", "right",
           "home", "end", "pgup", "pgdn", "resize"}


# --------------------------------------------------------------------- state


def new_state(group=None, show_all=False, width=120, height=40, no_tmux=False):
    return {
        "group": group, "show_all": show_all, "width": width, "height": height, "no_tmux": no_tmux,
        "roots": [], "meta": {"groups": 0, "seats": 0, "live": 0, "hidden": 0, "hidden_roots": 0, "hidden_groups": 0},
        "lay": {"boxes": [], "by_id": {}, "edges": [], "width": 0, "height": 0}, "parent": {},
        "collapsed": set(), "focus": None, "ox": 0, "oy": 0,
        "panel": "detail", "panel_focus": False, "board_cursor": 0,
        "overlay": None, "overlay_scroll": 0, "input": None, "input_target": None,
        "flash": None, "clock": time.time, "refreshed_at": 0.0, "refreshing": False, "loaded": False,
        "attached": {}, "actions": [], "quit": False, "styles": {}, "events": None, "refresher": None,
    }


def regions(state):
    w, h = state["width"], state["height"]
    panel_h = PANEL_H if h >= MIN_ROWS_FOR_PANEL else 0
    chart_h = max(1, h - 2 - panel_h)
    return {"chart_y": 1, "chart_h": chart_h, "chart_w": w, "panel_y": 1 + chart_h, "panel_h": panel_h,
            "footer_y": h - 1}


def flash(state, msg):
    state["flash"] = (str(msg), state["clock"]())


def attach_short(seat):
    """The id `claude attach` takes for a seat's current session: the harness
    row's id when the harness knows the session, else the recorded short."""
    row = sminos.harness_row(seat) if seat.get("current") else None
    return str((row or {}).get("id") or seat.get("short") or "")


def take_snapshot(group, show_all):
    """sminos_chart.snapshot plus, on every seat node, the short id Enter would
    attach to — resolved here so it comes from the same harness read as the
    live state."""
    roots, meta = chart.snapshot(group, show_all)

    def walk(n):
        if n["kind"] == "seat":
            n["short"] = attach_short(n["seat"])
        for c in n["children"]:
            walk(c)
    for r in roots:
        walk(r)
    return roots, meta


def rebuild(state):
    """Re-lay the current roots (after a snapshot, a collapse, or a resize),
    keep the focus if its box still exists, else move it to the first root."""
    lay = chart.layout(state["roots"], collapsed=state["collapsed"])
    state["lay"] = lay
    defaulted = state["focus"] not in lay["by_id"]
    if defaulted:
        state["focus"] = lay["boxes"][0]["node"]["id"] if lay["boxes"] else None
    parent = {}
    for b in lay["boxes"]:
        for k in b["kids"]:
            parent[k["id"]] = b["node"]["id"]
    state["parent"] = parent
    ensure_visible(state, center=defaulted)


def refresh(state):
    """Synchronous: forget the harness caches, re-read the fleet, re-lay."""
    sminos.refresh_caches()
    resnapshot(state)


def resnapshot(state):
    """Re-read the registry with the caches as they are (cheap; what `a` uses)."""
    state["roots"], state["meta"] = take_snapshot(state["group"], state["show_all"])
    state["refreshed_at"] = state["clock"]()
    state["refreshing"] = False
    state["loaded"] = True
    rebuild(state)


def focused_node(state):
    b = state["lay"]["by_id"].get(state["focus"])
    return b["node"] if b else None


def ensure_visible(state, center=False):
    """Scroll the chart viewport so the focused box is fully inside it — by the
    least amount (arrow keys), or centred vertically (a freshly placed focus,
    whose box may sit far below its first child)."""
    b = state["lay"]["by_id"].get(state["focus"])
    r = regions(state)
    if not b:
        state["ox"] = state["oy"] = 0
        return
    if center and not (state["oy"] <= b["y"] and b["y"] + b["h"] <= state["oy"] + r["chart_h"]):
        state["oy"] = b["y"] + b["h"] // 2 - r["chart_h"] // 2
    elif b["y"] < state["oy"]:
        state["oy"] = b["y"]
    elif b["y"] + b["h"] > state["oy"] + r["chart_h"]:
        state["oy"] = b["y"] + b["h"] - r["chart_h"]
    if b["x"] < state["ox"]:
        state["ox"] = b["x"]
    elif b["x"] + b["w"] > state["ox"] + r["chart_w"]:
        state["ox"] = b["x"] + b["w"] - r["chart_w"]
    state["ox"] = max(0, state["ox"])
    state["oy"] = max(0, state["oy"])


def board_group(state):
    n = focused_node(state)
    if n is None:
        return state["group"]
    return n["seat"]["group"] if n["kind"] == "seat" else n["label"]


def board_posts(state):
    g = board_group(state)
    return list(reversed(sminos.read_board(g))) if g else []


# ------------------------------------------------------------------- keymap


def move(state, key):
    lay, f = state["lay"], state["focus"]
    if not f or f not in lay["by_id"]:
        return
    b = lay["by_id"][f]
    if key in ("up", "down"):
        cands = [o for o in lay["boxes"] if o["depth"] == b["depth"] and
                 (o["y"] < b["y"] if key == "up" else o["y"] > b["y"])]
        if cands:
            state["focus"] = min(cands, key=lambda o: abs(o["y"] - b["y"]))["node"]["id"]
    elif key == "right":
        if b["kids"]:
            state["focus"] = b["kids"][0]["id"]
    elif key == "left":
        p = state["parent"].get(f)
        if p:
            state["focus"] = p
    elif key == "home":
        state["focus"] = lay["boxes"][0]["node"]["id"]
    elif key == "end":
        roots = [o for o in lay["boxes"] if o["depth"] == 0]
        state["focus"] = roots[-1]["node"]["id"]
    ensure_visible(state)


ARROWS = {"up": "up", "down": "down", "left": "left", "right": "right", "home": "home", "end": "end",
          "k": "up", "j": "down", "h": "left", "l": "right"}


def handle_key(state, key, actions):
    """The whole keymap. `key` is a token: a special name (see SPECIAL) or a
    single printable character."""
    if state["overlay"]:
        if key in ("esc", "q", "?", "enter"):
            state["overlay"], state["overlay_scroll"] = None, 0
        elif key in ("up", "k"):
            state["overlay_scroll"] = max(0, state["overlay_scroll"] - 1)
        elif key in ("down", "j"):
            state["overlay_scroll"] += 1
        elif key == "pgup":
            state["overlay_scroll"] = max(0, state["overlay_scroll"] - 10)
        elif key == "pgdn":
            state["overlay_scroll"] += 10
        return
    if state["input"] is not None:
        if key == "esc":
            state["input"], state["input_target"] = None, None
        elif key == "enter":
            # The message goes to the seat that was focused when the editor
            # opened, never to whatever is focused now: a refresh that lands
            # while the operator is typing rebuilds the layout, and a target
            # that retired or went away moves the focus elsewhere.
            text, target = state["input"].strip(), state["input_target"]
            state["input"], state["input_target"] = None, None
            box = state["lay"]["by_id"].get(target)
            node = box["node"] if box else None
            if not text:
                pass
            elif node is None or node["kind"] != "seat":
                flash(state, "%s is no longer on the chart — nothing was sent" % (target or "the seat"))
            else:
                actions.send(node, text)
        elif key == "backspace":
            state["input"] = state["input"][:-1]
        elif key == "space":
            state["input"] += " "
        elif key not in SPECIAL and len(key) == 1:
            state["input"] += key
        return
    if key == "resize":
        ensure_visible(state)
        return
    if key == "q":
        state["quit"] = True
        return
    if key == "?":
        state["overlay"], state["overlay_scroll"] = "help", 0
        return
    if state["panel_focus"]:
        posts = board_posts(state)
        cur = min(state["board_cursor"], max(0, len(posts) - 1))
        if key in ("up", "k"):
            state["board_cursor"] = max(0, cur - 1)
        elif key in ("down", "j"):
            state["board_cursor"] = min(max(0, len(posts) - 1), cur + 1)
        elif key == "enter" and posts:
            state["overlay"], state["overlay_scroll"] = ("post", posts[cur]), 0
        elif key in ("tab", "esc", "left", "h"):
            state["panel_focus"] = False
        elif key == "b":
            state["panel"], state["panel_focus"] = "detail", False
        return
    node = focused_node(state)
    if key in ARROWS:
        move(state, ARROWS[key])
    elif key == "enter":
        if node is None:
            return
        if node["kind"] == "group":
            if node["id"] in state["collapsed"]:
                state["collapsed"].discard(node["id"])
            else:
                state["collapsed"].add(node["id"])
            rebuild(state)
        else:
            actions.attach(node)
    elif key == "s":
        if node is None or node["kind"] == "group":
            flash(state, "move to a seat to send it a message")
        elif node["live"] in sminos.FILLED:
            state["input"], state["input_target"] = "", node["id"]
        else:
            flash(state, "%s is %s — enter attaches (and wakes) a stopped seat; a vacant or gone seat needs sminos fill"
                  % (node["label"], node["live"]))
    elif key == "a":
        state["show_all"] = not state["show_all"]
        resnapshot(state)
    elif key == "b":
        state["panel"] = "board" if state["panel"] == "detail" else "detail"
        state["board_cursor"], state["panel_focus"] = 0, False
    elif key == "tab":
        if state["panel"] == "board" and regions(state)["panel_h"]:
            state["panel_focus"] = True
    elif key == "r":
        actions.refresh()


# ------------------------------------------------------------------ actions


def attach_target(node):
    """(short, reason): the id Enter attaches to, or why it cannot."""
    if node["kind"] != "seat":
        return "", "move to a seat to open its conversation"
    seat = node["seat"]
    ref = "%s/%s" % (seat["group"], seat["alias"])
    if node["live"] == "gone":
        return "", "%s is gone from the harness — sminos fill --resume %s \"<msg>\" may revive its session" % (node["label"], ref)
    if node["live"] == "vacant" or not node.get("short"):
        return "", "%s is vacant — no session to attach; sminos fill %s \"<task>\"" % (node["label"], ref)
    return node["short"], ""


def send_argv(node, text):
    return [sminos.LAUNCHER, "send", "%s/%s" % (node["seat"]["group"], node["seat"]["alias"]), text]


def first_line(p):
    out = (p.stdout or "").strip() or (p.stderr or "").strip()
    return out.splitlines()[0] if out else "rc=%d" % p.returncode


class HeadlessActions:
    """Records decisions instead of touching tmux; `send` still runs the real
    `sminos send` so a socket stand-in can assert delivery."""

    def __init__(self, state):
        self.state = state

    def attach(self, node):
        short, why = attach_target(node)
        if not short:
            flash(self.state, why)
            return
        cmd = "claude attach %s" % short
        if not self.state["no_tmux"] and os.environ.get("TMUX"):
            cmd = "tmux new-window -n %s %s" % (node["label"], cmd)
        # The qualified id, not the bare alias: two groups may hold the same
        # one, and it is what RealActions keys its open windows by.
        self.state["actions"].append("attach %s %s → %s" % (node["id"], short, cmd))
        flash(self.state, "would run: " + cmd)

    def send(self, node, text):
        try:
            p = subprocess.run(send_argv(node, text), capture_output=True, text=True, timeout=60)
            line, rc = first_line(p), p.returncode
        except (OSError, subprocess.SubprocessError) as e:
            line, rc = str(e), -1
        self.state["actions"].append("send %s %s → rc=%d %s" % (node["label"], text, rc, line))
        flash(self.state, line)

    def refresh(self):
        refresh(self.state)


class RealActions:
    def __init__(self, state):
        self.state = state

    def _tmux(self, *args):
        return subprocess.run(["tmux", *args], capture_output=True, text=True, timeout=10)

    def attach(self, node):
        st = self.state
        short, why = attach_target(node)
        if not short:
            flash(st, why)
            return
        if st["no_tmux"] or not os.environ.get("TMUX"):
            flash(st, "run in another terminal: claude attach %s" % short)
            return
        alias = node["label"]
        # Keyed by the seat's qualified id: two groups may hold the same alias,
        # and a bare-alias key would send one group's Enter to the other's
        # conversation window.
        key = node["id"]
        try:
            wins = self._tmux("list-windows", "-F", "#{window_id}").stdout.split()
            wid = st["attached"].get(key)
            if wid and wid in wins:
                p = self._tmux("select-window", "-t", wid)
                flash(st, "switched to %s (tmux window %s)" % (key, wid) if p.returncode == 0 else first_line(p))
                return
            p = self._tmux("new-window", "-P", "-F", "#{window_id}", "-n", alias, "claude", "attach", short)
            if p.returncode != 0:
                flash(st, "tmux: " + first_line(p))
                return
            wid = p.stdout.strip()
            st["attached"][key] = wid
            flash(st, "opened %s in tmux window %s (claude attach %s)" % (alias, wid, short))
        except (OSError, subprocess.SubprocessError) as e:
            flash(st, "tmux: %s" % e)

    def send(self, node, text):
        st = self.state
        flash(st, "sending to %s/%s…" % (node["seat"]["group"], node["label"]))
        argv = send_argv(node, text)

        def go():
            try:
                p = subprocess.run(argv, capture_output=True, text=True, timeout=60)
                st["events"].put(("flash", first_line(p)))
            except (OSError, subprocess.SubprocessError) as e:
                st["events"].put(("flash", "send failed: %s" % e))
        threading.Thread(target=go, daemon=True).start()

    def refresh(self):
        self.state["refreshing"] = True
        if self.state["refresher"]:
            self.state["refresher"].wake.set()


class Refresher(threading.Thread):
    """Re-reads the fleet every SMINOS_TUI_REFRESH seconds (default 3) — or
    at once when woken — and hands the snapshot to the main loop over the
    events queue. The harness read (`claude agents --json`) takes a second or
    more, which is why it never runs on the drawing thread."""

    def __init__(self, state, events):
        super().__init__(daemon=True)
        self.state, self.events, self.wake = state, events, threading.Event()

    def run(self):
        try:
            interval = float(os.environ.get("SMINOS_TUI_REFRESH", "3"))
        except ValueError:
            interval = 3.0
        while not self.state["quit"]:
            self.events.put(("refreshing",))
            try:
                sminos.refresh_caches()
                roots, meta = take_snapshot(self.state["group"], self.state["show_all"])
                self.events.put(("snapshot", roots, meta))
            except Exception as e:  # a failed read must not kill the screen
                self.events.put(("flash", "refresh failed: %s" % e))
            self.wake.wait(interval)
            self.wake.clear()


# -------------------------------------------------------------------- paint


class Viewport(chart.Screen):
    """A Screen whose rows land on `base` shifted down by y0, clipped to h."""

    def __init__(self, base, y0, h):
        super().__init__(base.w, h)
        self.base, self.y0 = base, y0

    def cell(self, y, x, ch, cw, attr):
        self.base.cell(self.y0 + y, x, ch, cw, attr)


def wrap(text, w):
    out = []
    for para in str(text).split("\n"):
        line = ""
        for word in para.split(" "):
            while chart.dwidth(word) > w:  # a word wider than the box is cut hard
                if line:
                    out.append(line)
                    line = ""
                out.append(chart.fit(word, w).rstrip())
                word = word[len(chart.fit(word, w).rstrip()) - 1:]
            cand = word if not line else line + " " + word
            if chart.dwidth(cand) > w and line:
                out.append(line)
                line = word
            else:
                line = cand
        out.append(line)
    return out


def glyph_line(node):
    live = node["live"] or "unknown"
    return "%s %s" % (chart.GLYPH.get(live, "?"), live)


def detail_lines(state, node, w):
    if node is None:
        m = state["meta"]
        if not state["loaded"]:
            return ["loading the fleet from the harness…"]
        if m["hidden"] and not state["show_all"]:
            return ["nothing to show — %d seat(s) are retired, failed or gone" % m["hidden"], "press a to show them"]
        return ["no seats yet — sminos spawn <alias> \"<task>\" --group <group> creates the first"]
    if node["kind"] == "group":
        g = node["label"]
        lines = ["group %s · %d seats · %d live%s" % (g, node["seats"], node["alive"],
                 (" · %d retired" % node["hidden"]) if node["hidden"] else "")]
        roots = ", ".join(c["label"] for c in node["children"])
        lines.append("roots: " + (roots or "(none visible)"))
        posts = sminos.read_board(g)
        if posts:
            last = posts[-1]
            lines.append("board: %d post(s) — latest #%s%s by %s @ %s" % (
                len(posts), last.get("id"), (' "%s"' % last["title"]) if last.get("title") else "",
                last.get("from"), last.get("ts")))
        else:
            lines.append("board: (no posts)")
        lines.append("enter collapses / expands · b shows the board")
        return lines
    s = node["seat"]
    head = "%s/%s" % (s["group"], s["alias"])
    if s.get("role"):
        head += " · %s" % s["role"].upper()
    head += " · seat %s" % s["seat_id"][:8]
    if s.get("current"):
        head += " · session %s" % s["current"][:8]
    if s.get("parent"):
        head += " · under %s" % s["parent"]
    state_line = "%s · status %s" % (glyph_line(node), s.get("status") or "?")
    if node.get("short"):
        state_line += " · short %s" % node["short"]
    if s.get("updated"):
        state_line += " · updated %s" % s["updated"]
    lines = [head, state_line, "now: " + (s.get("now") or "-"), "brief: " + (s.get("brief") or "-"),
             "cwd: " + (s.get("cwd") or "-") + ((" (worktree %s)" % s["worktree"]) if s.get("worktree") else "")]
    reply = sminos.reply_text(s["seat_id"]).strip()
    lines.append("reply: " + (" ".join(reply.split()) if reply else "-"))
    return [chart.fit(x, w).rstrip() for x in lines]


def paint(state, screen):
    """Draw the whole screen: header, chart, panel, footer, then any overlay."""
    w = screen.w
    r = regions(state)
    st = state["styles"]
    m = state["meta"]
    title = "sminos · " + (state["group"] or "fleet")
    bits = [title]
    if state["group"] is None:
        bits.append("%d groups" % m["groups"])
    bits += ["%d seats" % m["seats"], "%d live" % m["live"]]
    if state["show_all"]:
        bits.append("all shown · a")
    elif m["hidden"]:
        bits.append("%d hidden · a" % m["hidden"])
    screen.put(0, 0, chart.fit(" · ".join(bits), w).rstrip(), st.get("title", 0))
    if state["refreshing"] or not state["loaded"]:
        right = "refreshing…" if state["loaded"] else "loading…"
    else:
        right = "updated " + time.strftime("%H:%M:%S", time.localtime(state["refreshed_at"]))
    if chart.dwidth(right) + 2 < w - chart.dwidth(" · ".join(bits)):
        screen.put(0, w - chart.dwidth(right) - 1, right, st.get("dim", 0))

    lay = state["lay"]
    if lay["boxes"]:
        chart.paint_chart(Viewport(screen, r["chart_y"], r["chart_h"]), lay, state["focus"], state["ox"], state["oy"],
                          st, state["collapsed"])
    else:
        msg = detail_lines(state, None, w - 4)
        for i, line in enumerate(msg[:r["chart_h"]]):
            screen.put(r["chart_y"] + 1 + i, 2, line, st.get("dim", 0))

    if r["panel_h"]:
        node = focused_node(state)
        if state["panel"] == "board":
            g = board_group(state) or "-"
            posts = board_posts(state)
            label = " board · %s · %d post%s · %s " % (g, len(posts), "" if len(posts) == 1 else "s",
                                                       "↑↓ enter opens · tab back" if state["panel_focus"] else "tab to browse")
        else:
            label = " detail "
        sep = "─" * 2 + label + "─" * max(0, w - 2 - chart.dwidth(label))
        screen.put(r["panel_y"], 0, chart.fit(sep, w).rstrip(), st.get("edge", 0))
        rows = r["panel_h"] - 1
        if state["panel"] == "board":
            posts = board_posts(state)
            if not posts:
                screen.put(r["panel_y"] + 1, 1, "(no posts)", st.get("dim", 0))
            else:
                cur = min(state["board_cursor"], len(posts) - 1)
                top = max(0, min(cur - rows + 1, len(posts) - rows)) if cur >= rows else 0
                for i, p in enumerate(posts[top:top + rows]):
                    text = p.get("title") or " ".join(str(p.get("text", "")).split())
                    line = "#%-4s %-20s %-14s %s" % (p.get("id"), str(p.get("ts", ""))[:20], str(p.get("from", ""))[:14], text)
                    attr = st.get("sel", 0) if (state["panel_focus"] and top + i == cur) else 0
                    screen.put(r["panel_y"] + 1 + i, 1, chart.fit(line, w - 2, collapse=False), attr)
        else:
            for i, line in enumerate(detail_lines(state, node, w - 2)[:rows]):
                screen.put(r["panel_y"] + 1 + i, 1, line, st.get("title", 0) if i == 0 else 0)

    if state["input"] is not None:
        # The captured target, not the current focus — they differ when a
        # refresh moves the focus while the operator is typing.
        prompt = "send → %s ▏" % (state["input_target"] or "?")
        footer = prompt + state["input"]
        if chart.dwidth(footer) > w - 1:  # keep the tail visible while typing
            footer = prompt + state["input"][-(max(1, w - 1 - chart.dwidth(prompt)) // 2):]
        screen.put(r["footer_y"], 0, chart.fit(footer, w - 1), st.get("title", 0))
    elif state["flash"] and state["clock"]() - state["flash"][1] < FLASH_SECONDS:
        screen.put(r["footer_y"], 0, chart.fit(state["flash"][0], w - 1), st.get("flash", 0))
    else:
        screen.put(r["footer_y"], 0, chart.fit(KEY_HINTS, w - 1), st.get("dim", 0))

    if state["overlay"]:
        paint_overlay(state, screen)


def overlay_lines(state, inner_w):
    ov = state["overlay"]
    if ov == "help":
        return HELP_LINES
    _, p = ov
    head = "#%s · %s · %s" % (p.get("id"), p.get("from", ""), p.get("ts", ""))
    if p.get("branch"):
        head += " · " + str(p["branch"])
    lines = [head]
    if p.get("title"):
        lines += [str(p["title"]), ""]
    lines += wrap(p.get("text", ""), inner_w)
    return lines


def paint_overlay(state, screen):
    w, h = screen.w, screen.h
    st = state["styles"]
    bw = min(w - 4, 100)
    if bw < 10 or h < 6:
        return
    inner = bw - 4
    lines = overlay_lines(state, inner)
    bh = max(4, min(h - 2, 30, len(lines) + 2))  # sized to the text, capped
    x0, y0 = (w - bw) // 2, (h - bh) // 2
    rows = bh - 2
    scroll = max(0, min(state["overlay_scroll"], max(0, len(lines) - rows)))
    state["overlay_scroll"] = scroll
    attr = st.get("title", 0)
    screen.put(y0, x0, "┏" + "━" * (bw - 2) + "┓", attr)
    for i in range(rows):
        line = lines[scroll + i] if scroll + i < len(lines) else ""
        screen.put(y0 + 1 + i, x0, "┃ " + chart.fit(line, inner) + " ┃", attr)
    foot = " esc closes" + (" · ↑↓ scroll (%d/%d) " % (scroll + rows, len(lines)) if len(lines) > rows else " ")
    bottom = "┗" + "━" * (bw - 2) + "┛"
    screen.put(y0 + bh - 1, x0, bottom, attr)
    screen.put(y0 + bh - 1, x0 + 2, foot, attr)


# ------------------------------------------------------------------- drivers


def parse_keys(spec):
    """"right,down,enter,text:hello,enter" → tokens; text:… types each character
    (a space becomes the `space` token)."""
    out = []
    for tok in (spec or "").split(","):
        tok = tok.strip()
        if not tok:
            continue
        if tok.startswith("text:"):
            out += ["space" if ch == " " else ch for ch in tok[5:]]
        else:
            out.append(tok)
    return out


def drive(state, tok):
    """A `!`-prefixed token in --keys is an instruction to the DRIVER, not a
    keystroke: it reaches past the keymap to do what only the refresh thread
    does in a live screen. `!focus:<id>` moves the focus (what a rebuild does
    when the focused seat disappears) and `!drop:<id>` removes a box from the
    layout (what a snapshot does when a seat is retired mid-turn). Returns
    True when the token was a driver instruction."""
    if not tok.startswith("!"):
        return False
    verb, _, arg = tok[1:].partition(":")
    if verb == "focus":
        state["focus"] = arg
    elif verb == "drop":
        state["lay"]["by_id"].pop(arg, None)
        state["lay"]["boxes"] = [b for b in state["lay"]["boxes"] if b["node"]["id"] != arg]
    elif verb == "refresh":
        resnapshot(state)
    return True


def run_headless(a):
    state = new_state(a.group, a.all, a.width or 120, a.height or 40, no_tmux=a.no_tmux)
    refresh(state)
    actions = HeadlessActions(state)
    for tok in parse_keys(a.keys):
        if drive(state, tok):
            continue
        handle_key(state, tok, actions)
        if state["quit"]:
            break
    scr = chart.GridScreen(state["width"], state["height"])
    paint(state, scr)
    print(scr.text())
    print("--- focus: %s" % (state["focus"] or "-"))
    print("--- actions:")
    for line in state["actions"]:
        print(line)
    if state["quit"]:
        print("--- quit")


class CursesScreen(chart.Screen):
    def __init__(self, stdscr, curses_mod):
        h, w = stdscr.getmaxyx()
        super().__init__(w, h)
        self.scr, self.curses = stdscr, curses_mod

    def put(self, y, x, text, attr=0):
        if y < 0 or y >= self.h:
            return
        out, cx, start = [], x, None
        for ch in text:
            cw = chart.cwidth(ch)
            if cw == 0:
                continue
            if cx + cw > self.w:
                break
            if cx >= 0:
                if start is None:
                    start = cx
                out.append(ch)
            cx += cw
        if out:
            try:
                self.scr.addstr(y, start, "".join(out), attr)
            except self.curses.error:
                pass  # the bottom-right cell always raises after writing

    def cell(self, y, x, ch, cw, attr):
        del cw  # curses advances by the character's own width
        if 0 <= y < self.h and 0 <= x < self.w:
            try:
                self.scr.addstr(y, x, ch, attr)
            except self.curses.error:
                pass


def init_styles(curses):
    st = {"focus": curses.A_BOLD, "dim": curses.A_DIM, "title": curses.A_BOLD, "sel": curses.A_REVERSE,
          "flash": curses.A_BOLD, "vacant": curses.A_DIM, "gone": curses.A_DIM}
    if not curses.has_colors():
        return st
    try:
        curses.use_default_colors()
        colours = [("busy", curses.COLOR_GREEN), ("idle", curses.COLOR_CYAN), ("blocked", curses.COLOR_YELLOW),
                   ("stopped", curses.COLOR_WHITE), ("unknown", curses.COLOR_MAGENTA), ("group", curses.COLOR_BLUE),
                   ("flash", curses.COLOR_YELLOW)]
        for i, (name, col) in enumerate(colours, 1):
            curses.init_pair(i, col, -1)
            st[name] = curses.color_pair(i) | (curses.A_BOLD if name == "flash" else 0)
    except curses.error:
        pass
    return st


def read_key(stdscr, curses):
    try:
        c = stdscr.get_wch()
    except curses.error:
        return None
    if isinstance(c, str):
        table = {"\n": "enter", "\r": "enter", "\x1b": "esc", "\t": "tab", "\x7f": "backspace", "\b": "backspace",
                 " ": "space"}
        if c in table:
            return table[c]
        return c if c.isprintable() else None
    table = {curses.KEY_UP: "up", curses.KEY_DOWN: "down", curses.KEY_LEFT: "left", curses.KEY_RIGHT: "right",
             curses.KEY_ENTER: "enter", curses.KEY_BACKSPACE: "backspace", curses.KEY_HOME: "home",
             curses.KEY_END: "end", curses.KEY_PPAGE: "pgup", curses.KEY_NPAGE: "pgdn", curses.KEY_RESIZE: "resize"}
    return table.get(c)


def main_loop(stdscr, state, curses):
    curses.curs_set(0)
    stdscr.keypad(True)
    stdscr.timeout(250)
    state["styles"] = init_styles(curses)
    h, w = stdscr.getmaxyx()
    state["width"], state["height"] = w, h
    events = queue.Queue()
    state["events"] = events
    refresher = Refresher(state, events)
    state["refresher"] = refresher
    refresher.start()
    actions = RealActions(state)
    while not state["quit"]:
        while True:
            try:
                ev = events.get_nowait()
            except queue.Empty:
                break
            if ev[0] == "snapshot":
                state["roots"], state["meta"] = ev[1], ev[2]
                state["refreshed_at"], state["refreshing"], state["loaded"] = state["clock"](), False, True
                rebuild(state)
            elif ev[0] == "refreshing":
                state["refreshing"] = True
            elif ev[0] == "flash":
                flash(state, ev[1])
        stdscr.erase()
        paint(state, CursesScreen(stdscr, curses))
        stdscr.refresh()
        key = read_key(stdscr, curses)
        if key is None:
            continue
        if key == "resize":
            h, w = stdscr.getmaxyx()
            state["width"], state["height"] = w, h
        handle_key(state, key, actions)
    refresher.wake.set()


def run_curses(state):
    import curses
    import locale
    os.environ.setdefault("ESCDELAY", "25")
    locale.setlocale(locale.LC_ALL, "")
    curses.wrapper(lambda scr: main_loop(scr, state, curses))


TMUX_SESSION = "sminos"


def enter_tmux(argv):
    """Re-run this command inside the `sminos` tmux session, then hand the
    terminal to that session — this call does not return.

    The session usually outlives the chart: quitting leaves the conversation
    windows Enter opened. `new-session -A` would then merely ATTACH and drop
    the command, landing the operator in an old conversation with no chart, so
    an existing session gets a fresh window instead.
    """
    cmd = [sys.executable, os.path.realpath(sminos.__file__), *argv]
    exists = subprocess.run(["tmux", "has-session", "-t", TMUX_SESSION],
                            capture_output=True).returncode == 0
    if exists:
        subprocess.run(["tmux", "new-window", "-t", TMUX_SESSION, "-n", "chart", *cmd], check=False)
        os.execvp("tmux", ["tmux", "attach-session", "-t", TMUX_SESSION])
    os.execvp("tmux", ["tmux", "new-session", "-s", TMUX_SESSION, "-n", "chart", *cmd])


def cmd_tui(a):
    if a.headless:
        run_headless(a)
        return
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        sminos.die("sminos tui needs a terminal — for text use: sminos chart%s" % ((" " + a.group) if a.group else ""),
                  sminos.EXIT_USAGE)
    if not a.no_tmux and not os.environ.get("TMUX"):
        if not shutil.which("tmux"):
            sminos.die("sminos tui runs inside tmux so that enter can open a seat's conversation in its own window; "
                      "install tmux, or pass --no-tmux to run here (enter then prints the attach command)",
                      sminos.EXIT_UNKNOWN)
        enter_tmux(sys.argv[1:])
    state = new_state(a.group, a.all, no_tmux=a.no_tmux)
    run_curses(state)
