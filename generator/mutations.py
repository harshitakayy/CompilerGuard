"""Controlled mutation of valid CG-Lang programs into invalid ones.

Each mutation operator edits the token stream of a valid program in a specific,
grammar-aware way and declares the error class it *intends* to cause
(lexical, syntax or semantic). The intent is only an expectation: the test
pipeline executes every mutant and compares the actual compiler result with
both the intent and an independent oracle, so an operator that accidentally
produces a valid program is detected rather than assumed to be invalid.

The module has no dependency on the compiler under test.
"""

import random
import re
from collections import namedtuple
from typing import Callable, Dict, List, Optional, Tuple

Span = namedtuple("Span", "kind start end text")

_SPAN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|[0-9]+|==|!=|<=|>=|\S")
_CANON = _SPAN_RE

BINOPS = ["+", "-", "*", "/"]
INVALID_CHARS = list("@#$%&^~?.:\"'\\`|,[]!")
UNICODE_CHARS = ["é", "²", "٣", "中", "＋", "\u00a0", "\u200b"]
UNSUPPORTED_OPERATORS = ["%", "^", "&", "|"]
RESERVED_TOKENS = ["if", "else", "while", "{", "}", "==", "!=", "<", ">", "<=", ">="]
FRESH_NAMES = ["ghost", "phantom", "unknown1", "undef_q", "w9", "missing"]


def canonical(code):
    return " ".join(_CANON.findall(code))


def _kind(text):
    if re.fullmatch(r"[0-9]+", text):
        return "NUMBER"
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", text):
        return "ID"
    return {
        "+": "BINOP", "-": "BINOP", "*": "BINOP", "/": "BINOP",
        "(": "LPAREN", ")": "RPAREN", "=": "ASSIGN", ";": "SEMI",
    }.get(text, "OTHER")


def spans_of(code):
    return [Span(_kind(m.group()), m.start(), m.end(), m.group()) for m in _SPAN_RE.finditer(code)]


def _replace(code, span, text):
    return code[: span.start] + text + code[span.end:]


def _insert_before(code, span, text):
    return code[: span.start] + f" {text} " + code[span.start:]


def _insert_after(code, span, text):
    return code[: span.end] + f" {text} " + code[span.end:]


def _of(spans, *kinds):
    return [s for s in spans if s.kind in kinds]


# -- operators: (code, spans, rng) -> Optional[str] ---------------------------

def _delete_semicolon(code, spans, rng):
    c = _of(spans, "SEMI")
    return _replace(code, rng.choice(c), "") if c else None


def _delete_assign(code, spans, rng):
    c = _of(spans, "ASSIGN")
    return _replace(code, rng.choice(c), "") if c else None


def _duplicate_assign(code, spans, rng):
    c = _of(spans, "ASSIGN")
    return _insert_after(code, rng.choice(c), "=") if c else None


def _insert_unary(code, spans, rng):
    c = [s for i, s in enumerate(spans) if s.kind in ("ASSIGN", "LPAREN")]
    return _insert_after(code, rng.choice(c), rng.choice(BINOPS)) if c else None


def _delete_operand_after_op(code, spans, rng):
    c = [spans[i + 1] for i, s in enumerate(spans[:-1])
         if s.kind == "BINOP" and spans[i + 1].kind in ("NUMBER", "ID")]
    return _replace(code, rng.choice(c), "") if c else None


def _delete_operand_before_op(code, spans, rng):
    c = [spans[i - 1] for i, s in enumerate(spans)
         if i > 0 and s.kind == "BINOP" and spans[i - 1].kind in ("NUMBER", "ID")]
    return _replace(code, rng.choice(c), "") if c else None


def _duplicate_binop(code, spans, rng):
    c = _of(spans, "BINOP")
    return _insert_after(code, rng.choice(c), rng.choice(BINOPS)) if c else None


def _trailing_operator(code, spans, rng):
    c = _of(spans, "SEMI")
    return _insert_before(code, rng.choice(c), rng.choice(BINOPS)) if c else None


def _delete_open_paren(code, spans, rng):
    c = _of(spans, "LPAREN")
    return _replace(code, rng.choice(c), "") if c else None


def _delete_close_paren(code, spans, rng):
    c = _of(spans, "RPAREN")
    return _replace(code, rng.choice(c), "") if c else None


