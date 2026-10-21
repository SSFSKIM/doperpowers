"""Exit codes (I16) and the one error every command ends with."""

OK = 0
FAILED = 1      # the step named
USAGE = 2       # flags, host.toml, driver.toml
REFUSED = 3     # the provider refused, or a capability the request needs is missing
CAP = 4         # over a cap: needs --confirmed
GUARD = 5       # down guard: unpushed work
NOT_DRIVER = 6  # no seed key, or this machine is a devcloud host
UNUSABLE = 7    # the account's provider is not registered, or has no passing copy


class DriverError(Exception):
    """Ends a command with `code`; the message is one line, never a value."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
