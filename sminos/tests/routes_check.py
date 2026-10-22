"""Shape of the route fixture (routes-2.1.307.json): the desk control surface's route table, which the bridge
loads and MAWS vendors. Checks that it parses, that every entry and route has the Entry/Route/Forms shape of the
spec's Interfaces, and what M0 enables: the five measured `run` rows alone.
Prints one `ok <name>` or `FAIL <name>` line per check, for run-sminos-tests.sh to count.

    python3 routes_check.py <routes-2.1.307.json>
"""

import json
import re
import sys

CLASSES = {"run", "run-prompt", "routed", "follow", "panel", "local", "drop"}
ROUTE_KEYS = {"class", "to", "reason", "forms", "outlives", "confirm", "enabled", "measured", "otherwise"}
FORMS_KEYS = {"args", "pattern", "hint"}
ENTRY_KEYS = {"name", "bare", "withArgs", "plugin"}
M0_ENABLED = {("rename", "bare"), ("color", "bare"), ("reload-plugins", "bare"), ("reload-skills", "bare"),
              ("mcp", "withArgs")}

FAILED = []


def check(name, ok, detail=""):
    print(("ok " if ok else "FAIL ") + name + ("" if ok or not detail else ": " + detail))
    if not ok:
        FAILED.append(name)


def route_problems(r, where):
    """The problems of one route, recursively through `otherwise`."""
    bad = []
    if not isinstance(r, dict):
        return [where + ": not an object"]
    if set(r) - ROUTE_KEYS:
        bad.append(where + ": unknown keys " + str(sorted(set(r) - ROUTE_KEYS)))
    if r.get("class") not in CLASSES:
        bad.append(where + ": class " + repr(r.get("class")))
    if not isinstance(r.get("enabled"), bool):
        bad.append(where + ": enabled is not a boolean")
    if r.get("measured") not in ("M", "I"):
        bad.append(where + ": measured " + repr(r.get("measured")))
    for k in ("to", "reason", "outlives"):
        if k in r and not (isinstance(r[k], str) and r[k]):
            bad.append(where + ": " + k + " is not a non-empty string")
    if "confirm" in r and r["confirm"] is not True:
        bad.append(where + ": confirm is present and not true")
    if r.get("enabled") is False and not r.get("reason"):
        bad.append(where + ": disabled without a reason")
    if r.get("class") == "drop" and not r.get("reason"):
        bad.append(where + ": drop without a reason")
    if r.get("class") == "routed" and not r.get("to"):
        bad.append(where + ": routed without a destination")
    if "forms" in r:
        f = r["forms"]
        if not isinstance(f, dict) or set(f) - FORMS_KEYS or f.get("args") not in ("none", "required", "optional"):
            bad.append(where + ": forms " + json.dumps(f))
        else:
            for k in ("pattern", "hint"):
                if k in f and not (isinstance(f[k], str) and f[k]):
                    bad.append(where + ": forms." + k + " is not a non-empty string")
            if "pattern" in f:
                if f["args"] != "required":
                    bad.append(where + ": a pattern on a form whose args are not required")
                try:
                    re.compile(f["pattern"])
                except re.error as e:
                    bad.append(where + ": pattern does not compile: " + str(e))
    if "otherwise" in r:
        if "pattern" not in r.get("forms", {}):
            bad.append(where + ": otherwise without a pattern")
        bad += route_problems(r["otherwise"], where + ".otherwise")
    return bad


doc = json.load(open(sys.argv[1], encoding="utf-8"))
check("the fixture parses and is for 2.1.307", isinstance(doc, dict) and doc.get("engine") == "2.1.307")
entries = doc.get("entries", [])
exceptions = doc.get("pluginExceptions", [])
check("entries and pluginExceptions are lists", isinstance(entries, list) and isinstance(exceptions, list))