def _extra_close_paren(code, spans, rng):
    c = _of(spans, "NUMBER", "ID", "RPAREN")
    # Skip assignment targets: "x ) = 1" is still invalid but uninteresting.
    c = [s for s in c if not (s.kind == "ID" and _is_target(spans, s))]
    return _insert_after(code, rng.choice(c), ")") if c else None


def _extra_open_paren(code, spans, rng):
    c = [s for s in _of(spans, "NUMBER", "ID") if not _is_target(spans, s)]
    return _insert_before(code, rng.choice(c), "(") if c else None


def _empty_parentheses(code, spans, rng):
    c = [s for s in _of(spans, "NUMBER", "ID") if not _is_target(spans, s)]
    return _replace(code, rng.choice(c), "()") if c else None


def _is_target(spans, span):
    idx = spans.index(span)
    return idx + 1 < len(spans) and spans[idx + 1].kind == "ASSIGN"


def _insert_reserved(code, spans, rng):
    if not spans:
        return None
    anchor = rng.choice(spans)
    token = rng.choice(RESERVED_TOKENS)
    return _insert_before(code, anchor, token) if rng.random() < 0.5 else _insert_after(code, anchor, token)


def _assign_to_number(code, spans, rng):
    c = [s for s in _of(spans, "ID") if _is_target(spans, s)]
    return _replace(code, rng.choice(c), str(rng.randint(0, 99))) if c else None


def _delete_target(code, spans, rng):
    c = [s for s in _of(spans, "ID") if _is_target(spans, s)]
    return _replace(code, rng.choice(c), "") if c else None


def _digit_leading_identifier(code, spans, rng):
    c = _of(spans, "ID")
    if not c:
        return None
    span = rng.choice(c)
    return _replace(code, span, str(rng.randint(1, 9)) + span.text)


def _adjacent_operands(code, spans, rng):
    c = [s for s in _of(spans, "NUMBER", "ID", "RPAREN") if not (s.kind == "ID" and _is_target(spans, s))]
    return _insert_after(code, rng.choice(c), rng.choice(["7", "v", "42"])) if c else None


def _truncate(code, spans, rng):
    c = [s for s in spans if s.kind != "SEMI"]
    return code[: rng.choice(c).end] if c else None


def _assign_to_operator(code, spans, rng):
    c = _of(spans, "ASSIGN")
    return _replace(code, rng.choice(c), rng.choice(BINOPS)) if c else None


def _double_semicolon(code, spans, rng):
    c = _of(spans, "SEMI")
    return _insert_after(code, rng.choice(c), ";") if c else None


def _operator_to_assign(code, spans, rng):
    c = _of(spans, "BINOP")
    return _replace(code, rng.choice(c), "=") if c else None


def _invalid_char(code, spans, rng):
    if not spans:
        return None
    anchor = rng.choice(spans)
    ch = rng.choice(INVALID_CHARS)
    return _insert_before(code, anchor, ch) if rng.random() < 0.5 else _insert_after(code, anchor, ch)


def _unicode_char(code, spans, rng):
    if not spans:
        return None
    return _insert_after(code, rng.choice(spans), rng.choice(UNICODE_CHARS))


def _decimal_literal(code, spans, rng):
    c = _of(spans, "NUMBER")
    return _replace(code, rng.choice(c), f"{rng.randint(0, 9)}.{rng.randint(1, 9)}") if c else None


def _unsupported_operator(code, spans, rng):
    c = _of(spans, "BINOP")
    return _replace(code, rng.choice(c), rng.choice(UNSUPPORTED_OPERATORS)) if c else None


