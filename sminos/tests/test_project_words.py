#!/usr/bin/env python3
"""`project init` and `project show` beside a stored statement (the project
registry's M7; MAWS docs/doperpowers/plans/2026-11-10-project-registry.md,
Interfaces §E.5). Where a stored statement on this machine decides a folder
over any .smns there (one at the folder, or a linked worktree's main
checkout's), init writes the id in effect, the link's else the minted id, as
a hub project of the org, and says the file is not what decides; show names
a .smns in the deciding folder that names another project, both ids and
which decides. init still needs a git repository, and its refusal in a plain
folder names `maws project add`. Nothing here writes a stored statement.

Hermetic: HOME and SMINOS_HOME are temporary, the org file is written
directly as the endpoint's frame would leave it, no daemon; git runs only to
make the repositories.
Run: python3 -B -I sminos/tests/test_project_words.py
"""

import argparse
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.realpath(__file__))
T = os.path.realpath(tempfile.mkdtemp(prefix="smwords.", dir="/tmp"))
for k in ("SMINOS_RL10", "MAWS_USER_DATA", "CLAUDE_CODE_SESSION_ID", "DAEMON_HOME", "AGORA_HOME", "DAEMON_HOST",
          "MAWS_LANE", "SMNS_MEMBER", "SMNS_INTERNAL", "XDG_CONFIG_HOME", "CLAUDE_CONFIG_DIR"):
    os.environ.pop(k, None)
os.environ.update(HOME=os.path.join(T, "home"), SMINOS_HOME=os.path.join(T, "s"), SMINOS_DERIVE_EVERY="0",
                  GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
os.makedirs(os.path.join(T, "s", "daemon"))
os.makedirs(os.path.join(T, "home", ".claude", "sessions"))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "skills", "sminos", "scripts"))
import sminos  # noqa: E402

ORG, MACHINE, URL = "org-words", "words-mac", "http://127.0.0.1:9"
LINKED = "11111111-1111-4111-8111-111111111111"
MINTED = "22222222-2222-4222-8222-222222222222"
FILED = "33333333-3333-4333-8333-333333333333"


def git(*args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "init.defaultBranch=main", *args],
                   check=True, capture_output=True)


def repo(name):
    d = os.path.join(T, "w", name)
    os.makedirs(d)
    git("init", "-q", d)
    git("-C", d, "commit", "-q", "--allow-empty", "-m", "root")
    return d


def smns(d, pid, name="filed"):
    with open(os.path.join(d, ".smns"), "w") as f:
        json.dump({"project": pid, "name": name, "remote": ""}, f)


def stated(path, pid, kind):
    st = os.stat(path)
    birth = sminos.birth_ns(getattr(st, "st_birthtime", 0))
    return {"path": sminos.canonical(path), "project": pid, "stated": kind,
            "anchor": {"dev": str(st.st_dev), "ino": str(st.st_ino), "birth": str(int(birth or 0))}}


def keep_org(at):
    """org.json as a frame with `locations` leaves it, the statements' projects named in the directory."""
    sminos.write_json(sminos.org_path(), {
        "projects": [{"id": LINKED, "name": "linked"}, {"id": MINTED, "name": "minted"}],
        "machines": [], "at": "", "locations": {"gen": 1, "at": at}})
    sminos.forget_caches()


def run(fn, cwd, **args):
    """(exit code, stdout, stderr) of a project verb run in `cwd`."""
    a = argparse.Namespace(**{"name": "", "remote": "", "hub": False, "dir": "", **args})
    out, err, code = io.StringIO(), io.StringIO(), 0
    here = os.getcwd()
    os.chdir(cwd)
    sminos.forget_caches()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            fn(a)
    except SystemExit as e:
        code = e.code
    finally:
        os.chdir(here)
    return code, out.getvalue(), err.getvalue()


def init(cwd, **args):
    return run(sminos.project_init, cwd, **args)


def show(d):
    return run(sminos.cmd_project, d, op="show", dir=d)


def written(d):
    with open(os.path.join(d, ".smns")) as f:
        return json.load(f)


