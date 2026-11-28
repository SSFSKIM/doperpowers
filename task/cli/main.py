"""`task`: the agents' one command for tracked work (R9). Every verb this
release builds works tickets on a GitHub board; the verbs that would write
to the human's Task Board are a separate unit, and their names stay unused
here (`assign-human` says so)."""
import argparse
import json
import pathlib
import sys

sys.dont_write_bytecode = True

import claiming  # noqa: E402
import migrate  # noqa: E402
import verbs  # noqa: E402
from common import FAILED, USAGE, Stop  # noqa: E402
from github import GitHubError  # noqa: E402
from record import ValueNotOneLine  # noqa: E402

PLUGIN = pathlib.Path(__file__).resolve().parent.parent


def version():
    data = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())
    return "task %s (the task plugin of the doperpowers marketplace)" % data["version"]


def issue_number(text):
    """An issue's number: a positive integer."""
    try:
        n = int(text)
    except ValueError:
        n = 0
    if n < 1 or not text.strip().isdigit():
        raise argparse.ArgumentTypeError("%r is no issue number (a positive integer)" % text)
    return n


class Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        sys.stderr.write("%s: error: %s\n" % (self.prog, message))
        sys.exit(USAGE)


def parser():
    p = Parser(prog="task", description="Tickets on a repository's GitHub board: the board is the repository of "
               "the clone's designated remote (git config task.remote, else origin), configured by "
               ".doperpowers/board.json on that remote's default branch as last fetched; --repo owner/name works "
               "a board from anywhere.")
    p.add_argument("--version", action="version", version=version())
    sub = p.add_subparsers(dest="verb", metavar="<verb>", parser_class=Parser)

    on_board = Parser(add_help=False)
    on_board.add_argument("--repo", metavar="OWNER/NAME", help="work this repository's board, from anywhere")
    reading = Parser(add_help=False)
    reading.add_argument("--json", action="store_true", help="print JSON")

    def verb(name, run, help, parents=(on_board,)):
        v = sub.add_parser(name, help=help, description=help, parents=list(parents))
        v.set_defaults(run=run)
        return v

    v = verb("create", verbs.create, "open a ticket with its labels, edges and record; prints <number> <url>")
    v.add_argument("title")
    v.add_argument("--category", required=True, help="bug, enhancement, spike or env-issue")
    v.add_argument("--priority", required=True, help="P0 to P3")
    v.add_argument("--readiness", required=True, help="ready-to-work, need-design or need-input")
    v.add_argument("--body-file", required=True, metavar="FILE")
    v.add_argument("--horizon", default="expected", help="planned, expected (the default) or undecided")
    v.add_argument("--blocked-by", metavar="N,...", help="blockers: N or owner/name#N, comma-separated")
    v.add_argument("--parent", type=issue_number, metavar="N")
    v.add_argument("--batch", metavar="NAME")
    v.add_argument("--due", metavar="YYYY-MM-DD")
    v.add_argument("--spec", metavar="PATH[@SHA]|URL")
    v.add_argument("--to", metavar="THREAD", help="register it for a thread, which is sent one message")

    v = verb("show", verbs.show, "a ticket: labels, record, edges, linked activity, body and comments, each "
             "marked trusted or not", (on_board, reading))
    v.add_argument("number", type=issue_number)

    v = verb("list", verbs.list_, "the board's tickets, by priority then number", (on_board, reading))
    v.add_argument("--takeable", action="store_true", help="only what a session may take on its own initiative")
    v.add_argument("--readiness")
    v.add_argument("--horizon")
    held = v.add_mutually_exclusive_group()
    held.add_argument("--claimed", action="store_true")
    held.add_argument("--unclaimed", action="store_true")
    v.add_argument("--batch", metavar="NAME")
    v.add_argument("--untracked", action="store_true", help="the open issues that are not on the board instead")

    v = verb("search", verbs.search, "GitHub's issue search, held to the board's repository", (on_board, reading))
    v.add_argument("query")
    v.add_argument("--state", choices=("open", "closed", "all"), default="all")
    v.add_argument("--bodies", action="store_true")

    v = verb("set", verbs.set_, "change a ticket's labels, record, title or text; no body it does not trust")
    v.add_argument("number", type=issue_number)
    v.add_argument("--readiness")
    v.add_argument("--horizon")
    v.add_argument("--priority")
    v.add_argument("--category")
    for flag, metavar in (("batch", "NAME"), ("due", "YYYY-MM-DD"), ("spec", "S"), ("to", "THREAD")):
        g = v.add_mutually_exclusive_group()
        g.add_argument("--" + flag, metavar=metavar)
        g.add_argument("--no-" + flag, action="store_true")
    v.add_argument("--title")
    v.add_argument("--body-file", metavar="FILE", help="the text above the record block")

    v = verb("adopt", verbs.adopt, "make a body another account edited trusted, on the owner's word, after it "
             "was read whole")
    v.add_argument("number", type=issue_number)
    v.add_argument("--digest", required=True, help="the body_digest task show printed with the text read")

    v = verb("edge", verbs.edge, "write or cut one edge")
    v.add_argument("number", type=issue_number)
    g = v.add_mutually_exclusive_group(required=True)
    g.add_argument("--block", metavar="N", help="the ticket is blocked by N (or owner/name#N)")
    g.add_argument("--unblock", metavar="N")
    g.add_argument("--parent", type=issue_number, metavar="N")
    g.add_argument("--orphan", action="store_true")

    v = verb("comment", verbs.comment, "comment on a ticket")
    v.add_argument("number", type=issue_number)
    v.add_argument("--body-file", required=True, metavar="FILE")

    v = verb("close", claiming.close, "close a ticket, completed unless --not-planned; not one another thread "
             "holds, without --force")
    v.add_argument("number", type=issue_number)
    v.add_argument("--not-planned", action="store_true")
    v.add_argument("--body-file", metavar="FILE", help="a comment written before the close")
    v.add_argument("--force", metavar="REASON", help="close a ticket another thread holds, saying why")

    v = verb("claim", claiming.claim, "take tickets for this session's thread, one by one; prints which were won")
    v.add_argument("numbers", type=issue_number, nargs="*", metavar="N")
    v.add_argument("--batch", metavar="NAME", help="the open tickets of batch:NAME")

    v = verb("release", claiming.release, "set a claimed ticket down")
    v.add_argument("number", type=issue_number)
    v.add_argument("--body-file", metavar="FILE", help="prose after the record: where the work stands")
    v.add_argument("--force", metavar="REASON", help="release another thread's claim, saying why")
    v.add_argument("--of", type=issue_number, metavar="CLAIM", help="with --force: only while that claim holds")

    v = verb("takeover", claiming.takeover, "take over the current claim: along a /clear's grant, or --force")
    v.add_argument("number", type=issue_number)
    v.add_argument("--force", metavar="REASON", help="take over a live thread's claim, saying why")

    machine = Parser(add_help=False)
    machine.add_argument("--json", action="store_true", help="print JSON")
    v = verb("held", claiming.held, "what this machine's index says a thread holds, lapsed or is offered; no "
             "network", (machine,))
    v.add_argument("--session", required=True, metavar="ID")
    v.add_argument("--thread", metavar="ID")
    v.add_argument("--cleared-from", metavar="ID", help="first grant --session the takeover of that thread's "
                   "claims (a /clear left it)")
    v = verb("settle", claiming.settle, "make this machine's claims true: each row read again, each thread asked "
             "whether it has ended", (machine,))
    v.add_argument("--thread", metavar="ID", help="only that thread's rows")

    verb("lint", verbs.lint, "the board's invariants; exit 3 on a FAIL", (on_board, reading))

    v = sub.add_parser("migrate", help="the one-time relabel from the old status labels, by a plan read first",
                       description="the one-time relabel from the old status labels: a plan, read and settled, "
                       "then applied")
    steps = v.add_subparsers(dest="step", metavar="<step>", parser_class=Parser, required=True)
    s = steps.add_parser("plan", parents=[on_board], help="read the open issues and write the plan (needs only a "
                         "repository, not a board that has moved)")
    s.add_argument("--out", metavar="FILE", help="where to write it, outside every repository's tree (by default "
                   "the plugin's home)")
    s.set_defaults(run=migrate.plan)
    s = steps.add_parser("apply", parents=[on_board], help="write a settled plan onto the board, whose default "
                         "branch says binding \"task\"")
    s.add_argument("plan", metavar="PLAN")
    s.set_defaults(run=migrate.apply)

    v = sub.add_parser("assign-human", help="(the human's Task Board: not built)", add_help=False)
    v.add_argument("rest", nargs=argparse.REMAINDER)
    v.set_defaults(run=None)
    return p


def main(argv):
    p = parser()
    args = p.parse_args(argv)
    if args.verb is None:
        p.print_help(sys.stderr)
        return USAGE
    if args.verb == "assign-human":
        sys.stderr.write("task assign-human: the Task Board is not built (what agents ask of the human, and the "
                         "human's to-dos, are a unit of their own); task works tickets on GitHub boards only\n")
        return USAGE
    try:
        args.run(verbs.Context(args))
    except Stop as stop:
        if stop.message:
            sys.stderr.write("error: %s\n" % stop.message)
        return stop.code
    except GitHubError as e:
        sys.stderr.write("error: GitHub: %s\n" % e.message)
        return FAILED
    except ValueNotOneLine as e:  # the record writer's own guard, met before any write
        sys.stderr.write("error: %s\n" % e)
        return USAGE
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
