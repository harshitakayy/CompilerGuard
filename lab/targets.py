"""Test targets: a compiler under test, its independent oracle and its grammar."""

import re
import sys
from collections import OrderedDict
from pathlib import Path

from compiler import compiler as _cg_compiler, lexer as _cg_lexer, parser as _cg_parser, semantic as _cg_semantic
from compiler.compiler import compile_code
from generator.generator import GrammarGenerator
from grammarkit import lexer as _gk_lexer, rdparser as _gk_rdparser
from grammarkit.earley import EarleyParser
from grammarkit.generate import SentenceGenerator, render
from grammarkit.grammar import Grammar
from grammarkit.lexer import LexError, Lexer
from grammarkit.rdparser import PegParser
from harness.oracle import reference_check
from harness.pathcov import executable_lines, trace_lines

GRAMMAR_DIR = Path(__file__).resolve().parents[1] / "grammars"
MAX_TOKENS = 400


def _fail(kind, line, col, msg):
    return {"status": "FAIL", "type": kind, "line": line, "column": col, "message": msg}


def _describe(kind):
    return "end of input" if kind == "EOF" else (kind if kind in ("ID", "NUMBER", "STRING", "CHAR") else f"'{kind}'")


class Target:
    id = name = description = notes = ""
    modules = ()

    def __init__(self, grammar_text):
        self.grammar_text = grammar_text
        self.grammar = Grammar(grammar_text)
        self.lexer = Lexer(self.grammar)
        self.earley = EarleyParser(self.grammar)
        self._cache = OrderedDict()
        self.files = [m.__file__ for m in self.modules]

    # -- analysis shared by oracle, coverage, mutation ---------------------
    def analyze(self, src):
        if src in self._cache:
            self._cache.move_to_end(src)
            return self._cache[src]
        info = {"tokens": None, "lex_error": None, "earley": None}
        try:
            toks = self.lexer.tokenize(src)
            info["tokens"] = toks
            if len(toks) > MAX_TOKENS:
                info["lex_error"] = LexError("Program too long", 1, 1)
                info["tokens"] = None
            else:
                info["earley"] = self.earley.parse([t.kind for t in toks[:-1]])
        except LexError as e:
            info["lex_error"] = e
        self._cache[src] = info
        if len(self._cache) > 4000:
            self._cache.popitem(last=False)
        return info

    def expected_after(self, kinds):
        return self.earley.parse(list(kinds), want_tree=False).expected

    def canonical(self, src):
        info = self.analyze(src)
        if info["tokens"]:
            return " ".join(t.text for t in info["tokens"][:-1])
        return " ".join(src.split())

    def oracle(self, src):
        raise NotImplementedError

    def compile(self, src):
        raise NotImplementedError

    def compile_traced(self, src):
        return trace_lines(lambda: self.compile(src), self.files)

    def total_lines(self):
        return sum(len(executable_lines(f)) for f in self.files)

    def exec_lines(self):
        out = set()
        for f in self.files:
            out |= executable_lines(f)
        return out

    def valid_programs(self, count, seed):
        gen = SentenceGenerator(self.grammar, seed=seed)
        out, seen, attempts = [], set(), 0
        while len(out) < count and attempts < count * 40 + 100:
            attempts += 1
            src = render(gen.sentence())
            key = self.canonical(src)
            if key in seen or self.oracle(src)["status"] != "PASS":
                continue
            seen.add(key)
            out.append(_valid_test(len(out) + 1, src, seed))
        return out


def _valid_test(i, code, seed):
    return {"id": f"valid-{i:03d}", "category": "valid", "source": "grammar_generator", "code": code,
            "expected_status": "PASS", "expected_basis": "grammar_construction", "provenance": {"seed": seed, "index": i}}


