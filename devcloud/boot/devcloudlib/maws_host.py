"""MAWS's endpoint on a host (P5 O14 M3): boot step 13, `maws`, and the
departure's word to the desk for a machine the endpoint certified.

A host created with the MAWS project under the driver profile's v2 code
carries the code's Secret Manager id and its delegation's id in its
descriptor. Step 1 puts the id in the host environment as
`MAWS_DELEGATION_ID`, so step 12's `devenv up maws` mints the machine's ref
under it before `mawsd` first starts; step 13 then fetches the code and pipes
it to `mawsd endpoint provision` as the user, which redeems it into a
certificate under the delegation, resumably: an endpoint the hub confirmed
but whose certificate is not yet live (exit 4) is left to the devcloud-enroll
timer, which runs the same command again without a second redemption. The
code is held in memory and handed over on stdin, never written to disk or an
argument list. A host without the wrapper has no `mawsd`: the step skips.

At its departure such a host retires its certificate itself (`mawsd endpoint
retire`), which also frees its hub row, so a recreated VM may take its name;
when it cannot, the owner's `machine drop` from a Mac does the same."""

import dataclasses
import json
import os
import pathlib

from . import proc
from .proc import StepError

UNIT = "mawsd.service"
# M1's `provision --wait`; the call's own bound adds mawsd's margin (O2: --wait + 10 s) and the start.
PROVISION_WAIT = 120
PROVISION_TIMEOUT = PROVISION_WAIT + 60
KEYS_TIMEOUT = 60
RETIRE_TIMEOUT = 120
# O2's exit codes for `mawsd`.
DONE, REFUSED, NOT_HERE, NOT_RUNNING, NOT_LISTED = 0, 1, 2, 3, 4


def wrapper(user, env):
    """The default profile's `mawsd` command line (`mawsd install`'s
    wrapper), under `${XDG_CONFIG_HOME:-~/.config}/MAWS` as MAWS keeps its
    profile on Linux."""
    config = env.get("XDG_CONFIG_HOME") or str(user.home / ".config")
    return pathlib.Path(config) / "MAWS/mawsd/bin/mawsd"


def present(program):
    return os.access(program, os.X_OK)


def drop_command(name):
    """The owner's command, in a MAWS worktree on a Mac, that retires the
    machine's key or certificate and frees its hub row (O14 M2's `machine
    drop`): the remedy wherever the machine cannot retire itself."""
    return f"zsh apps/desk-hub/deploy/production-run.sh admin machine drop {name}"


@dataclasses.dataclass(frozen=True)
class Provisioned:
    state: str      # ok | deferred | skipped
    detail: str


def provision(user, desc, env, fetch_code, call=proc.call):
    """Step 13's provisioning. `env` is the user's environment with the
    host's; `fetch_code(secret_id)` returns the code as text. Raises
    StepError on a refusal (exit 1) and on anything a retry cannot mend."""
    if not desc.maws_secret:
        return Provisioned("skipped", "no MAWS provisioning code named")
    program = wrapper(user, env)
    if not present(program):
        return Provisioned("skipped", f"no mawsd here ({program}): skipped")
    code = fetch_code(desc.maws_secret)
    argv = [str(program), "endpoint", "provision", "--name", desc.name, "--wait", str(PROVISION_WAIT)]
    exit_code, _, err = call(argv, user=user, env=env, log="maws", input=code + "\n", timeout=PROVISION_TIMEOUT,
                             cwd=str(user.home))
    if exit_code == DONE:
        return Provisioned("ok", f"{desc.name} org-listed under its certificate (mawsd endpoint provision)")
    if exit_code == NOT_LISTED:
        return Provisioned("deferred", "hub-confirmed, its certificate not yet live; devcloud-enroll runs the same "
                                       "provision again")
    if exit_code in (NOT_RUNNING, 124):
        return Provisioned("deferred", f"mawsd did not answer ({err or f'exit {exit_code}'}); devcloud-enroll runs "
                                       "the provision again")
    if exit_code == REFUSED:
        raise StepError(f"mawsd endpoint provision refused: {err or 'exit 1'}")
    raise StepError(f"mawsd endpoint provision exited {exit_code}" + (f": {err}" if err else "")
                    + (" (a mawsd without the endpoint module)" if exit_code == NOT_HERE else ""))


def keys(user, env, call=proc.call, timeout=KEYS_TIMEOUT):
    """`mawsd keys --json` as the user: (its answer, None), or (None, why)
    when the wrapper is absent or the answer cannot be read."""
    program = wrapper(user, env)
    if not present(program):
        return None, f"no mawsd here ({program})"
    exit_code, out, err = call([str(program), "keys", "--json"], user=user, env=env, log="lifecycle",
                               timeout=timeout, cwd=str(user.home))
    if exit_code != DONE:
        return None, err or f"mawsd keys exited {exit_code}"
    try:
        answer = json.loads(out.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return None, "mawsd keys printed no JSON"
    return (answer, None) if isinstance(answer, dict) else (None, "mawsd keys printed no JSON object")


def certified(answer):
    """Whether the endpoint holds a delegated enrollment to retire: a
    certificate, or a redemption under the delegation not yet whole (M1
    shows it `hub-confirmed` and `delegated`)."""
    return bool(answer and answer.get("delegated") is True and answer.get("enrollment", "none") != "none")


def retire(user, env, name, call=proc.call, timeout=RETIRE_TIMEOUT):
    """`mawsd endpoint retire` as the user; returns "left the desk", the line
    the driver reads as the desk confirming it, or raises StepError naming
    the owner's command when the hub side may remain."""
    program = wrapper(user, env)
    exit_code, out, err = call([str(program), "endpoint", "retire", "--json"], user=user, env=env, log="lifecycle",
                               timeout=timeout, cwd=str(user.home))
    if exit_code != DONE:
        raise StepError(f"the desk did not answer the retirement ({err or f'exit {exit_code}'}); "
                        f"run: {drop_command(name)}")
    try:
        kind = json.loads(out.strip().splitlines()[-1]).get("kind")
    except (ValueError, IndexError, AttributeError):
        kind = None
    if kind in ("retired", "uncertified", "nothing"):
        return "left the desk"
    if kind == "orphaned":
        raise StepError("retired here, but the hub no longer took the machine's credential, so its row and "
                        f"certificate are an admin's to drop; run: {drop_command(name)}")
    raise StepError(f"mawsd endpoint retire answered no outcome it names; run: {drop_command(name)}")