SYNTAX_OPERATORS: Dict[str, Tuple[Callable, str]] = {
    "delete_semicolon": (_delete_semicolon, "SYNTAX_ERROR"),
    "delete_assign_operator": (_delete_assign, "SYNTAX_ERROR"),
    "duplicate_assign_operator": (_duplicate_assign, "SYNTAX_ERROR"),
    "insert_unary_operator": (_insert_unary, "SYNTAX_ERROR"),
    "delete_operand_after_operator": (_delete_operand_after_op, "SYNTAX_ERROR"),
    "delete_operand_before_operator": (_delete_operand_before_op, "SYNTAX_ERROR"),
    "duplicate_binary_operator": (_duplicate_binop, "SYNTAX_ERROR"),
    "trailing_operator": (_trailing_operator, "SYNTAX_ERROR"),
    "delete_open_paren": (_delete_open_paren, "SYNTAX_ERROR"),
    "delete_close_paren": (_delete_close_paren, "SYNTAX_ERROR"),
    "insert_extra_close_paren": (_extra_close_paren, "SYNTAX_ERROR"),
    "insert_extra_open_paren": (_extra_open_paren, "SYNTAX_ERROR"),
    "empty_parentheses": (_empty_parentheses, "SYNTAX_ERROR"),
    "insert_reserved_token": (_insert_reserved, "SYNTAX_ERROR"),
    "assign_to_number": (_assign_to_number, "SYNTAX_ERROR"),
    "delete_assignment_target": (_delete_target, "SYNTAX_ERROR"),
    "digit_leading_identifier": (_digit_leading_identifier, "SYNTAX_ERROR"),
    "adjacent_operands": (_adjacent_operands, "SYNTAX_ERROR"),
    "truncate_mid_statement": (_truncate, "SYNTAX_ERROR"),
    "replace_assign_with_operator": (_assign_to_operator, "SYNTAX_ERROR"),
    "double_semicolon": (_double_semicolon, "SYNTAX_ERROR"),
    "replace_operator_with_assign": (_operator_to_assign, "SYNTAX_ERROR"),
    "insert_invalid_char": (_invalid_char, "LEXICAL_ERROR"),
    "insert_unicode_char": (_unicode_char, "LEXICAL_ERROR"),
    "decimal_literal": (_decimal_literal, "LEXICAL_ERROR"),
    "unsupported_operator": (_unsupported_operator, "LEXICAL_ERROR"),
}


# -- semantic operators work on whole statements ------------------------------

def _statements(code) -> List[str]:
    return [s.strip() + ";" for s in code.split(";") if s.strip()]


def _target_and_uses(stmt):
    toks = [m.group() for m in _SPAN_RE.finditer(stmt)]
    ids = [t for t in toks if _kind(t) == "ID"]
    return (ids[0], ids[1:]) if ids else (None, [])


def _undefined_operand(code, spans, rng):
    c = [s for s in _of(spans, "NUMBER")]
    if not c:
        return None
    present = {s.text for s in spans}
    names = [n for n in FRESH_NAMES if n not in present]
    return _replace(code, rng.choice(c), rng.choice(names)) if names else None


def _self_reference_first(code, spans, rng):
    stmts = _statements(code)
    if not stmts:
        return None
    first = stmts[0]
    target, _ = _target_and_uses(first)
    numbers = [s for s in spans_of(first) if s.kind == "NUMBER"]  # token spans, not raw digits
    if not numbers:
        return None
    chosen = rng.choice(numbers)
    mutated = first[: chosen.start] + target + first[chosen.end:]
    return "\n".join([mutated] + stmts[1:])


def _use_before_definition(code, spans, rng):
    stmts = _statements(code)
    options = []
    for i in range(len(stmts) - 1):
        target, _ = _target_and_uses(stmts[i])
        earlier = {_target_and_uses(s)[0] for s in stmts[:i]}
        _, later_uses = _target_and_uses(stmts[i + 1])
        if target not in earlier and target in later_uses:
            options.append(i)
    if not options:
        return None
    i = rng.choice(options)
    stmts[i], stmts[i + 1] = stmts[i + 1], stmts[i]
    return "\n".join(stmts)


def _delete_defining_statement(code, spans, rng):
    stmts = _statements(code)
    options = []
    for j, stmt in enumerate(stmts):
        target, _ = _target_and_uses(stmt)
        if any(_target_and_uses(s)[0] == target for s in stmts[:j]):
            continue
        for k in range(j + 1, len(stmts)):
            t_k, uses_k = _target_and_uses(stmts[k])
            if target in uses_k:
                options.append(j)
                break
            if t_k == target:
                break
    if not options:
        return None
    j = rng.choice(options)
    return "\n".join(stmts[:j] + stmts[j + 1:])


