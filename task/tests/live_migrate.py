"""The steps of `live.sh migrate` (acceptance 22) that are easier said in
Python: seed the scratch board with one issue for each row of D6's table,
settle a plan's decisions, and read what the apply left. Every issue it
makes is titled `live migrate: …`, and nothing else on the board is
written: a row of any other issue is settled as "leave".

  python3 live_migrate.py clear  <repo>          close what an earlier run left open
  python3 live_migrate.py seed   <repo> <task>   make the issues; prints their numbers as JSON
  python3 live_migrate.py settle <plan> <seeded> settle every decision row
  python3 live_migrate.py check  <repo> <task> <seeded>   the bodies and labels the apply left
"""
import json
import subprocess
import sys

PREFIX = "live migrate: "
META = ("A scratch ticket of live.sh migrate.\n\n<!-- board:meta\nrelates-to: #1\n"
        "plan: docs/specs/scratch.md@0123abc\nnote: waits on nothing; a scratch note\n-->\n")
NOTE = "A scratch ticket of live.sh migrate, parked for the owner.\n\n<!-- board:meta\nnote: 1. a question?\n-->\n"
BANNER = ("`arkho-board:ticket:7` — mirrored from the Arkho board.\n"
          "**Read-only.** Edits here are reverted; closing this issue does not close the ticket. The board is the "
          "source of truth.\n"
          "Board ticket: https://board.example.invalid/ui/t/7\n\n---\n\nA scratch ticket of live.sh migrate.\n")
PLAIN = "A scratch ticket of live.sh migrate; closed by it."
# One issue per row of D6's table (a row naming several labels gets one each): key -> (labels, body).
SEED = {
    "no status label": ([], PLAIN),
    "ready-for-implementer": (["status:ready-for-implementer"], META),
    "ready-for-architect": (["status:ready-for-architect"], PLAIN),
    "interactive-preferred": (["status:interactive-preferred"], PLAIN),
    "needs-human": (["status:needs-human"], NOTE),
    "needs-info": (["status:needs-info"], PLAIN),
    "blocked": (["status:blocked"], PLAIN),
    "ready-for-agent": (["status:ready-for-agent"], PLAIN),
    "deferred": (["status:deferred"], BANNER),
    "in-design": (["status:in-design"], PLAIN),
    "in-progress": (["status:in-progress"], PLAIN),
    "in-review": (["status:in-review"], PLAIN),
    "confident-ready": (["status:confident-ready"], PLAIN),
    "two status labels": (["status:ready-for-implementer", "status:deferred"], PLAIN),
}


def gh(*args, data=None):
    argv = ["gh", "api", "--hostname", "github.com"] + list(args) + (["--input", "-"] if data is not None else [])
    done = subprocess.run(argv, input=json.dumps(data) if data is not None else None, capture_output=True,
                          text=True, check=True)
    return json.loads(done.stdout) if done.stdout.strip() else None


def open_issues(repo):
    pages = gh("repos/%s/issues" % repo, "-X", "GET", "-f", "state=open", "-f", "per_page=100", "--paginate",
               "--slurp")
    return [i for page in pages for i in page if "pull_request" not in i]


def clear(repo):
    for i in open_issues(repo):
        if i["title"].startswith(PREFIX):
            gh("repos/%s/issues/%d" % (repo, i["number"]), "-X", "PATCH",
               data={"state": "closed", "state_reason": "not_planned"})


def seed(repo, task):
    made = {}
    for key, (labels, body) in SEED.items():
        out = gh("repos/%s/issues" % repo, "-X", "POST",
                 data={"title": PREFIX + key, "body": body, "labels": labels + ["priority:P3", "spike"]})
        made[key] = out["number"]
    # The horizon rule: the architect's ticket waits on an open issue, so it is planned.
    subprocess.run([task, "edge", str(made["ready-for-architect"]), "--block", str(made["no status label"]),
                    "--repo", repo], check=True, capture_output=True, text=True)
    print(json.dumps(made))


def settle(plan_path, seeded):
    seeded = json.loads(seeded)
    ours = {n: k for k, n in seeded.items()}
    plan = json.load(open(plan_path))
    for r in plan["rows"]:
        key = ours.get(r["number"])
        if key is None:
            r.update(action="leave", decided=True, why="not this case's issue")
        elif key == "no status label":
            r.update(action="leave", decided=True, why="the case's blocker stays untracked")
        elif not r["decided"]:
            r.update(decided=True, why="settled by live.sh migrate with the plan's proposal")
    json.dump(plan, open(plan_path, "w"))
    print("settled %d rows; %d of them this case's" % (len(plan["rows"]), len([r for r in plan["rows"]
                                                                              if r["number"] in ours])))


def check(repo, task, seeded):
    seeded = json.loads(seeded)
    bad = []
    for key, n in seeded.items():
        t = json.loads(subprocess.run([task, "show", str(n), "--repo", repo, "--json"], check=True,
                                      capture_output=True, text=True).stdout)
        statuses = [l for l in t["labels"] if l.startswith("status:")]
        if key == "no status label":
            if t["on_board"]:
                bad.append("#%d (%s) was put on the board" % (n, key))
            continue
        if statuses or not t["readiness"] or not t["horizon"]:
            bad.append("#%d (%s) has labels %s" % (n, key, t["labels"]))
        if key == "ready-for-architect" and t["horizon"] != "planned":
            bad.append("#%d is %s, not planned" % (n, t["horizon"]))
        if key == "ready-for-implementer" and ("Board note: waits on nothing" not in t["body"]
                                               or (t["record"] or {}).get("spec") != "docs/specs/scratch.md@0123abc"):
            bad.append("#%d's board:meta block is not visible: %r" % (n, t["body"]))
        if key == "in-progress" and not t["body"].endswith(
                "Board state before the relabel: in-progress."):
            bad.append("#%d's body does not say the state it had: %r" % (n, t["body"][-160:]))
        if key == "deferred" and (not t["body"].startswith("_Moved from board ticket 7 ") or "Read-only" in t["body"]):
            bad.append("#%d's banner is not replaced: %r" % (n, t["body"][:120]))
    for line in bad:
        print("migrate: " + line, file=sys.stderr)
    print("checked %d seeded issues: %s" % (len(seeded), "as the table says" if not bad else "%d wrong" % len(bad)))
    return 1 if bad else 0


if __name__ == "__main__":
    step, rest = sys.argv[1], sys.argv[2:]
    sys.exit({"clear": clear, "seed": seed, "settle": settle, "check": check}[step](*rest) or 0)
