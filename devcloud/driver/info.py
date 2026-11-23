"""`devcloud vm info [--within <seconds>] <name>...` (EN.G2's plan,
docs/doperpowers/plans/2026-11-23-sminos-environments-en-g2.md, Interfaces
§2): what each named host is, for a program that words it itself (sminos's
`channel show`). One JSON object, exit 0:

  hosts    every server of every configured account, and every adoption
           record, whose name equals a name asked without regard to case
           (two hosts of one name give two rows): name, account, provider
           (null for an adopted machine, whose `adopted` is true; a
           provider's host has no `adopted`), creator (`@` and the short id
           the host holds, the label's word: after a handover the owning
           thread's session; null where it holds none), created (Unix
           seconds as the provider reports them; null for an adopted
           machine), spent and currency (the type's hourly list price times
           the age, by the rule `vm ls` prints SPENT with, and its currency;
           both null for an adopted machine, a type with no price, and a
           type list that could not be read, in time or at all)
  unknown  what could not be asked: account, provider, failed ("account":
           not usable; "listing": its list failed with time left; "time":
           its list was not started, or ended only when the budget did),
           reason
  listed   the accounts listed in full
  unused   the accounts not asked because their provider never passed under
           this profile, as `vm owned-by` computes them (owned.py). For an
           inventory that is coverage not had: a host another Mac made
           there is not seen from here.

`--within` (12 seconds unless given) bounds the providers' work: the
accounts are walked one after another under Context.bounded, then the price
reads, and each account's fate is decided at that account, as it is walked,
never judged after the walk. One stalled account can take all that is left;
the reply is composed and printed after, in the margin the caller keeps.
No name, or a `--within` that is no positive number, is usage (exit 2). It
asks no host, runs no reaper and writes nothing."""

import json
import math

from . import adopt, ops, provider
from .errors import USAGE, DriverError, Spent

WITHIN = 12


def provider_host(name, account, provider_name, creator, created, spent, currency):
    """One provider's host as the reply carries it (`creator` the short id the host holds, or None)."""
    return {"name": name, "account": account, "provider": provider_name, "creator": _tag(creator),
            "created": created, "spent": spent, "currency": currency}


def adopted_host(name, creator):
    """One adopted machine as the reply carries it: no age, no cost."""
    return {"name": name, "account": "adopted", "provider": None, "adopted": True, "creator": _tag(creator),
            "created": None, "spent": None, "currency": None}


def missing(account, provider_name, failed, reason):
    """One thing that could not be asked."""
    return {"account": account, "provider": provider_name, "failed": failed, "reason": str(reason)}


def reply(hosts, unknown, listed, unused):
    return {"hosts": hosts, "unknown": unknown, "listed": listed, "unused": unused}


def _tag(short):
    return f"@{short}" if short else None


def _budget(text):
    if text is None:
        return WITHIN
    try:
        seconds = float(text)
    except ValueError:
        seconds = math.nan
    if not math.isfinite(seconds) or seconds <= 0:
        raise DriverError(USAGE, f"--within takes a positive number of seconds, not {text!r}")
    return seconds


def _fate(ctx, error):
    """What became of an account whose list raised, decided there: `time`
    when the call was not started for the budget (Spent), or ended only
    when the budget did; else an ordinary `listing` failure."""
    left = ctx.remaining()
    return "time" if isinstance(error, Spent) or (left is not None and left <= 0) else "listing"


def _cost(type_, created, now):
    """(spent, currency) at the type's list price, or (None, None) where the
    type holds no price that is a finite number of 0 or more, or the amount
    it comes to is no finite number (a price or an age past a float's range,
    a product that overflows): one host's cost not represented, never a
    reply its reader must discard."""
    price = (type_ or {}).get("hourly_price")
    if isinstance(price, bool) or not isinstance(price, (int, float)):
        return None, None
    try:
        price = float(price)
        spent = ops.spent({"hourly_price": price}, created, now)
    except OverflowError:
        return None, None
    if not (math.isfinite(price) and price >= 0 and math.isfinite(spent)):
        return None, None
    currency = type_.get("currency")
    return spent, currency if isinstance(currency, str) else None


def _prices(client, location):
    """The location's types by name, or none where the list could not be
    read: a failed call, a provider that cannot be started, or a row whose
    `type` is not a name (the client takes any value under the key)."""
    try:
        rows = client.types(location)
    except (DriverError, OSError):
        return {}
    if not all(isinstance(t["type"], str) for t in rows):
        return {}
    return {t["type"]: t for t in rows}


def run(ctx, names, within=None):
    budget = _budget(within)
    if not names:
        raise DriverError(USAGE, "info takes one or more host names")
    asked = {name.lower() for name in names}
    found, unknown, listed, unused, hosts = [], [], [], [], []
    with ctx.bounded(budget):
        for account in ctx.profile.accounts.values():
            try:
                client = ctx.client(account)
            except (DriverError, OSError) as error:     # an OSError: a pass record or a copy that cannot be read
                if provider.never_passed(ctx.paths.profile, account, ctx.profile.accounts):
                    unused.append(account.name)
                    ctx.warn(f"devcloud vm info: account {account.name} not asked: its provider never passed "
                             f"under this profile")
                else:
                    unknown.append(missing(account.name, account.provider, "account", error))
                continue
            try:
                entries = ctx.fleet_of(account, client, kinds=None)
            except (DriverError, OSError) as error:     # an OSError: a provider that cannot be started
                unknown.append(missing(account.name, account.provider, _fate(ctx, error), error))
                continue
            listed.append(account.name)
            found += [e for e in entries if e.vm["name"].lower() in asked]
        now = ctx.clock()
        types = {}
        for e in found:
            key = (e.account.name, e.vm["location"])
            if key not in types:
                types[key] = _prices(e.client, e.vm["location"])
            spent, currency = _cost(types[key].get(e.vm["type"]), e.vm["created"], now)
            hosts.append(provider_host(e.vm["name"], e.account.name, e.account.provider,
                                       e.vm["labels"].get("devcloud-creator"), e.vm["created"], spent, currency))
    try:
        records = adopt.records(ctx)
    except DriverError as error:
        records = []
        unknown.append(missing("adopted", None, "listing", error))
    hosts += [adopted_host(r.name, r.creator) for r in records if r.name.lower() in asked]
    ctx.say(json.dumps(reply(hosts, unknown, listed, unused)))
    return 0
