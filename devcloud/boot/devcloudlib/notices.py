"""Delivery shared by the idle notice and the lease warning (§4.5)."""
import pathlib

from . import envfile, proc, sminos_host

ENV_PATH = "/etc/devcloud/env"
# The program a notice names (sminos's `say --notice`): sminos delivers it as
# this machine's notice, from `devcloud@<host>`, never as a person's words.
NOTICE = "devcloud"
MARKED = ("--notice", NOTICE)
HELD = 3      # `say --exit-held`: the thread that owns the host is held and not woken with it
UNKNOWN = 2   # a usage error: a sminos that does not know the two flags


def deliver(user, d, text, call=proc.call, say=print):
    """Try the thread that owns the host, its project's live members, then
    its durable log.

    Each step is a `say` marked as this host's notice. sminos refuses an
    ended thread and no member with exit 4, and says with exit 3 that the
    owning thread is held and is not woken with it now: either way the
    notice goes on. A project broadcast also exits 4 when nobody is live,
    recording nothing: --in without a tag is the note a future session
    reads, written whenever nobody live heard it, whatever the first step
    recorded. A step a sminos without the notice flags refuses (exit 2) runs
    once more without them. Other failures fall through to the journal and
    wall; neither notice ever changes lifetime.
    """
    try:
        env = envfile.parse(pathlib.Path(ENV_PATH).read_text())
    except (FileNotFoundError, ValueError):
        env = {}
    env = user.env(env)
    # These are host service messages, not a session tagging itself. --in is
    # the operator form, and --notice refuses a session's environment.
    env.pop("CLAUDE_CODE_SESSION_ID", None)
    program = sminos_host.cli(user)
    if program and sminos_host.cut_over(user, env):
        def run(args):
            code, _, error = call([sminos_host.PYTHON, str(program), "say", *args], user=user, env=env,
                                  log="lease", cwd=str(user.home), timeout=120)
            return code, error

        def send(flags, args):
            code, error = run([*flags, *args])
            if code == UNKNOWN:
                say("devcloud notice: this host's sminos does not know the notice flags; sent without them")
                code, error = run(args)
            if code == HELD:
                say("devcloud notice: recorded for the thread that owns this host, which is not woken with it "
                    "now; going on to its project")
            elif code:
                say(f"devcloud notice: delivery failed (exit {code}): {error}")
            else:
                say(f"devcloud notice: sent: {text}")
            return code
        if d.creator and send([*MARKED, "--exit-held"], [f"{d.creator} {text}"]) == 0:
            return
        if d.creator_project:
            code = send(MARKED, ["--project", d.creator_project, text])
            if code == 0:
                return
            if code == 4 and send(MARKED, ["--in", d.creator_project, text]) == 0:
                return
    say(f"devcloud notice: {text}")
    call(["wall", f"devcloud: {text}"], log="lease", timeout=30)
