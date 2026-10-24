import pytest

from compiler.compiler import compile_code
from grammarkit.earley import EarleyParser
from grammarkit.generate import SentenceGenerator, render
from grammarkit.grammar import Grammar, GrammarError
from grammarkit.lexer import LexError, Lexer
from grammarkit.mutate import SmartMutator
from grammarkit.rdparser import PegParser
from harness.execution import run_test
from lab.targets import GRAMMAR_DIR, GrammarTarget, get_preset

CALC = "expr -> term (('+'|'-') term)*\nterm -> factor (('*'|'/') factor)*\nfactor -> NUMBER | ID | '(' expr ')'\n"


def kinds(g, src):
    return [t.kind for t in Lexer(g).tokenize(src)[:-1]]


# -- grammar notation ---------------------------------------------------------
def test_ebnf_is_desugared_into_countable_productions():
    g = Grammar(CALC)
    assert g.start == "expr" and [r[0] for r in g.source_rules] == ["expr", "term", "factor"]
    assert len(g.alts) == 13 and {"+", "-", "*", "/", "(", ")"} <= set(g.terminals)
    assert set(g.classes) == {"NUMBER", "ID"} and g.label(0).startswith("expr →")


def test_alternatives_on_continuation_lines_and_comments():
    g = Grammar("# comment\na -> 'x' // trailing\n   | 'y'\n  | b\nb -> 'z' # more\n")
    assert len(g.rule_alts["a"]) == 3 and g.terminals == ["x", "y", "z"]


@pytest.mark.parametrize("text,fragment,line", [
    ("a -> b", "Undefined nonterminal 'b'", 1),
    ("a -> 'x'\na -> 'y'", "defined twice", 2),
    ("a -> ('x'", "Missing ')'", 1),
    ("a -> 'x')", "Unbalanced", 1),
    ("ID -> 'x'", "built-in", 1),
    ("", "no rules", None),
    ("a -> a 'x'", "cannot derive", 1),
    ("a -> *", "repetition operator", 1),
    ("%bogus x\na -> 'x'", "Unknown directive", 1),
    ("a -> 'unterminated", "unterminated", 1),
    ("just text", "Expected a rule", 1),
])
def test_grammar_errors_report_line_numbers(text, fragment, line):
    with pytest.raises(GrammarError) as e:
        Grammar(text)
    assert fragment.lower() in e.value.message.lower() and e.value.line == line


def test_grammar_warnings():
    w = lambda text: " ".join(x["message"] for x in Grammar(text).warnings)
    assert "left-recursive" in w("E -> E '+' T | T\nT -> NUMBER")
    assert "unreachable" in w("a -> 'x'\nb -> 'y'")
    assert "Ordered-choice hazard" in w("a -> 'x' | 'x' 'y'")
    assert Grammar(CALC).warnings == []


# -- lexer ---------------------------------------------------------------------
def test_lexer_positions_comments_keywords_and_literals():
    g = Grammar((GRAMMAR_DIR / "cpp_subset.gr").read_text())
    toks = Lexer(g).tokenize('#include <x>\n// c\nint /* m */ x = "s" + \'c\' + 1.5;')
    assert [t.kind for t in toks] == ["int", "ID", "=", "STRING", "+", "CHAR", "+", "NUMBER", ";", "EOF"]
    assert (toks[0].line, toks[0].col) == (3, 1)


@pytest.mark.parametrize("src,msg", [("x = é", "Unexpected character"), ("x = @", "Unexpected character '@'")])
def test_lexer_rejects_unknown_characters(src, msg):
    with pytest.raises(LexError) as e:
        Lexer(Grammar("a -> ID '=' ID")).tokenize(src)
    assert msg in e.value.message


def test_lexer_unterminated_constructs():
    g = Grammar((GRAMMAR_DIR / "cpp_subset.gr").read_text())
    for src in ['"abc', "/* never closed", "'ab'"]:
        with pytest.raises(LexError):
            Lexer(g).tokenize(src)


