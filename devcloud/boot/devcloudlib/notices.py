"""Delivery shared by the idle notice and the lease warning (§4.5)."""
import pathlib

from . import envfile, proc, sminos_host

ENV_PATH = "/etc/devcloud/env"
# The program a notice names (sminos's `say --notice`): sminos delivers it as
# this machine's notice, from `devcloud@<host>`, never as a person's words.
NOTICE = "devcloud"
MARKED = ("--notice", NOTICE)
HELD = 3      # `say --exit-held`: the thread that owns the host is held and not woken with it
UNKNOWN = 2   # a usage error: a sminos that does not know the two flags (or, after the chain, --pools)
# Which text the channels' record carries (EN.G2's O6, the owner's answer: the notice's own text): "full", the
# chain's, the repositories with unpushed work included, read by everyone who may read the channel's log; or
# "short", the one each notice composes for a channel (the machine, what happened, its lifetime and cost, nothing of
# what is on it). Frozen on every host built from this file, and a text posted into a channel cannot be recalled.
CHANNEL_TEXT = "full"


def deliver(user, d, text, call=proc.call, say=print, short=None):
    """Try the thread that owns the host, its project's live members, then
    its durable log; then record it in the channels whose pool holds the
    host.

    Each step is a `say` marked as this host's notice. sminos refuses an
    ended thread and no member with exit 4, and says with exit 3 that the
    owning thread is held and is not woken with it now: either way the
    notice goes on. A project broadcast also exits 4 when nobody is live,
    recording nothing: --in without a tag is the note a future session
    reads, written whenever nobody live heard it, whatever the first step
    recorded. A step a sminos without the notice flags refuses (exit 2) runs
    once more without them. Other failures fall through to the journal and
    wall; neither notice ever changes lifetime.

    After that chain, whichever way it ended, and wherever the host's sminos
    is found and the host cut over: one `say --notice devcloud --pools` with
    the channels' text (CHANNEL_TEXT: the full text; set to "short", the
    short one, and none where none is given), which sminos records, untagged and prompting no one, in each
    channel whose pool holds this machine. Its outcome is said and changes
    nothing: no step is called again, and nothing is sent twice.
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
            return call([sminos_host.PYTHON, str(program), "say", *args], user=user, env=env, log="lease",
                        cwd=str(user.home), timeout=120)

        def send(flags, args):
            code, _, error = run([*flags, *args])
            if code == UNKNOWN:
                say("devcloud notice: this host's sminos does not know the notice flags; sent without them")
                code, _, error = run(args)
            if code == HELD:
                say("devcloud notice: recorded for the thread that owns this host, which is not woken with it "
                    "now; going on to its project")
            elif code:
                say(f"devcloud notice: delivery failed (exit {code}): {error}")
            else:
                say(f"devcloud notice: sent: {text}")
            return code

        def chain():
            if d.creator and send([*MARKED, "--exit-held"], [f"{d.creator} {text}"]) == 0:
                return True
            if d.creator_project:
                code = send(MARKED, ["--project", d.creator_project, text])
                if code == 0:
                    return True
                if code == 4 and send(MARKED, ["--in", d.creator_project, text]) == 0:
                    return True
            return False
        if not chain():
            journal(say, call, text)
        channel_text = text if CHANNEL_TEXT == "full" else short
        if channel_text is not None:
            record_in_channels(run, say, channel_text)
        return
    journal(say, call, text)


def journal(say, call, text):
    say(f"devcloud notice: {text}")
    call(["wall", f"devcloud: {text}"], log="lease", timeout=30)


def record_in_channels(run, say, text):
    """The channels' record (EN.G2's M3), after the chain: a usage error
    (exit 2) is a sminos that predates --pools, never a reason to send the
    text again without it, which would be a plain say into the project of
    the host's directory."""
    try:
        code, out, error = run([*MARKED, "--pools", text])
    except Exception as failure:   # the chain's outcome stands whatever became of this record
        say(f"devcloud notice: the channels' record failed: {failure}")
        return
    if code == 0:
        for line in out.splitlines():
            say(f"devcloud notice: channels: {line}")
    elif code == UNKNOWN:
        say("devcloud notice: this host's sminos does not know --pools; no channel's timeline was written")
    else:
        say(f"devcloud notice: the channels' record failed (exit {code}): {error}")
