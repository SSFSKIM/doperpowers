#!/usr/bin/env python3
"""gh-stub.py — a stateful stand-in for the GitHub CLI, for ONE drill.

test-transcript-diff.sh runs the same verb sequence twice: once against the
real A1 service, once in gh mode. The gh side needs a board, and the real
GitHub is not available to a hermetic test — so this answers the handful of
`gh` calls the toolkit's gh path actually makes, out of a JSON state file.

It is deliberately NOT a GitHub emulator. It implements exactly what
`_board.py` asks for on the walk under test (issue create/edit/comment/close,
the label pass, the snapshot GraphQL query, the single-issue id query, and the
REST comment read), and dies loudly on anything else — an unimplemented call
must fail the drill, never quietly return something plausible.

State: $GH_STUB_STATE (JSON). Every call is recorded there too, so a drill can
assert on what the gh path actually asked for.
"""
import json
import os
import re
import sys

STATE = os.environ["GH_STUB_STATE"]
REPO = os.environ.get("GH_STUB_REPO", "drill/board")
# Frozen, because a timestamp is exactly the kind of transport noise the
# comparison normalizes away — and a stub that emitted `now()` would make the
# gh capture differ from itself between runs.
STAMP = "2026-08-10T00:00:00Z"


def load():
    try:
        with open(STATE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"issues": {}, "labels": [], "next": 1, "calls": []}


def save(s):
    with open(STATE, "w") as f:
        json.dump(s, f, indent=1)


def die(msg):
    sys.stderr.write("gh-stub: %s\n" % msg)
    raise SystemExit(1)


def opt(args, name, many=False):
    """--name VALUE (repeatable when many)."""
    out = []
    i = 0
    while i < len(args):
        if args[i] == name and i + 1 < len(args):
            out.append(args[i + 1])
            i += 2
            continue
        i += 1
    if many:
        return out
    return out[0] if out else None


def body_arg(args):
    """--body TEXT, or --body-file F ('-' is stdin)."""
    b = opt(args, "--body")
    if b is not None:
        return b
    f = opt(args, "--body-file")
    if f is None:
        return None
    return sys.stdin.read() if f == "-" else open(f).read()


def issue_node(s, num):
    it = s["issues"][num]
    return {
        "id": "gid-%s" % num, "number": int(num), "title": it["title"],
        "body": it["body"], "url": "https://github.com/%s/issues/%s" % (REPO, num),
        "state": it["state"], "stateReason": it.get("stateReason"),
        "createdAt": STAMP, "updatedAt": STAMP,
        "labels": {"nodes": [{"name": l} for l in it["labels"]]},
        "assignees": {"nodes": []}, "parent": None, "blockedBy": {"nodes": []},
        "closedByPullRequestsReferences": {"totalCount": 0, "nodes": []},
        "timelineItems": {"totalCount": 0, "nodes": []},
    }


def main(argv):
    s = load()
    s["calls"].append(argv)
    cmd = argv[0] if argv else ""
    rest = argv[1:]

    if cmd == "label":
        if rest[0] == "list":
            save(s)
            print(json.dumps([{"name": n} for n in s["labels"]]))
            return
        if rest[0] == "create":
            name = rest[1]
            if name not in s["labels"]:
                s["labels"].append(name)
            save(s)
            return
        die("unsupported label subcommand: %s" % rest[0])

    if cmd == "issue":
        sub = rest[0]
        if sub == "create":
            num = str(s["next"])
            s["next"] += 1
            s["issues"][num] = {
                "title": opt(rest, "--title") or "",
                "body": body_arg(rest) or "",
                "labels": [l for l in (opt(rest, "--label") or "").split(",") if l],
                "state": "OPEN", "stateReason": None, "comments": [],
            }
            for l in s["issues"][num]["labels"]:
                if l not in s["labels"]:
                    s["labels"].append(l)
            save(s)
            print("https://github.com/%s/issues/%s" % (REPO, num))
            return
        num = rest[1].lstrip("#")
        if num not in s["issues"]:
            die("issue %s not found" % num)
        it = s["issues"][num]
        if sub == "edit":
            for l in opt(rest, "--remove-label", many=True):
                if l in it["labels"]:
                    it["labels"].remove(l)
            for l in opt(rest, "--add-label", many=True):
                if l not in it["labels"]:
                    it["labels"].append(l)
            if opt(rest, "--body-file") is not None:
                it["body"] = body_arg(rest) or ""
            save(s)
            return
        if sub == "comment":
            cid = 1000 + sum(len(i["comments"]) for i in s["issues"].values())
            it["comments"].append({"id": cid, "body": body_arg(rest) or "",
                                   "created_at": STAMP, "author_association": "OWNER"})
            save(s)
            print("https://github.com/%s/issues/%s#issuecomment-%d" % (REPO, num, cid))
            return
        if sub == "close":
            it["state"] = "CLOSED"
            it["stateReason"] = ("NOT_PLANNED" if opt(rest, "--reason") == "not planned"
                                 else "COMPLETED")
            save(s)
            return
        die("unsupported issue subcommand: %s" % sub)

    if cmd == "api":
        target = rest[0]
        if target == "graphql":
            q = ""
            for i, a in enumerate(rest):
                if a in ("-f", "-F") and i + 1 < len(rest) and rest[i + 1].startswith("query="):
                    q = rest[i + 1][len("query="):]
            save(s)
            if "issues(first:100" in q:
                nodes = [issue_node(s, n) for n in sorted(s["issues"], key=int)]
                print(json.dumps({"data": {"repository": {"issues": {
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                    "nodes": nodes}}}}))
                return
            m = re.search(r"issue\(number:\$n\)", q)
            if m:
                n = None
                for i, a in enumerate(rest):
                    if a in ("-f", "-F") and i + 1 < len(rest) and rest[i + 1].startswith("n="):
                        n = rest[i + 1][2:]
                print(json.dumps({"data": {"repository": {"issue": {"id": "gid-%s" % n}}}}))
                return
            die("unsupported graphql query:\n%s" % q[:400])
        m = re.match(r"repos/[^/]+/[^/]+/issues/(\d+)/comments$", target)
        if m:
            save(s)
            print(json.dumps([s["issues"][m.group(1)]["comments"]]))
            return
        die("unsupported api path: %s" % target)

    die("unsupported command: %s" % " ".join(argv))


main(sys.argv[1:])
