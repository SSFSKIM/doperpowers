#!/usr/bin/env python3
"""Reads result files of the question-sheet evals and prints what a baseline
reports: per arm and scenario the outcomes with a 95% upper bound on the
failure rate, responses before the first sheet call, E2's pass rates, the
paired capture comparison, fact presence by where the fact was shown, and
the spend at list price (subject, judges, shell simulator).

Composite spec: docs/doperpowers/specs/2026-11-23-question-sheet-design.md in
the MAWS repository, child C1 (parent pin ad4427f93, MAWS board ticket #866).

  python3 tests/output-styles/question-sheet-report.py RESULTS.json [RESULTS.json ...]
"""
import json, math, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import question_sheet as qs  # noqa: E402
import question_sheet_session as ss  # noqa: E402

E1_FAIL = {"duplicated", "revised+duplicated", "untouched", "cut_off", "repurposed"}


def upper(k, n, z=1.96):
    """Wilson's 95% upper bound for k of n."""
    if n == 0:
        return None
    p = k / n
    return round((p + z * z / (2 * n) + z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / (1 + z * z / n), 3)


def lower(k, n, z=1.96):
    if n == 0:
        return None
    p = k / n
    return round((p + z * z / (2 * n) - z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / (1 + z * z / n), 3)


def median(xs):
    xs = sorted(xs)
    return None if not xs else xs[len(xs) // 2] if len(xs) % 2 else (xs[len(xs) // 2 - 1] + xs[len(xs) // 2]) / 2


def spend(doc):
    model = doc["args"]["model"]
    subject = qs.cost(doc["usage"], model)
    side = doc.get("side_usage", {})
    j, s = side.get("judge", {}), side.get("shell_simulator", {})
    judge = round((j.get("input", 0) * 4 + j.get("output", 0) * 20) / 1e6, 2)
    sim = round((s.get("input", 0) * 2 + s.get("output", 0) * 10) / 1e6, 2)
    return subject, judge, sim


def e1(runs):
    rows = {}
    for x in runs:
        if "error" in x:
            continue
        r = rows.setdefault((x["arm"], x["scenario"], x["history"]), {"n": 0, "outcomes": {}, "first": [], "target": [],
                                                                     "never": 0})
        r["n"] += 1
        r["outcomes"][x["outcome"]] = r["outcomes"].get(x["outcome"], 0) + 1
        if x.get("first_sheet_step") is None:
            r["never"] += 1
        else:
            r["first"].append(x["first_sheet_step"])
        if x.get("target_step") is not None:
            r["target"].append(x["target_step"])
    print("\nE1: outcomes per arm, scenario and history")
    totals = {}
    for (arm, sc, h), r in sorted(rows.items()):
        fails = sum(v for k, v in r["outcomes"].items() if k in E1_FAIL)
        t = totals.setdefault((arm, h, sc == "distinct"), [0, 0, 0, 0])
        t[0] += fails
        t[1] += r["n"]
        t[2] += r["outcomes"].get("revised", 0)
        t[3] += r["outcomes"].get("duplicated", 0) + r["outcomes"].get("revised+duplicated", 0)
        print(f"  {arm} {sc} {h}: n={r['n']} {json.dumps(r['outcomes'])} failures {fails} "
              f"| responses before first sheet call: median {median(r['first'])}, {sorted(r['first'])}; "
              f"within the trigger's response or the next {sum(f <= 1 for f in r['first'])}/{r['n']}"
              + (f", never {r['never']}" if r["never"] else "")
              + (f" | before the target's revision: median {median(r['target'])}" if r["target"] else ""))
    print("\nE1 by arm (changed scenarios pooled; the control apart)")
    for (arm, h, control), (f, n, rev, dup) in sorted(totals.items()):
        what = "control (distinct)" if control else "changed"
        print(f"  {arm} {h} {what}: failures {f}/{n} (95% upper {upper(f, n)})"
              + ("" if control else f", revised {rev}/{n} (95% lower {lower(rev, n)}), duplicates {dup}/{n} "
                                    f"(95% upper {upper(dup, n)})"))


def e2(runs):
    rows, pairs = {}, {}
    for x in runs:
        if "error" in x:
            continue
        keys = ss.E2_TRIGGERS[x["scenario"]]["matters"]
        r = rows.setdefault((x["arm"], x["scenario"], x["history"]), {
            "runs": 0, "asking": 0, "calls": [], "first": [], "unasked": 0, "cards": 0, "pass": 0, "essential": 0,
            "reader_yes": 0, "where": {}, "other": 0, "other_yes": 0})
        r["runs"] += 1
        r["asking"] += bool(x["cards"])
        r["calls"].append(x["asking_calls"])
        if x.get("first_sheet_step") is not None:
            r["first"].append(x["first_sheet_step"])
        r["unasked"] += len(set(keys) - set(x.get("matters_asked", [])))
        for c in x["cards"]:
            a = c.get("alone") or {}
            if a.get("matter") not in keys:
                r["other"] += 1
                r["other_yes"] += (a.get("reader") or {}).get("could_decide") == "yes"
                continue
            r["cards"] += 1
            r["pass"] += a["pass"]
            r["essential"] += a["essential"]
            r["reader_yes"] += a["reader"].get("could_decide") == "yes"
            for i, (_, _, where) in enumerate(ss.MATTERS[a["matter"]]["facts"], 1):
                w = r["where"].setdefault(where.split(":")[0], [0, 0])
                w[0] += bool(a["present"].get(i) or a["present"].get(str(i)))
                w[1] += 1
            p = pairs.setdefault((x["arm"], x["history"]), {"both": 0, "alone_only": 0, "capture_only": 0, "neither": 0,
                                                            "no_notes": 0})
            w = c.get("with_capture") or a
            if not c.get("notes"):
                p["no_notes"] += 1
            p[{(True, True): "both", (True, False): "alone_only", (False, True): "capture_only",
               (False, False): "neither"}[(bool(a["pass"]), bool(w["pass"]))]] += 1
    print("\nE2: per arm, scenario and history (counted cards: about the scenario's own matters)")
    totals = {}
    for (arm, sc, h), r in sorted(rows.items()):
        t = totals.setdefault((arm, h), [0, 0, 0, 0, [], 0, 0])
        t[0] += r["pass"]
        t[1] += r["cards"]
        t[2] += r["essential"]
        t[3] += r["reader_yes"]
        t[4] += r["first"]
        t[5] += r["unasked"]
        t[6] += sum(len(ss.E2_TRIGGERS[sc]["matters"]) for _ in range(r["runs"]))
        print(f"  {arm} {sc} {h}: runs {r['runs']} (asking {r['asking']}), asking calls per run {r['calls']}, "
              f"matters unasked {r['unasked']} | cards {r['cards']}: pass {r['pass']}, essential facts {r['essential']}, "
              f"reader yes {r['reader_yes']} | other cards {r['other']} (reader yes {r['other_yes']}) | facts by where "
              f"{ {k: f'{v[0]}/{v[1]}' for k, v in r['where'].items()} } | responses before first sheet call {sorted(r['first'])}")
    print("\nE2 by arm")
    for (arm, h), (ps, n, ess, yes, first, unasked, matters) in sorted(totals.items()):
        print(f"  {arm} {h}: pass {ps}/{n} (95% lower {lower(ps, n)}), essential facts {ess}/{n}, reader yes {yes}/{n}, "
              f"matters asked {matters - unasked}/{matters}, responses before first sheet call median {median(first)}, "
              f"within the trigger's response or the next {sum(f <= 1 for f in first)}/{len(first)}")
    print("\nE2 capture, paired on the same cards (pass alone vs pass with the agent's notes appended)")
    for key, p in sorted(pairs.items()):
        print(f"  {key[0]} {key[1]}: {json.dumps(p)}")


if __name__ == "__main__":
    total = [0, 0, 0]
    for f in sys.argv[1:]:
        doc = json.loads(Path(f).read_text())
        runs = doc["runs"]
        s = spend(doc)
        total = [a + b for a, b in zip(total, s)]
        errors = sum("error" in x for x in runs)
        waits = len(doc.get("side_usage", {}).get("plan_usage_waits", []))
        print(f"== {f}: {len(runs)} runs, {errors} errors, {waits} plan-usage waits; spend subject ${s[0]}, judges ${s[1]}, "
              f"simulator ${s[2]}")
        for x in runs:
            if "error" in x:
                print("   error", x.get("job"), x["error"][:200])
        (e1 if "outcome" in next((x for x in runs if "error" not in x), {}) else e2)(runs)
    print(f"\nspend at list price: subject ${round(total[0], 2)}, judges ${round(total[1], 2)}, simulator "
          f"${round(total[2], 2)}, total ${round(sum(total), 2)}")
