"""Lexical analysis for CG-Lang.

The lexer converts source text into a flat list of :class:`Token` objects,
each carrying a 1-based line and column. CG-Lang is an ASCII-only language:
identifiers are ``[A-Za-z_][A-Za-z0-9_]*`` and numbers are ``[0-9]+``.
Any other character (including non-ASCII letters or digits) is a lexical
error.

Some token types (braces, comparison operators and the ``if``/``else``/
``while`` keywords) are recognised so that the lexer is ready for future
grammar extensions, but the current grammar does not accept them. A program
that contains them is rejected by the parser with a syntax error.

Note: this module deliberately avoids importing the standard library modules
that depend on the stdlib ``ast`` module, because this package contains its
own ``ast.py``.
"""


class LexerError(Exception):
    """Raised when the source contains a character CG-Lang cannot tokenize."""

    def __init__(self, message, line, column):
        self.message = message
        self.line = line
        self.column = column
        super().__init__(message)


class Token:
    """A lexical token with its source position (1-based line and column)."""

    __slots__ = ("type", "value", "line", "column")

    def __init__(self, type_, value, line, column):
        self.type = type_
        self.value = value
        self.line = line
        self.column = column

    def __repr__(self):
        return (
            f"Token({self.type}, {self.value!r}, "
            f"line={self.line}, col={self.column})"
        )

    def to_dict(self):
        return {
            "type": self.type,
            "value": self.value,
            "line": self.line,
            "column": self.column,
        }


SINGLE_CHAR_TOKENS = {
    "+": "PLUS",
    "-": "MINUS",
    "*": "MULTIPLY",
    "/": "DIVIDE",
    "(": "LPAREN",
    ")": "RPAREN",
    ";": "SEMICOLON",
    "{": "LBRACE",
    "}": "RBRACE",
}

KEYWORDS = {
    "if": "IF",
    "else": "ELSE",
    "while": "WHILE",
}

# Token types that the lexer produces but the current grammar does not accept.
RESERVED_TOKEN_TYPES = frozenset(
    {"LBRACE", "RBRACE", "EQ", "NEQ", "LT", "GT", "LTE", "GTE",
     "IF", "ELSE", "WHILE"}
)

WHITESPACE = " \t\n\r"


def _is_digit(char):
    return "0" <= char <= "9"


def _is_ident_start(char):
    return ("a" <= char <= "z") or ("A" <= char <= "Z") or char == "_"


def _is_ident_part(char):
    return _is_ident_start(char) or _is_digit(char)


def _describe_char(char):
    """Printable characters are shown as-is; others are escaped."""
    if char.isprintable():
        return char
    return char.encode("unicode_escape").decode("ascii")


class Lexer:
    """Single-pass, hand-written scanner."""

    def __init__(self, source_code):
        self.source = source_code
        self.pos = 0
        self.line = 1
        self.column = 1
        self.tokens = []

    # -- cursor helpers -------------------------------------------------
    def current_char(self):
        if self.pos < len(self.source):
            return self.source[self.pos]
        return None

    def peek(self):
        """Return the next character without consuming anything."""
        peek_pos = self.pos + 1
        if peek_pos < len(self.source):
            return self.source[peek_pos]
        return None

    def advance(self):
        """Consume one character, updating line/column bookkeeping."""
        char = self.current_char()
        if char == "\n":
            self.line += 1
            self.column = 1
        else:
            self.column += 1
        self.pos += 1

    def skip_whitespace(self):
        while self.current_char() is not None and self.current_char() in WHITESPACE:
            self.advance()

    # -- token readers --------------------------------------------------
    def read_number(self):
        start_line, start_col = self.line, self.column
        digits = ""
        while self.current_char() is not None and _is_digit(self.current_char()):
            digits += self.current_char()
            self.advance()
        return Token("NUMBER", digits, start_line, start_col)

    def read_identifier(self):
        start_line, start_col = self.line, self.column
        name = ""
        while self.current_char() is not None and _is_ident_part(self.current_char()):
            name += self.current_char()
            self.advance()
        if name in KEYWORDS:
            return Token(KEYWORDS[name], name, start_line, start_col)
        return Token("ID", name, start_line, start_col)

    def read_operator_or_comparison(self):
        start_line, start_col = self.line, self.column
        char = self.current_char()
        nxt = self.peek()

        two_char = {"==": "EQ", "!=": "NEQ", "<=": "LTE", ">=": "GTE"}
        if nxt is not None and (char + nxt) in two_char:
            self.advance()
            self.advance()
            return Token(two_char[char + nxt], char + nxt, start_line, start_col)

        one_char = {"=": "ASSIGN", "<": "LT", ">": "GT"}
        if char in one_char:
            self.advance()
            return Token(one_char[char], char, start_line, start_col)

        # A lone '!' is not a valid token.
        raise LexerError(
            f"Unexpected character '{_describe_char(char)}'", start_line, start_col
        )

    # -- main entry point -----------------------------------------------
    def tokenize(self):
        """Scan the whole source and return the token list (ending in EOF)."""
        self.pos = 0
        self.line = 1
        self.column = 1
        self.tokens = []

        while self.current_char() is not None:
            char = self.current_char()

            if char in WHITESPACE:
                self.skip_whitespace()
            elif _is_digit(char):
                self.tokens.append(self.read_number())
            elif _is_ident_start(char):
                self.tokens.append(self.read_identifier())
            elif char in ("=", "!", "<", ">"):
                self.tokens.append(self.read_operator_or_comparison())
            elif char in SINGLE_CHAR_TOKENS:
                start_line, start_col = self.line, self.column
                self.advance()
                self.tokens.append(
                    Token(SINGLE_CHAR_TOKENS[char], char, start_line, start_col)
                )
            else:
                raise LexerError(
                    f"Unexpected character '{_describe_char(char)}'",
                    self.line,
                    self.column,
                )

        self.tokens.append(Token("EOF", None, self.line, self.column))
        return self.tokens