def test_number_option_controls_decimals():
    ints, floats = Grammar("%number int\na -> NUMBER"), Grammar("a -> NUMBER")
    assert [t.kind for t in Lexer(floats).tokenize("1.5")[:-1]] == ["NUMBER"]
    with pytest.raises(LexError):  # '.' is not part of an integer-only language
        Lexer(ints).tokenize("1.5")


# -- Earley oracle ---------------------------------------------------------------
def test_earley_accepts_rejects_and_reports_expected_tokens():
    g = Grammar(CALC)
    ep = EarleyParser(g)
    assert ep.parse(kinds(g, "1 + 2 * ( x - 3 )")).ok
    bad = ep.parse(kinds(g, "1 + * 2"))
    assert not bad.ok and bad.error_index == 2 and {"NUMBER", "ID", "("} <= bad.expected
    unfinished = ep.parse(kinds(g, "1 +"))
    assert not unfinished.ok and unfinished.error_index == 2


def test_earley_handles_left_recursion_nullable_and_ambiguity():
    lr = Grammar("E -> E '+' T | T\nT -> NUMBER")
    assert EarleyParser(lr).parse(["NUMBER", "+", "NUMBER", "+", "NUMBER"]).ok
    nul = Grammar("s -> a 'x' b\na -> 'p'?\nb -> 'q'*")
    ep = EarleyParser(nul)
    assert ep.parse(["x"]).ok and ep.parse(["p", "x", "q", "q"]).ok and not ep.parse(["q", "x"]).ok
    amb = Grammar("s -> s s | 'a'")
    assert EarleyParser(amb).parse(["a"] * 5).ok


def test_earley_tree_and_partial_production_coverage():
    g = Grammar(CALC)
    ep = EarleyParser(g)
    res = ep.parse(kinds(g, "1 + 2"))
    assert res.tree.name == "expr" and res.tree.lo == 0 and res.tree.hi == 3
    rejected = ep.parse(kinds(g, "1 + * 2"))
    assert rejected.completed, "productions completed before the error still count"


# -- generated PEG parser vs Earley --------------------------------------------------
@pytest.mark.parametrize("name", ["calc", "json", "cpp_subset"])
def test_peg_parser_matches_earley_on_peg_safe_grammars(name):
    t = GrammarTarget((GRAMMAR_DIR / f"{name}.gr").read_text())
    for seed in range(3):
        parents = t.valid_programs(15, seed)
        assert len(parents) >= 10
        for test in parents + SmartMutator(t, seed).generate(parents, 60):
            r = run_test(test, target=t)
            assert not r["potential_compiler_bug"], (name, test["code"], r["compiler_response"], r["oracle"])


def test_ordered_choice_hazard_is_detected_as_a_bug_signal():
    t = get_preset("hazard")
    r = run_test({"id": "h", "category": "x", "source": "x", "code": "a b x", "expected_status": "PASS"}, target=t)
    assert r["oracle"]["status"] == "PASS" and r["compiler_response"]["status"] == "FAIL"
    assert r["potential_compiler_bug"] and "STATUS_MISMATCH" in r["bug_reasons"]


def test_left_recursive_grammar_exposes_the_generated_parser_limitation():
    t = GrammarTarget("E -> E '+' NUMBER | NUMBER")
    r = run_test({"id": "l", "category": "x", "source": "x", "code": "1 + 2", "expected_status": "PASS"}, target=t)
    assert r["potential_compiler_bug"] and t.grammar.left_recursive == ["E"]


# -- generation -------------------------------------------------------------------------
@pytest.mark.parametrize("pid", ["cglang", "cpp", "calc", "json"])
def test_valid_programs_are_accepted_by_compiler_and_oracle(pid):
    t = get_preset(pid)
    programs = t.valid_programs(20, seed=3)
    assert len(programs) == 20 and len({t.canonical(p["code"]) for p in programs}) == 20
    for p in programs:
        assert t.compile(p["code"])["status"] == "PASS" and t.oracle(p["code"])["status"] == "PASS", p["code"]