shape_bad = []
for e in entries + exceptions:
    where = str(e.get("name") if isinstance(e, dict) else e)
    if not isinstance(e, dict) or set(e) - ENTRY_KEYS or not isinstance(e.get("name"), str) or "bare" not in e:
        shape_bad.append(where + ": entry shape")
        continue
    shape_bad += route_problems(e["bare"], where + ".bare")
    if "withArgs" in e:
        shape_bad += route_problems(e["withArgs"], where + ".withArgs")
check("every entry and route has the Entry/Route/Forms shape", not shape_bad, "; ".join(shape_bad[:5]))

names = [e["name"] for e in entries]
check("built-in names are unique", len(names) == len(set(names)))
check("the table holds its 72 built-in names", len(names) == 72, str(len(names)))
check("plugin exceptions are diff of cc-plugin-diff",
      [(e["name"], e.get("plugin")) for e in exceptions] == [("diff", "cc-plugin-diff")])
check("a plugin exception is not also a built-in", not (set(names) & {e["name"] for e in exceptions}))
check("a built-in names no plugin", all("plugin" not in e for e in entries))

enabled_runs = set()
for e in entries:
    for which in ("bare", "withArgs"):
        r = e.get(which)
        while r is not None:
            if r["class"] in ("run", "run-prompt") and r["enabled"]:
                enabled_runs.add((e["name"], which))
            r = r.get("otherwise")
check("M0 enables the five measured run rows and no other run or run-prompt route",
      enabled_runs == M0_ENABLED, str(sorted(enabled_runs ^ M0_ENABLED)))

by_name = {e["name"]: e for e in entries}
check("exit is run with a confirm, disabled until M1",
      by_name["exit"]["bare"]["class"] == "run" and by_name["exit"]["bare"].get("confirm") is True
      and by_name["exit"]["bare"]["enabled"] is False and by_name["exit"]["bare"]["reason"] == "comes with M1")
check("every disabled run or run-prompt route says which milestone brings it, or why not",
      all(r["reason"].startswith("comes with M") or r["reason"].startswith("not settled")
          for e in entries for r in (e.get("bare"), e.get("withArgs")) if r and r["class"] in ("run", "run-prompt")
          and not r["enabled"]))
check("fast carries its own not-settled reason and is unmeasured",
      by_name["fast"]["bare"]["reason"].startswith("not settled") and by_name["fast"]["bare"]["measured"] == "I")
check("mcp: bare is the panel, the three forms run and outlive the session",
      by_name["mcp"]["bare"]["class"] == "panel" and by_name["mcp"]["withArgs"]["class"] == "run"
      and "outlives" in by_name["mcp"]["withArgs"])


def whole(pattern, text):
    return re.fullmatch(pattern, text) is not None


mcp = by_name["mcp"]["withArgs"]["forms"]["pattern"]
check("mcp's pattern takes enable, disable and reconnect with one server",
      all(whole(mcp, t) for t in ("enable probe", "disable probe", "reconnect a:b")))
check("mcp's pattern refuses a bare verb, two servers and any other verb",
      not any(whole(mcp, t) for t in ("enable", "enable a b", "remove probe", "disable  probe")))
color = by_name["color"]["bare"]["forms"]["pattern"]
check("color's pattern takes a lowercase word alone", whole(color, "red") and not whole(color, "Red")
      and not whole(color, "red blue") and not whole(color, ""))
fast = by_name["fast"]["bare"]["forms"]["pattern"]
check("fast's pattern takes on and off alone", whole(fast, "on") and whole(fast, "off") and not whole(fast, "onoff"))
goal = by_name["goal"]["withArgs"]
check("goal: clear is a run, any other condition a run-prompt, the bare form a panel",
      goal["class"] == "run" and whole(goal["forms"]["pattern"], "clear")
      and not whole(goal["forms"]["pattern"], "clear it") and goal["otherwise"]["class"] == "run-prompt"
      and by_name["goal"]["bare"]["class"] == "panel")

sys.exit(1 if FAILED else 0)
