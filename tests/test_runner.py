import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


from compiler.compiler import compile_code
from generator.generator import generate_tests
from generator.mutations import generate_invalid_tests


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

    # Generate valid tests
    valid_tests = generate_tests(10)

    # Generate invalid tests by mutating valid tests
    invalid_tests = generate_invalid_tests(valid_tests, 10)

    # Combine both
    all_tests = valid_tests + invalid_tests

    print("========== COMPILERGUARD ==========")
    print()

    results = run_tests(all_tests)

    print_results(results)