SEMANTIC_OPERATORS: Dict[str, Tuple[Callable, str]] = {
    "undefined_variable_operand": (_undefined_operand, "SEMANTIC_ERROR"),
    "self_reference_first_assignment": (_self_reference_first, "SEMANTIC_ERROR"),
    "use_before_definition": (_use_before_definition, "SEMANTIC_ERROR"),
    "delete_defining_statement": (_delete_defining_statement, "SEMANTIC_ERROR"),
}


class MutationEngine:
    """Seeded, bounded, duplicate-free generation of mutant test records."""

    def __init__(self, seed: Optional[int] = None):
        if seed is None:
            seed = random.SystemRandom().randrange(2**32)
        self.seed = seed
        self.rng = random.Random(seed)
        self.shortfall = 0

    def mutate(self, code, operator_name):
        table = {**SYNTAX_OPERATORS, **SEMANTIC_OPERATORS}
        func, _ = table[operator_name]
        return func(code, spans_of(code), self.rng)

    def _generate(self, parents, count, operators, category, exclude):
        seen = set(exclude)
        names = list(operators)
        self.rng.shuffle(names)
        tests, attempts = [], 0
        limit = count * 40 + len(names) * 5
        while len(tests) < count and attempts < limit and parents:
            name = names[attempts % len(names)]
            attempts += 1
            parent = self.rng.choice(parents)
            func, intended = operators[name]
            mutated = func(parent["code"], spans_of(parent["code"]), self.rng)
            if mutated is None or mutated == parent["code"]:
                continue
            key = canonical(mutated)
            if key in seen:
                continue
            seen.add(key)
            tests.append(
                {
                    "category": category,
                    "source": "mutation",
                    "code": mutated,
                    "expected_status": "FAIL",
                    "expected_error_type": intended,
                    "expected_basis": "mutation_intent",
                    "provenance": {
                        "seed": self.seed,
                        "operator": name,
                        "parent_id": parent.get("id"),
                        "parent_code": parent["code"],
                    },
                }
            )
        self.shortfall += count - len(tests)
        return tests

    def generate(self, valid_tests, count, semantic_ratio=0.0, exclude=None):
        """Return ``count`` mutants (syntax/lexical plus a ``semantic_ratio``
        share of semantic ones), shuffled so any prefix keeps the mix."""
        parents = [t if isinstance(t, dict) else {"code": t} for t in valid_tests]
        exclude = set(exclude or ())
        exclude |= {canonical(p["code"]) for p in parents}
        semantic_count = round(count * semantic_ratio)
        semantic = self._generate(
            parents, semantic_count, SEMANTIC_OPERATORS, "invalid_semantic", exclude
        )
        exclude |= {canonical(t["code"]) for t in semantic}
        syntax = self._generate(
            parents, count - semantic_count, SYNTAX_OPERATORS, "invalid_syntax", exclude
        )
        tests = semantic + syntax
        self.rng.shuffle(tests)
        for index, test in enumerate(tests, 1):
            test["id"] = f"invalid-{index:03d}"
            test["provenance"]["index"] = index
        return tests


def generate_invalid_tests(valid_tests, count=10, seed=None, semantic_ratio=0.0, exclude=None):
    return MutationEngine(seed).generate(valid_tests, count, semantic_ratio, exclude)


def mutate_test(code, rng=None):
    """Return one randomly mutated version of ``code`` (or ``code`` itself
    if no operator applies)."""
    rng = rng or random.Random()
    names = list(SYNTAX_OPERATORS)
    rng.shuffle(names)
    for name in names:
        mutated = SYNTAX_OPERATORS[name][0](code, spans_of(code), rng)
        if mutated is not None and mutated != code:
            return mutated
    return code


if __name__ == "__main__":
    import sys

    if hasattr(sys.stdout, "reconfigure"):  # keep Windows consoles from choking on non-ASCII mutants
        sys.stdout.reconfigure(errors="backslashreplace")
    demo_parents = [
        {"id": "demo-1", "code": "x = 10 + 5;\ny = x * (2 - 1);"},
        {"id": "demo-2", "code": "a = (4 + 2) / 3;"},
    ]
    for t in generate_invalid_tests(demo_parents, 8, seed=1, semantic_ratio=0.25):
        print(f"--- {t['id']} [{t['provenance']['operator']}] -> intended {t['expected_error_type']}")
        print(t["code"])
