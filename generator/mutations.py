"""Token-level mutation operators that turn valid programs into (mostly) invalid ones.

Each operator returns (new_tokens, must_fail). `must_fail=True` means the mutant is GUARANTEED
invalid by construction, so a compiler that accepts it has a false-accept bug.
Neutral operators (must_fail=False) may or may not stay valid; they probe robustness.
"""
import random
from compiler.lexer import tokenize, Token
from compiler.errors import CompilerError

ILLEGAL = list("@$?`~!^&|\\")
OPS_NO_MINUS = ["+", "*", "/", "%"]
ALL_BIN = ["+", "-", "*", "/", "%"]
TYPES = {"+": "PLUS", "-": "MINUS", "*": "STAR", "/": "SLASH", "%": "PERCENT"}


def lex_tokens(src):
    return [t for t in tokenize(src) if t.type != "EOF"]


def render(tokens):
    lines, cur_line, cur = [], None, []
    for t in tokens:
        if cur_line is None or t.line != cur_line:
            if cur:
                lines.append(" ".join(cur))
            cur, cur_line = [], t.line
        cur.append(t.text)
    if cur:
        lines.append(" ".join(cur))
    return "\n".join(lines) + "\n"


def _idx(toks, pred):
    return [i for i, t in enumerate(toks) if pred(t)]


def _tok(ttype, text, near):
    return Token(ttype, text, near.line if near else 1, 0)


# ---------------- operators that GUARANTEE an invalid program ----------------
def drop_semicolon(toks, rng):
    ix = _idx(toks, lambda t: t.type == "SEMICOLON")
    if not ix: return None
    i = rng.choice(ix); return toks[:i] + toks[i + 1:], True


def drop_rparen(toks, rng):
    ix = _idx(toks, lambda t: t.type == "RPAREN")
    if not ix: return None
    i = rng.choice(ix); return toks[:i] + toks[i + 1:], True


def drop_lparen(toks, rng):
    ix = _idx(toks, lambda t: t.type == "LPAREN")
    if not ix: return None
    i = rng.choice(ix); return toks[:i] + toks[i + 1:], True


def drop_brace(toks, rng):
    ix = _idx(toks, lambda t: t.type in ("LBRACE", "RBRACE"))
    if not ix: return None
    i = rng.choice(ix); return toks[:i] + toks[i + 1:], True


def stray_operator(toks, rng):
    ix = _idx(toks, lambda t: t.type == "SEMICOLON")
    if not ix: return None
    i = rng.choice(ix); op = rng.choice(ALL_BIN)
    return toks[:i] + [_tok(TYPES[op], op, toks[i])] + toks[i:], True


def double_operator(toks, rng):
    ix = _idx(toks, lambda t: t.type in ("PLUS", "STAR", "SLASH", "PERCENT"))
    if not ix: return None
    i = rng.choice(ix); return toks[:i + 1] + [toks[i]] + toks[i + 1:], True


def missing_operand(toks, rng):
    ix = [i for i in _idx(toks, lambda t: t.type == "ASSIGN")
          if i + 2 < len(toks) and toks[i + 1].type in ("NUMBER", "IDENT")]
    if not ix: return None
    i = rng.choice(ix) + 1
    out = toks[:i] + toks[i + 1:]
    return out, out[i].type != "MINUS"        # '= - 2' would still be valid


def illegal_char(toks, rng):
    if not toks: return None
    i = rng.randrange(len(toks) + 1); ch = rng.choice(ILLEGAL)
    near = toks[min(i, len(toks) - 1)]
    return toks[:i] + [_tok("ILLEGAL", ch, near)] + toks[i:], True


def keyword_typo(toks, rng):
    ix = _idx(toks, lambda t: t.type in ("IF", "WHILE", "PRINT"))
    if not ix: return None
    i = rng.choice(ix); t = toks[i]
    typo = rng.choice([t.text.upper(), t.text[:-1], t.text + t.text[-1], t.text[::-1]])
    return toks[:i] + [Token("IDENT", typo, t.line, 0)] + toks[i + 1:], True


def drop_else(toks, rng):
    ix = _idx(toks, lambda t: t.type == "ELSE")
    if not ix: return None
    i = rng.choice(ix); return toks[:i] + toks[i + 1:], True


