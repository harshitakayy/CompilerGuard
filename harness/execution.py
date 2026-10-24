"""Run test programs against the compiler and classify the outcomes."""

from compiler.compiler import compile_code

from .analysis import error_pattern
from .dedupe import DuplicateTracker
from .oracle import compare_to_oracle, reference_check


def run_test(test, duplicates=None, patterns=None, target=None):
    """Execute one test and return the full result record.

    ``test`` needs ``id``, ``category``, ``source``, ``code`` and
    ``expected_status`` (``expected_error_type`` is optional).
    """
    code = test["code"]
    response = target.compile(code) if target is not None else compile_code(code)
    oracle = target.oracle(code) if target is not None else reference_check(code)

    duplicate_of = duplicates.add(code, test["id"]) if duplicates is not None else None

    expected = test.get("expected_status")
    actual = response["status"]
    if actual == expected:
        outcome = "CORRECT_ACCEPT" if actual == "PASS" else "CORRECT_REJECT"
    else:
        outcome = "UNEXPECTED_ACCEPT" if actual == "PASS" else "UNEXPECTED_REJECT"

    expected_type = test.get("expected_error_type")
    error_type_matched = None
    if expected_type and actual == "FAIL" and expected == "FAIL":
        error_type_matched = response.get("type") == expected_type

    reasons = compare_to_oracle(response, oracle)
    if reasons:
        adjudication = "POTENTIAL_COMPILER_BUG"
    elif outcome.startswith("UNEXPECTED"):
        adjudication = "EXPECTATION_REVISED_BY_ORACLE"
    else:
        adjudication = "CONSISTENT"

    pattern = error_pattern(response)
    new_pattern = patterns.observe(pattern, test["id"]) if patterns is not None else None

    record = dict(test)
    record.update(
        {
            "actual_status": actual,
            "compiler_response": response,
            "oracle": oracle,
            "outcome": outcome,
            "expectation_matched": actual == expected,
            "error_type_matched": error_type_matched,
            "adjudication": adjudication,
            "potential_compiler_bug": bool(reasons),
            "bug_reasons": reasons,
            "error_pattern": pattern,
            "error_pattern_raw": error_pattern(response, normalized=False),
            "new_pattern": new_pattern,
            "duplicate_of": duplicate_of,
        }
    )
    return record


def run_tests(tests, duplicates=None, patterns=None, target=None):
    return [run_test(t, duplicates, patterns, target) for t in tests]


def new_trackers():
    from .analysis import PatternTracker

    return DuplicateTracker(), PatternTracker()
