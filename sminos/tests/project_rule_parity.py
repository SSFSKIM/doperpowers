"""Parity of sminos's rule for a directory's project (sminos.decision) with
MAWS's shared vectors, vendored at vectors/maws/project-rule.json beside
this file and pinned by PIN.json there (Interfaces §B of MAWS's
docs/doperpowers/plans/2026-11-10-project-registry.md; the file's `about`
states the conventions this harness follows).

Each case's tree is made under a fresh real temporary directory (in `under`,
spelled as written, when the case names one), git's files written directly,
no git run. The statements reach sminos as production hands them over: the
kept org file's `locations`, at the canonical form of each path, anchored to
the folder there by a stat, but `replaced`, anchored to another folder (and
once more marked `state: replaced` with its own anchor), and `removed`, a
removed row, which is no declared location and so not in the file. Each
`dir` is asked as written; the deciding source and folder are compared as
well as the project. A case with no statements is asked again with no
`locations` in the org file at all, the resolution of a machine whose
endpoint sends none. Every `anchors` case is compared too, and the copy's
sha256 against its pin.

Prints `ok <name>`, `FAIL <name> — detail` or `SKIP <name> — why` per case,
then `N cases, M failed`, for run-sminos-tests.sh to count.

    python3 -B -I project_rule_parity.py [<skills/sminos/scripts> [<project-rule.json>]]
"""

import hashlib
import json
import os
import shutil
import sys
import tempfile
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "skills", "sminos", "scripts")
VECTOR = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "vectors", "maws", "project-rule.json")

# Never the real registry, nor the real home.
SCRATCH = os.path.realpath(tempfile.mkdtemp(prefix="project-rule-"))
os.environ["HOME"] = os.path.join(SCRATCH, "home")
os.environ["SMINOS_HOME"] = os.path.join(SCRATCH, "sminos")
for k in ("DAEMON_HOME", "AGORA_HOME", "CLAUDE_CODE_SESSION_ID"):
    os.environ.pop(k, None)
os.makedirs(os.path.join(os.environ["SMINOS_HOME"], "daemon"))
os.makedirs(os.environ["HOME"])
sys.path.insert(0, SCRIPTS)
import sminos  # noqa: E402

RAW = open(VECTOR, "rb").read()
RULE = json.loads(RAW)
PIN = json.load(open(os.path.join(os.path.dirname(VECTOR), "PIN.json"), encoding="utf-8"))
nfc = lambda p: unicodedata.normalize("NFC", p)  # noqa: E731
CHECKS, FAILED, SKIPPED = [0], [], [0]


def check(name, problems):
    CHECKS[0] += 1
    print("ok " + name if not problems else "FAIL %s — %s" % (name, "; ".join(problems)))
    if problems:
        FAILED.append(name)


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def make_tree(base, tree):
    """Each entry of a case's tree under `base`, as git lays a checkout out."""
    for e in tree:
        if "dir" in e:
            os.makedirs(os.path.join(base, e["dir"]), exist_ok=True)
        elif "repo" in e:
            git = os.path.join(base, e["repo"], ".git")
            for d in ("objects", "refs/heads", "refs/tags"):
                os.makedirs(os.path.join(git, d), exist_ok=True)
            write(os.path.join(git, "HEAD"), "ref: refs/heads/main\n")
            remotes = e.get("remotes") or ({"origin": e["remote"]} if "remote" in e else {})
            write(os.path.join(git, "config"), "[core]\n\trepositoryformatversion = 0\n\tbare = false\n" + "".join(
                '[remote "%s"]\n\turl = %s\n\tfetch = +refs/heads/*:refs/remotes/%s/*\n' % (n, u, n)
                for n, u in remotes.items()))
        elif "worktree" in e:
            wt, main = os.path.join(base, e["worktree"]), os.path.join(base, e["of"])
            admin = os.path.join(main, ".git", "worktrees", os.path.basename(wt))
            write(os.path.join(admin, "gitdir"), os.path.join(wt, ".git") + "\n")
            write(os.path.join(admin, "commondir"), "../..\n")
            write(os.path.join(admin, "HEAD"), "ref: refs/heads/%s\n" % os.path.basename(wt))
            write(os.path.join(wt, ".git"), "gitdir: %s\n" % admin)
        elif "smns" in e:
            smns = {"project": e["project"], "name": e.get("name") or e["project"], "remote": ""}
            if e.get("hub") is True:
                smns["hub"] = {"org": RULE["org"]}
            elif e.get("hub") == "other-org":
                smns["hub"] = {"org": "other-org"}
            write(os.path.join(base, e["smns"], ".smns"), json.dumps(smns) + "\n")
        elif "symlink" in e:
            os.symlink(os.path.join(base, e["to"]), os.path.join(base, e["symlink"]))
        else:
            raise ValueError("an unknown tree entry: %r" % e)


