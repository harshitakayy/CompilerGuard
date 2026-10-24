"""Earley recogniser/parser: the independent oracle for grammar targets.

Handles any context-free grammar (left recursion, ambiguity, nullable rules).
Besides accept/reject it reports the first failing token, the set of expected
terminals, every production completed in the chart (production coverage, even
for rejected input) and one parse tree for accepted input.
"""

from .grammar import sym_text


class Node:
    __slots__ = ("name", "alt", "kids", "lo", "hi")

    def __init__(self, name, alt, kids, lo, hi):
        self.name, self.alt, self.kids, self.lo, self.hi = name, alt, kids, lo, hi


class EarleyResult:
    def __init__(self, ok, error_index, expected, completed, tree):
        self.ok, self.error_index, self.expected, self.completed, self.tree = ok, error_index, expected, completed, tree


class EarleyParser:
    def __init__(self, grammar):
        self.g = grammar

    def parse(self, kinds, want_tree=True):
        g, alts, n = self.g, self.g.alts, len(kinds)
        S = [dict() for _ in range(n + 1)]
        for a in g.rule_alts[g.start]:
            S[0][(a.idx, 0, 0)] = None
        completed, err, last = set(), None, 0
        for k in range(n + 1):
            last = k
            agenda, i = list(S[k]), 0

            def add(item, bp):
                if item not in S[k]:
                    S[k][item] = bp
                    agenda.append(item)

            while i < len(agenda):
                item = agenda[i]
                i += 1
                ai, dot, org = item
                syms = alts[ai].syms
                if dot < len(syms):
                    sym = syms[dot]
                    if sym[0] == "N":
                        for a in g.rule_alts[sym[1]]:
                            add((a.idx, 0, k), None)
                        if sym[1] in g.nullable:
                            add((ai, dot + 1, org), ("null", item, sym[1]))
                    elif k < n and kinds[k] == sym[1]:
                        nxt = (ai, dot + 1, org)
                        if nxt not in S[k + 1]:
                            S[k + 1][nxt] = ("scan", item, k)
                else:
                    completed.add(ai)
                    lhs = alts[ai].lhs
                    for item2 in list(S[org]):
                        a2, d2, o2 = item2
                        s2 = alts[a2].syms
                        if d2 < len(s2) and s2[d2] == ("N", lhs):
                            add((a2, d2 + 1, o2), ("comp", item2, item))
            if k < n and not S[k + 1]:
                err = k
                break
        expected = set()
        for ai, dot, org in S[last]:
            syms = alts[ai].syms
            if dot < len(syms) and syms[dot][0] != "N":
                expected.add(syms[dot][1])
        tree, ok = None, False
        if err is None:
            for a in g.rule_alts[g.start]:
                item = (a.idx, len(a.syms), 0)
                if item in S[n]:
                    ok = True
                    if want_tree:
                        tree = self._build(S, item, n)
                    break
        if not ok and err is None:
            err = n
        return EarleyResult(ok, None if ok else err, expected, completed, tree)

    def _empty(self, name, k, depth=0):
        alt = self.g.alts[self.g.empty_alt[name]]
        kids = [self._empty(s[1], k, depth + 1) for s in alt.syms] if depth < 200 else []
        return Node(name, alt.idx, kids, k, k)

    def _build(self, S, item, k, depth=0):
        if depth > 400:
            raise RecursionError("parse tree too deep")
        alt = self.g.alts[item[0]]
        kids, cur, pos = [], item, k
        while cur[1] > 0:
            bp = S[pos][cur]
            kind, prev = bp[0], bp[1]
            if kind == "scan":
                kids.append(Node(self.g.alts[prev[0]].syms[prev[1]][1], None, [], bp[2], bp[2] + 1))
                pos -= 1
            elif kind == "comp":
                kids.append(self._build(S, bp[2], pos, depth + 1))
                pos = bp[2][2]
            else:
                kids.append(self._empty(bp[2], pos))
            cur = prev
        kids.reverse()
        return Node(alt.lhs, alt.idx, kids, item[2], k)
