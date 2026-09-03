import os
import json
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


GRAMMAR = """
program     -> statement*
statement   -> IDENTIFIER '=' expression ';'
expression  -> term (('+' | '-') term)*
term        -> factor (('*' | '/') factor)*
factor      -> NUMBER | IDENTIFIER | '(' expression ')'
"""


def analyze_error_patterns(failures):

    patterns = {}

    for failure in failures:

        error_type = failure.get("type", "UNKNOWN")
        message = failure.get("message", "UNKNOWN")

        key = error_type + ": " + message

        if key not in patterns:
            patterns[key] = 0

        patterns[key] += 1

    return patterns


def remove_duplicates(tests):

    unique_tests = []

    for test in tests:

        test = test.strip()

        if test and test not in unique_tests:
            unique_tests.append(test)

    return unique_tests


def generate_targeted_tests(failures, count=5, previous_tests=None):

    if previous_tests is None:
        previous_tests = []

    patterns = analyze_error_patterns(failures)

    pattern_text = json.dumps(patterns, indent=2)
    failure_text = json.dumps(failures, indent=2)
    previous_text = json.dumps(previous_tests, indent=2)

    prompt = f"""
You are an intelligent compiler fuzzing test generator.

We have a tiny programming language called CG-Lang.

Its grammar is:

{GRAMMAR}

The compiler recently produced these errors:

{failure_text}

The frequency of each error pattern is:

{pattern_text}

Previously generated AI tests are:

{previous_text}

Generate {count} NEW test programs.

The goal is NOT simply to reproduce the same compiler errors.
The goal is to explore NEW compiler behavior related to the
observed failures.

Rules:

1. Use only CG-Lang syntax.
2. Each test must be a complete program.
3. Tests should be intentionally malformed.
4. Focus on the observed error patterns.
5. Explore different structures that can trigger similar errors.
6. Do NOT copy any previous test.
7. Do NOT make only a tiny change to a previous test.
8. Avoid producing the same compiler error pattern for every test.
9. Try different combinations of:
   - missing operands
   - extra operators
   - missing semicolons
   - extra semicolons
   - unmatched parentheses
   - incorrect assignment syntax
   - malformed expressions
   - malformed statements
   - multiple statements
10. Explore both simple and nested expressions.
11. If semantic errors are present, explore semantic edge cases too.
12. Prefer structural diversity over repetition.
13. Do not explain anything.
14. Return ONLY a JSON array of strings.
15. Return exactly {count} tests.

Previously generated tests MUST NOT be repeated:

{previous_text}

Example:

[
    "x = ((10 + 5);",
    "y = + (4 * 2);",
    "z = (10 +);"
]
"""

    response = client.responses.create(
        model="gpt-5.4-mini",
        input=prompt
    )

    text = response.output_text.strip()

    if text.startswith("```"):
        text = text.replace("```json", "")
        text = text.replace("```", "")
        text = text.strip()

    tests = json.loads(text)

    if not isinstance(tests, list):
        raise ValueError("AI did not return a JSON array")

    tests = remove_duplicates(tests)

    old_tests = set(previous_tests)

    tests = [
        test for test in tests
        if test not in old_tests
    ]

    return tests[:count]


if __name__ == "__main__":

    failures = [
        {
            "code": "x = + 10;",
            "type": "SYNTAX_ERROR",
            "message": "Expected expression but got PLUS"
        },
        {
            "code": "x = (10 + 5;",
            "type": "SYNTAX_ERROR",
            "message": "Expected RPAREN but got SEMICOLON"
        }
    ]

    tests = generate_targeted_tests(
        failures,
        5
    )

    print("========== AI GENERATED TESTS ==========")

    for i, test in enumerate(tests, 1):
        print(f"{i}. {test}")