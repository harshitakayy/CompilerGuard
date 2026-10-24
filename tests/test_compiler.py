import json
import random

import pytest

from compiler.compiler import compile_code
from compiler.lexer import Lexer
from compiler.parser import MAX_NESTING_DEPTH, Parser

PASS = {"status": "PASS"}


def fail(kind, line, column, message):
    return {"status": "FAIL", "type": kind, "line": line, "column": column, "message": message}


def ast_repr(source):
    return repr(Parser(Lexer(source).tokenize()).parse_program())


# -- valid programs -------------------------------------------------------
@pytest.mark.parametrize(
    "source",
    [
        "x = 10 + 5;",
        "x = 1;\ny = x * 2;\nz = (y + 4) / 2;",
        "x=1;y=x+2;",
        "x = ((((1))));",
        "a = 1;  a = a + 1;",  # reassignment may use the old value
        "_v = 007;",
        "total_1 = 5 - 3 - 1;",
        "x = 1; y = 2;\n\n\tz = x + y;",
    ],
)
def test_valid_programs_pass(source):
    assert compile_code(source) == PASS


@pytest.mark.parametrize("source", ["", "   ", "\n\t\r\n"])
def test_empty_program_is_valid(source):
    # program -> statement* admits zero statements
    assert compile_code(source) == PASS


# -- precedence and associativity ------------------------------------------
def test_multiplication_binds_tighter_than_addition():
    assert ast_repr("x = 1 + 2 * 3;") == (
        "Program([Assignment(x = BinOp(Number(1) + BinOp(Number(2) * Number(3))))])"
    )


def test_parentheses_override_precedence():
    assert "BinOp(BinOp(Number(1) + Number(2)) * Number(3))" in ast_repr("x = (1 + 2) * 3;")


def test_subtraction_and_division_are_left_associative():
    assert "BinOp(BinOp(Number(8) - Number(3)) - Number(2))" in ast_repr("x = 8 - 3 - 2;")
    assert "BinOp(BinOp(Number(8) / Number(4)) / Number(2))" in ast_repr("x = 8 / 4 / 2;")


# -- nesting ---------------------------------------------------------------
def test_nesting_at_limit_is_accepted():
    n = MAX_NESTING_DEPTH
    assert compile_code("x = " + "(" * n + "1" + ")" * n + ";") == PASS


def test_nesting_beyond_limit_is_a_structured_syntax_error():
    n = MAX_NESTING_DEPTH + 1
    result = compile_code("x = " + "(" * n + "1" + ")" * n + ";")
    assert result["type"] == "SYNTAX_ERROR"
    assert "nesting" in result["message"]


def test_extreme_nesting_does_not_crash():
    result = compile_code("x = " + "(" * 50000)
    assert result["status"] == "FAIL" and result["type"] != "INTERNAL_ERROR"


# -- structured errors with exact positions --------------------------------
@pytest.mark.parametrize(
    "source,expected",
    [
        ("x = + 10;", fail("SYNTAX_ERROR", 1, 5, "Expected expression but got PLUS")),
        ("x = 10", fail("SYNTAX_ERROR", 1, 7, "Expected SEMICOLON but got EOF")),
        ("x = 10 +;", fail("SYNTAX_ERROR", 1, 9, "Expected expression but got SEMICOLON")),
        ("x = (10 + 5;", fail("SYNTAX_ERROR", 1, 12, "Expected RPAREN but got SEMICOLON")),
        ("x = 10 + 5);", fail("SYNTAX_ERROR", 1, 11, "Expected SEMICOLON but got RPAREN")),
        ("x 10;", fail("SYNTAX_ERROR", 1, 3, "Expected ASSIGN but got NUMBER")),
        ("= 5;", fail("SYNTAX_ERROR", 1, 1, "Expected ID but got ASSIGN")),
        ("x = ();", fail("SYNTAX_ERROR", 1, 6, "Expected expression but got RPAREN")),
        ("x = 1;;", fail("SYNTAX_ERROR", 1, 7, "Expected ID but got SEMICOLON")),
        ("x = 5 $ 3;", fail("LEXICAL_ERROR", 1, 7, "Unexpected character '$'")),
        ("x = 1.5;", fail("LEXICAL_ERROR", 1, 6, "Unexpected character '.'")),
        ("x = 1;\ny = z;", fail("SEMANTIC_ERROR", 2, 5, "Variable 'z' is undefined")),
        ("x = x + 1;", fail("SEMANTIC_ERROR", 1, 5, "Variable 'x' is undefined")),
        ("x = 1;\ny = 2 +;", fail("SYNTAX_ERROR", 2, 8, "Expected expression but got SEMICOLON")),
        ("x = 1;\r\ny = ;", fail("SYNTAX_ERROR", 2, 5, "Expected expression but got SEMICOLON")),
        ("a = 1; b = c + d;", fail("SEMANTIC_ERROR", 1, 12, "Variable 'c' is undefined")),
    ],
)
def test_error_responses(source, expected):
    assert compile_code(source) == expected


