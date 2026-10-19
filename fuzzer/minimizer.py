"""Test-case minimisation: shrinks a failing program to a minimal reproducer.

Three passes, each keeping a candidate only if the bug still reproduces (`pred`):
  1. remove whole statements / unwrap if-while blocks (structure-aware)
  2. classic delta debugging (ddmin) on tokens
  3. final whitespace normalisation
Uses its own tolerant tokenizer, so programs with illegal characters can be minimised too.
"""
import re

KEYWORDS = {"if", "else", "while", "print"}
TOK = re.compile(r"#[^\n]*|\d+(?:\.\d+)?|[A-Za-z_][A-Za-z0-9_]*|==|!=|<=|>=|\S")


def tokens_of(src):
    return [t for t in TOK.findall(src) if not t.startswith("#")]


def join(toks):
    return " ".join(toks) + "\n"


def _match(toks, i):
    depth = 0
    for j in range(i, len(toks)):
        if toks[j] == "{":
            depth += 1
        elif toks[j] == "}":
            depth -= 1
            if depth == 0:
                return j
    return len(toks) - 1


def _stmt_end(toks, i):
    if toks[i] in ("if", "while"):
        try:
            b = toks.index("{", i)
        except ValueError:
            return len(toks) - 1
        e = _match(toks, b)
        if e + 2 < len(toks) and toks[e + 1] == "else" and toks[e + 2] == "{":
            e = _match(toks, e + 2)
        return e
    for j in range(i, len(toks)):
        if toks[j] == ";":
            return j
    return len(toks) - 1


def _spans(toks, lo, hi, out):
    i = lo
    while i < hi:
        e = min(_stmt_end(toks, i), hi - 1)
        out.append((i, e))
        if toks[i] in ("if", "while") and "{" in toks[i:e + 1]:
            b = toks.index("{", i)
            _spans(toks, b + 1, _match(toks, b), out)
        i = e + 1
    return out


def ddmin(items, pred, max_calls=3000):
    calls = [0]

    def test(x):
        calls[0] += 1
        return calls[0] <= max_calls and len(x) > 0 and pred(x)

    n = 2
    while len(items) >= 2:
        size = max(1, -(-len(items) // n))
        parts = [items[i:i + size] for i in range(0, len(items), size)]
        reduced = False
        for i in range(len(parts)):
            comp = [t for j, p in enumerate(parts) if j != i for t in p]
            if test(comp):
                items, n, reduced = comp, max(n - 1, 2), True
                break
        if not reduced:
            if n >= len(items):
                break
            n = min(len(items), n * 2)
    return items


def minimize(source, reproduces):
    """`reproduces(src) -> bool`. Returns the smallest program found that still reproduces."""
    def ok(toks):
        try:
            return reproduces(join(toks))
        except Exception:
            return False

    toks = tokens_of(source)
    if not ok(toks):
        return source.strip()
    progress = True
    while progress:                                     # pass 1: structure-aware
        progress = False
        for (a, b) in sorted(_spans(toks, 0, len(toks), []), key=lambda s: s[0] - s[1]):
            cands = [toks[:a] + toks[b + 1:]]
            if toks[a] in ("if", "while") and b > a and toks[b] == "}" and "{" in toks[a:b]:
                b1 = toks.index("{", a)
                e1 = _match(toks, b1)
                if e1 == b:                             # no else: keep only the body
                    cands.append(toks[:a] + toks[b1 + 1:b] + toks[b + 1:])
                elif toks[e1 + 1:e1 + 3] == ["else", "{"]:   # keep only then-branch / only else-branch
                    cands.append(toks[:a] + toks[b1 + 1:e1] + toks[b + 1:])
                    cands.append(toks[:a] + toks[e1 + 3:b] + toks[b + 1:])
            for c in cands:
                if len(c) < len(toks) and ok(c):
                    toks, progress = c, True
                    break
            if progress:
                break
    for i in range(len(toks)):                           # pass 1b: simplify identifiers / numbers
        t = toks[i]
        is_target = i + 1 < len(toks) and toks[i + 1] == "="
        if (re.fullmatch(r"[A-Za-z_]\w*", t) and t not in KEYWORDS and not is_target) or \
                (re.fullmatch(r"\d+\.\d+|\d{2,}", t)):
            c = toks[:i] + ["1"] + toks[i + 1:]
            if ok(c):
                toks = c
    toks = ddmin(toks, ok)                               # pass 2: token-level ddmin
    return join(toks).strip()
