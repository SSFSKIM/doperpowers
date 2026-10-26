"""Shape of the route fixtures (routes-<engine>.json, one per measured engine): the desk control surface's route
tables, which the bridge loads and MAWS vendors (2.1.307's). Checks that each parses, that every entry and route has
the Entry/Route/Forms shape of the spec's Interfaces, what M1 enables (the measured commands and prompt routes), that
a table carried from an older one (`carriedFrom`) differs from it only in the entries measured on its own engine
(`remeasured`), and that the bridge's copy, hooks/mods/bridge-routes.tsx, is the fixtures: a mod loads TypeScript
modules alone, so the tables reach the bridge as a module written from them (`--write` writes it).
Prints one `ok <name>` or `FAIL <name>` line per check, for run-sminos-tests.sh to count; a check of a table other
than 2.1.307's names its engine first.

    python3 routes_check.py <routes-2.1.307.json> <routes-2.1.310.json> ...
    python3 routes_check.py --write <routes-2.1.307.json> <routes-2.1.310.json> ...
"""

import json
import os
import re
import sys

MODULE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks", "mods", "bridge-routes.tsx")
HEADER = """// Written from sminos/tests/routes-<engine>.json, one table per measured engine, by `python3
// sminos/tests/routes_check.py --write sminos/tests/routes-*.json`: edit a fixture and write this again, never this
// by hand; the route check in run-sminos-tests.sh fails while the two differ. A mod loads TypeScript modules alone,
// so the fixtures reach the bridge as this module. The shapes are the spec's Interfaces, "The route table".

/** What the desk does with one (command, form): the spec's seven classes. */
export type RouteClass = 'run' | 'run-prompt' | 'routed' | 'follow' | 'panel' | 'local' | 'drop'
/** The arguments a route takes: whether, and which (a JS RegExp source matched whole against the trimmed args). */
export type RouteForms = { args: 'none' | 'required' | 'optional'; pattern?: string; hint?: string }
/** One route; `otherwise` is the route that args missing `forms.pattern` take, instead of being bad-args. */
export type Route = {
  class: RouteClass
  to?: string
  reason?: string
  forms?: RouteForms
  outlives?: string
  confirm?: true
  enabled: boolean
  measured: 'M' | 'I'
  otherwise?: Route
}
/** A command's routes: `withArgs` when the trimmed args are not empty, else (or with none) `bare`. */
export type RouteEntry = { name: string; bare: Route; withArgs?: Route; plugin?: string }
/** One measured engine's table: its built-ins, and the non-built-ins with a fixed route (by name and plugin). */
export type RouteTable = { engine: string; entries: readonly RouteEntry[]; pluginExceptions: readonly RouteEntry[] }

"""


def release(engine):
    return tuple(int(n) for n in engine.split("."))


def module_text(docs):
    """The bridge's route module for the fixtures `docs`: their tables, oldest engine first, one entry a line, as
    JSON."""
    def rows(entries):
        return "".join("      %s,\n" % json.dumps(e, ensure_ascii=False) for e in entries)
    tables = "".join("  {\n" + "    engine: %s,\n" % json.dumps(doc["engine"])
                     + "    entries: [\n" + rows(doc["entries"]) + "    ],\n"
                     + "    pluginExceptions: [\n" + rows(doc["pluginExceptions"]) + "    ],\n  },\n"
                     for doc in sorted(docs, key=lambda d: release(d["engine"])))
    return HEADER + "export const ROUTE_TABLES: readonly RouteTable[] = [\n" + tables + "]\n"

CLASSES = {"run", "run-prompt", "routed", "follow", "panel", "local", "drop"}
ROUTE_KEYS = {"class", "to", "reason", "forms", "outlives", "confirm", "enabled", "measured", "otherwise"}
FORMS_KEYS = {"args", "pattern", "hint"}
ENTRY_KEYS = {"name", "bare", "withArgs", "plugin"}
TABLE_KEYS = {"engine", "about", "entries", "pluginExceptions", "catalog", "carriedFrom", "remeasured"}
M1_ENABLED = {("rename", "bare"), ("color", "bare"), ("reload-plugins", "bare"), ("reload-skills", "bare"),
              ("mcp", "withArgs"), ("cd", "bare"), ("goal", "withArgs"), ("plan", "withArgs"),
              ("init", "bare"), ("security-review", "bare"), ("insights", "bare"),
              ("team-onboarding", "bare"), ("list-agents", "bare")}

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


