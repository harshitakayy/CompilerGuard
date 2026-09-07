import random


VARIABLES = ["x", "y", "z", "a", "b"]
NUMBERS = list(range(1, 21))


def generate_factor(defined_variables, depth=0):
    """
    factor → NUMBER | IDENTIFIER | '(' expression ')'
    """

    if depth >= 2:
        choices = ["number"]

        if defined_variables:
            choices.append("variable")

        choice = random.choice(choices)
    else:
        choices = ["number"]

        if defined_variables:
            choices.append("variable")

        choices.append("expression")

        choice = random.choice(choices)

    if choice == "number":
        return str(random.choice(NUMBERS))

    elif choice == "variable":
        return random.choice(defined_variables)

    else:
        return "(" + generate_expression(defined_variables, depth + 1) + ")"


def generate_term(defined_variables, depth=0):
    """
    term → factor (('*' | '/') factor)*
    """

    expression = generate_factor(defined_variables, depth)

    number_of_operations = random.randint(0, 2)

    for _ in range(number_of_operations):
        operator = random.choice(["*", "/"])
        expression += " " + operator + " "
        expression += generate_factor(defined_variables, depth)

    return expression


def generate_expression(defined_variables, depth=0):
    """
    expression → term (('+' | '-') term)*
    """

    expression = generate_term(defined_variables, depth)

    number_of_operations = random.randint(0, 2)

    for _ in range(number_of_operations):
        operator = random.choice(["+", "-"])
        expression += " " + operator + " "
        expression += generate_term(defined_variables, depth)

    return expression


def generate_statement(defined_variables):
    """
    statement → IDENTIFIER '=' expression ';'
    """

    variable = random.choice(VARIABLES)
    expression = generate_expression(defined_variables)

    defined_variables.append(variable)

    return f"{variable} = {expression};"


def generate_program():
    """
    program → statement*
    """

    number_of_statements = random.randint(1, 4)

    statements = []
    defined_variables = []

    for _ in range(number_of_statements):
        statements.append(generate_statement(defined_variables))

    return "\n".join(statements)


def generate_tests(count=20):
    """
    Generate multiple valid programs.
    """

    tests = []

    for _ in range(count):
        tests.append({
            "code": generate_program(),
            "expected": "PASS"
        })

    return tests


if __name__ == "__main__":

    tests = generate_tests(20)

    print("========== GENERATED VALID TESTS ==========")

    for i, test in enumerate(tests, 1):
        print(f"\nTest #{i}")
        print(test["code"])
        print("Expected:", test["expected"])