def anchor_of(path):
    st = os.stat(path)
    birth = getattr(st, "st_birthtime", 0)
    # The anchor as MAWS writes it, an integer of nanoseconds ("0" for none).
    return {"dev": str(st.st_dev), "ino": str(st.st_ino), "birth": str(int(sminos.birth_ns(birth) or 0))}


def locations(base, statements, other, replaced_by_state=False):
    """The org file's `locations` for a case's statements."""
    at = []
    for s in statements:
        if s.get("removed"):
            continue   # a removed row is no declared location
        path = os.path.join(base, s["path"])
        entry = {"path": sminos.canonical(path), "project": s.get("linked") or s["minted"],
                 "stated": "linked" if "linked" in s else "minted", "anchor": anchor_of(path)}
        if s.get("replaced"):
            if replaced_by_state:
                entry["state"] = "replaced"
            else:
                entry["anchor"] = anchor_of(other)
        at.append(entry)
    return {"gen": 1, "at": at}


def keep_org(locs):
    org = {"projects": [], "machines": [], "at": "2026-11-10T00:00:00.000Z"}
    if locs is not None:
        org["locations"] = locs
    sminos.write_json(sminos.org_path(), org)
    sminos.forget_caches()


def expected_id(project):
    if project == "machine":
        return sminos.machine_project_id(RULE["org"], RULE["machine"])
    if isinstance(project, dict):
        return sminos.repo_project_id(RULE["org"], project["remote"])
    return project


def ask_all(c, base, root, label):
    problems = []
    for a in c["ask"]:
        got = sminos.decision(os.path.join(base, a["dir"]))
        at = os.path.relpath(sminos.canonical(got.at), root) if got.at else None
        want = (expected_id(a["project"]), a["by"], nfc(a["at"]) if "at" in a else None)
        have = (got.project.id if got.project else None, got.by, nfc(at) if at else None)
        if have != want:
            problems.append("%s%s: got %s by %s at %s, want %s by %s at %s" % (a["dir"], label, *have, *want))
    return problems


def run_case(c):
    if c.get("platform") and c["platform"] != ("darwin" if sys.platform == "darwin" else "linux"):
        SKIPPED[0] += 1
        print("SKIP %s — a %s case" % (c["name"], c["platform"]))
        return
    made = tempfile.mkdtemp(prefix="case-", dir=c.get("under") or SCRATCH)
    try:
        base = made   # in `under`, spelled as it is written there
        root = sminos.canonical(base)
        other = os.path.join(made, ".another-folder")
        os.mkdir(other)
        make_tree(base, c["tree"])
        keep_org(locations(base, c["statements"], other))
        problems = ask_all(c, base, root, "")
        if any(s.get("replaced") for s in c["statements"]):
            keep_org(locations(base, c["statements"], other, replaced_by_state=True))
            problems += ask_all(c, base, root, " (replaced by its state)")
        if not c["statements"]:
            keep_org(None)
            problems += ask_all(c, base, root, " (no locations kept)")
        check(c["name"], problems)
    finally:
        shutil.rmtree(made, ignore_errors=True)


def reading(r):
    if "birthNs" in r:
        return int(r["birthNs"]) or None
    return sminos.birth_ns(r["birthSeconds"]) if "birthSeconds" in r else None


def main():
    sha = hashlib.sha256(RAW).hexdigest()
    if sha == PIN["sha256"]:
        check("project-rule.json is the pinned copy (MAWS %s)" % PIN["commit"], [])
    else:
        CHECKS[0] += 1
        FAILED.append("pin")
        print("project-rule.json: vendored %s is not the pinned %s (MAWS %s)" % (sha, PIN["sha256"], PIN["commit"]))
    sminos.write_json(os.path.join(os.environ["SMINOS_HOME"], "daemon", "identity.json"),
                      {"org": RULE["org"], "hub": "http://127.0.0.1:9", "name": RULE["machine"], "former": {}})
    for c in RULE["cases"]:
        run_case(c)
    for a in RULE["anchors"]:
        r = a["reading"]
        same = sminos.anchor_same(a["anchor"], r["dev"], r["ino"], reading(r))
        check("anchors: " + a["name"], [] if same == a["same"] else ["compared %s, want %s" % (same, a["same"])])
    print("%d cases, %d failed" % (CHECKS[0], len(FAILED)))
    shutil.rmtree(SCRATCH, ignore_errors=True)
    sys.exit(1 if FAILED else 0)


main()