def test_generation_is_deterministic_and_coverage_directed():
    g = Grammar((GRAMMAR_DIR / "cpp_subset.gr").read_text())
    a = [render(SentenceGenerator(g, seed=4).sentence()) for _ in range(1)]
    b = [render(SentenceGenerator(g, seed=4).sentence()) for _ in range(1)]
    assert a == b
    gen = SentenceGenerator(g, seed=1)
    for _ in range(60):
        gen.sentence()
    assert len(gen.cover) > 0.6 * len(g.alts)


@pytest.mark.parametrize("src,ok", [
    ("int main() { return 0; }", True),
    ("int x = 1, *p = 0, a[10];", True),
    ("class A { public: int f(int a) { return a; } private: int z; };", True),
    ("namespace n { using namespace std; }", True),
    ("void f() { if (a) b = 1; else { c(); } while (x) { x--; } do { x++; } while (x < 3); }", True),
    ("void f() { for (int i = 0; i < 10; i++) { continue; } switch (x) { case 1: break; default: x = 2; } }", True),
    ("int f() { return a ? b : c || d && e | f ^ g & h == i < j << k + l * -m; }", True),
    ("void f() { cout << \"hi\" << endl; p->q.r[2](1, 2); }", True),
    ("int main() { return 0 }", False),
    ("int main( { }", False),
    ("int 5x;", False),
    ("void f() { if x { } }", False),
    ("int f() { return (1 + ; }", False),
])
def test_cpp_subset_grammar(src, ok):
    assert get_preset("cpp").compile(src)["status"] == ("PASS" if ok else "FAIL")


# -- targets ---------------------------------------------------------------------------
def test_grammar_target_error_contract_and_messages():
    t = GrammarTarget(CALC)
    r = t.compile("1 + * 2")
    assert r["status"] == "FAIL" and r["type"] == "SYNTAX_ERROR" and (r["line"], r["column"]) == (1, 5)
    assert "Unexpected '*'" in r["message"] and "NUMBER" in r["message"]
    assert t.compile("1 + 2 $")["type"] == "LEXICAL_ERROR"
    assert "end of input" in t.compile("1 +")["message"]


def test_cglang_target_uses_the_handwritten_compiler_and_traces_lines():
    t = get_preset("cglang")
    assert t.compile("x = ;") == compile_code("x = ;")
    resp, lines = t.compile_traced("x = 1 + 2;")
    assert resp == {"status": "PASS"} and lines and t.total_lines() > 50
    assert len(lines & t.exec_lines()) < t.total_lines()


def test_grammar_target_traces_the_generated_parser():
    t = GrammarTarget(CALC)
    _, lines = t.compile_traced("1 + 2")
    assert lines and all(f in t.files for f, _ in lines)


# -- smart mutator ----------------------------------------------------------------------
@pytest.mark.parametrize("pid", ["cglang", "cpp", "calc", "json"])
def test_smart_mutator_is_deterministic_unique_and_diverse(pid):
    t = get_preset(pid)
    parents = t.valid_programs(20, 1)
    a = SmartMutator(t, 5).generate(parents, 60)
    b = SmartMutator(t, 5).generate(parents, 60)
    assert [x["code"] for x in a] == [x["code"] for x in b] and len(a) == 60
    assert len({t.canonical(x["code"]) for x in a}) == 60
    assert len({x["provenance"]["operator"] for x in a}) >= 15
    assert all(x["expected_basis"] == "oracle" and x["category"] == "smart_mutation" for x in a)


def test_regenerate_subtree_preserves_validity_and_unexpected_token_is_rejected():
    for pid in ("calc", "json", "cpp"):
        t = get_preset(pid)
        m, parents = SmartMutator(t, 2), t.valid_programs(15, 2)
        regen = [m.mutate(p["code"], "regenerate_subtree") for p in parents]
        assert all(r is None or t.oracle(r)["status"] == "PASS" for r in regen)
        unexpected = [m.mutate(p["code"], "insert_unexpected_token") for p in parents]
        assert all(u is None or t.oracle(u)["status"] == "FAIL" for u in unexpected)


def test_mutation_generation_is_bounded():
    t = get_preset("json")
    m = SmartMutator(t, 1)
    out = m.generate([{"id": "p", "code": "null"}], 5000)
    assert 0 < len(out) < 5000
