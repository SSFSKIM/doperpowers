"""Delivery shared by the idle notice and the lease warning (§4.5)."""
import pathlib

from . import envfile, proc, sminos_host

ENV_PATH = "/etc/devcloud/env"


def deliver(user, d, text, call=proc.call, say=print):
    """Try the creator, the project's live members, then its durable log.

    sminos refuses an ended interactive session with exit 4. A project
    broadcast also exits 4 when nobody is live, recording nothing: --in
    without a tag is the note a future session reads. Other failures fall
    through to the journal and wall; neither notice ever changes lifetime.
    """
    try:
        env = envfile.parse(pathlib.Path(ENV_PATH).read_text())
    except (FileNotFoundError, ValueError):
        env = {}
    env = user.env(env)
    # These are host service messages, not a session tagging itself. --in is
    # the operator form and refuses a session's environment.
    env.pop("CLAUDE_CODE_SESSION_ID", None)
    program = sminos_host.cli(user)
    enrolled = (sminos_host.sminos_home(user, env) / "daemon/hub.json").is_file()
    if program and enrolled:
        def send(args):
            code, _, error = call([sminos_host.PYTHON, str(program), "say", *args], user=user, env=env,
                                  log="lease", cwd=str(user.home), timeout=120)
            if code:
                say(f"devcloud notice: delivery failed (exit {code}): {error}")
            else:
                say(f"devcloud notice: sent: {text}")
            return code
        if d.creator and send([f"{d.creator} {text}"]) == 0:
            return
        if d.creator_project:
            code = send(["--project", d.creator_project, text])
            if code == 0:
                return
            if code == 4 and send(["--in", d.creator_project, text]) == 0:
                return
    say(f"devcloud notice: {text}")
    call(["wall", f"devcloud: {text}"], log="lease", timeout=30)
