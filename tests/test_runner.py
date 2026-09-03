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


def get_failures(results):
    failures = []

    for result in results:
        if not result["passed"]:
            error = result["result"]

            failures.append({
                "code": result["code"],
                "type": error.get("type"),
                "message": error.get("message")
            })

    return failures


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


if __name__ == "__main__":

    print()
    print("========================================")
    print("          COMPILERGUARD")
    print("   AI-GUIDED COMPILER TESTING")
    print("========================================")

    # ------------------------------------
    # 1. Generate valid tests
    # ------------------------------------

    valid_tests = generate_tests(10)

    valid_results = run_tests(valid_tests)

    print_section("VALID TESTING")

    valid_correct, valid_wrong = print_test_summary(valid_results)

    print("Expected: compiler should ACCEPT all")

    # ------------------------------------
    # 2. Generate invalid tests
    # ------------------------------------

    invalid_tests = generate_invalid_tests(valid_tests, 10)

    invalid_results = run_tests(invalid_tests)

    print_section("INVALID TESTING")

    invalid_correct, invalid_wrong = print_test_summary(invalid_results)

    print("Expected: compiler should REJECT all")

    # ------------------------------------
    # 3. Collect initial compiler errors
    # ------------------------------------

    failures = collect_errors(invalid_results)

    # ------------------------------------
    # 4. AI feedback loop
    # ------------------------------------

    if failures:

        print_section("AI-GUIDED TESTING")

        current_failures = failures

        rounds = 3
        tests_per_round = 5

        for round_no in range(1, rounds + 1):

            print()
            print(f"----- AI ROUND {round_no} -----")

            print(
                f"Compiler errors given to AI : "
                f"{len(current_failures)}"
            )

            ai_tests = generate_targeted_tests(
                current_failures,
                tests_per_round
            )

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

            print(f"Correctly rejected           : {correct}")
            print(
                f"Unexpectedly accepted       : "
                f"{len(ai_results) - correct}"
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
                    print(f"AI Test #{i} -> PASS")

            # Use the new compiler errors
            # as feedback for the next AI round
            current_failures = collect_errors(ai_results)

            if not current_failures:
                print()
                print("No new compiler errors found.")
                print("AI feedback loop stopped.")
                break

    else:

        print_section("AI-GUIDED TESTING")

        print("No compiler errors detected.")
        print("AI generation skipped.")

    # ------------------------------------
    # Final summary
    # ------------------------------------

    print()
    print("========================================")
    print("             FINAL SUMMARY")
    print("========================================")

    print(f"Valid tests generated   : {len(valid_tests)}")
    print(f"Valid tests accepted    : {valid_correct}")

    print(f"Invalid tests generated : {len(invalid_tests)}")
    print(f"Invalid tests rejected  : {invalid_correct}")

    print(f"AI rounds attempted      : {round_no if failures else 0}")

    print("========================================")