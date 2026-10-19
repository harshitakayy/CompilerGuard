class CompilerError(Exception):
    """Structured compiler error (every *expected* failure uses this class).

    Anything else that escapes the compiler is an *unexpected* crash and is
    reported by the fuzzer as a real bug.
    """

    def __init__(self, error_type, message, line=0, col=0):
        super().__init__(message)
        self.error_type = error_type
        self.message = message
        self.line = line
        self.col = col
