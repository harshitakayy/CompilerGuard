"""Grammar-based generator of valid CG-Lang programs.

Programs are built from the grammar::

    program     -> statement*
    statement   -> IDENTIFIER '=' expression ';'
    expression  -> term (('+' | '-') term)*
    term        -> factor (('*' | '/') factor)*
    factor      -> NUMBER | IDENTIFIER | '(' expression ')'

Generation is deterministic for a given seed (a private ``random.Random`` is
used, never the global generator). Identifiers are only used after an earlier
statement has assigned them, so every generated program is expected to compile.
Parenthesis nesting is bounded by ``max_depth``.
"""

import random
import re
from typing import List, Optional

DEFAULT_VARIABLES = [
    "x", "y", "z", "a", "b", "c", "total", "count_1", "tmp", "result", "_v", "n2",
]
STYLES = ("spaced", "compact", "loose")

_CANON = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|[0-9]+|==|!=|<=|>=|\S")


def _canonical(code):
    return " ".join(_CANON.findall(code))


class GrammarGenerator:
    def __init__(
        self,
        seed: Optional[int] = None,
        max_depth: int = 3,
        max_statements: int = 5,
        max_operations: int = 2,
        variables: Optional[List[str]] = None,
    ):
        if seed is None:
            seed = random.SystemRandom().randrange(2**32)
        self.seed = seed
        self.rng = random.Random(seed)
        self.max_depth = max_depth
        self.max_statements = max_statements
        self.max_operations = max_operations
        self.variables = list(variables or DEFAULT_VARIABLES)
        self.shortfall = 0

    # -- token-level generation ----------------------------------------
    def _number(self, avoid_zero=False):
        roll = self.rng.random()
        if roll < 0.75:
            value = str(self.rng.randint(1 if avoid_zero else 0, 20))
        elif roll < 0.95:
            value = str(self.rng.randint(21, 99999))
        else:
            value = "00" + str(self.rng.randint(1, 9))  # leading zeros are legal
        return value

    def _factor(self, declared, depth, avoid_zero=False):
        choices = [("number", 0.45)]
        if declared:
            choices.append(("variable", 0.30))
        if depth < self.max_depth:
            choices.append(("group", 0.25))
        kind = self.rng.choices(
            [c[0] for c in choices], weights=[c[1] for c in choices]
        )[0]
        if kind == "number":
            return [self._number(avoid_zero)]
        if kind == "variable":
            return [self.rng.choice(declared)]
        return ["("] + self._expression(declared, depth + 1) + [")"]

    def _term(self, declared, depth):
        tokens = self._factor(declared, depth)
        for _ in range(self.rng.randint(0, self.max_operations)):
            op = self.rng.choice(["*", "/"])
            tokens += [op] + self._factor(declared, depth, avoid_zero=(op == "/"))
        return tokens

    def _expression(self, declared, depth):
        tokens = self._term(declared, depth)
        for _ in range(self.rng.randint(0, self.max_operations)):
            tokens += [self.rng.choice(["+", "-"])] + self._term(declared, depth)
        return tokens

    def _statement(self, declared):
        if declared and self.rng.random() < 0.3:
            target = self.rng.choice(declared)  # reassignment
        else:
            target = self.rng.choice(self.variables)
        tokens = [target, "="] + self._expression(declared, 0) + [";"]
        if target not in declared:
            declared.append(target)
        return tokens

    # -- rendering -----------------------------------------------------
    @staticmethod
    def _render_spaced(tokens):
        out = ""
        for i, tok in enumerate(tokens):
            if i == 0:
                out = tok
                continue
            prev = tokens[i - 1]
            if tok in (")", ";") or prev == "(":
                out += tok
            else:
                out += " " + tok
        return out

    def _render(self, statements, style):
        if style == "compact":
            sep = self.rng.choice(["", "\n"])
            return sep.join("".join(s) for s in statements)
        if style == "loose":
            lines = []
            for stmt in statements:
                pieces = []
                for tok in stmt:
                    pieces.append(tok)
                    pieces.append(self.rng.choice([" ", "  ", "\t"]))
                lines.append("".join(pieces).rstrip())
            return self.rng.choice(["\n", "\n\n", "  \n"]).join(lines)
        return "\n".join(self._render_spaced(s) for s in statements)

    # -- public API ----------------------------------------------------
    def generate_program(self):
        """Return ``(code, metadata)`` for one random valid program."""
        count = self.rng.randint(1, self.max_statements)
        declared, statements = [], []
        for _ in range(count):
            statements.append(self._statement(declared))
        style = self.rng.choice(STYLES)
        return self._render(statements, style), {"style": style, "statements": count}

    def generate_unique_programs(self, count, exclude=None):
        """Generate up to ``count`` programs, unique after whitespace
        normalisation. Sets ``self.shortfall`` if the bounded search could
        not reach ``count``."""
        seen = set(exclude or ())
        tests = []
        attempts, limit = 0, max(count * 50, 100)
        while len(tests) < count and attempts < limit:
            attempts += 1
            code, meta = self.generate_program()
            key = _canonical(code)
            if key in seen:
                continue
            seen.add(key)
            index = len(tests) + 1
            tests.append(
                {
                    "id": f"valid-{index:03d}",
                    "category": "valid",
                    "source": "grammar_generator",
                    "code": code,
                    "expected_status": "PASS",
                    "expected_basis": "grammar_construction",
                    "provenance": {"seed": self.seed, "index": index, **meta},
                }
            )
        self.shortfall = count - len(tests)
        return tests


def generate_program(seed=None):
    return GrammarGenerator(seed=seed).generate_program()[0]


def generate_tests(count=20, seed=None, **kwargs):
    """Generate ``count`` unique valid programs (structured test records)."""
    return GrammarGenerator(seed=seed, **kwargs).generate_unique_programs(count)


if __name__ == "__main__":
    for test in generate_tests(10, seed=1):
        print(f"--- {test['id']} ({test['provenance']['style']})")
        print(test["code"])
