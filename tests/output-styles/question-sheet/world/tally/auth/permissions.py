"""Column-level read permissions.

A column listed in COLUMN_GRANTS is readable only by the roles named for it.
A column that is not listed is readable by every member of the account: the
grants are an allow-list of restrictions, added table by table as data turns
out to be sensitive (#140).
"""
from __future__ import annotations

from collections.abc import Iterable

from tally.auth.roles import Role

COLUMN_GRANTS: dict[str, dict[str, frozenset[Role]]] = {
    "invoices": {
        "total": frozenset({Role.FINANCE, Role.ADMIN}),
        "notes": frozenset({Role.FINANCE, Role.ADMIN}),
    },
    "invoice_lines": {
        "amount": frozenset({Role.FINANCE, Role.ADMIN}),
        "cost": frozenset({Role.ADMIN}),
    },
    "payments": {
        "method": frozenset({Role.FINANCE, Role.ADMIN}),
        "card_last4": frozenset({Role.FINANCE, Role.ADMIN}),
    },
    "users": {
        "email": frozenset({Role.MEMBER, Role.FINANCE, Role.ADMIN}),
        "last_login_ip": frozenset({Role.ADMIN}),
    },
    "usage_events": {
        "unit_price": frozenset({Role.MEMBER, Role.FINANCE, Role.ADMIN}),
    },
}


def can_read(role: Role, table: str, column: str) -> bool:
    grants = COLUMN_GRANTS.get(table, {})
    allowed = grants.get(column)
    return allowed is None or role in allowed


def readable_columns(role: Role, columns: Iterable[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    """The columns of `columns` the role may read, in their order."""
    return [c for c in columns if can_read(role, c[0], c[1])]
