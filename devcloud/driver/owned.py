"""`devcloud vm owned-by` (contract X9): which hosts name any of the given
creators, for a program that must not take a partial fleet for the whole.

A name is a creator tag (@short, @alias#short, @alias, @project/alias) or a
session's bare short id. What a host holds is its creator's short id (the
`devcloud-creator` label; an adoption record's `creator`), so a host matches
a name equal to its tag `@<short>`, to the bare short id, or ending in
`#<short>`. The answer is one JSON object, exit 0:

  answer   "owned" when a host matched, else "unknown" when anything could
           not be listed, else "none": every account listed in full
  vms      the hosts that matched: name, account, provider, creator
           (an adopted host: account "adopted", provider null, adopted true)
  unknown  what could not be asked: account, provider, failed ("account":
           not usable; "listing": its list failed), reason
  listed   the accounts listed in full

Any other exit printed no answer. It asks no host and runs no reaper."""

import json
import re

from . import adopt
from .errors import USAGE, DriverError

_TAG = re.compile(r"@[A-Za-z0-9][A-Za-z0-9._/-]*(?:#[0-9a-f]+)?\Z")   # descriptor.py's _CREATOR
_SHORT = re.compile(r"[0-9a-f]+\Z")


def _check(names):
    if not names:
        raise DriverError(USAGE, "owned-by takes one or more creator tags or short ids")
    for name in names:
        if not (_TAG.match(name) or _SHORT.match(name)):
            raise DriverError(USAGE, f"{name!r} is neither a creator tag (@short, @alias#short, @alias, "
                                     "@project/alias) nor a short id")


def _matches(short, names):
    return bool(short) and any(n in (short, f"@{short}") or n.endswith(f"#{short}") for n in names)


def run(ctx, names):
    _check(names)
    entries, listed, missing = ctx.census(kinds=None)
    vms = [{"name": e.vm["name"], "account": e.account.name, "provider": e.account.provider,
            "creator": f"@{e.vm['labels']['devcloud-creator']}"}
           for e in entries if _matches(e.vm["labels"].get("devcloud-creator"), names)]
    unknown = [{"account": account.name, "provider": account.provider, "failed": failed, "reason": str(error)}
               for account, failed, error in missing]
    try:
        records = adopt.records(ctx)
    except DriverError as error:
        records = []
        unknown.append({"account": "adopted", "provider": None, "failed": "listing", "reason": str(error)})
    vms += [{"name": r.name, "account": "adopted", "provider": None, "creator": f"@{r.creator}", "adopted": True}
            for r in records if _matches(r.creator, names)]
    answer = "owned" if vms else "unknown" if unknown else "none"
    ctx.say(json.dumps({"answer": answer, "vms": vms, "unknown": unknown,
                        "listed": [account.name for account in listed]}))
    return 0
