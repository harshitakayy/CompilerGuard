"""Independent reference implementation (the *test oracle*).

CG-Lang source is translated token-by-token to Python and executed in a sandbox.
It shares NO code with compiler/ (own tokenizer, own translator), so disagreement between
the two on a program that both accept points to a bug in one of them (differential testing).
"""
import re

TOKEN_RE = re.compile(
    r"\s+|#[^\n]*|(?P<num>\d+(?:\.\d+)?)|(?P<id>[A-Za-z_][A-Za-z0-9_]*)"
    r"|(?P<op>==|!=|<=|>=|[-+*/%()<>={};])")
EXPR_OPS = {"+", "-", "*", "/", "%", "(", ")", "<", ">", "<=", ">=", "==", "!="}
KEYWORDS = {"if", "else", "while", "print"}
MAX_STEPS = 200000
MAX_BITS = 10000


class RefReject(Exception):
    pass


class RefRuntime(Exception):
    pass


def _tokens(src):
    toks, pos = [], 0
    while pos < len(src):
        m = TOKEN_RE.match(src, pos)
        if not m:
            raise RefReject("bad character")
        pos = m.end()
        if m.lastgroup:
            toks.append((m.lastgroup, m.group(m.lastgroup)))
    return toks


def _expr(toks):
    if not toks:
        raise RefReject("empty expression")
    out = []
    for kind, v in toks:
        if kind == "num":
            out.append(repr(float(v)) if "." in v else repr(int(v)))
        elif kind == "id":
            if v in KEYWORDS:
                raise RefReject("keyword in expression")
            out.append("v_" + v)
        elif v in EXPR_OPS:
            out.append(v)
        else:
            raise RefReject("bad token in expression")
    return " ".join(out)


def transpile(src):
    toks, i, n = _tokens(src), 0, 0
    n = len(toks)
    lines, indent, stack = [], 0, []

    def emit(s):
        lines.append("    " * indent + s)

    def find(sym, start):
        for j in range(start, n):
            if toks[j][1] == sym and toks[j][0] == "op":
                return j
        raise RefReject("missing " + sym)

    def match_paren(start):          # toks[start] == '('
        depth = 0
        for j in range(start, n):
            if toks[j] == ("op", "("):
                depth += 1
            elif toks[j] == ("op", ")"):
                depth -= 1
                if depth == 0:
                    return j
        raise RefReject("unbalanced")

    while i < n:
        kind, v = toks[i]
        if kind == "id" and v == "print":
            j = find(";", i)
            emit("print_(%s)" % _expr(toks[i + 1:j]))
            i = j + 1
        elif kind == "id" and v in ("if", "while"):
            if i + 1 >= n or toks[i + 1] != ("op", "("):
                raise RefReject("expected (")
            j = match_paren(i + 1)
            if j + 1 >= n or toks[j + 1] != ("op", "{"):
                raise RefReject("expected {")
            emit("%s %s:" % (v, _expr(toks[i + 2:j])))
            indent += 1
            emit("pass")
            if v == "while":
                emit("_tick()")
            stack.append(v)
            i = j + 2
        elif kind == "op" and v == "}":
            if not stack:
                raise RefReject("unexpected }")
            stack.pop()
            indent -= 1
            if i + 2 < n and toks[i + 1] == ("id", "else") and toks[i + 2] == ("op", "{") \
                    and (not stack or True):
                emit("else:")
                indent += 1
                emit("pass")
                stack.append("else")
                i += 3
            else:
                i += 1
        elif kind == "id" and v not in KEYWORDS and i + 1 < n and toks[i + 1] == ("op", "="):
            j = find(";", i)
            emit("v_%s = %s" % (v, _expr(toks[i + 2:j])))
            i = j + 1
        else:
            raise RefReject("unexpected token %r" % v)
    if stack:
        raise RefReject("unclosed block")
    return "\n".join(lines) + "\n"


def run(src):
    """Return {'ok': bool, 'output': [...], 'error': str|None, 'kind': 'reject'|'runtime'|None}."""
    try:
        code = transpile(src)
        compiled = compile(code, "<ref>", "exec")
    except RefReject as e:
        return {"ok": False, "output": [], "error": str(e), "kind": "reject"}
    except (SyntaxError, RecursionError, MemoryError, ValueError, OverflowError) as e:
        return {"ok": False, "output": [], "error": "python rejects: " + type(e).__name__, "kind": "reject"}
    out, steps = [], [0]
    g = {"__builtins__": {}}

    def tick():
        steps[0] += 1
        if steps[0] > MAX_STEPS:
            raise RefRuntime("step limit")
        for k, val in g.items():
            if k.startswith("v_") and isinstance(val, int) and val.bit_length() > MAX_BITS:
                raise RefRuntime("overflow")

    def print_(v):
        if isinstance(v, int) and v.bit_length() > MAX_BITS:
            raise RefRuntime("overflow")
        out.append(str(v))

    g["print_"], g["_tick"] = print_, tick
    try:
        exec(compiled, g)
    except RefRuntime as e:
        return {"ok": False, "output": out, "error": str(e), "kind": "runtime"}
    except (ZeroDivisionError, NameError, TypeError, OverflowError, ValueError, RecursionError) as e:
        return {"ok": False, "output": out, "error": type(e).__name__, "kind": "runtime"}
    return {"ok": True, "output": out, "error": None, "kind": None}
