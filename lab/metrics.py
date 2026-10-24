"""Per-arm metrics: error patterns, bug signals, production coverage,
AST diversity, path coverage and per-test novelty."""

CLASSES = ("ID", "NUMBER", "STRING", "CHAR")


def _flat(node):
    out = []
    for k in node.kids:
        if k.alt is not None and "~" in k.name:
            out += _flat(k)
        else:
            out.append(k)
    return out


def ast_shape(node, depth=0, max_depth=4):
    """Structural signature of a parse tree: rule names down to ``max_depth``,
    literals kept, identifiers/numbers abstracted to their class."""
    if node.alt is None:
        return node.name
    if depth >= max_depth:
        return node.name
    kids = " ".join(ast_shape(k, depth + 1, max_depth) for k in _flat(node))
    return f"({node.name} {kids})" if kids else f"({node.name})"


def production_edges(node, out):
    for k in _flat(node):
        if k.alt is not None:
            out.add((node.alt, k.alt))
            production_edges(k, out)
    return out


def describe(values):
    import statistics

    values = list(values)
    if not values:
        return {"n": 0, "mean": None, "stdev": None, "min": None, "max": None, "values": []}
    return {"n": len(values), "mean": round(statistics.mean(values), 4),
            "stdev": round(statistics.stdev(values), 4) if len(values) > 1 else None,
            "min": min(values), "max": max(values), "values": values}


class ArmTracker:
    def __init__(self, target):
        self.t, self.g = target, target.grammar
        self.exec_lines = target.exec_lines()
        self.patterns, self.alts, self.shapes, self.edges, self.lines = set(), set(), set(), set(), set()
        self.accepted = 0
        self.bug_ids, self.novelty, self.curves = [], [], {"patterns": [], "productions": [], "shapes": [], "lines": []}
        self.trace_ok = False

    def observe(self, rec, lines):
        info = self.t.analyze(rec["code"])
        e = info["earley"]
        pat = rec.get("error_pattern")
        new_pattern = pat is not None and pat not in self.patterns
        if pat:
            self.patterns.add(pat)
        new_prod = len(e.completed - self.alts) if e else 0
        if e:
            self.alts |= e.completed
        new_shape = new_edges = 0
        if e and e.ok and e.tree is not None:
            self.accepted += 1
            sig = ast_shape(e.tree)
            if sig not in self.shapes:
                self.shapes.add(sig)
                new_shape = 1
            edges = production_edges(e.tree, set())
            new_edges = len(edges - self.edges)
            self.edges |= edges
        covered = lines & self.exec_lines
        if lines:
            self.trace_ok = True
        new_lines = len(covered - self.lines)
        self.lines |= covered
        if rec.get("potential_compiler_bug"):
            self.bug_ids.append(rec["id"])
        score = 3.0 * new_pattern + min(new_prod, 3) + new_shape + 0.25 * min(new_edges, 4) + 0.05 * min(new_lines, 20) + 5.0 * bool(rec.get("potential_compiler_bug"))
        nov = {"new_pattern": new_pattern, "new_productions": new_prod, "new_ast_shape": bool(new_shape),
               "new_edges": new_edges, "new_lines": new_lines, "score": round(score, 3)}
        self.novelty.append([int(new_pattern), new_prod, new_shape, new_lines])
        self.curves["patterns"].append(len(self.patterns))
        self.curves["productions"].append(len(self.alts))
        self.curves["shapes"].append(len(self.shapes))
        self.curves["lines"].append(len(self.lines))
        return nov

    def summary(self, n_tests, categories):
        total = len(self.g.alts)
        by_rule = {}
        for a in self.g.alts:
            r = by_rule.setdefault(a.root, [0, 0])
            r[1] += 1
            r[0] += a.idx in self.alts
        uncovered = [self.g.label(a.idx) for a in self.g.alts if a.idx not in self.alts]
        total_lines = len(self.exec_lines)
        return {
            "tests": n_tests,
            "unique_error_patterns": len(self.patterns),
            "patterns": sorted(self.patterns),
            "error_categories": categories,
            "bug_signals": len(self.bug_ids),
            "bug_signal_ids": self.bug_ids,
            "production_coverage": {"covered": len(self.alts), "total": total,
                                    "percent": round(100 * len(self.alts) / total, 1) if total else 0.0,
                                    "by_rule": {k: {"covered": v[0], "total": v[1]} for k, v in by_rule.items()},
                                    "uncovered": uncovered[:40]},
            "ast": {"accepted_programs": self.accepted, "unique_shapes": len(self.shapes), "unique_edges": len(self.edges),
                    "shapes_per_accepted": round(len(self.shapes) / self.accepted, 3) if self.accepted else 0.0},
            "path_coverage": {"available": self.trace_ok, "covered": len(self.lines), "total": total_lines,
                              "percent": round(100 * len(self.lines) / total_lines, 1) if total_lines else 0.0},
            "new_patterns_per_test": round(len(self.patterns) / n_tests, 4) if n_tests else 0.0,
            "novel_tests": sum(1 for x in self.novelty if x[0]),
            "curves": self.curves,
            "novelty": self.novelty,
        }
