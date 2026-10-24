"""EBNF grammar notation -> BNF, with analysis.

Notation (one rule per line; continuation lines may start with ``|``)::

    name -> alt | alt        # also ::=  :=  →
    'literal'  "literal"     terminals
    ID NUMBER STRING CHAR    built-in token classes
    ( ... )  x*  x+  x?      grouping and repetition
    eps                      the empty string
    %comments c              skip // and /* */ comments and #-lines (C-like)
    %number int              NUMBER is digits only (default also allows 1.5)

The first rule is the start symbol. EBNF operators are desugared into helper
rules named ``<rule>~<n>`` (right-recursive repetition, greedy-first options),
so every BNF alternative is a countable *production* for coverage purposes.
"""

import re
from collections import OrderedDict

BUILTINS = ("ID", "NUMBER", "STRING", "CHAR")
_ARROW = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?:->|::=|:=|→)\s*(.*)$")
_TOK = re.compile(
    r"""\s+|(?P<lit>'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*")|(?P<name>[A-Za-z_][A-Za-z0-9_]*|ε)|(?P<op>[|()*+?])|(?P<bad>.)""",
    re.X,
)
MAX_RULES = 200


class GrammarError(Exception):
    def __init__(self, message, line=None):
        super().__init__(message)
        self.message, self.line = message, line

    def to_dict(self):
        return {"message": self.message, "line": self.line}


class Alt:
    __slots__ = ("idx", "lhs", "syms", "root")

    def __init__(self, idx, lhs, syms, root):
        self.idx, self.lhs, self.syms, self.root = idx, lhs, tuple(syms), root


def sym_text(sym):
    if sym[0] == "N":
        return sym[1]
    return sym[1] if sym[0] == "C" else "'" + sym[1] + "'"


def _strip_comment(line):
    quote = None
    for i, ch in enumerate(line):
        if quote:
            if ch == quote and line[i - 1] != "\\":
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch == "#" or line.startswith("//", i):
            return line[:i]
    return line


def _unquote(lit):
    body = lit[1:-1]
    return re.sub(r"\\(.)", lambda m: {"n": "\n", "t": "\t"}.get(m.group(1), m.group(1)), body)


