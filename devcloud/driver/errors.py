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


class NotOwned(DriverError):
    """The ownership gate refused a delete or a relabel: the target, read
    again right before, no longer carries what the decision was made on."""

    def __init__(self, message):
        super().__init__(FAILED, message)


class Spent(DriverError):
    """A bounded run's time is spent: no new provider call starts."""

    def __init__(self, message="the bounded run's time is spent"):
        super().__init__(FAILED, message)
