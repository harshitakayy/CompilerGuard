import re

from compiler.compiler import compile_code
from generator.generator import GrammarGenerator, generate_tests
from harness.dedupe import canonical_form
from harness.oracle import reference_check


def test_same_seed_gives_identical_programs():
    a = [t["code"] for t in generate_tests(30, seed=7)]
    b = [t["code"] for t in generate_tests(30, seed=7)]
    assert a == b


def test_different_seeds_give_different_programs():
    a = [t["code"] for t in generate_tests(30, seed=7)]
    b = [t["code"] for t in generate_tests(30, seed=8)]
    assert a != b


def test_every_generated_program_is_accepted_by_compiler_and_oracle():
    for seed in range(20):
        for test in generate_tests(25, seed=seed):
            assert compile_code(test["code"]) == {"status": "PASS"}, test["code"]
            assert reference_check(test["code"]) == {"status": "PASS"}


def test_count_is_configurable_and_programs_are_unique():
    for count in (1, 10, 80):
        tests = generate_tests(count, seed=3)
        assert len(tests) == count
        assert len({canonical_form(t["code"]) for t in tests}) == count


def test_records_are_structured():
    test = generate_tests(1, seed=5)[0]
    assert test["category"] == "valid" and test["source"] == "grammar_generator"
    assert test["expected_status"] == "PASS" and test["expected_basis"] == "grammar_construction"
    assert test["provenance"]["seed"] == 5 and test["id"] == "valid-001"


def test_nesting_depth_is_bounded():
    def depth(code):
        best = current = 0
        for ch in code:
            current += ch == "("
            best = max(best, current)
            current -= ch == ")"
        return best

    for max_depth in (0, 1, 2):
        gen = GrammarGenerator(seed=1, max_depth=max_depth)
        assert all(depth(t["code"]) <= max_depth for t in gen.generate_unique_programs(60))


def test_no_literal_zero_divisor():
    for test in generate_tests(200, seed=2):
        assert not re.search(r"/\s*0+\b", test["code"])


def test_output_varies_in_layout_and_size():
    tests = generate_tests(60, seed=11)
    assert len({t["provenance"]["style"] for t in tests}) == 3
    assert len({t["provenance"]["statements"] for t in tests}) > 2
    assert any("\n" in t["code"] for t in tests)


def test_exclusion_set_is_respected():
    first = generate_tests(10, seed=4)
    exclude = {canonical_form(t["code"]) for t in first}
    again = GrammarGenerator(seed=4).generate_unique_programs(10, exclude=exclude)
    assert not exclude & {canonical_form(t["code"]) for t in again}


def test_generator_does_not_touch_global_random_state():
    import random

    random.seed(123)
    expected = random.random()
    random.seed(123)
    generate_tests(20, seed=1)
    assert random.random() == expected
