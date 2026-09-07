import random


def mutate_test(code):
    """
    Take a valid program and create an invalid version.
    """

    mutations = []

    # 1. Remove semicolon
    if ";" in code:
        mutations.append(code.replace(";", "", 1))

    # 2. Remove assignment operator
    if "=" in code:
        mutations.append(code.replace("=", "", 1))

    # 3. Add an extra operator after '='
    if "=" in code:
        mutations.append(code.replace("=", "= +", 1))

    # 4. Remove expression after '+'
    if "+" in code:
        mutations.append(code.replace("+", "+;", 1))

    # 5. Remove expression after '-'
    if "-" in code:
        mutations.append(code.replace("-", "-;", 1))

    # 6. Remove closing parenthesis
    if ")" in code:
        mutations.append(code.replace(")", "", 1))

    # 7. Add an extra closing parenthesis
    mutations.append(code.replace(";", ");", 1))

    # 8. Add an extra operator
    if "+" in code:
        mutations.append(code.replace("+", "++", 1))
    elif "-" in code:
        mutations.append(code.replace("-", "--", 1))

    # 9. Remove the first character
    if code:
        mutations.append(code[1:])

    if not mutations:
        return code

    return random.choice(mutations)

def generate_invalid_tests(valid_tests, count=10):
    """
    Generate unique invalid tests by mutating valid programs.
    """

    invalid_tests = []
    seen = set()

    # Try several times to find unique mutations
    max_attempts = count * 10
    attempts = 0

    while len(invalid_tests) < count and attempts < max_attempts:
        attempts += 1

        test = random.choice(valid_tests)

        if isinstance(test, dict):
            code = test["code"]
        else:
            code = test

        mutated_code = mutate_test(code)

        # Skip duplicates
        if mutated_code in seen:
            continue

        # Skip unchanged valid programs
        if mutated_code == code:
            continue

        seen.add(mutated_code)

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