class Words(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        sminos.write_json(os.path.join(T, "s", "daemon", "identity.json"),
                          {"org": ORG, "hub": URL, "name": MACHINE, "former": {}})

    def test_a_plain_folder_is_declared_with_maws(self):
        d = os.path.join(T, "w", "plain")
        os.makedirs(d)
        code, _, err = init(d)
        self.assertEqual(code, sminos.EXIT_USAGE)
        self.assertIn("project init needs a git repository: .smns is committed at its root; "
                      "a plain folder is declared with `maws project add`", err)

    def test_init_beside_a_link_writes_the_links_id(self):
        r = repo("linked")
        keep_org([stated(r, LINKED, "linked")])   # a minted folder linked: its one entry carries the link (§D)
        os.makedirs(os.path.join(r, "sub"))
        code, out, err = init(os.path.join(r, "sub"))
        self.assertEqual(code, 0, err)
        self.assertEqual(written(r), {"project": LINKED, "name": "linked", "remote": "", "hub": {"org": ORG}})
        self.assertIn("project linked (%s) at %s/.smns, a hub project of org %s" % (LINKED, r, ORG), out)
        self.assertIn("a stored statement on this machine decides this folder's project, a link at %s: the .smns "
                      "just written, which names the id in effect, is not what decides here" % r, out)
        self.assertEqual(sminos.decision(r).by, "link")

    def test_init_beside_a_minted_id_says_a_stored_id(self):
        r = repo("minted")
        keep_org([stated(r, MINTED, "minted")])
        code, out, err = init(r, name="mine", hub=True)
        self.assertEqual(code, 0, err)
        self.assertEqual(written(r), {"project": MINTED, "name": "mine", "remote": "", "hub": {"org": ORG}})
        self.assertIn("decides this folder's project, a stored id at %s:" % r, out)

    def test_init_beside_a_file_that_names_the_id_in_effect(self):
        r = repo("same")
        smns(r, LINKED)
        keep_org([stated(r, LINKED, "linked")])
        code, out, err = init(r)
        self.assertEqual(code, 0, err)
        self.assertEqual(out, "%s/.smns already names project filed (%s), the id in effect\na stored statement on "
                         "this machine decides this folder's project, a link at %s: the .smns is not what decides "
                         "here\n" % (r, LINKED, r))

    def test_init_and_show_beside_a_file_that_names_another_project(self):
        r = repo("other")
        smns(r, FILED)
        keep_org([stated(r, LINKED, "linked")])
        code, _, err = init(r)
        self.assertEqual(code, sminos.EXIT_USAGE)
        self.assertIn("%s is already project filed (%s); a stored statement on this machine decides this folder's "
                      "project, a link at %s, project linked (%s): the .smns is not what decides here"
                      % (r, FILED, r, LINKED), err)
        self.assertEqual(written(r)["project"], FILED)
        code, out, err = show(os.path.join(r))
        self.assertEqual(code, 0, err)
        self.assertIn("id       %s\n" % LINKED, out)
        self.assertIn("source   a link at %s\nfile     .smns at %s names another project, filed (%s): the link at "
                      "%s decides here, project %s\n" % (r, r, FILED, r, LINKED), out)

    def test_a_worktree_of_a_linked_main_checkout(self):
        r = repo("main")
        wt = os.path.join(r, ".claude", "worktrees", "wt")
        git("-C", r, "worktree", "add", "-q", wt, "-b", "wt")
        keep_org([stated(r, LINKED, "linked")])
        code, out, err = init(wt)
        self.assertEqual(code, 0, err)
        self.assertEqual(written(wt)["project"], LINKED)
        self.assertIn("decides this folder's project, a link at %s:" % r, out)
        os.remove(os.path.join(wt, ".smns"))
        smns(wt, FILED)   # the committed file a worktree carries, naming another project
        code, out, err = show(wt)
        self.assertEqual(code, 0, err)
        self.assertIn("file     .smns at %s names another project, filed (%s): the link at %s decides here"
                      % (wt, FILED, r), out)

    def test_a_statement_above_the_repository_leaves_init_as_today(self):
        top = os.path.join(T, "w", "declared")
        os.makedirs(top)
        r = os.path.join(top, "inner")
        os.makedirs(r)
        git("init", "-q", r)
        keep_org([stated(top, MINTED, "minted")])
        code, out, err = init(r, name="inner")
        self.assertEqual(code, 0, err)
        pid = written(r)["project"]
        self.assertNotIn(pid, (MINTED, LINKED))
        self.assertNotIn("stored statement", out)
        self.assertEqual(sminos.decision(r).by, "smns")

    def test_show_says_nothing_of_a_file_above_the_statement(self):
        top = os.path.join(T, "w", "outer")
        os.makedirs(top)
        smns(top, FILED)
        d = os.path.join(top, "nested")
        os.makedirs(d)
        keep_org([stated(d, MINTED, "minted")])
        code, out, err = show(d)
        self.assertEqual(code, 0, err)
        self.assertIn("source   a stored id at %s\n" % d, out)
        self.assertNotIn("file     ", out)


def tearDownModule():
    shutil.rmtree(T, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
