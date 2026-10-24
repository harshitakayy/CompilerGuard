"""Independent reference recogniser for CG-Lang (differential-testing oracle).

This module re-implements the *documented* CG-Lang contract using different
techniques from the compiler under test: a regular-expression scanner and an
iterative pushdown state machine instead of a hand-written lexer and
recursive-descent parser. Disagreement between the compiler and the oracle on
any input is reported as a *potential* compiler bug (it may equally be an
oracle bug, so it always requires investigation).

Phase ordering mirrors the compiler: the whole input is scanned first
(lexical errors), then parsed (syntax errors), then checked for undefined
variables (semantic errors). Only the first error is reported.
"""

import bisect
import re

from compiler.parser import MAX_NESTING_DEPTH

_TOKEN_RE = re.compile(
    r"""
      (?P<WS>[ \t\r\n]+)
    | (?P<NUMBER>[0-9]+)
    | (?P<WORD>[A-Za-z_][A-Za-z0-9_]*)
    | (?P<OP2>==|!=|<=|>=)
    | (?P<CH>[-+*/()=;<>{}])
    """,
    re.VERBOSE,
)

_KEYWORDS = {"if", "else", "while"}
_BINOPS = set("+-*/")


def _position(line_starts, offset):
    index = bisect.bisect_right(line_starts, offset) - 1
    return index + 1, offset - line_starts[index] + 1


def _fail(error_type, position, message):
    line, column = position
    return {
        "status": "FAIL",
        "type": error_type,
        "line": line,
        "column": column,
        "message": message,
    }


def reference_check(source):
    """Return an oracle verdict in the same shape as ``compile_code``."""
    line_starts = [0] + [i + 1 for i, ch in enumerate(source) if ch == "\n"]

    # Phase 1: scan.
    tokens = []  # (kind, text, (line, column))
    pos = 0
    while pos < len(source):
        match = _TOKEN_RE.match(source, pos)
        if match is None:
            return _fail(
                "LEXICAL_ERROR",
                _position(line_starts, pos),
                f"oracle: character {source[pos]!r} is not part of CG-Lang",
            )
        group, text = match.lastgroup, match.group()
        where = _position(line_starts, pos)
        pos = match.end()
        if group == "WS":
            continue
        if group == "NUMBER":
            kind = "NUMBER"
        elif group == "WORD":
            kind = "OTHER" if text in _KEYWORDS else "ID"
        elif group == "OP2":
            kind = "OTHER"
        elif text in _BINOPS:
            kind = "BINOP"
        elif text == "(":
            kind = "LPAREN"
        elif text == ")":
            kind = "RPAREN"
        elif text == "=":
            kind = "ASSIGN"
        elif text == ";":
            kind = "SEMI"
        else:
            kind = "OTHER"
        tokens.append((kind, text, where))
    tokens.append(("EOF", None, _position(line_starts, len(source))))

    # Phase 2: iterative pushdown recognition.
    state = "START"
    depth = 0
    target = None
    uses = []
    statements = []
    for kind, text, where in tokens:
        error = None
        if state == "START":
            if kind == "EOF":
                break
            if kind == "ID":
                target, uses, state = text, [], "ASSIGN"
            else:
                error = "expected an identifier"
        elif state == "ASSIGN":
            if kind == "ASSIGN":
                state = "OPERAND"
            else:
                error = "expected '='"
        elif state == "OPERAND":
            if kind == "NUMBER":
                state = "OPERATOR"
            elif kind == "ID":
                uses.append((text, where))
                state = "OPERATOR"
            elif kind == "LPAREN":
                depth += 1
                if depth > MAX_NESTING_DEPTH:
                    error = "nesting limit exceeded"
            else:
                error = "expected an operand"
        else:  # OPERATOR
            if kind == "BINOP":
                state = "OPERAND"
            elif kind == "RPAREN":
                if depth > 0:
                    depth -= 1
                else:
                    error = "unmatched ')'"
            elif kind == "SEMI":
                if depth == 0:
                    statements.append((target, uses))
                    state = "START"
                else:
                    error = "unclosed '('"
            else:
                error = "expected an operator, ')' or ';'"
        if error:
            return _fail("SYNTAX_ERROR", where, f"oracle: {error}")

    # Phase 3: definitions must precede uses.
    declared = set()
    for name, name_uses in statements:
        for used, where in name_uses:
            if used not in declared:
                return _fail(
                    "SEMANTIC_ERROR", where, f"oracle: '{used}' used before assignment"
                )
        declared.add(name)
    return {"status": "PASS"}


def compare_to_oracle(compiler_response, oracle_response):
    """Return a list of disagreement reasons (empty when they agree)."""
    reasons = []
    if compiler_response.get("type") == "INTERNAL_ERROR":
        reasons.append("INTERNAL_ERROR")
    if compiler_response["status"] != oracle_response["status"]:
        reasons.append("STATUS_MISMATCH")
        return reasons
    if compiler_response["status"] == "FAIL":
        if compiler_response.get("type") != oracle_response.get("type"):
            if "INTERNAL_ERROR" not in reasons:
                reasons.append("TYPE_MISMATCH")
        elif (
            compiler_response.get("line"),
            compiler_response.get("column"),
        ) != (oracle_response.get("line"), oracle_response.get("column")):
            reasons.append("LOCATION_MISMATCH")
    return reasons
