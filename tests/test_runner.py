import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from compiler.compiler import compile_code
from generator.generator import generate_tests
from generator.mutations import generate_invalid_tests
from ai.ai_generator import generate_targeted_tests


def run_tests(tests):
    results = []

    for test in tests:
        code = test["code"]
        expected = test["expected"]

        result = compile_code(code)
        actual = result["status"]

        results.append({
            "code": code,
            "expected": expected,
            "actual": actual,
            "result": result,
            "passed": actual == expected
        })

    return results


def collect_errors(results):
    errors = []

    for result in results:
        compiler_result = result["result"]

        if compiler_result["status"] == "FAIL":
            errors.append({
                "code": result["code"],
                "type": compiler_result.get("type"),
                "message": compiler_result.get("message")
            })

    return errors


def print_section(title):
    print()
    print("========== " + title + " ==========")


def print_test_summary(results):
    passed = sum(1 for result in results if result["passed"])
    failed = len(results) - passed

    print(f"Total Tests : {len(results)}")
    print(f"Correct     : {passed}")
    print(f"Incorrect   : {failed}")

    return passed, failed


def analyze_errors(errors):

    patterns = {}

    for error in errors:

        error_type = error.get("type", "UNKNOWN")
        message = error.get("message", "UNKNOWN")

        key = error_type + ": " + message

        if key not in patterns:
            patterns[key] = 0

        patterns[key] += 1

    return patterns


def print_error_patterns(errors):

    patterns = analyze_errors(errors)

    print()
    print("========== ERROR PATTERNS ==========")

    if not patterns:
        print("No compiler errors found.")
        return

    for pattern, count in patterns.items():
        print(f"{count} -> {pattern}")


def calculate_novelty(results, known_patterns, known_tests):

    new_tests = 0
    repeated_tests = 0

    new_patterns = 0
    repeated_patterns = 0

    round_patterns = set()

    for result in results:

        code = result["code"]

        compiler_result = result["result"]

        if code in known_tests:
            repeated_tests += 1
        else:
            new_tests += 1

        if compiler_result["status"] == "FAIL":

            error_type = compiler_result.get("type", "UNKNOWN")
            message = compiler_result.get("message", "UNKNOWN")

            pattern = error_type + ": " + message

            round_patterns.add(pattern)

    for pattern in round_patterns:

        if pattern in known_patterns:
            repeated_patterns += 1
        else:
            new_patterns += 1

    return new_tests, repeated_tests, new_patterns, repeated_patterns


def print_novelty(
    new_tests,
    repeated_tests,
    new_patterns,
    repeated_patterns
):

    print()
    print("---------- NOVELTY ANALYSIS ----------")

    print(f"New tests              : {new_tests}")
    print(f"Repeated tests         : {repeated_tests}")
    print(f"New error patterns     : {new_patterns}")
    print(f"Repeated error patterns: {repeated_patterns}")


if __name__ == "__main__":

    print()
    print("========================================")
    print("          COMPILERGUARD")
    print("   AI-GUIDED COMPILER TESTING")
    print("========================================")

    valid_tests = generate_tests(10)
    valid_results = run_tests(valid_tests)

    print_section("VALID TESTING")

    valid_correct, valid_wrong = print_test_summary(valid_results)

    print("Expected: compiler should ACCEPT all")

    invalid_tests = generate_invalid_tests(valid_tests, 10)
    invalid_results = run_tests(invalid_tests)

    print_section("INVALID TESTING")

    invalid_correct, invalid_wrong = print_test_summary(invalid_results)

    print("Expected: compiler should REJECT all")

    failures = collect_errors(invalid_results)

    if failures:

        print_error_patterns(failures)

        print_section("AI-GUIDED TESTING")

        current_failures = failures

        previous_tests = []

        known_tests = set()
        known_patterns = set()

        initial_patterns = analyze_errors(failures)

        for pattern in initial_patterns:
            known_patterns.add(pattern)

        rounds = 3
        tests_per_round = 5
        round_no = 0

        for round_no in range(1, rounds + 1):

            print()
            print(f"----- AI ROUND {round_no} -----")

            print(
                f"Compiler errors given to AI : "
                f"{len(current_failures)}"
            )

            ai_tests = generate_targeted_tests(
                current_failures,
                tests_per_round,
                previous_tests
            )

            previous_tests.extend(ai_tests)

            print(
                f"Targeted tests generated     : "
                f"{len(ai_tests)}"
            )

            ai_test_objects = []

            for test in ai_tests:

                ai_test_objects.append({
                    "code": test,
                    "expected": "FAIL"
                })

            ai_results = run_tests(ai_test_objects)

            correct = sum(
                1 for result in ai_results
                if result["passed"]
            )

            unexpected = len(ai_results) - correct

            print(f"Correctly rejected           : {correct}")
            print(f"Unexpectedly accepted        : {unexpected}")

            new_tests, repeated_tests, new_patterns, repeated_patterns = calculate_novelty(
                ai_results,
                known_patterns,
                known_tests
            )

            print_novelty(
                new_tests,
                repeated_tests,
                new_patterns,
                repeated_patterns
            )

            print()
            print("AI-generated test results:")

            for i, result in enumerate(ai_results, 1):

                compiler_result = result["result"]

                if compiler_result["status"] == "FAIL":

                    print(
                        f"AI Test #{i} -> "
                        f"{compiler_result.get('type')}: "
                        f"{compiler_result.get('message')}"
                    )

                else:

                    print(
                        f"AI Test #{i} -> "
                        f"PASS"
                    )

            for test in ai_tests:
                known_tests.add(test)

            round_errors = collect_errors(ai_results)

            for error in round_errors:

                error_type = error.get("type", "UNKNOWN")
                message = error.get("message", "UNKNOWN")

                known_patterns.add(
                    error_type + ": " + message
                )

            current_failures = round_errors

            if current_failures:

                print_error_patterns(current_failures)

            if not current_failures:

                print()
                print("No new compiler errors found.")
                print("AI feedback loop stopped.")

                break

        if round_no == rounds:

            print()
            print("AI testing completed.")

    else:

        print_section("AI-GUIDED TESTING")

        print("No compiler errors detected.")
        print("AI generation skipped.")

        round_no = 0

        previous_tests = []

    print()
    print("========================================")
    print("             FINAL SUMMARY")
    print("========================================")

    print(
        f"Valid tests generated   : "
        f"{len(valid_tests)}"
    )

    print(
        f"Valid tests accepted    : "
        f"{valid_correct}"
    )

    print(
        f"Invalid tests generated : "
        f"{len(invalid_tests)}"
    )

    print(
        f"Invalid tests rejected  : "
        f"{invalid_correct}"
    )

    print(
        f"AI rounds attempted      : "
        f"{round_no}"
    )

    print(
        f"AI tests generated      : "
        f"{len(previous_tests)}"
    )

    print("========================================")