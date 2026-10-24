"""Generic lexer derived from a grammar's terminals and token classes."""

import bisect
import re
from collections import namedtuple

Tok = namedtuple("Tok", "kind text line col start end")
_ID = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_STRING = re.compile(r'"(?:[^"\\\n]|\\.)*"')
_CHAR = re.compile(r"'(?:[^'\\\n]|\\.)'")
_NUM_INT = re.compile(r"[0-9]+")
_NUM_FLOAT = re.compile(r"[0-9]+(?:\.[0-9]+)?")


class LexError(Exception):
    def __init__(self, message, line, col):
        super().__init__(message)
        self.message, self.line, self.col = message, line, col


class Lexer:
    def __init__(self, grammar):
        terms = set(grammar.terminals)
        self.words = {t for t in terms if _ID.fullmatch(t)}
        self.puncts = sorted(terms - self.words, key=lambda t: (-len(t), t))
        self.classes = set(grammar.classes)
        self.c_comments = grammar.options.get("comments") == "c"
        self.number = _NUM_INT if grammar.options.get("number") == "int" else _NUM_FLOAT

    def tokenize(self, src):
        starts = [0] + [i + 1 for i, c in enumerate(src) if c == "\n"]

        def pos(i):
            ln = bisect.bisect_right(starts, i) - 1
            return ln + 1, i - starts[ln] + 1

        out, i, n = [], 0, len(src)
        while i < n:
            ch = src[i]
            if ch in " \t\r\n":
                i += 1
                continue
            if self.c_comments:
                if src.startswith("//", i):
                    j = src.find("\n", i)
                    i = n if j < 0 else j
                    continue
                if src.startswith("/*", i):
                    j = src.find("*/", i + 2)
                    if j < 0:
                        raise LexError("Unterminated comment", *pos(i))
                    i = j + 2
                    continue
                if ch == "#" and not src[starts[bisect.bisect_right(starts, i) - 1]:i].strip():
                    j = src.find("\n", i)
                    i = n if j < 0 else j
                    continue
            m = None
            if ch == '"' and "STRING" in self.classes:
                m = _STRING.match(src, i)
                if not m:
                    raise LexError("Unterminated string literal", *pos(i))
                kind = "STRING"
            elif ch == "'" and "CHAR" in self.classes:
                m = _CHAR.match(src, i)
                if not m:
                    raise LexError("Malformed character literal", *pos(i))
                kind = "CHAR"
            elif ch.isdigit() and ch.isascii() and "NUMBER" in self.classes:
                m, kind = self.number.match(src, i), "NUMBER"
            elif _ID.match(src, i):
                m = _ID.match(src, i)
                kind = m.group() if m.group() in self.words else "ID"
                if kind == "ID" and "ID" not in self.classes:
                    raise LexError(f"Unexpected character '{ch}'", *pos(i))
            if m is None:
                for p in self.puncts:
                    if src.startswith(p, i):
                        line, col = pos(i)
                        out.append(Tok(p, p, line, col, i, i + len(p)))
                        i += len(p)
                        break
                else:
                    raise LexError(f"Unexpected character '{ch if ch.isprintable() else ch.encode('unicode_escape').decode()}'", *pos(i))
                continue
            line, col = pos(i)
            out.append(Tok(kind, m.group(), line, col, i, m.end()))
            i = m.end()
        line, col = pos(n)
        out.append(Tok("EOF", "", line, col, n, n))
        return out