def undefined_var(toks, rng):
    ix = [i for i, t in enumerate(toks) if t.type == "IDENT"
          and not (i + 1 < len(toks) and toks[i + 1].type == "ASSIGN")]
    if not ix: return None
    i = rng.choice(ix); t = toks[i]
    return toks[:i] + [Token("IDENT", "undef_%d" % rng.randint(1, 99), t.line, 0)] + toks[i + 1:], True


def div_by_zero(toks, rng):
    ix = [i + 1 for i in _idx(toks, lambda t: t.type in ("SLASH", "PERCENT"))
          if i + 1 < len(toks) and toks[i + 1].type == "NUMBER"]
    if not ix: return None
    i = rng.choice(ix)
    return toks[:i] + [Token("NUMBER", rng.choice(["0", "0.0"]), toks[i].line, 0)] + toks[i + 1:], True


def drop_assign(toks, rng):
    ix = _idx(toks, lambda t: t.type == "ASSIGN")
    if not ix: return None
    i = rng.choice(ix); return toks[:i] + toks[i + 1:], True


def double_assign(toks, rng):
    ix = _idx(toks, lambda t: t.type == "ASSIGN")
    if not ix: return None
    i = rng.choice(ix); return toks[:i + 1] + [toks[i]] + toks[i + 1:], True


def drop_relop(toks, rng):
    ix = _idx(toks, lambda t: t.type in ("LT", "GT", "LE", "GE", "EQ", "NE"))
    if not ix: return None
    i = rng.choice(ix); return toks[:i] + toks[i + 1:], True


def number_glued_to_ident(toks, rng):
    ix = _idx(toks, lambda t: t.type == "NUMBER" and "." not in t.text)
    if not ix: return None
    i = rng.choice(ix); t = toks[i]
    return toks[:i] + [Token("ILLEGAL", t.text + rng.choice(["abc", "x", "_1"]), t.line, 0)] + toks[i + 1:], True


# ---------------- neutral operators (may stay valid) ----------------
def swap_adjacent(toks, rng):
    if len(toks) < 2: return None
    i = rng.randrange(len(toks) - 1)
    t = list(toks); t[i], t[i + 1] = t[i + 1], t[i]; return t, False


def duplicate_token(toks, rng):
    if not toks: return None
    i = rng.randrange(len(toks)); return toks[:i + 1] + [toks[i]] + toks[i + 1:], False


def delete_token(toks, rng):
    if not toks: return None
    i = rng.randrange(len(toks)); return toks[:i] + toks[i + 1:], False


def replace_number(toks, rng):
    ix = _idx(toks, lambda t: t.type == "NUMBER")
    if not ix: return None
    i = rng.choice(ix); t = toks[i]
    new = rng.choice(["0", "1", "007", "999999999999999999", "1.5", "99999999999999999999"])
    return toks[:i] + [Token("NUMBER", new, t.line, 0)] + toks[i + 1:], False


def replace_operator(toks, rng):
    ix = _idx(toks, lambda t: t.type in TYPES.values())
    if not ix: return None
    i = rng.choice(ix); t = toks[i]; op = rng.choice(ALL_BIN)
    return toks[:i] + [Token(TYPES[op], op, t.line, 0)] + toks[i + 1:], False


MUTATIONS = {f.__name__: f for f in [
    drop_semicolon, drop_rparen, drop_lparen, drop_brace, stray_operator, double_operator,
    missing_operand, illegal_char, keyword_typo, drop_else, undefined_var, div_by_zero,
    drop_assign, double_assign, drop_relop, number_glued_to_ident,
    swap_adjacent, duplicate_token, delete_token, replace_number, replace_operator]}


def mutate(source, rng, count=1, ops=None):
    """Apply `count` random mutations. Returns dict(source, mutation, must_fail) or None."""
    try:
        toks = lex_tokens(source)
    except CompilerError:
        return None
    names, must_fail = [], False
    pool = list(ops or MUTATIONS)
    for step in range(count):
        for _ in range(12):                         # retry until an operator applies
            name = rng.choice(pool)
            res = MUTATIONS[name](toks, rng)
            if res is not None:
                toks, mf = res
                names.append(name)
                must_fail = mf if count == 1 else False   # stacking can accidentally repair
                break
    if not names:
        return None
    return {"source": render(toks), "mutation": "+".join(names), "must_fail": must_fail}
