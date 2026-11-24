import enum


class Role(str, enum.Enum):
    VIEWER = "viewer"     # read-only seat; contractors and auditors get this one
    MEMBER = "member"
    FINANCE = "finance"
    ADMIN = "admin"