class Grammar:
    def __init__(self, text):
        self.text = text
        self.options = {}
        self.source_rules = []            # (name, line_no, text)
        self.rules = OrderedDict()         # name -> list[tuple[sym]]
        self.roots = {}                    # rule (incl. helpers) -> user rule
        self.alts = []
        self.warnings = []
        self._helper_counts = {}
        self._used_at = {}
        self._parse(text)
        self._build_alts()
        self._analyze()

    # -- parsing ----------------------------------------------------------
    def _parse(self, text):
        if len(text) > 30000:
            raise GrammarError("Grammar is too large (limit 30,000 characters)")
        entries = []
        for no, raw in enumerate(text.splitlines(), 1):
            line = _strip_comment(raw).rstrip()
            if not line.strip():
                continue
            if line.strip().startswith("%"):
                parts = line.strip()[1:].split()
                if len(parts) == 2 and parts[0] in ("comments", "number"):
                    self.options[parts[0]] = parts[1]
                else:
                    raise GrammarError("Unknown directive; use '%comments c' or '%number int'", no)
                continue
            m = _ARROW.match(line)
            if m:
                entries.append([m.group(1), no, m.group(2), raw.strip()])
            elif entries:
                entries[-1][2] += " " + line.strip()
                entries[-1][3] += "\n    " + raw.strip()
            else:
                raise GrammarError("Expected a rule of the form  name -> ...", no)
        if not entries:
            raise GrammarError("The grammar has no rules")
        if len(entries) > MAX_RULES:
            raise GrammarError(f"Too many rules (limit {MAX_RULES})")
        seen = {}
        for name, no, _, _ in entries:
            if name in BUILTINS:
                raise GrammarError(f"'{name}' is a built-in token class and cannot be defined", no)
            if name in seen:
                raise GrammarError(f"Rule '{name}' is defined twice (first on line {seen[name]})", no)
            seen[name] = no
        for name, no, body, shown in entries:
            self.source_rules.append((name, no, shown))
            self.rules[name] = []
            self.roots[name] = name
        for name, no, body, shown in entries:
            alts = self._parse_body(body, no)
            self._current = (name, no)
            self.rules[name] = self._desugar_alts(alts, name, no, top=True)
        self.start = entries[0][0]

    def _tokens(self, body, no):
        out = []
        for m in _TOK.finditer(body):
            if m.lastgroup == "bad":
                raise GrammarError(f"Unexpected character {m.group()!r} (unterminated quote?)", no)
            if m.lastgroup:
                out.append((m.lastgroup, m.group()))
        return out

    def _parse_body(self, body, no):
        toks, pos = self._tokens(body, no), [0]

        def peek():
            return toks[pos[0]] if pos[0] < len(toks) else (None, None)

        def alts():
            result = [seq()]
            while peek() == ("op", "|"):
                pos[0] += 1
                result.append(seq())
            return result

        def seq():
            items = []
            while True:
                kind, val = peek()
                if kind is None or (kind == "op" and val in "|)"):
                    return items
                atom = None
                pos[0] += 1
                if kind == "lit":
                    lit = _unquote(val)
                    if not lit:
                        raise GrammarError("Empty literal ''", no)
                    atom = ("lit", lit)
                elif kind == "name":
                    atom = ("eps",) if val in ("ε", "eps", "epsilon") else ("name", val)
                elif val == "(":
                    inner = alts()
                    if peek() != ("op", ")"):
                        raise GrammarError("Missing ')'", no)
                    pos[0] += 1
                    atom = ("group", inner)
                else:
                    raise GrammarError(f"Unexpected '{val}' (a repetition operator needs something before it)", no)
                suffix = None
                if peek()[0] == "op" and peek()[1] in "*+?":
                    suffix = peek()[1]
                    pos[0] += 1
                items.append((atom, suffix))

        result = alts()
        if pos[0] != len(toks):
            raise GrammarError("Unbalanced ')'", no)
        return result

    # -- desugaring -------------------------------------------------------
    def _helper(self, root):
        n = self._helper_counts.get(root, 0) + 1
        self._helper_counts[root] = n
        name = f"{root}~{n}"
        self.roots[name] = root
        self.rules[name] = []
        return name

    def _desugar_alts(self, alts, root, no, top=False):
        out = []
        for seq in alts:
            syms = []
            for atom, suffix in seq:
                syms.extend(self._desugar_item(atom, suffix, root, no))
            out.append(tuple(syms))
        return out

    def _atom_syms(self, atom, root, no):
        kind = atom[0]
        if kind == "lit":
            return [("T", atom[1])]
        if kind == "eps":
            return []
        if kind == "name":
            name = atom[1]
            if name in BUILTINS:
                return [("C", name)]
            self._used_at.setdefault(name, no)
            return [("N", name)]
        alts = self._desugar_alts(atom[1], root, no)
        if len(alts) == 1:
            return list(alts[0])
        helper = self._helper(root)
        self.rules[helper] = alts
        return [("N", helper)]

    def _desugar_item(self, atom, suffix, root, no):
        base = self._atom_syms(atom, root, no)
        if suffix is None:
            return base
        helper = self._helper(root)
        if suffix == "?":
            self.rules[helper] = [tuple(base), ()]
            return [("N", helper)]
        self.rules[helper] = [tuple(base) + (("N", helper),), ()]
        return [("N", helper)] if suffix == "*" else base + [("N", helper)]

    def _build_alts(self):
        for name, lst in self.rules.items():
            for syms in lst:
                self.alts.append(Alt(len(self.alts), name, syms, self.roots[name]))
        self.rule_alts = {n: [a for a in self.alts if a.lhs == n] for n in self.rules}

    # -- analysis ---------------------------------------------------------
    def _analyze(self):
        for name, no in self._used_at.items():
            if name not in self.rules:
                raise GrammarError(f"Undefined nonterminal '{name}'", no)
        self.terminals = sorted({s[1] for a in self.alts for s in a.syms if s[0] == "T"})
        self.classes = sorted({s[1] for a in self.alts for s in a.syms if s[0] == "C"})
        self.nullable = set()
        changed = True
        while changed:
            changed = False
            for a in self.alts:
                if a.lhs not in self.nullable and all(s[0] == "N" and s[1] in self.nullable for s in a.syms):
                    self.nullable.add(a.lhs)
                    changed = True
        inf = 10 ** 6
        self.height = {n: inf for n in self.rules}
        self.alt_height = {}
        changed = True
        while changed:
            changed = False
            for a in self.alts:
                h = 1 + max([self.height[s[1]] for s in a.syms if s[0] == "N"] or [0])
                self.alt_height[a.idx] = min(h, inf)
                if h < self.height[a.lhs]:
                    self.height[a.lhs] = h
                    changed = True
        self.empty_alt = {}
        for a in self.alts:
            if a.lhs in self.nullable and a.lhs not in self.empty_alt and all(
                s[0] == "N" and s[1] in self.nullable for s in a.syms
            ):
                self.empty_alt[a.lhs] = a.idx
        reach, stack = set(), [self.start]
        while stack:
            n = stack.pop()
            if n in reach:
                continue
            reach.add(n)
            stack += [s[1] for a in self.rule_alts[n] for s in a.syms if s[0] == "N"]
        for n in self.rules:
            if self.height[n] >= inf and n in reach:
                line = next((no for nm, no, _ in self.source_rules if nm == self.roots[n]), None)
                raise GrammarError(f"Rule '{self.roots[n]}' cannot derive any finite string", line)
        for nm, no, _ in self.source_rules:
            if nm not in reach:
                self.warnings.append({"line": no, "message": f"Rule '{nm}' is unreachable from the start symbol '{self.start}'."})
        self._left_recursion()
        self._peg_hazards()

    def _left_recursion(self):
        edges = {n: set() for n in self.rules}
        for a in self.alts:
            for s in a.syms:
                if s[0] != "N":
                    break
                edges[a.lhs].add(s[1])
                if s[1] not in self.nullable:
                    break
        color, bad = {}, set()

        def dfs(n, path):
            color[n] = 1
            for m in edges[n]:
                if color.get(m) == 1:
                    bad.update(path[path.index(m):] if m in path else [m])
                elif m not in color:
                    dfs(m, path + [m])
            color[n] = 2

        for n in self.rules:
            if n not in color:
                dfs(n, [n])
        self.left_recursive = sorted({self.roots[n] for n in bad})
        for nm in self.left_recursive:
            no = next((no for r, no, _ in self.source_rules if r == nm), None)
            self.warnings.append({"line": no, "message": f"Rule '{nm}' is left-recursive. The generated PEG parser cannot handle left recursion and will reject valid input; rewrite it with repetition, e.g.  x -> y (op y)*."})

    def _peg_hazards(self):
        seen = set()
        for n, alts in self.rule_alts.items():
            for i, a in enumerate(alts):
                for b in alts[i + 1:]:
                    if len(a.syms) < len(b.syms) and b.syms[: len(a.syms)] == a.syms or (not a.syms and b.syms):
                        key = (self.roots[n], i)
                        if key not in seen:
                            seen.add(key)
                            no = next((no for r, no, _ in self.source_rules if r == self.roots[n]), None)
                            self.warnings.append({"line": no, "message": f"Ordered-choice hazard in '{self.roots[n]}': an alternative is a prefix of a later one, so a PEG parser may never reach the longer alternative."})

    # -- presentation -----------------------------------------------------
    def label(self, alt_idx):
        a = self.alts[alt_idx]
        return f"{a.lhs} → " + (" ".join(sym_text(s) for s in a.syms) or "ε")

    def to_dict(self):
        return {
            "start": self.start,
            "rules": [{"name": n, "line": no, "text": t, "alternatives": len([a for a in self.alts if a.root == n])} for n, no, t in self.source_rules],
            "terminals": self.terminals,
            "classes": self.classes,
            "options": self.options,
            "bnf": [{"idx": a.idx, "label": self.label(a.idx), "root": a.root} for a in self.alts],
            "warnings": self.warnings,
            "stats": {"rules": len(self.source_rules), "productions": len(self.alts), "terminals": len(self.terminals)},
        }
