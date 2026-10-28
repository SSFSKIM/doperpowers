"""VM names (§3 step 2): `<prefix><label>-<4 hex>`, the prefix the profile's
(`[desk] name_prefix`, `dc-` by default: the devcloud delegation's), drawn
again until no live server in any account, adoption record, tailnet node or
desk machine has it."""

import re

from .errors import USAGE, DriverError

LABEL = re.compile(r"[a-z0-9-]{1,20}\Z")


def check_label(label):
    if not LABEL.match(label):
        raise DriverError(USAGE, f"--label {label!r} is not 1-20 of a-z, 0-9 and -")
    return label


def draw(label, taken, token_hex, prefix, tries=64):
    for _ in range(tries):
        name = f"{prefix}{label}-{token_hex()}"
        if name not in taken:
            return name
    raise DriverError(USAGE, f"no free name for label {label} after {tries} draws")
