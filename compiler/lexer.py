"""Lexer for CG-Lang."""
from dataclasses import dataclass
from .errors import CompilerError

DIGITS = "0123456789"
ID_START = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_"
ID_PART = ID_START + DIGITS
KEYWORDS = {"if": "IF", "else": "ELSE", "while": "WHILE", "print": "PRINT"}
SINGLE = {
    "+": "PLUS", "-": "MINUS", "*": "STAR", "/": "SLASH", "%": "PERCENT",
    "(": "LPAREN", ")": "RPAREN", "{": "LBRACE", "}": "RBRACE",
    ";": "SEMICOLON", "=": "ASSIGN", "<": "LT", ">": "GT",
}
DOUBLE = {"==": "EQ", "!=": "NE", "<=": "LE", ">=": "GE"}
MAX_DIGITS = 18


@dataclass
class Token:
    type: str
    text: str
    line: int = 0
    col: int = 0
    value: object = None


def tokenize(src, cov=None):
    cov = cov if cov is not None else set()
    tokens, i, n = [], 0, len(src)
    line, col = 1, 1
    while i < n:
        c = src[i]
        if c == "\n":
            i += 1; line += 1; col = 1
            continue
        if c in " \t\r":
            i += 1; col += 1
            continue
        if c == "#":
            cov.add("lex:comment")
            while i < n and src[i] != "\n":
                i += 1
            continue
        start, scol = i, col
        if c in DIGITS:
            j = i
            while j < n and src[j] in DIGITS:
                j += 1
            is_float = False
            if j < n and src[j] == ".":
                k = j + 1
                if k >= n or src[k] not in DIGITS:
                    raise CompilerError("LEXICAL_ERROR", "Malformed number literal", line, scol)
                while k < n and src[k] in DIGITS:
                    k += 1
                j, is_float = k, True
            if j < n and (src[j] == "." or src[j] in ID_START):
                raise CompilerError("LEXICAL_ERROR", "Malformed number literal", line, scol)
            text = src[start:j]
            if len(text.replace(".", "")) > MAX_DIGITS:
                raise CompilerError("LEXICAL_ERROR", "Number literal too large", line, scol)
            cov.add("lex:float" if is_float else "lex:int")
            tokens.append(Token("NUMBER", text, line, scol, float(text) if is_float else int(text)))
            col += j - i; i = j
            continue
        if c in ID_START:
            j = i
            while j < n and src[j] in ID_PART:
                j += 1
            text = src[i:j]
            ttype = KEYWORDS.get(text, "IDENT")
            cov.add("lex:" + ("keyword" if ttype != "IDENT" else "ident"))
            tokens.append(Token(ttype, text, line, scol))
            col += j - i; i = j
            continue
        two = src[i:i + 2]
        if two in DOUBLE:
            tokens.append(Token(DOUBLE[two], two, line, scol))
            cov.add("lex:op2")
            i += 2; col += 2
            continue
        if c in SINGLE:
            tokens.append(Token(SINGLE[c], c, line, scol))
            cov.add("lex:op1")
            i += 1; col += 1
            continue
        raise CompilerError("LEXICAL_ERROR", "Illegal character %r" % c, line, scol)
    tokens.append(Token("EOF", "", line, col))
    return tokens
