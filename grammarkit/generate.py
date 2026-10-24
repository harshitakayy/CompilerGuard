"""Coverage-directed random sentence generation from a grammar."""

import random


class SentenceGenerator:
    IDS = ["x", "y", "z", "a", "b", "total", "count", "value", "tmp", "i", "n", "result"]

    def __init__(self, grammar, seed=None, max_depth=14, max_tokens=120):
        self.g = grammar
        self.rng = random.Random(seed)
        self.max_depth, self.max_tokens = max_depth, max_tokens
        self.cover, self.count = set(), 0

    def _terminal(self, sym):
        if sym[0] == "T":
            return (sym[1], sym[1])
        cls = sym[1]
        if cls == "ID":
            return ("ID", self.rng.choice(self.IDS))
        if cls == "NUMBER":
            if self.g.options.get("number") != "int" and self.rng.random() < 0.15:
                return ("NUMBER", f"{self.rng.randint(0, 9)}.{self.rng.randint(1, 9)}")
            return ("NUMBER", str(self.rng.randint(0, 99)))
        if cls == "STRING":
            return ("STRING", '"' + self.rng.choice(["s", "hi", "text", ""]) + '"')
        return ("CHAR", "'" + self.rng.choice("abc") + "'")

    def derive(self, name=None, depth=0):
        name = name or self.g.start
        alts = self.g.rule_alts[name]
        if depth >= self.max_depth or self.count >= self.max_tokens:
            best = min(self.g.alt_height[a.idx] for a in alts)
            choice = self.rng.choice([a for a in alts if self.g.alt_height[a.idx] == best])
        else:
            weights = []
            for a in alts:
                w = 3.0 if a.idx not in self.cover else 1.0
                if ("N", name) in a.syms:  # repetition step: favour a few iterations near the root
                    w = (1.8 if depth < 5 else 0.6) * (1.0 if a.idx in self.cover else 1.6)
                elif not a.syms and "~" in name:
                    w = 1.0
                weights.append(w)
            choice = self.rng.choices(alts, weights)[0]
        self.cover.add(choice.idx)
        out = []
        for s in choice.syms:
            if s[0] == "N":
                out += self.derive(s[1], depth + 1)
            else:
                self.count += 1
                out.append(self._terminal(s))
        return out

    def sentence(self, name=None, depth=0):
        self.count = 0
        return self.derive(name, depth)


def render(pairs):
    out, prev = "", None
    for kind, text in pairs:
        if prev is None:
            out = text
        elif prev in ("\n",):
            out += text
        elif text in (";", ",", ")", "]") or prev in ("(", "["):
            out += text
        else:
            out += " " + text
        prev = "\n" if text in (";", "{", "}") and kind == text else text
        if text in (";", "{", "}") and kind == text:
            out += "\n"
    return out.strip()