def test_error_reporting_is_reproducible():
    source = "x = (1 + ;"
    assert compile_code(source) == compile_code(source)


def test_phase_ordering_lexical_before_syntax_before_semantic():
    assert compile_code("x = y @")["type"] == "LEXICAL_ERROR"
    assert compile_code("x = y; z = ;")["type"] == "SYNTAX_ERROR"
    assert compile_code("x = y;")["type"] == "SEMANTIC_ERROR"


# -- language boundary -----------------------------------------------------
@pytest.mark.parametrize("source", ["x = ²;", "é = 1;", "x = ١٢;", "x = 1\u00a0+ 2;", "x = ＋1;"])
def test_language_is_ascii_only(source):
    assert compile_code(source)["type"] == "LEXICAL_ERROR"


@pytest.mark.parametrize(
    "source,message",
    [
        ("if = 1;", "Expected ID but got IF"),
        ("x = 1 == 2;", "Expected SEMICOLON but got EQ"),
        ("x = {1};", "Expected expression but got LBRACE"),
        ("while (x) { y = 1; }", "Expected ID but got WHILE"),
    ],
)
def test_reserved_constructs_are_rejected_not_supported(source, message):
    result = compile_code(source)
    assert result["type"] == "SYNTAX_ERROR" and result["message"] == message


# -- robustness ------------------------------------------------------------
def test_non_string_input_returns_structured_failure():
    for bad in (None, 5, b"x = 1;", ["x = 1;"]):
        assert compile_code(bad)["type"] == "INVALID_INPUT"


def test_output_contract_keys():
    assert set(compile_code("x = ;")) == {"status", "type", "line", "column", "message"}
    assert compile_code("x = 1;") == PASS


def test_random_garbage_never_crashes_the_compiler():
    rng = random.Random(1234)
    alphabet = list("xyz019 \n\t\r=+-*/();@$é²{}<>!.\"'\\") + ["if", "while", "==", "\u0000", "💥"]
    for _ in range(3000):
        source = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 40)))
        result = compile_code(source)
        assert result["status"] in ("PASS", "FAIL")
        assert result.get("type") != "INTERNAL_ERROR", repr(source)


def test_internal_errors_are_caught_and_reported(monkeypatch):
    import compiler.compiler as module

    class Exploding:
        def __init__(self, *_):
            pass

        def parse_program(self):
            raise RuntimeError("boom")

    monkeypatch.setattr(module, "Parser", Exploding)
    result = compile_code("x = 1;")
    assert result["type"] == "INTERNAL_ERROR" and "boom" in result["message"]


# -- lexer / AST details ---------------------------------------------------
def test_token_positions():
    tokens = Lexer("x = 10;\n  y").tokenize()
    got = [(t.type, t.line, t.column) for t in tokens]
    assert got == [
        ("ID", 1, 1), ("ASSIGN", 1, 3), ("NUMBER", 1, 5), ("SEMICOLON", 1, 7),
        ("ID", 2, 3), ("EOF", 2, 4),
    ]


def test_lexer_can_be_reused():
    lexer = Lexer("x = 1;")
    assert len(lexer.tokenize()) == len(lexer.tokenize())


def test_ast_is_json_serialisable():
    tree = Parser(Lexer("x = 1 + y;").tokenize()).parse_program().to_dict()
    assert json.loads(json.dumps(tree))["statements"][0]["identifier"] == "x"
