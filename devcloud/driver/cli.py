"""`devcloud vm`: the command line (I16).

  devcloud vm up [--label L] [--project owner/repo[@ref]]... [--account A] [--type T] [--location L]
                 [--disk GB] [--ttl D | --keep] [--spot] [--enroll-code -] [--confirmed] [--dry-run]
  devcloud vm adopt <user@address> [--label L] [--project …]... [--ttl D] [--confirmed] [--dry-run]
  devcloud vm ls [--json]
  devcloud vm ssh <name> [--root] [-- command...]
  devcloud vm lease <name> <duration> [--confirmed]
  devcloud vm down <name> [--force]
  devcloud vm image build [--account A] | image ls
  devcloud vm reap [--install]
  devcloud vm provider register <account> --confirmed | provider test <account>

Exit: 0 ok · 1 failed · 2 usage · 3 the provider refused, or a capability is
missing · 4 over a cap: needs --confirmed · 5 down guard: unpushed work ·
6 not a driver here: no seed key, or a devcloud host · 7 the account's
provider is not usable: not registered, or no passing copy yet."""

import argparse
import os
import signal
import sys

from . import adopt, conformance, images, ops, reaper, up
from .context import Context, Paths
from .errors import NOT_DRIVER, USAGE, DriverError

HOST_MARKER = "/etc/devcloud/boot.env"


class Terminated(BaseException):
    """A SIGTERM, raised where the driver is, so its cleanups run (the
    provider's group stopped, a provider test's server deleted)."""


def _terminate(signum, frame):
    raise Terminated()


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise DriverError(USAGE, message)


def parser():
    top = _Parser(prog="devcloud vm", description="Cloud machines for sessions.", epilog=__doc__,
                  formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = top.add_subparsers(dest="command", required=True, parser_class=_Parser)
    p = sub.add_parser("up", help="create a host")
    p.add_argument("--label", default=None)
    p.add_argument("--project", action="append", default=[])
    p.add_argument("--account")
    p.add_argument("--type")
    p.add_argument("--location")
    p.add_argument("--disk", type=int)
    life = p.add_mutually_exclusive_group()
    life.add_argument("--ttl")
    life.add_argument("--keep", action="store_true")
    p.add_argument("--spot", action="store_true")
    p.add_argument("--enroll-code", dest="enroll_code", choices=["-"])
    p.add_argument("--confirmed", action="store_true")
    p.add_argument("--dry-run", dest="dry_run", action="store_true")
    p = sub.add_parser("adopt", help="make a machine the driver did not make a host, until released")
    p.add_argument("target", metavar="user@address")
    p.add_argument("--label", default=None)
    p.add_argument("--project", action="append", default=[])
    p.add_argument("--ttl")
    p.add_argument("--confirmed", action="store_true")
    p.add_argument("--dry-run", dest="dry_run", action="store_true")
    p = sub.add_parser("ls", help="list hosts")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("ssh", help="a shell or a command on a host")
    p.add_argument("name")
    p.add_argument("--root", action="store_true")
    p = sub.add_parser("lease", help="set a host's lease end to now + duration")
    p.add_argument("name")
    p.add_argument("duration")
    p.add_argument("--confirmed", action="store_true")
    p = sub.add_parser("down", help="depart and delete a host")
    p.add_argument("name")
    p.add_argument("--force", action="store_true")
    p = sub.add_parser("image", help="build or list an account's images")
    isub = p.add_subparsers(dest="image_action", required=True, parser_class=_Parser)
    q = isub.add_parser("build")
    q.add_argument("--account")
    isub.add_parser("ls")
    p = sub.add_parser("reap", help="delete what outlived its lease, purpose or retention")
    p.add_argument("--install", action="store_true")
    p = sub.add_parser("provider", help="register or test an account's provider")
    psub = p.add_subparsers(dest="action", required=True, parser_class=_Parser)
    q = psub.add_parser("register")
    q.add_argument("account")
    q.add_argument("--confirmed", action="store_true")
    q = psub.add_parser("test")
    q.add_argument("account")
    return top


def _dispatch(ctx, args, command, stdin):
    if args.command == "up":
        if args.enroll_code == "-":
            code = stdin.read()
            if not code.strip():
                raise DriverError(USAGE, "--enroll-code -: no code on stdin")
            args.enroll_code = code
        return up.run(ctx, args)
    if args.command == "adopt":
        return adopt.run(ctx, args)
    if args.command == "ls":
        return ops.ls(ctx, as_json=args.json)
    if args.command == "ssh":
        return ops.ssh(ctx, args.name, root=args.root, command=command)
    if args.command == "lease":
        return ops.lease(ctx, args.name, args.duration, confirmed=args.confirmed)
    if args.command == "down":
        return ops.down(ctx, args.name, force=args.force)
    if args.command == "image":
        return images.build_command(ctx, args.account) if args.image_action == "build" else images.ls(ctx)
    if args.command == "reap":
        return reaper.install(ctx) if args.install else reaper.run(ctx)
    if args.action == "register":
        return conformance.register(ctx, args.account, confirmed=args.confirmed)
    return conformance.test(ctx, args.account)


def main(argv, env=None, ctx=None, host_marker=HOST_MARKER, stdin=None):
    env = dict(os.environ if env is None else env)
    err = ctx.err if ctx is not None else sys.stderr
    if os.path.exists(host_marker):
        print("devcloud vm: this machine is a devcloud host; drive from a Mac", file=err)
        return NOT_DRIVER
    command = []
    if argv[:1] == ["ssh"] and "--" in argv:
        cut = argv.index("--")
        argv, command = argv[:cut], argv[cut + 1:]
    try:
        try:
            args = parser().parse_args(argv)
        except SystemExit as stop:      # --help
            return stop.code or 0
        ctx = ctx or Context(Paths.from_env(env), env=env)
        if not ctx.paths.seed.exists():
            raise DriverError(NOT_DRIVER, f"no seed key at {ctx.paths.seed} ($DEVCLOUD_SEED_FILE, else "
                                          "~/.config/devcloud/seed.json): this machine is not a driver")
        return _dispatch(ctx, args, command, stdin or sys.stdin.buffer)
    except DriverError as error:
        print(f"devcloud vm: {error}", file=err)
        return error.code
    except KeyboardInterrupt:
        print("devcloud vm: interrupted", file=err)
        return 130
    except Terminated:
        print("devcloud vm: terminated", file=err)
        return 143


def command_line(argv):
    """`devcloud vm` as a process: a SIGTERM ends it as an interrupt does."""
    signal.signal(signal.SIGTERM, _terminate)
    return main(argv)
