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

        passed = actual == expected

        results.append({
            "code": code,
            "expected": expected,
            "actual": actual,
            "result": result,
            "passed": passed
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


def print_results(results):

    passed = 0
    failed = 0

    for i, result in enumerate(results, 1):

        if result["passed"]:
            print(f"Test #{i}   PASS")
            passed += 1

        else:
            error = result["result"]

            print(
                f"Test #{i}   FAIL - "
                f"{error.get('type', 'UNKNOWN_ERROR')}: "
                f"{error.get('message', '')}"
            )

            failed += 1

    print()
    print("================================")
    print(f"Total:  {len(results)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print("================================")


if __name__ == "__main__":

    print("========== COMPILERGUARD ==========")
    print()

    # Step 1: Generate normal valid tests
    valid_tests = generate_tests(10)

    # Step 2: Generate deliberately invalid tests
    invalid_tests = generate_invalid_tests(valid_tests, 10)

    # Step 3: Combine tests
    all_tests = valid_tests + invalid_tests

    # Step 4: Run tests through compiler
    results = run_tests(all_tests)

    print("========== INITIAL TESTS ==========")
    print_results(results)

    # Step 5: Find unexpected compiler failures
    failures = get_failures(results)

    # Step 6: Give failures to AI
    if failures:

        print()
        print("========== AI ANALYSIS ==========")
        print(f"Sending {len(failures)} failures to AI...")

        ai_tests = generate_targeted_tests(failures, 5)

        print()
        print("AI Generated Targeted Tests:")

        for i, test in enumerate(ai_tests, 1):
            print(f"{i}. {test}")

        # Step 7: Run AI-generated tests
        ai_test_objects = []

        for test in ai_tests:
            ai_test_objects.append({
                "code": test,
                "expected": "PASS"
            })

        ai_results = run_tests(ai_test_objects)

        print()
        print("========== AI TEST RESULTS ==========")

        for i, result in enumerate(ai_results, 1):

            if result["passed"]:
                print(f"AI Test #{i}   PASS")

            else:
                error = result["result"]

                print(
                    f"AI Test #{i}   FAIL - "
                    f"{error.get('type')}: "
                    f"{error.get('message')}"
                )

    else:
        print()
        print("No failures found. AI generation skipped.")