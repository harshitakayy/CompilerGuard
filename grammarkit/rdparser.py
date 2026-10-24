"""Generated packrat (PEG-style) recursive-descent parser: the compiler under
test for grammar targets.

Ordered choice and greedy repetition make this behave like parsers produced by
PEG tools. It deliberately fails on left recursion. The Earley oracle checks it
against the grammar's true context-free meaning, so any divergence is reported
as a potential bug (or a grammar hazard).
"""

from collections import Counter


class PegParser:
    def __init__(self, grammar):
        self.g = grammar
        self.rules = {n: [(a.idx, a.syms) for a in alts] for n, alts in grammar.rule_alts.items()}

    def parse(self, kinds):
        self.kinds, self.n = kinds, len(kinds)
        self.memo, self.far, self.far_expected = {}, -1, set()
        self.attempts, self.success = Counter(), Counter()
        end = self._rule(self.g.start, 0)
        ok = end == self.n
        if end is not None and end < self.n:
            self._fail(end, ("T", "end of input"))
        return ok, (None if ok else max(self.far, 0)), set(self.far_expected)

    def _fail(self, pos, sym):
        if pos > self.far:
            self.far, self.far_expected = pos, {sym[1]}
        elif pos == self.far:
            self.far_expected.add(sym[1])

    def _rule(self, name, pos):
        key = (name, pos)
        if key in self.memo:
            return self.memo[key]
        self.memo[key] = None  # in-progress marker: left recursion fails
        result = None
        for idx, syms in self.rules[name]:
            self.attempts[idx] += 1
            p, ok = pos, True
            for s in syms:
                if s[0] == "N":
                    p = self._rule(s[1], p)
                    if p is None:
                        ok = False
                        break
                elif p < self.n and self.kinds[p] == s[1]:
                    p += 1
                else:
                    self._fail(p, s)
                    ok = False
                    break
            if ok:
                self.success[idx] += 1
                result = p
                break
        self.memo[key] = result
        return result
