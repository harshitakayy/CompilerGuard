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

        if isinstance(test, dict):
            code = test["code"]
        else:
            code = test

        result = compile_code(code)

        results.append({
            "code": code,
            "result": result
        })

    return results


def get_error_pattern(result):

    compiler_result = result["result"]

    if compiler_result["status"] != "FAIL":
        return None

    error_type = compiler_result.get("type", "UNKNOWN")
    message = compiler_result.get("message", "UNKNOWN")

    return error_type + ": " + message


def get_patterns(results):

    patterns = set()

    for result in results:

        pattern = get_error_pattern(result)

        if pattern:
            patterns.add(pattern)

    return patterns


def get_bugs(results):

    bugs = []

    for result in results:

        if result["result"]["status"] == "PASS":

            bugs.append(result["code"])

    return bugs


def evaluate_random_testing(count):

    base_tests = generate_tests(count)

    invalid_tests = generate_invalid_tests(
        base_tests,
        count
    )

    results = run_tests(invalid_tests)

    patterns = get_patterns(results)
    bugs = get_bugs(results)

    return {
        "tests": invalid_tests,
        "results": results,
        "patterns": patterns,
        "bugs": bugs
    }


def evaluate_ai_testing(total_tests, rounds):

    base_tests = generate_tests(total_tests)

    invalid_tests = generate_invalid_tests(
        base_tests,
        total_tests
    )

    base_results = run_tests(invalid_tests)

    failures = []

    for result in base_results:

        compiler_result = result["result"]

        if compiler_result["status"] == "FAIL":

            failures.append({
                "code": result["code"],
                "type": compiler_result.get("type"),
                "message": compiler_result.get("message")
            })

    all_tests = []
    all_results = []

    previous_tests = []

    tests_remaining = total_tests

    for round_no in range(1, rounds + 1):

        if not failures:
            break

        if tests_remaining <= 0:
            break

        current_count = min(
            5,
            tests_remaining
        )

        ai_tests = generate_targeted_tests(
            failures,
            current_count,
            previous_tests
        )

        if not ai_tests:
            break

        previous_tests.extend(ai_tests)

        ai_results = run_tests(ai_tests)

        all_tests.extend(ai_tests)
        all_results.extend(ai_results)

        tests_remaining -= len(ai_tests)

        failures = []

        for result in ai_results:

            compiler_result = result["result"]

            if compiler_result["status"] == "FAIL":

                failures.append({
                    "code": result["code"],
                    "type": compiler_result.get("type"),
                    "message": compiler_result.get("message")
                })

    bugs = get_bugs(all_results)

    return {
        "tests": all_tests,
        "results": all_results,
        "patterns": get_patterns(all_results),
        "bugs": bugs
    }


def print_results(name, data):

    print()
    print("========== " + name + " ==========")

    print(
        f"Tests generated          : "
        f"{len(data['tests'])}"
    )

    print(
        f"Unique error patterns    : "
        f"{len(data['patterns'])}"
    )

    print(
        f"Potential compiler bugs  : "
        f"{len(data['bugs'])}"
    )

    if data["bugs"]:

        print()
        print("---------- POTENTIAL COMPILER BUGS ----------")

        for i, bug in enumerate(data["bugs"], 1):

            print()
            print(f"Bug #{i}")
            print(f"Code: {bug}")


def compare_results(random_data, ai_data):

    random_patterns = random_data["patterns"]
    ai_patterns = ai_data["patterns"]

    new_ai_patterns = ai_patterns - random_patterns

    random_tests = len(random_data["tests"])
    ai_tests = len(ai_data["tests"])

    random_efficiency = 0
    ai_efficiency = 0

    if random_tests > 0:
        random_efficiency = (
            len(random_patterns) / random_tests
        )

    if ai_tests > 0:
        ai_efficiency = (
            len(ai_patterns) / ai_tests
        )

    print()
    print("========================================")
    print("          TESTING COMPARISON")
    print("========================================")

    print()
    print("Metric                    Random      AI-Guided")

    print(
        f"Tests generated           "
        f"{random_tests:<12}"
        f"{ai_tests}"
    )

    print(
        f"Unique error patterns    "
        f"{len(random_patterns):<12}"
        f"{len(ai_patterns)}"
    )

    print(
        f"Potential compiler bugs   "
        f"{len(random_data['bugs']):<12}"
        f"{len(ai_data['bugs'])}"
    )

    print(
        f"Patterns per test        "
        f"{random_efficiency:<12.3f}"
        f"{ai_efficiency:.3f}"
    )

    print(
        f"Patterns AI found beyond "
        f"random testing           "
        f"{len(new_ai_patterns)}"
    )

    print()
    print("---------- AI-ONLY ERROR PATTERNS ----------")

    if not new_ai_patterns:

        print("No additional patterns found.")

    else:

        for pattern in sorted(new_ai_patterns):

            print(pattern)

    print()
    print("========================================")


if __name__ == "__main__":

    print()
    print("========================================")
    print("       COMPILERGUARD EVALUATION")
    print("========================================")

    test_count = 45
    ai_rounds = 9

    print()
    print("Test budget for each approach : 45")

    print()
    print("Running random/mutation testing...")

    random_data = evaluate_random_testing(
        test_count
    )

    print_results(
        "RANDOM / MUTATION TESTING",
        random_data
    )

    print()
    print("Running AI-guided testing...")

    ai_data = evaluate_ai_testing(
        test_count,
        ai_rounds
    )

    print_results(
        "AI-GUIDED TESTING",
        ai_data
    )

    compare_results(
        random_data,
        ai_data
    )