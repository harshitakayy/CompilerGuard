"""Grammar-aware ('smart') mutation of valid programs for any target.

Operators work at two levels:
* token level - delete/duplicate/swap/replace/insert tokens, break brackets,
  inject invalid or non-ASCII characters, unterminate literals;
* grammar level - using the Earley parse tree of the parent: delete a required
  child, swap or duplicate siblings, splice a subtree from a different rule,
  truncate at a production boundary, insert a token the grammar does *not*
  expect at a position (computed from the Earley chart), and regenerate a subtree
  (a valid-preserving mutation that diversifies AST structure).

Each mutant's expected status is the oracle verdict (basis ``oracle``); the
operator's intent is kept in the provenance so unrealised intents are visible.
"""

import random
import re
from collections import OrderedDict

from .generate import SentenceGenerator, render

INVALID_CHARS = list("@#$`\\?~^|!")
UNICODE_CHARS = ["é", "²", "٣", "中", "＋", "\u00a0", "\u200b"]
MAX_CHARS = 2500
BRACKETS = {"(": ")", "[": "]", "{": "}"}


def _user_nodes(tree):
    out, stack = [], [tree]
    while stack:
        n = stack.pop()
        if n.alt is not None:
            if "~" not in n.name and n.hi > n.lo:
                out.append(n)
            stack += n.kids
    return out


def _flat_kids(node):
    out = []
    for k in node.kids:
        if k.alt is not None and "~" in k.name:
            out += _flat_kids(k)
        elif k.hi > k.lo:
            out.append(k)
    return out


