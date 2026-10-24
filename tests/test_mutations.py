import pytest

from compiler.compiler import compile_code
from generator.generator import generate_tests
from generator.mutations import (
    SEMANTIC_OPERATORS,
    SYNTAX_OPERATORS,
    MutationEngine,
    canonical,
    generate_invalid_tests,
    mutate_test,
)
from harness.oracle import reference_check

PARENTS = generate_tests(60, seed=2024)


@pytest.mark.parametrize("name", list(SYNTAX_OPERATORS) + list(SEMANTIC_OPERATORS))
def test_each_operator_causes_its_intended_error(name):
    table = {**SYNTAX_OPERATORS, **SEMANTIC_OPERATORS}
    intended = table[name][1]
    engine = MutationEngine(seed=1)
    applied = 0
    for parent in PARENTS:
        mutated = engine.mutate(parent["code"], name)
        if mutated is None or mutated == parent["code"]:
            continue
        applied += 1
        result = compile_code(mutated)
        assert result["status"] == "FAIL", (name, mutated)
        assert result["type"] == intended, (name, mutated, result)
        assert reference_check(mutated)["type"] == intended
    assert applied > 0, f"operator {name} never applied"


def test_same_seed_same_mutants():
    a = generate_invalid_tests(PARENTS, 40, seed=5, semantic_ratio=0.25)
    b = generate_invalid_tests(PARENTS, 40, seed=5, semantic_ratio=0.25)
    assert [t["code"] for t in a] == [t["code"] for t in b]


def test_mutants_are_unique_and_never_equal_a_parent():
    tests = generate_invalid_tests(PARENTS, 80, seed=1, semantic_ratio=0.2)
    keys = [canonical(t["code"]) for t in tests]
    assert len(keys) == len(set(keys)) == 80
    assert not set(keys) & {canonical(p["code"]) for p in PARENTS}


def test_records_track_operator_and_intent():
    for t in generate_invalid_tests(PARENTS, 20, seed=3, semantic_ratio=0.3):
        assert t["source"] == "mutation" and t["expected_status"] == "FAIL"
        assert t["expected_basis"] == "mutation_intent"
        assert t["provenance"]["operator"] and t["provenance"]["parent_id"]
        assert t["category"] in ("invalid_syntax", "invalid_semantic")


def test_semantic_ratio_splits_categories_and_prefix_keeps_the_mix():
    tests = generate_invalid_tests(PARENTS, 40, seed=9, semantic_ratio=0.25)
    assert sum(t["category"] == "invalid_semantic" for t in tests) == 10
    assert any(t["category"] == "invalid_semantic" for t in tests[:15])


def test_syntax_only_by_default():
    tests = generate_invalid_tests(PARENTS, 30, seed=1)
    assert all(t["category"] == "invalid_syntax" for t in tests)


def test_generation_is_diverse():
    tests = generate_invalid_tests(PARENTS, 45, seed=1, semantic_ratio=0.2)
    assert len({t["provenance"]["operator"] for t in tests}) >= 20


def test_generation_is_bounded_when_few_mutants_exist():
    engine = MutationEngine(seed=1)
    tests = engine.generate([{"id": "p", "code": "x = 1;"}], 5000)
    assert 0 < len(tests) < 5000
    assert engine.shortfall > 0


def test_exclude_prevents_overlap_with_other_tests():
    first = generate_invalid_tests(PARENTS, 20, seed=1)
    second = generate_invalid_tests(
        PARENTS, 20, seed=1, exclude={canonical(t["code"]) for t in first}
    )
    assert not {canonical(t["code"]) for t in first} & {canonical(t["code"]) for t in second}


def test_mutate_test_changes_the_program():
    import random

    assert mutate_test("x = 1 + 2;", random.Random(1)) != "x = 1 + 2;"
    assert mutate_test("", random.Random(1)) == ""


def test_accepts_plain_string_parents():
    tests = generate_invalid_tests(["x = 1 + 2;", "y = (3);"], 6, seed=1)
    assert tests and all(compile_code(t["code"])["status"] == "FAIL" for t in tests)
