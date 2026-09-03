import os
import json
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


GRAMMAR = """
program     → statement*
statement   → IDENTIFIER '=' expression ';'
expression  → term (('+' | '-') term)*
term        → factor (('*' | '/') factor)*
factor      → NUMBER | IDENTIFIER | '(' expression ')'
"""


def generate_targeted_tests(failures, count=5):

    failure_text = json.dumps(failures, indent=2)

    prompt = f"""
You are a compiler fuzzing test generator.

We have a tiny programming language called CG-Lang.

Its grammar is:

{GRAMMAR}

The compiler recently produced these failures:

{failure_text}

Generate {count} NEW test programs that specifically explore
similar parser or semantic edge cases.

Rules:
1. Use only CG-Lang syntax.
2. Each test must be a complete program.
3. Do not explain anything.
4. Return ONLY a JSON array of strings.
5. Focus on edge cases related to the observed failures.

Example output:

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

    text = response.output_text

    return json.loads(text)


if __name__ == "__main__":

    failures = [
        {
            "code": "x = + 10;",
            "type": "SYNTAX_ERROR",
            "message": "Expected expression after '+'"
        },
        {
            "code": "x = (10 + 5;",
            "type": "SYNTAX_ERROR",
            "message": "Expected RPAREN"
        }
    ]

    tests = generate_targeted_tests(failures, 5)

    print("========== AI GENERATED TESTS ==========")

    for i, test in enumerate(tests, 1):
        print(f"{i}. {test}")