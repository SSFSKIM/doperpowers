"""What every module of the CLI shares: the way a verb ends."""

OK, FAILED, USAGE, REFUSED = 0, 1, 2, 3


class Stop(Exception):
    """End the verb with `code`, saying `message` on stderr (D4's exit
    codes: 1 failed, 2 usage, 3 refused by a rule of the board)."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def failed(message):
    return Stop(FAILED, message)


def usage(message):
    return Stop(USAGE, message)


def refused(message):
    return Stop(REFUSED, message)
