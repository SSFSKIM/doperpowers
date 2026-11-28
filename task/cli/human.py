"""The human's board (the Task Board, which sminos keeps: D2 and X5 of
docs/doperpowers/specs/2026-11-27-task-board-design.md): which of `task`'s
forms are its, and running each as the matching `sminos task` verb.

A form is the human's board's when its verb is `assign-human`, `revise`,
`withdraw` or `reopen`; `show` or `comment` with a first argument that is a
whole task id (`t<n>`); or `list` with `--human`, or with a prefix of it that
the ticket board's parser would take for it (`--hu` on: argparse resolves an
unambiguous prefix, and `--h` is ambiguous there). `main` asks before anything
of the ticket board (its configuration, `gh`) is read, so these forms work in
any directory, with no ticket board configured: the human's board is the
machine's. `revise`, `withdraw` and `reopen` given a ticket's number exit 2
here, sminos or not.

The run: `sminos task <verb>` with the arguments as given (`assign-human`
runs `assign`; `list --human` runs `list` without the flag), sminos found as
every call `task` makes to it is (`sminos_client.find`), bounded at
`sminos_client.TIMEOUT`. Standard input, output and error are this process's
own, handed over unread, so a heredoc's body reaches sminos byte for byte and
what sminos prints is what the caller reads: a verb's `--help` is sminos's,
its usage and its flags. The exit is kept when it is 0, 2
or 3, the codes the two commands share (done, usage, refused); anything else,
sminos's 75 (its store's lock not had) and a signal included, is 1.
"""
import re
import subprocess
import sys

import sminos_client
from common import FAILED, USAGE

TASK_ID = re.compile(r"t[1-9][0-9]*")
TICKET_NUMBER = re.compile(r"[0-9]+")
KEPT_EXITS = (0, 2, 3)
# What the ticket board's `list` parser resolves to --human (allow_abbrev): `--h` is also --help and --horizon.
HUMAN_FLAG = re.compile(r"--hu(?:m(?:an?)?)?")
# `task`'s verb that exists only for the human's board -> sminos's verb.
ONLY_HUMAN = {"assign-human": "assign", "revise": "revise", "withdraw": "withdraw", "reopen": "reopen"}


def form(argv):
    """The `sminos task` arguments a form of the human's board runs, or None
    when `argv` is the ticket board's."""
    if not argv:
        return None
    verb, rest = argv[0], argv[1:]
    if verb in ONLY_HUMAN:
        return [ONLY_HUMAN[verb]] + rest
    if verb in ("show", "comment") and rest and TASK_ID.fullmatch(rest[0]):
        return [verb] + rest
    if verb == "list" and any(HUMAN_FLAG.fullmatch(a) for a in rest):
        return ["list"] + [a for a in rest if not HUMAN_FLAG.fullmatch(a)]
    return None


def asks_help(args):
    """Whether `args` ask a verb for its help, as argparse reads them: `-h` or `--help` before any `--`."""
    head = args[:args.index("--")] if "--" in args else args
    return "-h" in head or "--help" in head


def run(verb, args):
    """Run `sminos task` with `args` (what `form` gave for `verb`); the exit
    `task` ends with."""
    if verb in ("revise", "withdraw", "reopen") and len(args) > 1 and TICKET_NUMBER.fullmatch(args[1]):
        sys.stderr.write("task %s: %s is a ticket's number; %s works tasks on the human's board, whose ids are t<n>\n"
                         % (verb, args[1], verb))
        return USAGE
    cli = sminos_client.find()
    if cli and verb != args[0] and asks_help(args):
        # sminos's help names its own verb (`sminos task assign`): say which `task` runs.
        sys.stdout.write("task %s runs sminos task %s, whose help this is:\n" % (verb, args[0]))
        sys.stdout.flush()
    if not cli:
        sys.stderr.write("task %s: the human's board is kept by sminos, which is not installed here (looked for: "
                         "TASK_SMINOS, else sminos on the PATH, else the doperpowers marketplace's clone)\n" % verb)
        return FAILED
    try:
        done = subprocess.run([cli, "task"] + args, timeout=sminos_client.TIMEOUT)
    except subprocess.TimeoutExpired:
        sys.stderr.write("task %s: sminos task %s gave no answer within %d s\n"
                         % (verb, args[0], sminos_client.TIMEOUT))
        return FAILED
    except OSError as e:
        sys.stderr.write("task %s: sminos (%s) could not be run: %s\n" % (verb, cli, e.strerror or e))
        return FAILED
    return done.returncode if done.returncode in KEPT_EXITS else FAILED
