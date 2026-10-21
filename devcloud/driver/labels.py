"""The labels every provider resource carries (I14). Keys and values are
`[a-z0-9-]`, at most 63 characters; the core refuses any other label before a
provider is called, since a provider stores labels verbatim and the reaper's
safety rests on them."""

import re

from .errors import FAILED, DriverError

_WORD = r"[a-z0-9-]{1,63}"
ALLOWED = {
    "devcloud": r"vm|image|builder|test",
    "devcloud-lifetime": r"ttl|keep",
    "devcloud-expires": r"[0-9]{1,12}",
    "devcloud-by": _WORD,
    "devcloud-creator": _WORD,
    "devcloud-recipe": r"[0-9a-f]{12}",
    "devcloud-confirmed": r"1",
    "devcloud-enroll": r"key|code",
    "devcloud-held": r"1",
    "devcloud-bake": r"failed-[a-z0-9-]{1,56}",
    "devcloud-test": _WORD,
}
_PATTERNS = {key: re.compile(rf"(?:{value})\Z") for key, value in ALLOWED.items()}


def check(labels):
    """Raises (exit 1: a bug in the driver) unless every label is one I14
    allows, the devcloud label among them."""
    if "devcloud" not in labels:
        raise DriverError(FAILED, "a bug: a resource without the devcloud label")
    for key, value in labels.items():
        pattern = _PATTERNS.get(key)
        if pattern is None or not isinstance(value, str) or not pattern.match(value):
            raise DriverError(FAILED, f"a bug: label {key}={value!r} is outside I14's set")


def machine(hostname):
    """A machine's name as a label value: its first DNS label, lowercased,
    every other character a hyphen."""
    first = hostname.split(".")[0].lower()
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9-]", "-", first)).strip("-")[:63] or "unknown"
