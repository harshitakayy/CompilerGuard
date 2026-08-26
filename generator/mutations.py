import random


def mutate_test(code):
    """
    Take a valid program and create an invalid version.
    """

    mutations = []

    # Remove semicolon
    if ";" in code:
        mutations.append(code.replace(";", "", 1))

    # Remove assignment operator
    if "=" in code:
        mutations.append(code.replace("=", "", 1))

    # Add operator after '='
    if "=" in code:
        mutated = code.replace("=", "= +", 1)
        mutations.append(mutated)

    # Remove expression after operator
    if "+" in code:
        mutated = code.replace("+", "+;", 1)
        mutations.append(mutated)

    elif "-" in code:
        mutated = code.replace("-", "-;", 1)
        mutations.append(mutated)

    # Remove closing parenthesis
    if ")" in code:
        mutations.append(code.replace(")", "", 1))

    if not mutations:
        return code

    return random.choice(mutations)


def generate_invalid_tests(valid_tests, count=10):
    """
    Generate invalid tests by mutating valid programs.
    """

    invalid_tests = []

    for _ in range(count):
        test = random.choice(valid_tests)

        if isinstance(test, dict):
            code = test["code"]
        else:
            code = test

        mutated_code = mutate_test(code)

        invalid_tests.append({
            "code": mutated_code,
            "expected": "FAIL"
        })

    return invalid_tests


if __name__ == "__main__":

    valid_tests = [
        {
            "code": "x = 10 + 5;",
            "expected": "PASS"
        }
    ]

    invalid_tests = generate_invalid_tests(valid_tests, 5)

    print("========== GENERATED INVALID TESTS ==========")

    for i, test in enumerate(invalid_tests, 1):
        print(f"\nTest #{i}")
        print(test["code"])
        print("Expected:", test["expected"])