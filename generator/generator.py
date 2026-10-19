"""Grammar-based generator of VALID CG-Lang programs (derives programs from the grammar)."""
import random

VAR_NAMES = ["x", "y", "z", "a", "b", "c", "total", "count", "result", "temp", "n", "m", "acc"]
RELOPS = ["<", ">", "<=", ">=", "==", "!="]
PREC = {"+": 1, "-": 1, "*": 2, "/": 2, "%": 2}


class ProgramGenerator:
    def __init__(self, seed=None, max_depth=2, max_stmts=6):
        self.rng = random.Random(seed)
        self.max_depth = max_depth
        self.max_stmts = max_stmts
        self.loop_id = 0
        self.compact = False

    # ---- expression trees: ("num", text) ("var", name) ("neg", n) ("paren", n) ("bin", op, l, r)
    def number(self):
        r = self.rng.random()
        if r < 0.7:
            return str(self.rng.randint(0, 99))
        if r < 0.9:
            return "%d.%d" % (self.rng.randint(0, 20), self.rng.randint(1, 99))
        return str(self.rng.randint(100, 99999))

    def nonzero(self):
        return str(self.rng.randint(1, 9)) if self.rng.random() < 0.8 else "%d.%d" % (self.rng.randint(1, 9), self.rng.randint(1, 9))

    def atom(self, readable):
        if readable and self.rng.random() < 0.55:
            return ("var", self.rng.choice(readable))
        return ("num", self.number())

    def expr(self, depth, readable):
        r = self.rng.random()
        if depth <= 0 or r < 0.25:
            return self.atom(readable)
        if r < 0.33:
            return ("neg", self.expr(depth - 1, readable))
        if r < 0.43:
            return ("paren", self.expr(depth - 1, readable))
        op = self.rng.choice(["+", "-", "*", "/", "%", "+", "-", "*"])
        left = self.expr(depth - 1, readable)
        right = ("num", self.nonzero()) if op in "/%" else self.expr(depth - 1, readable)
        return ("bin", op, left, right)

    def prec(self, n):
        return PREC[n[1]] if n[0] == "bin" else (3 if n[0] == "neg" else 4)

    def render(self, n):
        k = n[0]
        if k in ("num", "var"):
            return n[1]
        if k == "paren":
            return "(" + self.render(n[1]) + ")"
        if k == "neg":
            inner = self.render(n[1])
            if self.prec(n[1]) < 3:
                inner = "(" + inner + ")"
            return "-" + inner
        op, l, r = n[1], n[2], n[3]
        p = PREC[op]
        ls, rs = self.render(l), self.render(r)
        if self.prec(l) < p:
            ls = "(" + ls + ")"
        if self.prec(r) <= p:          # left-assoc: equal precedence on the right needs parens
            rs = "(" + rs + ")"
        return ("%s%s%s" if self.compact else "%s %s %s") % (ls, op, rs)

    def cond(self, readable):
        l, r = self.expr(1, readable), self.expr(1, readable)
        return "%s %s %s" % (self.render(l), self.rng.choice(RELOPS), self.render(r))

    # ---- statements
    def block(self, depth, defined, readonly, indent):
        lines, defined = [], set(defined)
        for _ in range(self.rng.randint(1, max(1, self.max_stmts // 2))):
            new_lines, defined = self.statement(depth, defined, readonly, indent)
            lines += new_lines
        return lines

    def statement(self, depth, defined, readonly, indent):
        pad = "    " * indent
        readable = sorted(defined | readonly)
        assignable = sorted(defined - readonly)
        r = self.rng.random()
        if r < 0.40 or not readable:
            if assignable and self.rng.random() < 0.4:
                name = self.rng.choice(assignable)
            else:
                name = self.rng.choice([v for v in VAR_NAMES if v not in readonly] or VAR_NAMES)
            e = self.render(self.expr(self.max_depth, readable))
            return [pad + "%s = %s;" % (name, e)], defined | {name}
        if r < 0.65:
            return [pad + "print %s;" % self.render(self.expr(self.max_depth, readable))], defined
        if depth <= 0:
            return [pad + "print %s;" % self.render(self.expr(1, readable))], defined
        if r < 0.85:
            lines = [pad + "if (%s) {" % self.cond(readable)]
            lines += self.block(depth - 1, defined, readonly, indent + 1)
            if self.rng.random() < 0.6:
                lines += [pad + "} else {"] + self.block(depth - 1, defined, readonly, indent + 1)
            return lines + [pad + "}"], defined
        self.loop_id += 1
        counter = "i%d" % self.loop_id
        bound = self.rng.randint(1, 4)
        lines = [pad + "%s = 0;" % counter, pad + "while (%s < %d) {" % (counter, bound)]
        lines += self.block(depth - 1, defined, readonly | {counter}, indent + 1)
        lines += ["    " * (indent + 1) + "%s = %s + 1;" % (counter, counter), pad + "}"]
        return lines, defined | {counter}

    def generate(self):
        self.compact = self.rng.random() < 0.2
        self.loop_id = 0
        lines, defined = [], set()
        for _ in range(self.rng.randint(3, self.max_stmts)):
            new, defined = self.statement(2, defined, set(), 0)
            lines += new
        lines.append("print %s;" % (sorted(defined)[0] if defined else "0"))
        return "\n".join(lines) + "\n"


def generate_programs(n, seed=0, **kw):
    gen = ProgramGenerator(seed, **kw)
    return [gen.generate() for _ in range(n)]