class GrammarTarget(Target):
    """Parser generated from a grammar (PEG) checked against Earley."""

    modules = (_gk_rdparser, _gk_lexer)

    def __init__(self, grammar_text, id="custom", name="Custom grammar", description="", notes=""):
        super().__init__(grammar_text)
        self.id, self.name, self.description = id, name, description
        self.notes = notes or self._default_notes()
        self.peg = PegParser(self.grammar)

    def _default_notes(self):
        g = self.grammar
        return ("- Programs are sequences of tokens separated by whitespace.\n"
                f"- Terminals: {', '.join(g.terminals[:60])}\n- Token classes: {', '.join(g.classes) or 'none'}\n"
                "- Error classes reported: LEXICAL_ERROR (bad character), SYNTAX_ERROR (message names the unexpected token and the expected ones).\n"
                "- Programs must not contain characters outside the token set unless you want to test lexical errors.")

    def _syntax_error(self, toks, idx, expected):
        tok = toks[min(idx, len(toks) - 1)]
        exp = ", ".join(sorted(_describe(e) for e in expected)[:8]) or "nothing"
        return _fail("SYNTAX_ERROR", tok.line, tok.col, f"Unexpected {_describe(tok.kind)}; expected {exp}")

    def compile(self, src):
        info = self.analyze(src)
        if info["lex_error"]:
            e = info["lex_error"]
            return _fail("LEXICAL_ERROR", e.line, e.col, e.message)
        toks = info["tokens"]
        try:
            ok, idx, expected = self.peg.parse([t.kind for t in toks[:-1]])
        except RecursionError:
            return _fail("INTERNAL_ERROR", None, None, "RecursionError: parser stack exhausted")
        return {"status": "PASS"} if ok else self._syntax_error(toks, idx, expected)

    def oracle(self, src):
        info = self.analyze(src)
        if info["lex_error"]:
            e = info["lex_error"]
            return _fail("LEXICAL_ERROR", e.line, e.col, e.message)
        res = info["earley"]
        return {"status": "PASS"} if res.ok else self._syntax_error(info["tokens"], res.error_index, res.expected)


class CGLangTarget(Target):
    id, name = "cglang", "CG-Lang"
    description = "The course language, compiled by the hand-written lexer, parser and semantic analyser."
    modules = (_cg_compiler, _cg_lexer, _cg_parser, _cg_semantic)
    notes = None

    def __init__(self):
        super().__init__((GRAMMAR_DIR / "cglang.gr").read_text(encoding="utf-8"))

    def compile(self, src):
        return compile_code(src)

    def oracle(self, src):
        return reference_check(src)

    def valid_programs(self, count, seed):
        tests = GrammarGenerator(seed=seed).generate_unique_programs(count)
        for t in tests:
            t["provenance"]["seed"] = seed
        return tests


PRESETS = OrderedDict([
    ("cglang", ("CG-Lang", "cglang", "Assignments and arithmetic with undefined-variable checking: the original course language, tested through its hand-written compiler.")),
    ("cpp", ("C++ subset", "cpp_subset", "Namespaces, classes, functions, declarations, control flow and the full C++ expression-precedence ladder, parsed by a generated parser.")),
    ("calc", ("Calculator", "calc", "A tiny expression grammar: the quickest way to see the machinery.")),
    ("json", ("JSON-like", "json", "Objects, arrays, strings, numbers and literals.")),
    ("hazard", ("Ordered-choice hazard", "hazard", "A deliberately PEG-hostile grammar: watch the oracle raise bug signals.")),
])

_CPP_NOTES = ("- This is a subset of C++: namespaces, classes/structs with access specifiers, functions, declarations with pointers/references/arrays, if/else, switch, while, do-while, for, return/break/continue, and all expression operators.\n"
              "- Not supported: templates, user-defined types as declaration types, casts, lambdas, new/delete, overloading.\n"
              "- Types are builtin keywords (int float double char bool void auto long short string). Comments and #include lines are ignored.\n"
              "- Error classes: LEXICAL_ERROR (bad character, unterminated string/comment), SYNTAX_ERROR (message names the unexpected token and the expected ones).")
_targets = {}


def get_preset(preset_id):
    if preset_id not in PRESETS:
        raise KeyError(preset_id)
    if preset_id not in _targets:
        if preset_id == "cglang":
            _targets[preset_id] = CGLangTarget()
        else:
            nm, fn, desc = PRESETS[preset_id]
            text = (GRAMMAR_DIR / f"{fn}.gr").read_text(encoding="utf-8")
            _targets[preset_id] = GrammarTarget(text, preset_id, nm, desc, _CPP_NOTES if preset_id == "cpp" else "")
    return _targets[preset_id]


def preset_info():
    out = []
    for pid, (nm, fn, desc) in PRESETS.items():
        out.append({"id": pid, "name": nm, "description": desc, "grammar": (GRAMMAR_DIR / f"{fn}.gr").read_text(encoding="utf-8")})
    return out