class SmartMutator:
    def __init__(self, target, seed=None):
        self.t, self.g = target, target.grammar
        self.rng = random.Random(seed)
        self.seed = seed
        self.gen = SentenceGenerator(self.g, seed=self.rng.randrange(2 ** 31), max_depth=9, max_tokens=40)
        terms = self.g.terminals
        self.words = [x for x in terms if re.fullmatch(r"[A-Za-z_]\w*", x)]
        self.puncts = [x for x in terms if x not in self.words]
        self.user_rules = [r for r, _, _ in self.g.source_rules]
        self.operators = OrderedDict()
        for name, intent, family in [
            ("delete_token", "invalid", "token"), ("duplicate_token", "invalid", "token"),
            ("swap_adjacent_tokens", "either", "token"), ("replace_same_class", "either", "token"),
            ("replace_cross_class", "invalid", "token"), ("insert_terminal", "invalid", "token"),
            ("truncate_tokens", "invalid", "token"), ("drop_bracket", "invalid", "token"),
            ("add_extra_bracket", "invalid", "token"), ("inject_invalid_char", "invalid", "lexical"),
            ("inject_unicode_char", "invalid", "lexical"), ("unterminate_literal", "invalid", "lexical"),
            ("keyword_as_identifier", "invalid", "token"), ("fresh_identifier", "either", "semantic"),
            ("number_edge_case", "either", "lexical"),
            ("delete_required_child", "invalid", "grammar"), ("swap_siblings", "either", "grammar"),
            ("duplicate_child", "invalid", "grammar"), ("splice_foreign_subtree", "either", "grammar"),
            ("regenerate_subtree", "valid", "grammar"), ("insert_unexpected_token", "invalid", "grammar"),
            ("truncate_at_boundary", "invalid", "grammar"),
        ]:
            self.operators[name] = (getattr(self, "_" + name), intent, family)

    # -- helpers ------------------------------------------------------------
    def _splice(self, code, toks, lo, hi, text):
        start = toks[lo].start if lo < len(toks) - 1 else len(code)
        end = toks[hi - 1].end if hi > lo else start
        pad = " " if text else ""
        return code[:start] + pad + text + pad + code[end:]

    def _sample(self, kind_or_text):
        if kind_or_text in self.g.classes:
            return self.gen._terminal(("C", kind_or_text))[1]
        return kind_or_text

    def _pick(self, toks):
        n = len(toks) - 1
        return self.rng.randrange(n) if n else None

    def _terminal_pool(self):
        return list(self.g.terminals) + list(self.g.classes)

    # -- token-level operators ---------------------------------------------
    def _delete_token(self, code, info):
        toks, i = info["tokens"], self._pick(info["tokens"])
        return None if i is None else self._splice(code, toks, i, i + 1, "")

    def _duplicate_token(self, code, info):
        toks, i = info["tokens"], self._pick(info["tokens"])
        return None if i is None else self._splice(code, toks, i, i + 1, toks[i].text + " " + toks[i].text)

    def _swap_adjacent_tokens(self, code, info):
        toks = info["tokens"]
        if len(toks) < 3:
            return None
        i = self.rng.randrange(len(toks) - 2)
        return self._splice(code, toks, i, i + 2, toks[i + 1].text + " " + toks[i].text)

    def _replace_same_class(self, code, info):
        toks, i = info["tokens"], self._pick(info["tokens"])
        if i is None:
            return None
        k = toks[i].kind
        if k in ("ID", "NUMBER", "STRING", "CHAR"):
            new = self.gen._terminal(("C", k))[1]
        else:
            group = self.words if k in self.words else [p for p in self.puncts if p not in BRACKETS and p not in BRACKETS.values()]
            options = [x for x in group if x != k]
            if not options:
                return None
            new = self.rng.choice(options)
        return self._splice(code, toks, i, i + 1, new)

    def _replace_cross_class(self, code, info):
        toks, i = info["tokens"], self._pick(info["tokens"])
        if i is None:
            return None
        k = toks[i].kind
        pool = [x for x in self._terminal_pool() if x != k and (x in self.g.classes) != (k in self.g.classes or (k in self.words) != (x in self.words))]
        pool = pool or [x for x in self._terminal_pool() if x != k]
        return self._splice(code, toks, i, i + 1, self._sample(self.rng.choice(pool))) if pool else None

    def _insert_terminal(self, code, info):
        toks = info["tokens"]
        i = self.rng.randrange(len(toks))
        return self._splice(code, toks, i, i, self._sample(self.rng.choice(self._terminal_pool())))

    def _truncate_tokens(self, code, info):
        toks = info["tokens"]
        if len(toks) < 3:
            return None
        i = self.rng.randrange(1, len(toks) - 1)
        return code[: toks[i - 1].end]

    def _drop_bracket(self, code, info):
        toks = info["tokens"]
        idx = [i for i, t in enumerate(toks[:-1]) if t.kind in BRACKETS or t.kind in BRACKETS.values()]
        if not idx:
            return None
        i = self.rng.choice(idx)
        return self._splice(code, toks, i, i + 1, "")

    def _add_extra_bracket(self, code, info):
        present = [b for b in list(BRACKETS) + list(BRACKETS.values()) if b in self.g.terminals]
        if not present:
            return None
        toks = info["tokens"]
        i = self.rng.randrange(len(toks))
        return self._splice(code, toks, i, i, self.rng.choice(present))

    def _inject_invalid_char(self, code, info):
        toks = info["tokens"]
        i = self.rng.randrange(len(toks))
        return self._splice(code, toks, i, i, self.rng.choice(INVALID_CHARS))

    def _inject_unicode_char(self, code, info):
        toks = info["tokens"]
        i = self.rng.randrange(len(toks))
        return self._splice(code, toks, i, i, self.rng.choice(UNICODE_CHARS))

    def _unterminate_literal(self, code, info):
        toks = info["tokens"]
        idx = [i for i, t in enumerate(toks) if t.kind in ("STRING", "CHAR")]
        if not idx:
            return None
        t = toks[self.rng.choice(idx)]
        return code[: t.end - 1] + code[t.end:]

    def _keyword_as_identifier(self, code, info):
        toks = info["tokens"]
        idx = [i for i, t in enumerate(toks) if t.kind == "ID"]
        if not idx or not self.words:
            return None
        i = self.rng.choice(idx)
        return self._splice(code, toks, i, i + 1, self.rng.choice(self.words))

    def _fresh_identifier(self, code, info):
        toks = info["tokens"]
        idx = [i for i, t in enumerate(toks) if t.kind == "ID"]
        if not idx:
            return None
        i = self.rng.choice(idx)
        used = {t.text for t in toks}
        names = [n for n in ("ghost", "phantom", "unknown1", "undef_q", "w9") if n not in used]
        return self._splice(code, toks, i, i + 1, self.rng.choice(names)) if names else None

    def _number_edge_case(self, code, info):
        toks = info["tokens"]
        idx = [i for i, t in enumerate(toks) if t.kind == "NUMBER"]
        if not idx:
            return None
        i = self.rng.choice(idx)
        return self._splice(code, toks, i, i + 1, self.rng.choice(["1.5.2", "99999999999999999999", "007", "1e5", "12abc", "0x1F", "1."]))

    # -- grammar-level operators --------------------------------------------
    def _nodes(self, info):
        tree = info["earley"].tree if info["earley"] and info["earley"].ok else None
        return _user_nodes(tree) if tree else []

    def _delete_required_child(self, code, info):
        nodes = [n for n in self._nodes(info) if len(_flat_kids(n)) >= 2]
        if not nodes:
            return None
        n = self.rng.choice(nodes)
        k = self.rng.choice(_flat_kids(n))
        return self._splice(code, info["tokens"], k.lo, k.hi, "")

    def _swap_siblings(self, code, info):
        nodes = [n for n in self._nodes(info) if len(_flat_kids(n)) >= 2]
        if not nodes:
            return None
        kids = _flat_kids(self.rng.choice(nodes))
        i = self.rng.randrange(len(kids) - 1)
        a, b, toks = kids[i], kids[i + 1], info["tokens"]
        ta, tb = code[toks[a.lo].start:toks[a.hi - 1].end], code[toks[b.lo].start:toks[b.hi - 1].end]
        return code[: toks[a.lo].start] + tb + code[toks[a.hi - 1].end:toks[b.lo].start] + ta + code[toks[b.hi - 1].end:]

    def _duplicate_child(self, code, info):
        nodes = [n for n in self._nodes(info) if _flat_kids(n)]
        if not nodes:
            return None
        k = self.rng.choice(_flat_kids(self.rng.choice(nodes)))
        toks = info["tokens"]
        text = code[toks[k.lo].start:toks[k.hi - 1].end]
        return self._splice(code, toks, k.hi, k.hi, text)

    def _sentence_text(self, rule, depth=3):
        pairs = self.gen.sentence(rule, depth)
        return render(pairs).replace("\n", " ")

    def _splice_foreign_subtree(self, code, info):
        nodes = self._nodes(info)
        if not nodes or len(self.user_rules) < 2:
            return None
        n = self.rng.choice(nodes)
        others = [r for r in self.user_rules if r != n.name]
        return self._splice(code, info["tokens"], n.lo, n.hi, self._sentence_text(self.rng.choice(others)))

    def _regenerate_subtree(self, code, info):
        nodes = [n for n in self._nodes(info) if n.hi - n.lo < len(info["tokens"]) - 1 or True]
        if not nodes:
            return None
        n = self.rng.choice(nodes)
        return self._splice(code, info["tokens"], n.lo, n.hi, self._sentence_text(n.name, 4))

    def _insert_unexpected_token(self, code, info):
        toks = info["tokens"]
        i = self.rng.randrange(len(toks))
        expected = self.t.expected_after([t.kind for t in toks[:i]])
        pool = [x for x in self._terminal_pool() if x not in expected]
        return self._splice(code, toks, i, i, self._sample(self.rng.choice(pool))) if pool else None

    def _truncate_at_boundary(self, code, info):
        toks = info["tokens"]
        nodes = [n for n in self._nodes(info) if 0 < n.hi < len(toks) - 1]
        if not nodes:
            return None
        n = self.rng.choice(nodes)
        return code[: toks[n.hi - 1].end]

    # -- public -------------------------------------------------------------
    def mutate(self, code, op):
        info = self.t.analyze(code)
        if not info["tokens"]:
            return None
        return self.operators[op][0](code, info)

    def generate(self, parents, count, exclude=None, weights=None, id_prefix="mut", start_index=1):
        """Return up to ``count`` unique mutant test records (never loops forever)."""
        seen, out = set(exclude or ()), []
        names = list(self.operators)
        if weights is None:
            self.rng.shuffle(names)
        attempts, limit = 0, count * 80 + 200
        while len(out) < count and attempts < limit and parents:
            attempts += 1
            op = (self.rng.choices(names, [weights.get(n, 1.0) for n in names])[0] if weights else names[attempts % len(names)])
            parent = self.rng.choice(parents)
            code = self.mutate(parent["code"], op)
            if not code or code == parent["code"] or len(code) > MAX_CHARS or not code.strip():
                continue
            key = self.t.canonical(code)
            if key in seen:
                continue
            seen.add(key)
            verdict = self.t.oracle(code)
            _, intent, family = self.operators[op]
            test = {
                "id": f"{id_prefix}-{start_index + len(out):03d}", "category": "smart_mutation", "source": "mutation", "code": code,
                "expected_status": verdict["status"], "expected_basis": "oracle",
                "provenance": {"operator": op, "family": family, "intent": intent, "parent_id": parent.get("id"), "seed": self.seed},
            }
            if verdict["status"] == "FAIL":
                test["expected_error_type"] = verdict["type"]
            out.append(test)
        return out