WRITE = sys.argv[1:2] == ["--write"]
PATHS = sys.argv[2:] if WRITE else sys.argv[1:]
DOCS = [json.load(open(path, encoding="utf-8")) for path in PATHS]
if WRITE:
    with open(MODULE, "w", encoding="utf-8") as f:
        f.write(module_text(DOCS))
    print("wrote " + os.path.normpath(MODULE))
    sys.exit(0)


def whole(pattern, text):
    return re.fullmatch(pattern, text) is not None


def check_table(doc, by_engine):
    """Every check of one table; a table other than 2.1.307's names its engine in each check."""
    engine = doc.get("engine") if isinstance(doc, dict) else None
    label = "" if engine == "2.1.307" else "%s: " % engine

    def ok(name, cond, detail=""):
        check(label + name, cond, detail)

    ok("the fixture parses, names its engine and holds only the table's keys",
       isinstance(doc, dict) and isinstance(engine, str) and re.fullmatch(r"\d+\.\d+\.\d+", engine) is not None
       and not set(doc) - TABLE_KEYS)
    entries = doc.get("entries", [])
    exceptions = doc.get("pluginExceptions", [])
    ok("entries and pluginExceptions are lists", isinstance(entries, list) and isinstance(exceptions, list))

    shape_bad = []
    for e in entries + exceptions:
        where = str(e.get("name") if isinstance(e, dict) else e)
        if not isinstance(e, dict) or set(e) - ENTRY_KEYS or not isinstance(e.get("name"), str) or "bare" not in e:
            shape_bad.append(where + ": entry shape")
            continue
        shape_bad += route_problems(e["bare"], where + ".bare")
        if "withArgs" in e:
            shape_bad += route_problems(e["withArgs"], where + ".withArgs")
    ok("every entry and route has the Entry/Route/Forms shape", not shape_bad, "; ".join(shape_bad[:5]))

    names = [e["name"] for e in entries]
    ok("built-in names are unique", len(names) == len(set(names)))
    ok("the table holds its 72 built-in names", len(names) == 72, str(len(names)))
    ok("plugin exceptions are diff of cc-plugin-diff",
       [(e["name"], e.get("plugin")) for e in exceptions] == [("diff", "cc-plugin-diff")])
    ok("a plugin exception is not also a built-in", not (set(names) & {e["name"] for e in exceptions}))
    ok("a built-in names no plugin", all("plugin" not in e for e in entries))

    enabled_runs = set()
    for e in entries:
        for which in ("bare", "withArgs"):
            r = e.get(which)
            while r is not None:
                if r["class"] in ("run", "run-prompt") and r["enabled"]:
                    enabled_runs.add((e["name"], which))
                r = r.get("otherwise")
    ok("M1 enables measured commands and prompts, not future or unmeasured runs",
       enabled_runs == M1_ENABLED, str(sorted(enabled_runs ^ M1_ENABLED)))

    by_name = {e["name"]: e for e in entries}
    ok("exit stays measured with a confirm but no complete safety observation",
       by_name["exit"]["bare"]["class"] == "run" and by_name["exit"]["bare"].get("confirm") is True
       and by_name["exit"]["bare"]["enabled"] is False and by_name["exit"]["bare"]["reason"] == "can't tell whether work is running here: exit there")
    ok("every disabled run or run-prompt route says which milestone brings it, or why not",
       all(r["reason"].startswith("comes with M") or r["reason"].startswith("not settled") or r["reason"].startswith("can't tell")
           for e in entries for r in (e.get("bare"), e.get("withArgs")) if r and r["class"] in ("run", "run-prompt")
           and not r["enabled"]))
    ok("fast carries its own not-settled reason and is unmeasured",
       by_name["fast"]["bare"]["reason"].startswith("not settled") and by_name["fast"]["bare"]["measured"] == "I")
    ok("mcp: bare is the panel, the forms run and outlive the session",
       by_name["mcp"]["bare"]["class"] == "panel" and by_name["mcp"]["withArgs"]["class"] == "run"
       and "outlives" in by_name["mcp"]["withArgs"])
    color = by_name["color"]["bare"]["forms"]["pattern"]
    ok("color's pattern takes a lowercase word alone", whole(color, "red") and not whole(color, "Red")
       and not whole(color, "red blue") and not whole(color, ""))
    fast = by_name["fast"]["bare"]["forms"]["pattern"]
    ok("fast's pattern takes on and off alone", whole(fast, "on") and whole(fast, "off") and not whole(fast, "onoff"))
    goal = by_name["goal"]["withArgs"]
    ok("goal: clear is a run, any other condition a run-prompt, the bare form a panel",
       goal["class"] == "run" and whole(goal["forms"]["pattern"], "clear")
       and not whole(goal["forms"]["pattern"], "clear it") and goal["otherwise"]["class"] == "run-prompt"
       and by_name["goal"]["bare"]["class"] == "panel")

    mcp = by_name["mcp"]["withArgs"]
    if engine == "2.1.307":
        p = mcp["forms"]["pattern"]
        ok("mcp's pattern takes enable, disable and reconnect with one server",
           all(whole(p, t) for t in ("enable probe", "disable probe", "reconnect a:b")))
        ok("mcp's pattern refuses a bare verb, two servers and any other verb",
           not any(whole(p, t) for t in ("enable", "enable a b", "remove probe", "disable  probe")))
    else:
        # As measured on 2.1.310 (the spec's MW2): a server by its configured name, spaces included; enable and disable
        # with no server or all, and reconnect all, act on every server and confirm first; a bare reconnect opens the
        # panel, so no route takes it.
        one, every = mcp["forms"]["pattern"], mcp.get("otherwise", {}).get("forms", {}).get("pattern", "")
        takes = lambda t: whole(one, t) or whole(every, t)
        ok("mcp: one server by its configured name, spaces and punctuation included",
           all(whole(one, t) for t in ("enable probe", "disable probe server", "reconnect probe server",
                                       "disable plugin:cua:cua_repl", "reconnect claude.ai Gmail")))
        ok("mcp: every server with no server named, or all, confirmed first",
           all(whole(every, t) and not whole(one, t) for t in ("enable", "disable", "enable all", "disable all", "reconnect all"))
           and mcp["otherwise"].get("confirm") is True and mcp["otherwise"]["class"] == "run" and "outlives" in mcp["otherwise"])
        ok("mcp: a bare reconnect (the panel), another verb, two spaces or a control character run nothing",
           not any(takes(t) for t in ("reconnect", "remove probe", "enable  probe", "enable a\tb", "disable a\x01b", "all")))

    base_engine = doc.get("carriedFrom")
    if base_engine is not None:
        base = by_engine.get(base_engine)
        remeasured = doc.get("remeasured")
        ok("a carried table names the older table it carries and the entries measured on its own engine",
           base is not None and release(base_engine) < release(engine) and isinstance(remeasured, list)
           and remeasured and set(remeasured) <= set(names))
        if base is not None and isinstance(remeasured, list):
            older = {e["name"]: e for e in base["entries"]}
            ok("a carried table is its older table's but for the entries measured on its own engine",
               [e for e in entries if e["name"] not in remeasured] == [e for e in base["entries"] if e["name"] not in remeasured]
               and all(by_name[n] != older.get(n) for n in remeasured) and exceptions == base["pluginExceptions"])

    catalog = doc.get("catalog")
    if catalog is not None:
        commands = catalog.get("commands", [])
        ok("catalog carries both forms exactly from the canonical routes",
           all(c.get("route") == by_name[c["name"]]["bare"] and c.get("withArgs") == by_name[c["name"]].get("withArgs")
               for c in commands if c.get("source") == "builtin"))
        ok("catalog keeps the MCP name verbatim and the plugin origin",
           any(c["name"] == "probe:probe-prompt (MCP)" and c["source"] == "mcp" for c in commands)
           and any(c.get("plugin") == "doperpowers" for c in commands))
        body = {k: v for k, v in catalog.items() if k != "fingerprint"}
        h = 0xcbf29ce484222325
        for byte in json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode():
            h = ((h ^ byte) * 0x100000001b3) & ((1 << 64) - 1)
        ok("catalog fingerprint covers all routes, origins and model ids", catalog.get("fingerprint") == f"{h:016x}")


BY_ENGINE = {d.get("engine"): d for d in DOCS if isinstance(d, dict)}
check("the fixtures are 2.1.307's and the tables measured since, one per engine",
      "2.1.307" in BY_ENGINE and len(BY_ENGINE) == len(DOCS))
for d in DOCS:
    check_table(d, BY_ENGINE)

try:
    with open(MODULE, encoding="utf-8") as f:
        written = f.read()
except OSError as e:
    written = str(e)
check("the bridge's route module is these fixtures, as --write writes it", written == module_text(DOCS),
      "run: python3 routes_check.py --write " + " ".join(PATHS))
sys.exit(1 if FAILED else 0)
