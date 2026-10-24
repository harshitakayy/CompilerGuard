import random

import pytest

from compiler.compiler import compile_code
from harness.oracle import compare_to_oracle, reference_check


@pytest.mark.parametrize(
    "source,status,kind",
    [
        ("", "PASS", None),
        ("x = 1;", "PASS", None),
        ("x = (1 + 2) * y;", "SEMANTIC_ERROR", "SEMANTIC_ERROR"),
        ("x = 1 +;", "SYNTAX_ERROR", "SYNTAX_ERROR"),
        ("x = @;", "LEXICAL_ERROR", "LEXICAL_ERROR"),
        ("x = é;", "LEXICAL_ERROR", "LEXICAL_ERROR"),
    ],
)
def test_oracle_verdicts(source, status, kind):
    verdict = reference_check(source)
    if status == "PASS":
        assert verdict == {"status": "PASS"}
    else:
        assert verdict["status"] == "FAIL" and verdict["type"] == kind


def test_oracle_agrees_with_compiler_on_random_token_soup():
    rng = random.Random(99)
    pieces = ["x", "y", "z", "1", "23", "=", "+", "-", "*", "/", "(", ")", ";", " ", "\n",
              "@", "if", "{", "==", "é", "<", "!", "0", ";", "x = 1;", "y = x;"]
    for _ in range(5000):
        source = "".join(rng.choice(pieces) for _ in range(rng.randint(0, 14)))
        compiled, oracle = compile_code(source), reference_check(source)
        assert compare_to_oracle(compiled, oracle) == [], repr(source)


def test_compare_detects_each_kind_of_disagreement():
    pass_, fail_ = {"status": "PASS"}, {"status": "FAIL", "type": "SYNTAX_ERROR", "line": 1, "column": 1}
    assert compare_to_oracle(pass_, fail_) == ["STATUS_MISMATCH"]
    assert compare_to_oracle(fail_, {**fail_, "type": "LEXICAL_ERROR"}) == ["TYPE_MISMATCH"]
    assert compare_to_oracle(fail_, {**fail_, "column": 2}) == ["LOCATION_MISMATCH"]
    assert compare_to_oracle(pass_, pass_) == []
    assert "INTERNAL_ERROR" in compare_to_oracle({"status": "FAIL", "type": "INTERNAL_ERROR"}, pass_)
