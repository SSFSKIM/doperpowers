"""Bearer tokens and the sessions they resolve to."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

MEMBER = "member"
ADMIN = "admin"


@dataclass(frozen=True)
class Session:
    user: str
    tenant: str
    role: str


# Stand-in for the identity service; swapped out in deployment.
TOKENS: Dict[str, Session] = {
    "tok-ana": Session(user="ana", tenant="acme", role=MEMBER),
    "tok-rex": Session(user="rex", tenant="acme", role=ADMIN),
    "tok-ines": Session(user="ines", tenant="globex", role=MEMBER),
}


def bearer_token(headers: Dict[str, str]) -> Optional[str]:
    """Pull the bearer token out of an Authorization header, if there is one."""
    for key in ("Authorization", "authorization"):
        raw = headers.get(key)
        if raw:
            break
    else:
        return None

    parts = raw.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    return token or None


def session_for(token: Optional[str]) -> Optional[Session]:
    """Resolve a token to a session, or None when the token is not ours."""
    if token is None:
        return None
    return TOKENS.get(token)
