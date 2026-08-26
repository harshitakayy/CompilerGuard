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
    # 3. Collect compiler failures
    # ------------------------------------

    failures = []

    for result in invalid_results:

        if result["actual"] == "FAIL":

            error = result["result"]

            failures.append({
                "code": result["code"],
                "type": error.get("type"),
                "message": error.get("message")
            })

    # ------------------------------------
    # 4. AI-guided generation
    # ------------------------------------

    if failures:

        print_section("AI-GUIDED TESTING")

        print(f"Compiler errors collected : {len(failures)}")
        print("Sending error patterns to AI...")

        ai_tests = generate_targeted_tests(failures, 5)

        print(f"Targeted tests generated  : {len(ai_tests)}")

        # --------------------------------
        # 5. Run AI-generated tests
        # --------------------------------

        ai_test_objects = []

        for test in ai_tests:

            ai_test_objects.append({
                "code": test,
                "expected": "FAIL"
            })

        ai_results = run_tests(ai_test_objects)

        print()
        print("AI-generated test results:")

        for i, result in enumerate(ai_results, 1):

            compiler_result = result["result"]

            if compiler_result["status"] == "FAIL":

                print(
                    f"AI Test #{i} -> "
                    f"{compiler_result.get('type')}"
                )

            else:

                print(f"AI Test #{i} -> PASS")

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

    if failures:
        print(f"AI tests generated      : {len(ai_tests)}")
        print(f"Errors given to AI      : {len(failures)}")

    print("========================================")